"""Test cases for the slack_notify module."""

import unittest
from collections import namedtuple
from unittest.mock import MagicMock, patch

import requests
import slack_notify
from conflict_detector import ConflictCluster

# Lightweight stand-ins for conflict_detector types used by slack_notify
FileOverlap = namedtuple(
    "FileOverlap", ["filename", "pr_a_lines", "pr_b_lines", "overlapping_ranges"]
)
PRInfo = namedtuple("PRInfo", ["number", "url", "title", "author"])
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
    pr_a_title="Fix auth",
    pr_a_author="alice",
    pr_b_number=2,
    pr_b_url="https://github.com/org/repo/pull/2",
    pr_b_title="Add tests",
    pr_b_author="bob",
    filenames=None,
):
    """Helper to build a ConflictResult with sensible defaults."""
    files = [
        FileOverlap(
            filename=f,
            pr_a_lines=[(10, 20)],
            pr_b_lines=[(15, 25)],
            overlapping_ranges=[(15, 20)],
        )
        for f in (filenames or ["README.md"])
    ]
    return ConflictResult(
        pr_a=PRInfo(
            number=pr_a_number, url=pr_a_url, title=pr_a_title, author=pr_a_author
        ),
        pr_b=PRInfo(
            number=pr_b_number, url=pr_b_url, title=pr_b_title, author=pr_b_author
        ),
        conflicting_files=files,
    )


class TestSendSlackNotification(unittest.TestCase):
    """Tests for the send_slack_notification entry-point."""

    @patch("slack_notify.post_to_slack", return_value=True)
    def test_send_slack_notification_success(self, mock_post):
        """Happy path: webhook URL present, messages are sent (one per conflict)."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts
        )
        self.assertTrue(result)
        # Should send one message per conflict (1 conflict = 1 call)
        self.assertEqual(mock_post.call_count, 1)

    def test_send_slack_notification_no_webhook(self):
        """Missing webhook URL should return False without attempting to send."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification("", conflicts)
        self.assertFalse(result)

    def test_send_slack_notification_no_conflicts(self):
        """Empty conflicts should return True without sending."""
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", {}
        )
        self.assertTrue(result)

    def test_send_slack_notification_empty_conflict_lists(self):
        """Repos with empty conflict lists should be skipped."""
        conflicts = {"org/repo": []}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts
        )
        self.assertTrue(result)

    @patch("slack_notify.post_to_slack")
    def test_send_slack_notification_dry_run(self, mock_post):
        """Dry-run mode should return True but never call post_to_slack."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts, dry_run=True
        )
        self.assertTrue(result)
        mock_post.assert_not_called()

    @patch("slack_notify.post_to_slack", return_value=False)
    def test_send_slack_notification_failure(self, _mock_post):
        """If posting fails, should return False."""
        conflicts = {"org/repo": [_make_conflict()]}
        result = slack_notify.send_slack_notification(
            "https://hooks.slack.com/test", conflicts
        )
        self.assertFalse(result)


class TestBuildClusterMessage(unittest.TestCase):
    """Tests for the build_cluster_message function."""

    def test_build_cluster_message_simple_pair(self):
        """Message for a 2-PR cluster should show both PRs with file details."""
        conflict = _make_conflict(filenames=["src/app.py"])
        cluster = ConflictCluster(
            prs=[conflict.pr_a, conflict.pr_b],
            shared_files=["src/app.py"],
            conflicts=[conflict],
        )
        message = slack_notify.build_cluster_message("org/repo", cluster)

        self.assertIn("text", message)
        text = message["text"]
        self.assertIn("<@alice>", text)
        self.assertIn("<@bob>", text)
        self.assertIn("#1", text)
        self.assertIn("#2", text)
        self.assertIn("src/app.py", text)

    def test_build_cluster_message_multi_pr_cluster(self):
        """Message for 3+ PR cluster should show all PRs and shared files."""
        pr1 = PRInfo(1, "http://pr1", "PR 1", "alice")
        pr2 = PRInfo(2, "http://pr2", "PR 2", "bob")
        pr3 = PRInfo(3, "http://pr3", "PR 3", "charlie")

        cluster = ConflictCluster(
            prs=[pr1, pr2, pr3],
            shared_files=["main.py", "test.py"],
            conflicts=[],  # Not used in multi-PR rendering
        )
        message = slack_notify.build_cluster_message("org/repo", cluster)

        self.assertIn("text", message)
        text = message["text"]
        self.assertIn("<@alice>", text)
        self.assertIn("<@bob>", text)
        self.assertIn("<@charlie>", text)
        self.assertIn("3 PRs", text)
        self.assertIn("main.py", text)
        self.assertIn("test.py", text)


class TestPostToSlack(unittest.TestCase):
    """Tests for the low-level post_to_slack function."""

    @patch("requests.post")
    def test_post_to_slack_success(self, mock_requests_post):
        """Successful POST to webhook URL should return True."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        result = slack_notify.post_to_slack(
            "https://hooks.slack.com/test", {"text": "hello"}
        )
        self.assertTrue(result)
        mock_requests_post.assert_called_once()

    @patch("requests.post")
    def test_post_to_slack_failure(self, mock_requests_post):
        """Failed POST should return False."""
        mock_requests_post.side_effect = requests.RequestException("Network error")
        result = slack_notify.post_to_slack(
            "https://hooks.slack.com/test", {"text": "hello"}
        )
        self.assertFalse(result)

    @patch("requests.post")
    def test_post_to_slack_with_channel_override(self, mock_requests_post):
        """Channel override should be added to the message payload."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_requests_post.return_value = mock_response

        slack_notify.post_to_slack(
            "https://hooks.slack.com/test", {"text": "hello"}, channel="#general"
        )

        # Check the message dict passed to requests.post includes the channel
        call_args = mock_requests_post.call_args
        self.assertIn("json", call_args.kwargs)
        self.assertEqual(call_args.kwargs["json"]["channel"], "#general")


if __name__ == "__main__":
    unittest.main()
