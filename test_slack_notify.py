"""Test cases for the slack_notify module."""

import unittest
from collections import namedtuple
from unittest.mock import MagicMock, patch

import requests
import slack_notify

# Lightweight stand-ins for conflict_detector types used by slack_notify
FileOverlap = namedtuple("FileOverlap", ["filename"])
PRInfo = namedtuple("PRInfo", ["number", "url", "author"])
ConflictResult = namedtuple(
    "ConflictResult",
    [
        "pr_a",
        "pr_b",
        "conflicting_files",
    ],
)


def _make_conflict(
    pr_a_number=1,
    pr_a_url="https://github.com/org/repo/pull/1",
    pr_a_author="alice",
    pr_b_number=2,
    pr_b_url="https://github.com/org/repo/pull/2",
    pr_b_author="bob",
    filenames=None,
):
    """Helper to build a ConflictResult with sensible defaults."""
    files = [FileOverlap(f) for f in (filenames or ["README.md"])]
    return ConflictResult(
        pr_a=PRInfo(number=pr_a_number, url=pr_a_url, author=pr_a_author),
        pr_b=PRInfo(number=pr_b_number, url=pr_b_url, author=pr_b_author),
        conflicting_files=files,
    )


class TestSendSlackNotification(unittest.TestCase):
    """Tests for the send_slack_notification entry-point."""

    @patch("slack_notify.post_to_slack", return_value=True)
    def test_send_slack_notification_success(self, mock_post):
        """Happy path: webhook URL present, message is built and sent."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts
        )
        self.assertTrue(result)
        mock_post.assert_called_once()
        # Verify the message dict was passed
        _, args, _ = mock_post.mock_calls[0]
        self.assertIn("blocks", args[1])

    def test_send_slack_notification_no_webhook(self):
        """Missing webhook URL should return False without attempting to send."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification("", conflicts)
        self.assertFalse(result)

    @patch("slack_notify.post_to_slack")
    def test_send_slack_notification_dry_run(self, mock_post):
        """Dry-run mode should return True but never call post_to_slack."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts, dry_run=True
        )
        self.assertTrue(result)
        mock_post.assert_not_called()


class TestBuildSlackMessage(unittest.TestCase):
    """Tests for the build_slack_message function."""

    def test_build_slack_message_with_conflicts(self):
        """Message with conflicts should include a header and per-conflict blocks."""
        conflict = _make_conflict(filenames=["src/app.py", "README.md"])
        message = slack_notify.build_slack_message({"org/repo": [conflict]})

        blocks = message["blocks"]
        # Header block
        self.assertEqual(blocks[0]["type"], "header")
        self.assertIn("1 potential conflict(s)", blocks[0]["text"]["text"])

        # Repo section
        repo_block = blocks[2]
        self.assertIn("org/repo", repo_block["text"]["text"])

        # Conflict detail block should mention both files
        detail_block = blocks[3]
        self.assertIn("`src/app.py`", detail_block["text"]["text"])
        self.assertIn("`README.md`", detail_block["text"]["text"])

    def test_build_slack_message_no_conflicts(self):
        """Empty conflict dict should produce a success message."""
        message = slack_notify.build_slack_message({})

        blocks = message["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertIn(
            "No potential merge conflicts detected!", blocks[0]["text"]["text"]
        )

    def test_build_slack_message_skips_empty_conflict_list(self):
        """Test that repos with empty conflict lists are skipped."""
        conflicts_by_repo = {
            "org/empty-repo": [],
            "org/real-repo": [_make_conflict()],
        }
        message = slack_notify.build_slack_message(conflicts_by_repo)
        all_text = " ".join(
            b.get("text", {}).get("text", "") for b in message["blocks"] if "text" in b
        )
        self.assertNotIn("org/empty-repo", all_text)
        self.assertIn("org/real-repo", all_text)

    def test_build_slack_message_multiple_repos(self):
        """Multiple repos each get their own section."""
        conflicts = {
            "org/alpha": [_make_conflict(pr_a_number=10, pr_b_number=11)],
            "org/beta": [
                _make_conflict(pr_a_number=20, pr_b_number=21),
                _make_conflict(
                    pr_a_number=22,
                    pr_b_number=23,
                    filenames=["docs/index.md"],
                ),
            ],
        }
        message = slack_notify.build_slack_message(conflicts)

        blocks = message["blocks"]
        # Header should report total of 3 conflicts
        self.assertIn("3 potential conflict(s)", blocks[0]["text"]["text"])

        # Both repo names should appear somewhere in the blocks
        all_text = " ".join(
            b.get("text", {}).get("text", "") for b in blocks if "text" in b
        )
        self.assertIn("org/alpha", all_text)
        self.assertIn("org/beta", all_text)


class TestPostToSlack(unittest.TestCase):
    """Tests for the post_to_slack function."""

    @patch("slack_notify.requests.post")
    def test_post_to_slack_with_channel(self, mock_post):
        """Channel override should be injected into the payload."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        message = {"blocks": []}
        result = slack_notify.post_to_slack(
            "https://hooks.slack.com/test", message, channel="#alerts"
        )

        self.assertTrue(result)
        # The message dict should now contain the channel key
        self.assertEqual(message["channel"], "#alerts")
        mock_post.assert_called_once()

    @patch("slack_notify.requests.post")
    def test_post_to_slack_failure(self, mock_post):
        """A RequestException should be caught and return False."""
        mock_post.side_effect = requests.exceptions.RequestException("timeout")

        result = slack_notify.post_to_slack(
            "https://hooks.slack.com/test", {"blocks": []}
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
