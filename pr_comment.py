"""PR comment notifications for conflict detection."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from conflict_detector import ConflictResult, FileOverlap, PRInfo

logger = logging.getLogger(__name__)

# Bot signature to identify our comments
COMMENT_SIGNATURE = "<!-- pr-conflict-detector-bot -->"

MAX_RESOLVED_DISPLAY = 10


@dataclass
class ConflictEntry:
    """A single conflict entry for a PR, pairing the other PR with overlapping files."""

    other_pr: PRInfo
    files: list[FileOverlap]


@dataclass
class ResolvedConflictEntry:
    """A resolved conflict for display in the comment's resolved section."""

    pr_number: int
    pr_title: str
    pr_url: str
    resolved_at: str


def post_pr_comments(
    all_conflicts_by_repo: dict[str, list[ConflictResult]],
    github_connection: Any,
    new_conflict_keys: set[tuple[int, int]] | None = None,
    resolved_entries: list[dict] | None = None,
    dry_run: bool = False,
) -> bool:
    """Post consolidated comments on PRs about detected conflicts.

    Groups all conflicts for a given PR into a single comment. If an existing
    bot comment is found on the PR, it is updated in place instead of creating
    a new one. Includes a resolved conflicts section for previously detected
    conflicts that have been resolved.

    Args:
        all_conflicts_by_repo: Dict mapping repo names to ALL active conflict results.
        github_connection: Authenticated GitHub connection.
        new_conflict_keys: Set of (pr_a, pr_b) tuples for newly detected conflicts
            (used to render 🆕 badges).
        resolved_entries: List of resolved conflict dicts from the state file
            (used to render the resolved section).
        dry_run: If True, log what would be posted but don't actually post.

    Returns:
        True if all comments posted successfully, False otherwise.
    """
    # Determine all repos that need processing (active + resolved)
    all_repo_names = set(all_conflicts_by_repo.keys())
    if resolved_entries:
        all_repo_names.update(
            e.get("repo", "") for e in resolved_entries if e.get("repo")
        )
    all_repo_names.discard("")

    if not all_repo_names:
        logger.info("No conflicts to comment on")
        return True

    all_success = True
    total_comments = 0
    total_updates = 0

    for repo_name in all_repo_names:
        conflicts = all_conflicts_by_repo.get(repo_name, [])
        owner, repo = repo_name.split("/")
        repo_obj = github_connection.repository(owner, repo)

        # Group active conflicts by PR
        pr_conflicts = _group_conflicts_by_pr(conflicts) if conflicts else {}

        # Group resolved entries by PR for this repo
        resolved_by_pr = _group_resolved_by_pr(resolved_entries or [], repo_name)

        # All PRs that need a comment (active or resolved)
        all_pr_numbers = set(pr_conflicts.keys()) | set(resolved_by_pr.keys())

        for pr_number in all_pr_numbers:
            active = pr_conflicts.get(pr_number, [])
            resolved = resolved_by_pr.get(pr_number, [])

            # Compute which other PRs are newly detected
            new_other_prs: set[int] = set()
            if new_conflict_keys:
                for entry in active:
                    other = entry.other_pr.number
                    if (pr_number, other) in new_conflict_keys or (
                        other,
                        pr_number,
                    ) in new_conflict_keys:
                        new_other_prs.add(other)

            comment_body = _build_consolidated_comment(active, new_other_prs, resolved)
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


def _build_consolidated_comment(
    conflict_entries: list[ConflictEntry],
    new_pr_numbers: set[int] | None = None,
    resolved_entries: list[ResolvedConflictEntry] | None = None,
) -> str:
    """Build a single consolidated comment listing all conflicts for a PR.

    Args:
        conflict_entries: List of active ConflictEntry objects.
        new_pr_numbers: PR numbers that are newly detected (for 🆕 badge).
        resolved_entries: List of resolved conflict entries for the details section.

    Returns:
        Formatted comment body with active conflicts table and resolved section.
    """
    resolved_section = _build_resolved_section(resolved_entries or [])
    footer = (
        "\nThis is an automated notification from "
        "[pr-conflict-detector](https://github.com/github-community-projects/pr-conflict-detector)."
    )
    banner = (
        "\n> 🔄 **This comment updates automatically** "
        "as conflicts are detected and resolved.\n"
    )

    if not conflict_entries:
        return (
            f"{COMMENT_SIGNATURE}\n"
            f"## ✅ All Merge Conflicts Resolved\n"
            f"{banner}\n"
            f"All previously detected conflicts for this PR have been resolved. 🎉\n"
            f"{resolved_section}\n"
            f"{footer}"
        )

    count = len(conflict_entries)

    table_rows = []
    authors: list[str] = []
    for entry in conflict_entries:
        if entry.other_pr.author not in authors:
            authors.append(entry.other_pr.author)

        badge = (
            "🆕" if new_pr_numbers and entry.other_pr.number in new_pr_numbers else ""
        )
        file_details = ", ".join(
            f"`{fo.filename}` ({_format_ranges(fo.overlapping_ranges)})"
            for fo in entry.files
        )
        table_rows.append(
            f"| {badge} | [#{entry.other_pr.number}]({entry.other_pr.url})"
            f" ({entry.other_pr.title}) | {file_details} |"
        )

    table = "\n".join(table_rows)
    author_mentions = ", ".join(f"@{a}" for a in authors)

    return (
        f"{COMMENT_SIGNATURE}\n"
        f"## ⚠️ Potential Merge Conflicts Detected\n"
        f"{banner}\n"
        f"This PR may conflict with **{count}** other PR(s):\n\n"
        f"| | Conflicting PR | Conflicting Files (Lines) |\n"
        f"|---|---|---|\n"
        f"{table}\n\n"
        f"**What to do:** Review the overlapping changes and coordinate "
        f"with {author_mentions} to resolve conflicts.\n"
        f"{resolved_section}\n"
        f"{footer}"
    )


