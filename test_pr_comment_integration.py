"""Tests for comment update, delete, and integration with resolved entries."""

# pylint: disable=protected-access

import unittest
from unittest.mock import MagicMock, patch

import pr_comment


class TestUpdateComment(unittest.TestCase):
    """Tests for the _update_comment function."""

    def test_update_comment_success(self):
        """Should successfully update an existing comment."""
        comment = MagicMock()
        comment.id = 42

        result = pr_comment._update_comment(comment, "Updated body")

        self.assertTrue(result)
        comment.edit.assert_called_once_with("Updated body")

    def test_update_comment_failure(self):
        """Should return False on error."""
        comment = MagicMock()
        comment.id = 42
        comment.edit.side_effect = Exception("API error")

        result = pr_comment._update_comment(comment, "Updated body")

        self.assertFalse(result)


class TestDeleteComment(unittest.TestCase):
    """Tests for the _delete_comment function."""

    def test_delete_comment_success(self):
        """Should successfully delete a comment."""
        comment = MagicMock()
        comment.id = 99

        result = pr_comment._delete_comment(comment)

        self.assertTrue(result)
        comment.delete.assert_called_once()

    def test_delete_comment_failure(self):
        """Should return False on error."""
        comment = MagicMock()
        comment.id = 99
        comment.delete.side_effect = Exception("API error")

        result = pr_comment._delete_comment(comment)

        self.assertFalse(result)


class TestPostPRCommentsWithResolved(unittest.TestCase):
    """Tests for post_pr_comments with resolved_entries."""

    @patch("pr_comment._post_comment", return_value=True)
    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_resolved_only_pr_gets_comment(self, _mock_find, mock_post):
        """PRs that only appear in resolved_entries should still get comments."""
        # No active conflicts
        conflicts: dict[str, list] = {}
        resolved_entries = [
            {
                "repo": "org/repo",
                "pr_a": 1,
                "pr_b": 2,
                "pr_a_title": "PR 1",
                "pr_b_title": "PR 2",
                "pr_a_url": "http://pr1",
                "pr_b_url": "http://pr2",
                "resolved_at": "2026-03-15T10:00:00+00:00",
            }
        ]

        gh = MagicMock()
        repo_mock = MagicMock()
        gh.repository.return_value = repo_mock

        result = pr_comment.post_pr_comments(
            conflicts, gh, resolved_entries=resolved_entries
        )

        self.assertTrue(result)
        # Both PR #1 and PR #2 should get comments
        self.assertEqual(mock_post.call_count, 2)
        posted_prs = {call[0][1] for call in mock_post.call_args_list}
        self.assertEqual(posted_prs, {1, 2})
        # Comment should mention all-resolved
        for call in mock_post.call_args_list:
            body = call[0][2]
            self.assertIn("✅ All Merge Conflicts Resolved", body)


if __name__ == "__main__":
    unittest.main()
