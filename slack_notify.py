"""Slack webhook notifications for PR conflict detection results."""

import json
import logging

import requests

logger = logging.getLogger(__name__)


def send_slack_notification(
    webhook_url: str,
    conflicts_by_repo: dict,  # {repo_full_name: list[ConflictResult]}
    channel: str = "",
    dry_run: bool = False,
) -> bool:
    """Send a Slack notification about detected PR conflicts.

    Args:
        webhook_url: Slack incoming webhook URL
        conflicts_by_repo: Dict mapping repo names to their conflict results
        channel: Optional channel override
        dry_run: If True, log the message but don't send

    Returns:
        True if notification sent successfully, False otherwise
    """
    if not webhook_url:
        logger.info("No Slack webhook URL configured, skipping notification")
        return False

    message = build_slack_message(conflicts_by_repo)

    if dry_run:
        logger.info(
            "DRY RUN: Would send Slack notification: %s",
            json.dumps(message, indent=2),
        )
        return True

    return post_to_slack(webhook_url, message, channel)


def build_slack_message(conflicts_by_repo: dict) -> dict:
    """Build a Slack Block Kit message from conflict results.

    Returns a dict suitable for Slack's webhook API.
    """
    blocks = []

    # Header
    total_conflicts = sum(len(c) for c in conflicts_by_repo.values())
    if total_conflicts == 0:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *PR Conflict Report*\nNo potential merge conflicts detected!",
                },
            }
        )
        return {"blocks": blocks}

    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚠️ PR Conflict Report - {total_conflicts} potential conflict(s) found",
            },
        }
    )

    # Per-repo sections
    for repo_name, conflicts in conflicts_by_repo.items():
        if not conflicts:
            continue

        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{repo_name}* - {len(conflicts)} conflict(s)",
                },
            }
        )

        for conflict in conflicts:
            files_str = ", ".join(f"`{f.filename}`" for f in conflict.conflicting_files)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"• <{conflict.pr_a_url}|#{conflict.pr_a_number}> ({conflict.pr_a_author}) "
                            f"↔ <{conflict.pr_b_url}|#{conflict.pr_b_number}> ({conflict.pr_b_author})\n"
                            f"  Files: {files_str}"
                        ),
                    },
                }
            )

    return {"blocks": blocks}


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