def _format_ranges(ranges: list[tuple[int, int]]) -> str:
    """Format line ranges for display.

    Args:
        ranges: List of (start, end) line number tuples

    Returns:
        Formatted string like "L10-L25, L42-L55"
    """
    return ", ".join(f"L{start}-L{end}" for start, end in ranges)


def _group_resolved_by_pr(
    resolved_entries: list[dict], repo_name: str
) -> dict[int, list[ResolvedConflictEntry]]:
    """Group resolved conflict entries by PR number for a specific repo.

    Each resolved conflict pair contributes an entry to both PRs involved.

    Args:
        resolved_entries: List of resolved conflict dicts from state.
        repo_name: Repository full name to filter by.

    Returns:
        Dict mapping PR number to a list of ResolvedConflictEntry objects.
    """
    grouped: dict[int, list[ResolvedConflictEntry]] = defaultdict(list)
    for entry in resolved_entries:
        if entry.get("repo") != repo_name:
            continue

        # PR A sees PR B as resolved
        grouped[entry["pr_a"]].append(
            ResolvedConflictEntry(
                pr_number=entry["pr_b"],
                pr_title=entry.get("pr_b_title", "") or f"#{entry['pr_b']}",
                pr_url=entry.get("pr_b_url", ""),
                resolved_at=entry.get("resolved_at", ""),
            )
        )
        # PR B sees PR A as resolved
        grouped[entry["pr_b"]].append(
            ResolvedConflictEntry(
                pr_number=entry["pr_a"],
                pr_title=entry.get("pr_a_title", "") or f"#{entry['pr_a']}",
                pr_url=entry.get("pr_a_url", ""),
                resolved_at=entry.get("resolved_at", ""),
            )
        )
    return dict(grouped)


def _build_resolved_section(
    resolved_entries: list[ResolvedConflictEntry],
) -> str:
    """Build the collapsed resolved conflicts section.

    Args:
        resolved_entries: List of resolved conflict entries.

    Returns:
        Markdown string with collapsed details section, or empty string.
    """
    if not resolved_entries:
        return ""

    # Sort by resolved date, most recent first
    sorted_entries = sorted(resolved_entries, key=lambda e: e.resolved_at, reverse=True)
    # Cap display count
    sorted_entries = sorted_entries[:MAX_RESOLVED_DISPLAY]

    count = len(sorted_entries)
    rows = []
    for entry in sorted_entries:
        date_str = _format_resolved_date(entry.resolved_at)
        if entry.pr_url:
            pr_ref = f"[#{entry.pr_number}]({entry.pr_url}) ({entry.pr_title})"
        else:
            pr_ref = f"#{entry.pr_number} ({entry.pr_title})"
        rows.append(f"| ~{pr_ref}~ | {date_str} |")

    table = "\n".join(rows)
    suffix = "s" if count != 1 else ""

    return (
        f"\n<details>\n"
        f"<summary>✅ {count} previously resolved conflict{suffix}</summary>\n\n"
        f"| Conflicting PR | Resolved |\n"
        f"|---|---|\n"
        f"{table}\n\n"
        f"</details>"
    )


def _format_resolved_date(iso_timestamp: str) -> str:
    """Format an ISO 8601 timestamp as a readable date.

    Args:
        iso_timestamp: ISO 8601 formatted timestamp string.

    Returns:
        Formatted date string like 'Mar 19, 2026'.
    """
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return "Unknown"


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
