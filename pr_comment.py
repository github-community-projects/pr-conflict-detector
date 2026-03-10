"""PR comment notifications for conflict detection."""

import logging
from typing import Any

from conflict_detector import ConflictResult

logger = logging.getLogger(__name__)

# Bot signature to identify our comments
COMMENT_SIGNATURE = "<!-- pr-conflict-detector-bot -->"


def post_pr_comments(
    conflicts_by_repo: dict[str, list[ConflictResult]],
    github_connection: Any,
    dry_run: bool = False,
) -> bool:
    """Post comments on PRs about detected conflicts.

    Only posts comments for conflicts that don't already have a comment.

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
    skipped_duplicates = 0

    for repo_name, conflicts in conflicts_by_repo.items():
        if not conflicts:
            continue

        owner, repo = repo_name.split("/")
        repo_obj = github_connection.repository(owner, repo)

        for conflict in conflicts:
            # Check both PRs in the conflict
            for pr_info in [conflict.pr_a, conflict.pr_b]:
                other_pr = conflict.pr_b if pr_info == conflict.pr_a else conflict.pr_a

                # Check if we've already commented on this PR about this specific conflict
                if _has_existing_comment(repo_obj, pr_info.number, other_pr.number):
                    logger.info(
                        "Skipping duplicate comment on %s#%s (conflict with #%s already commented)",
                        repo_name,
                        pr_info.number,
                        other_pr.number,
                    )
                    skipped_duplicates += 1
                    continue

                # Build comment body
                comment_body = _build_comment(conflict, pr_info, other_pr)

                if dry_run:
                    logger.info(
                        "DRY RUN: Would comment on %s#%s:\n%s",
                        repo_name,
                        pr_info.number,
                        comment_body,
                    )
                    total_comments += 1
                else:
                    success = _post_comment(repo_obj, pr_info.number, comment_body)
                    if success:
                        total_comments += 1
                    else:
                        all_success = False

    if total_comments > 0:
        logger.info(
            "Posted %s PR comment(s), skipped %s duplicate(s)",
            total_comments,
            skipped_duplicates,
        )

    return all_success


def _has_existing_comment(repo, pr_number: int, other_pr_number: int) -> bool:
    """Check if a comment already exists on this PR about the conflict.

    Args:
        repo: GitHub repository object
        pr_number: PR number to check
        other_pr_number: The other PR in the conflict pair

    Returns:
        True if a comment already exists, False otherwise
    """
    try:
        pr = repo.pull_request(pr_number)
        for comment in pr.issue_comments():
            # Check if comment has our signature and mentions the other PR
            if (
                COMMENT_SIGNATURE in comment.body
                and f"#{other_pr_number}" in comment.body
            ):
                return True
        return False
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Failed to check existing comments on PR #%s: %s", pr_number, e)
        # If we can't check, assume no comment exists to avoid blocking
        return False


def _build_comment(conflict: ConflictResult, current_pr, other_pr) -> str:
    """Build a comment body for a PR conflict notification.

    Args:
        conflict: The conflict result
        current_pr: PRInfo for the PR being commented on (unused but kept for consistency)
        other_pr: PRInfo for the other PR in the conflict

    Returns:
        Formatted comment body
    """
    _ = current_pr  # Explicitly mark as unused
    files_list = "\n".join(
        f"- `{fo.filename}` (lines: {_format_ranges(fo.overlapping_ranges)})"
        for fo in conflict.conflicting_files
    )

    comment = f"""{COMMENT_SIGNATURE}
## ⚠️ Potential Merge Conflict Detected

This PR may conflict with [#{other_pr.number}]({other_pr.url}) ({other_pr.title}).

### Conflicting Files
{files_list}

### What to do
- Review the overlapping changes in the files above
- Coordinate with @{other_pr.author} to resolve conflicts
- Consider rebasing or merging to test compatibility

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
