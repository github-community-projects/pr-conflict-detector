"""Tests for the pr_comment module."""

# pylint: disable=protected-access

import unittest
from collections import namedtuple
from unittest.mock import MagicMock, patch

import pr_comment
from conflict_detector import ConflictResult, FileOverlap, PRInfo

# Lightweight stand-in for GitHub comment
Comment = namedtuple("Comment", ["body"])


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
    @patch("pr_comment._has_existing_comment", return_value=False)
    def test_post_pr_comments_success(self, _mock_has_comment, mock_post):
        """Should post comments to both PRs in a conflict."""
        conflict = _make_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        repo_mock = MagicMock()
        gh.repository.return_value = repo_mock

        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # Should post to both PR #1 and PR #2
        self.assertEqual(mock_post.call_count, 2)
        mock_post.assert_any_call(repo_mock, 1, unittest.mock.ANY)
        mock_post.assert_any_call(repo_mock, 2, unittest.mock.ANY)

    @patch("pr_comment._post_comment", return_value=True)
    @patch("pr_comment._has_existing_comment", return_value=True)
    def test_post_pr_comments_skips_duplicates(self, _mock_has_comment, mock_post):
        """Should skip posting if comment already exists."""
        conflict = _make_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        result = pr_comment.post_pr_comments(conflicts, gh)

        self.assertTrue(result)
        # Should not post any comments (both are duplicates)
        mock_post.assert_not_called()

    @patch("pr_comment._has_existing_comment", return_value=False)
    def test_post_pr_comments_dry_run(self, _mock_has_comment):
        """Dry run should not post comments."""
        conflict = _make_conflict()
        conflicts = {"org/repo": [conflict]}

        gh = MagicMock()
        result = pr_comment.post_pr_comments(conflicts, gh, dry_run=True)

        self.assertTrue(result)
        # Should check for existing comments but not post
        gh.repository.assert_called_once_with("org", "repo")


class TestHasExistingComment(unittest.TestCase):
    """Tests for the _has_existing_comment function."""

    def test_has_existing_comment_found(self):
        """Should return True if comment with signature and PR number exists."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        # Mock comments with one containing our signature
        comment1 = Comment(body="Some random comment")
        comment2 = Comment(body=f"{pr_comment.COMMENT_SIGNATURE}\nConflict with #456")
        pr.issue_comments.return_value = [comment1, comment2]

        result = pr_comment._has_existing_comment(repo, 123, 456)
        self.assertTrue(result)

    def test_has_existing_comment_not_found(self):
        """Should return False if no matching comment exists."""
        repo = MagicMock()
        pr = MagicMock()
        repo.pull_request.return_value = pr

        # Mock comments without our signature
        comment1 = Comment(body="Regular comment")
        comment2 = Comment(body="Another comment about #456")
        pr.issue_comments.return_value = [comment1, comment2]

        result = pr_comment._has_existing_comment(repo, 123, 456)
        self.assertFalse(result)

    def test_has_existing_comment_error_handling(self):
        """Should return False on error to avoid blocking."""
        repo = MagicMock()
        repo.pull_request.side_effect = Exception("API error")

        result = pr_comment._has_existing_comment(repo, 123, 456)
        self.assertFalse(result)


class TestBuildComment(unittest.TestCase):
    """Tests for the _build_comment function."""

    def test_build_comment_format(self):
        """Should build a properly formatted comment."""
        conflict = _make_conflict(
            pr_a_number=123,
            pr_b_number=456,
            pr_b_title="Refactor auth",
            pr_b_url="https://github.com/org/repo/pull/456",
            pr_b_author="bob",
            filenames=["src/auth.py", "src/test.py"],
        )

        comment = pr_comment._build_comment(conflict, conflict.pr_a, conflict.pr_b)

        # Check for required elements
        self.assertIn(pr_comment.COMMENT_SIGNATURE, comment)
        self.assertIn("#456", comment)
        self.assertIn("Refactor auth", comment)
        self.assertIn("@bob", comment)
        self.assertIn("src/auth.py", comment)
        self.assertIn("src/test.py", comment)
        self.assertIn("L15-L20", comment)


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
