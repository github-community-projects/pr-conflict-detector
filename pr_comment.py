"""PR comment notifications for conflict detection."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from conflict_detector import ConflictResult, FileOverlap, PRInfo

logger = logging.getLogger(__name__)

# Bot signature to identify our comments
COMMENT_SIGNATURE = "<!-- pr-conflict-detector-bot -->"


@dataclass
class ConflictEntry:
    """A single conflict entry for a PR, pairing the other PR with overlapping files."""

    other_pr: PRInfo
    files: list[FileOverlap]


def post_pr_comments(
    conflicts_by_repo: dict[str, list[ConflictResult]],
    github_connection: Any,
    dry_run: bool = False,
) -> bool:
    """Post consolidated comments on PRs about detected conflicts.

    Groups all conflicts for a given PR into a single comment. If an existing
    bot comment is found on the PR, it is updated in place instead of creating
    a new one.

    Args:
        conflicts_by_repo: Dict mapping repo names to conflict results
        github_connection: Authenticated GitHub connection
        dry_run: If True, log what would be posted but don't actually post

    Returns:
        True if all comments posted successfully, False otherwise
    """
    if not conflicts_by_repo or all(len(c) == 0 for c in conflicts_by_repo.values()):
        logger.info("No conflicts to comment on")
        return True

    all_success = True
    total_comments = 0
    total_updates = 0

    for repo_name, conflicts in conflicts_by_repo.items():
        if not conflicts:
            continue

        owner, repo = repo_name.split("/")
        repo_obj = github_connection.repository(owner, repo)

        # Group conflicts by PR number so each PR gets one consolidated comment
        pr_conflicts = _group_conflicts_by_pr(conflicts)

        for pr_number, conflict_entries in pr_conflicts.items():
            comment_body = _build_consolidated_comment(conflict_entries)

            existing_comments = _find_existing_comments(repo_obj, pr_number)

            if dry_run:
                action = "update" if existing_comments else "create"
                logger.info(
                    "DRY RUN: Would %s comment on %s#%s:\n%s",
                    action,
                    repo_name,
                    pr_number,
                    comment_body,
                )
                if existing_comments:
                    total_updates += 1
                    if len(existing_comments) > 1:
                        logger.info(
                            "DRY RUN: Would delete %s stale bot comment(s) on %s#%s",
                            len(existing_comments) - 1,
                            repo_name,
                            pr_number,
                        )
                else:
                    total_comments += 1
                continue

            if existing_comments:
                success = _update_comment(existing_comments[0], comment_body)
                if success:
                    total_updates += 1
                else:
                    all_success = False
                # Clean up any stale extra bot comments (e.g. old per-conflict format)
                for stale_comment in existing_comments[1:]:
                    _delete_comment(stale_comment)
            else:
                success = _post_comment(repo_obj, pr_number, comment_body)
                if success:
                    total_comments += 1
                else:
                    all_success = False

    if total_comments > 0 or total_updates > 0:
        logger.info(
            "Posted %s new comment(s), updated %s existing comment(s)",
            total_comments,
            total_updates,
        )

    return all_success


def _group_conflicts_by_pr(
    conflicts: list[ConflictResult],
) -> dict[int, list[ConflictEntry]]:
    """Group conflicts so each PR number maps to its list of conflicting PRs.

    Each conflict pair contributes an entry to both PRs involved.

    Args:
        conflicts: List of ConflictResult objects.

    Returns:
        Dict mapping PR number to a list of ConflictEntry objects.
    """
    grouped: dict[int, list[ConflictEntry]] = defaultdict(list)
    for conflict in conflicts:
        grouped[conflict.pr_a.number].append(
            ConflictEntry(other_pr=conflict.pr_b, files=conflict.conflicting_files)
        )
        grouped[conflict.pr_b.number].append(
            ConflictEntry(other_pr=conflict.pr_a, files=conflict.conflicting_files)
        )
    return dict(grouped)


def _find_existing_comments(repo: Any, pr_number: int) -> list[Any]:
    """Find all existing bot comments on the PR.

    Returns all comments matching the bot signature, ordered by creation time.
    The first element (if any) is the one to update; the rest are stale and
    should be deleted during migration from per-conflict to consolidated format.

    Args:
        repo: GitHub repository object
        pr_number: PR number to check

    Returns:
        List of comment objects with the bot signature (may be empty).
    """
    try:
        pr = repo.pull_request(pr_number)
        return [c for c in pr.issue_comments() if COMMENT_SIGNATURE in c.body]
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Failed to check existing comments on PR #%s: %s", pr_number, e)
        return []


def _build_consolidated_comment(conflict_entries: list[ConflictEntry]) -> str:
    """Build a single consolidated comment listing all conflicts for a PR.

    Args:
        conflict_entries: List of ConflictEntry objects.

    Returns:
        Formatted comment body with a table of all conflicting PRs.
    """
    count = len(conflict_entries)

    table_rows = []
    authors: list[str] = []
    for entry in conflict_entries:
        if entry.other_pr.author not in authors:
            authors.append(entry.other_pr.author)

        file_details = ", ".join(
            f"`{fo.filename}` ({_format_ranges(fo.overlapping_ranges)})"
            for fo in entry.files
        )
        table_rows.append(
            f"| [#{entry.other_pr.number}]({entry.other_pr.url}) ({entry.other_pr.title}) | {file_details} |"
        )

    table = "\n".join(table_rows)
    author_mentions = ", ".join(f"@{a}" for a in authors)

    comment = f"""{COMMENT_SIGNATURE}
## ⚠️ Potential Merge Conflicts Detected

This PR may conflict with **{count}** other PR(s):

| Conflicting PR | Conflicting Files (Lines) |
|---|---|
{table}

**What to do:** Review the overlapping changes and coordinate with {author_mentions} to resolve conflicts.

This is an automated notification from [pr-conflict-detector](https://github.com/github-community-projects/pr-conflict-detector)."""

    return comment


def _format_ranges(ranges: list[tuple[int, int]]) -> str:
    """Format line ranges for display.

    Args:
        ranges: List of (start, end) line number tuples

    Returns:
        Formatted string like "L10-L25, L42-L55"
    """
    return ", ".join(f"L{start}-L{end}" for start, end in ranges)


def _update_comment(comment: Any, body: str) -> bool:
    """Update an existing comment with new content.

    Args:
        comment: GitHub comment object to update
        body: New comment body

    Returns:
        True if successful, False otherwise
    """
    try:
        comment.edit(body)
        logger.info("Updated existing comment (id=%s)", comment.id)
        return True
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Failed to update comment (id=%s): %s", comment.id, e)
        return False


def _delete_comment(comment: Any) -> bool:
    """Delete a stale bot comment.

    Used during migration from per-conflict to consolidated comment format
    to clean up extra bot comments that are no longer needed.

    Args:
        comment: GitHub comment object to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        comment.delete()
        logger.info("Deleted stale bot comment (id=%s)", comment.id)
        return True
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Failed to delete stale comment (id=%s): %s", comment.id, e)
        return False


def _post_comment(repo, pr_number: int, body: str) -> bool:
    """Post a comment to a pull request.

    Args:
        repo: GitHub repository object
        pr_number: PR number
        body: Comment body

    Returns:
        True if successful, False otherwise
    """
    try:
        pr = repo.pull_request(pr_number)
        pr.create_comment(body)
        logger.info("Posted comment to PR #%s", pr_number)
        return True
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Failed to post comment to PR #%s: %s", pr_number, e)
        return False
