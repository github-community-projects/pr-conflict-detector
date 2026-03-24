"""Tests for PR comment posting, finding, and lifecycle management."""

# pylint: disable=protected-access

import unittest
from unittest.mock import MagicMock, patch

import pr_comment
from test_helpers import _make_comment_conflict


class TestPostPRComments(unittest.TestCase):
    """Tests for the post_pr_comments function."""

    def test_post_pr_comments_no_conflicts(self):
        """Empty conflicts should return True without posting."""
        gh = MagicMock()
        result = pr_comment.post_pr_comments({}, gh)
        self.assertTrue(result)

    @patch("pr_comment._post_comment", return_value=True)
    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_post_pr_comments_success(self, _mock_find, mock_post):
        """Should post one consolidated comment per PR."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        repo_mock = MagicMock()
        gh.repository.return_value = repo_mock

        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # Should post to both PR #1 and PR #2 (one consolidated comment each)
        self.assertEqual(mock_post.call_count, 2)
        mock_post.assert_any_call(repo_mock, 1, unittest.mock.ANY)
        mock_post.assert_any_call(repo_mock, 2, unittest.mock.ANY)

    @patch("pr_comment._update_comment", return_value=True)
    @patch("pr_comment._find_existing_comments")
    def test_post_pr_comments_updates_existing(self, mock_find, mock_update):
        """Should update existing bot comment instead of creating new one."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        existing_comment = MagicMock()
        mock_find.return_value = [existing_comment]

        gh = MagicMock()
        repo_mock = MagicMock()
        gh.repository.return_value = repo_mock

        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # Should update both PR #1 and PR #2 existing comments
        self.assertEqual(mock_update.call_count, 2)

    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_post_pr_comments_dry_run(self, _mock_find):
        """Dry run should not post comments."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        result = pr_comment.post_pr_comments(conflicts, gh, dry_run=True)

        self.assertTrue(result)
        gh.repository.assert_called_once_with("org", "repo")

    @patch("pr_comment._post_comment", return_value=True)
    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_multiple_conflicts_single_comment(self, _mock_find, mock_post):
        """Multiple conflicts for same PR should produce a single comment."""
        conflict1 = _make_comment_conflict(
            pr_a_number=1, pr_b_number=2, filenames=["file_a.py"]
        )
        conflict2 = _make_comment_conflict(
            pr_a_number=1,
            pr_b_number=3,
            pr_b_url="https://github.com/org/repo/pull/3",
            pr_b_title="Add logging",
            pr_b_author="charlie",
            filenames=["file_b.py"],
        )
        conflicts = {"org/repo": [conflict1, conflict2]}

        gh = MagicMock()
        repo_mock = MagicMock()
        gh.repository.return_value = repo_mock

        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # PR #1 has 2 conflicts -> 1 comment, PR #2 has 1 -> 1 comment, PR #3 has 1 -> 1 comment
        self.assertEqual(mock_post.call_count, 3)

        # Find the call for PR #1 and verify the body includes both conflicts
        pr1_calls = [c for c in mock_post.call_args_list if c[0][1] == 1]
        self.assertEqual(len(pr1_calls), 1)
        body = pr1_calls[0][0][2]
        self.assertIn("#2", body)
        self.assertIn("#3", body)
        self.assertIn("**2**", body)


class TestFindExistingComments(unittest.TestCase):
    """Tests for the _find_existing_comments function."""

    def test_find_existing_comments_found(self):
        """Should return all comments with the bot signature."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        comment1 = MagicMock()
        comment1.body = "Some random comment"
        comment2 = MagicMock()
        comment2.body = f"{pr_comment.COMMENT_SIGNATURE}\nConflict info"
        pr.issue_comments.return_value = [comment1, comment2]

        result = pr_comment._find_existing_comments(repo, 123)
        self.assertEqual(result, [comment2])

    def test_find_existing_comments_multiple(self):
        """Should return all bot comments for stale cleanup."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        comment1 = MagicMock()
        comment1.body = f"{pr_comment.COMMENT_SIGNATURE}\nOld conflict with #200"
        comment2 = MagicMock()
        comment2.body = f"{pr_comment.COMMENT_SIGNATURE}\nOld conflict with #300"
        comment3 = MagicMock()
        comment3.body = f"{pr_comment.COMMENT_SIGNATURE}\nOld conflict with #400"
        pr.issue_comments.return_value = [comment1, comment2, comment3]

        result = pr_comment._find_existing_comments(repo, 123)
        self.assertEqual(len(result), 3)
        self.assertEqual(result, [comment1, comment2, comment3])

    def test_find_existing_comments_not_found(self):
        """Should return empty list if no matching comment exists."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        comment1 = MagicMock()
        comment1.body = "Regular comment"
        pr.issue_comments.return_value = [comment1]

        result = pr_comment._find_existing_comments(repo, 123)
        self.assertEqual(result, [])

    def test_find_existing_comments_error_handling(self):
        """Should return empty list on error to avoid blocking."""
        repo = MagicMock()
        repo.pull_request.side_effect = Exception("API error")

        result = pr_comment._find_existing_comments(repo, 123)
        self.assertEqual(result, [])


