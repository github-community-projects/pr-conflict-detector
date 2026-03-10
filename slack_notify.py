"""Slack webhook notifications for PR conflict detection results."""

import json
import logging

import requests
from conflict_detector import ConflictCluster, cluster_conflicts

logger = logging.getLogger(__name__)


def send_slack_notification(
    webhook_url: str,
    conflicts_by_repo: dict,  # {repo_full_name: list[ConflictResult]}
    channel: str = "",
    dry_run: bool = False,
) -> bool:
    """Send Slack notifications about detected PR conflicts.

    Sends one message per conflict/cluster with @mentions for authors.

    Args:
        webhook_url: Slack incoming webhook URL
        conflicts_by_repo: Dict mapping repo names to their conflict results
        channel: Optional channel override
        dry_run: If True, log the messages but don't send

    Returns:
        True if all notifications sent successfully, False otherwise
    """
    if not webhook_url:
        logger.info("No Slack webhook URL configured, skipping notification")
        return False

    if not conflicts_by_repo or all(len(c) == 0 for c in conflicts_by_repo.values()):
        logger.info("No conflicts to notify about")
        return True

    all_success = True

    for repo_name, conflicts in conflicts_by_repo.items():
        if not conflicts:
            continue

        clusters = cluster_conflicts(conflicts)

        for cluster in clusters:
            message = build_cluster_message(repo_name, cluster)

            if dry_run:
                logger.info(
                    "DRY RUN: Would send Slack message: %s",
                    json.dumps(message, indent=2),
                )
            else:
                success = post_to_slack(webhook_url, message, channel)
                if not success:
                    all_success = False

    return all_success


def build_cluster_message(repo_name: str, cluster: ConflictCluster) -> dict:
    """Build a Slack message for a single conflict cluster.

    Args:
        repo_name: Repository full name.
        cluster: ConflictCluster containing one or more conflicts.

    Returns:
        Slack webhook payload dict.
    """
    # Collect unique authors for @mentions
    authors = sorted({pr.author for pr in cluster.prs if pr.author})
    mentions = " ".join(f"<@{author}>" for author in authors)

    if len(cluster.prs) == 2:
        # Simple pair
        conflict = cluster.conflicts[0]
        file_details = _format_file_details(conflict.conflicting_files)

        text = (
            f"{mentions} Your PRs may conflict:\n\n"
            f"*{repo_name}*\n"
            f"<{conflict.pr_a.url}|#{conflict.pr_a.number}> ({conflict.pr_a.title}) "
            f"↔ <{conflict.pr_b.url}|#{conflict.pr_b.number}> ({conflict.pr_b.title})\n\n"
            f"{file_details}"
        )
    else:
        # Multi-PR cluster
        pr_list = "\n".join(
            f"  • <{pr.url}|#{pr.number}> {pr.title}" for pr in cluster.prs
        )
        files_str = ", ".join(f"`{f}`" for f in cluster.shared_files)

        text = (
            f"{mentions} Your PRs may conflict:\n\n"
            f"*{repo_name} — Cluster: {len(cluster.prs)} PRs, "
            f"{len(cluster.conflicts)} conflict pair(s)*\n\n"
            f"PRs:\n{pr_list}\n\n"
            f"Shared files: {files_str}"
        )

    return {"text": text}


def _format_file_details(file_overlaps: list) -> str:
    """Format file overlap details with line ranges.

    Args:
        file_overlaps: List of FileOverlap objects.

    Returns:
        Formatted string with file names and line ranges.
    """
    lines = []
    for fo in file_overlaps:
        ranges = ", ".join(f"L{start}-L{end}" for start, end in fo.overlapping_ranges)
        lines.append(f"  • `{fo.filename}` ({ranges})")
    return "Files:\n" + "\n".join(lines)


def post_to_slack(webhook_url: str, message: dict, channel: str = "") -> bool:
    """Post a message to Slack via webhook.

    Returns True if successful, False otherwise.
    """
    if channel:
        message["channel"] = channel

    try:
        response = requests.post(
            webhook_url,
            json=message,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Failed to send Slack notification: %s", e)
        return False
