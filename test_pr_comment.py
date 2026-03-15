"""Tests for the pr_comment module."""

# pylint: disable=protected-access

import unittest
from unittest.mock import MagicMock, patch

import pr_comment
from conflict_detector import ConflictResult, FileOverlap, PRInfo
from pr_comment import ConflictEntry


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
    """Helper to build a ConflictResult."""
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
        conflict = _make_conflict()
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
        conflict = _make_conflict()
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
        conflict = _make_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        result = pr_comment.post_pr_comments(conflicts, gh, dry_run=True)

        self.assertTrue(result)
        gh.repository.assert_called_once_with("org", "repo")

    @patch("pr_comment._post_comment", return_value=True)
    @patch("pr_comment._find_existing_comments", return_value=[])
    def test_multiple_conflicts_single_comment(self, _mock_find, mock_post):
        """Multiple conflicts for same PR should produce a single comment."""
        conflict1 = _make_conflict(
            pr_a_number=1, pr_b_number=2, filenames=["file_a.py"]
        )
        conflict2 = _make_conflict(
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


class TestBuildConsolidatedComment(unittest.TestCase):
    """Tests for the _build_consolidated_comment function."""

    def test_single_conflict(self):
        """Should build a properly formatted comment for one conflict."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=456,
                    url="https://github.com/org/repo/pull/456",
                    title="Refactor auth",
                    author="bob",
                ),
                files=[
                    FileOverlap(
                        filename="src/auth.py",
                        pr_a_lines=[(10, 20)],
                        pr_b_lines=[(15, 25)],
                        overlapping_ranges=[(15, 20)],
                    )
                ],
            )
        ]

        comment = pr_comment._build_consolidated_comment(entries)

        self.assertIn(pr_comment.COMMENT_SIGNATURE, comment)
        self.assertIn("**1**", comment)
        self.assertIn("#456", comment)
        self.assertIn("Refactor auth", comment)
        self.assertIn("@bob", comment)
        self.assertIn("`src/auth.py`", comment)
        self.assertIn("L15-L20", comment)

    def test_multiple_conflicts(self):
        """Should list all conflicting PRs in the table."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=200,
                    url="https://github.com/org/repo/pull/200",
                    title="PR 200",
                    author="alice",
                ),
                files=[
                    FileOverlap(
                        filename="file_a.rb",
                        pr_a_lines=[(10, 20)],
                        pr_b_lines=[(10, 20)],
                        overlapping_ranges=[(10, 20)],
                    )
                ],
            ),
            ConflictEntry(
                other_pr=PRInfo(
                    number=300,
                    url="https://github.com/org/repo/pull/300",
                    title="PR 300",
                    author="charlie",
                ),
                files=[
                    FileOverlap(
                        filename="file_a.rb",
                        pr_a_lines=[(5, 15)],
                        pr_b_lines=[(5, 15)],
                        overlapping_ranges=[(5, 15)],
                    ),
                    FileOverlap(
                        filename="file_b.rb",
                        pr_a_lines=[(30, 40)],
                        pr_b_lines=[(30, 40)],
                        overlapping_ranges=[(30, 40)],
                    ),
                ],
            ),
        ]

        comment = pr_comment._build_consolidated_comment(entries)

        self.assertIn("**2**", comment)
        self.assertIn("#200", comment)
        self.assertIn("#300", comment)
        self.assertIn("@alice", comment)
        self.assertIn("@charlie", comment)
        self.assertIn("`file_a.rb`", comment)
        self.assertIn("`file_b.rb`", comment)
        # Verify file-to-range attribution: each file's ranges appear next to the filename
        self.assertIn("`file_a.rb` (L5-L15)", comment)
        self.assertIn("`file_b.rb` (L30-L40)", comment)


class TestGroupConflictsByPR(unittest.TestCase):
    """Tests for the _group_conflicts_by_pr function."""

    def test_single_conflict(self):
        """Should create entries for both PRs in a conflict."""
        conflict = _make_conflict(pr_a_number=1, pr_b_number=2)
        grouped = pr_comment._group_conflicts_by_pr([conflict])

        self.assertIn(1, grouped)
        self.assertIn(2, grouped)
        self.assertEqual(len(grouped[1]), 1)
        self.assertEqual(grouped[1][0].other_pr.number, 2)
        self.assertEqual(grouped[2][0].other_pr.number, 1)

    def test_multiple_conflicts_same_pr(self):
        """PR appearing in multiple conflicts should have all entries grouped."""
        conflict1 = _make_conflict(pr_a_number=1, pr_b_number=2)
        conflict2 = _make_conflict(pr_a_number=1, pr_b_number=3)
        grouped = pr_comment._group_conflicts_by_pr([conflict1, conflict2])

        self.assertEqual(len(grouped[1]), 2)
        other_numbers = {e.other_pr.number for e in grouped[1]}
        self.assertEqual(other_numbers, {2, 3})


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


class TestStaleCommentCleanup(unittest.TestCase):
    """Tests for stale bot comment cleanup during migration."""

    @patch("pr_comment._delete_comment", return_value=True)
    @patch("pr_comment._update_comment", return_value=True)
    @patch("pr_comment._find_existing_comments")
    def test_cleans_up_stale_comments(self, mock_find, mock_update, mock_delete):
        """Should update first bot comment and delete the rest."""
        conflict = _make_conflict()
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
        conflict = _make_conflict()
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
        conflict = _make_conflict()
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
        conflict = _make_conflict()
        conflicts = {"org/repo": [conflict]}

        mock_find.return_value = [MagicMock(), MagicMock(), MagicMock()]

        gh = MagicMock()
        gh.repository.return_value = MagicMock()

        with patch("pr_comment.logger") as mock_logger:
            pr_comment.post_pr_comments(conflicts, gh, dry_run=True)
            log_messages = [str(c) for c in mock_logger.info.call_args_list]
            stale_logs = [m for m in log_messages if "stale" in m]
            self.assertGreater(len(stale_logs), 0)


class TestFormatRanges(unittest.TestCase):
    """Tests for the _format_ranges function."""

    def test_format_ranges_single(self):
        """Should format a single range correctly."""
        result = pr_comment._format_ranges([(10, 25)])
        self.assertEqual(result, "L10-L25")

    def test_format_ranges_multiple(self):
        """Should format multiple ranges correctly."""
        result = pr_comment._format_ranges([(10, 25), (42, 55), (100, 120)])
        self.assertEqual(result, "L10-L25, L42-L55, L100-L120")


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


if __name__ == "__main__":
    unittest.main()
