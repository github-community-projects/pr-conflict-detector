"""PR comment notifications for conflict detection."""

import logging
from typing import Any

from comment_rendering import (
    COMMENT_SIGNATURE,
    MAX_RESOLVED_DISPLAY,
    ConflictEntry,
    ResolvedConflictEntry,
    build_consolidated_comment,
    group_conflicts_by_pr,
    group_resolved_by_pr,
)
from conflict_detector import ConflictResult

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "COMMENT_SIGNATURE",
    "MAX_RESOLVED_DISPLAY",
    "ConflictEntry",
    "ResolvedConflictEntry",
    "post_pr_comments",
]


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
        pr_conflicts = group_conflicts_by_pr(conflicts) if conflicts else {}

        # Group resolved entries by PR for this repo
        resolved_by_pr = group_resolved_by_pr(resolved_entries or [], repo_name)

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

            comment_body = build_consolidated_comment(active, new_other_prs, resolved)
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