class TestPostComment(unittest.TestCase):
    """Tests for the _post_comment function."""

    def test_post_comment_success(self):
        """Should successfully post a comment."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        result = pr_comment._post_comment(repo, 123, "Test comment")

        self.assertTrue(result)
        pr.create_comment.assert_called_once_with("Test comment")

    def test_post_comment_failure(self):
        """Should return False on error."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr
        pr.create_comment.side_effect = Exception("API error")

        result = pr_comment._post_comment(repo, 123, "Test comment")

        self.assertFalse(result)


class TestStaleCommentCleanup(unittest.TestCase):
    """Tests for stale bot comment cleanup during migration."""

    @patch("pr_comment._delete_comment", return_value=True)
    @patch("pr_comment._update_comment", return_value=True)
    @patch("pr_comment._find_existing_comments")
    def test_cleans_up_stale_comments(self, mock_find, mock_update, mock_delete):
        """Should update first bot comment and delete the rest."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        stale1 = MagicMock()
        stale1.id = 1
        stale2 = MagicMock()
        stale2.id = 2
        stale3 = MagicMock()
        stale3.id = 3
        mock_find.return_value = [stale1, stale2, stale3]

        gh = MagicMock()
        gh.repository.return_value = MagicMock()

        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # First comment should be updated, not deleted
        self.assertEqual(mock_update.call_count, 2)  # PR #1 and PR #2
        # Two stale comments deleted per PR = 4 total
        self.assertEqual(mock_delete.call_count, 4)

    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_dry_run_reports_new_comments(self, _mock_find):
        """Dry run with no existing comments should report as new."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        gh.repository.return_value = MagicMock()

        with patch("pr_comment.logger") as mock_logger:
            pr_comment.post_pr_comments(conflicts, gh, dry_run=True)
            log_messages = [str(c) for c in mock_logger.info.call_args_list]
            create_logs = [m for m in log_messages if "create" in m]
            self.assertGreater(len(create_logs), 0)

    @patch("pr_comment._find_existing_comments")
    def test_dry_run_reports_updates(self, mock_find):
        """Dry run with existing comments should report as update."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        mock_find.return_value = [MagicMock()]

        gh = MagicMock()
        gh.repository.return_value = MagicMock()

        with patch("pr_comment.logger") as mock_logger:
            pr_comment.post_pr_comments(conflicts, gh, dry_run=True)
            log_messages = [str(c) for c in mock_logger.info.call_args_list]
            update_logs = [m for m in log_messages if "update" in m]
            self.assertGreater(len(update_logs), 0)

    @patch("pr_comment._find_existing_comments")
    def test_dry_run_reports_stale_cleanup(self, mock_find):
        """Dry run should report stale comment cleanup."""
        conflict = _make_comment_conflict()
        conflicts = {"org/repo": [conflict]}

        mock_find.return_value = [MagicMock(), MagicMock(), MagicMock()]

        gh = MagicMock()
        gh.repository.return_value = MagicMock()

        with patch("pr_comment.logger") as mock_logger:
            pr_comment.post_pr_comments(conflicts, gh, dry_run=True)
            log_messages = [str(c) for c in mock_logger.info.call_args_list]
            stale_logs = [m for m in log_messages if "stale" in m]
            self.assertGreater(len(stale_logs), 0)


if __name__ == "__main__":
    unittest.main()
