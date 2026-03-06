"""Test cases for the pr_data module."""

import unittest
from unittest.mock import MagicMock, patch

from pr_data import (
    ChangedFile,
    PullRequestData,
    fetch_all_pr_data,
    get_open_prs,
    get_pr_changed_files,
    parse_patch_line_ranges,
)


class TestParsePatchLineRanges(unittest.TestCase):
    """Tests for parse_patch_line_ranges()."""

    def test_simple_single_hunk(self):
        """A single hunk patch should return one range."""
        patch_text = "@@ -10,5 +10,7 @@ def foo():\n+    added line\n+    another line"
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [(10, 16)])

    def test_multi_hunk_patch(self):
        """Multiple hunks should return multiple ranges."""
        patch_text = (
            "@@ -1,4 +1,5 @@\n"
            "+import os\n"
            " existing\n"
            "@@ -20,3 +21,6 @@ class Foo:\n"
            "+    new_method\n"
        )
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [(1, 5), (21, 26)])

    def test_none_patch_binary_file(self):
        """Binary files have no patch; should return empty list."""
        result = parse_patch_line_ranges(None)
        self.assertEqual(result, [])

    def test_empty_string_patch(self):
        """An empty string patch should return empty list."""
        result = parse_patch_line_ranges("")
        self.assertEqual(result, [])

    def test_single_line_change(self):
        """A hunk with no comma (implicit length=1) should return a single-line range."""
        patch_text = "@@ -5 +5 @@ some context\n-old\n+new"
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [(5, 5)])

    def test_zero_length_hunk(self):
        """A hunk with length 0 (pure deletion in new file) should be skipped."""
        patch_text = "@@ -10,3 +9,0 @@ context\n-deleted line"
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [])

    def test_large_line_numbers(self):
        """Handles large line numbers correctly."""
        patch_text = "@@ -1000,10 +2000,20 @@ function bigFile()"
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [(2000, 2019)])

    def test_new_file_hunk(self):
        """A new file starts at line 1."""
        patch_text = "@@ -0,0 +1,15 @@\n+line1\n+line2"
        result = parse_patch_line_ranges(patch_text)
        self.assertEqual(result, [(1, 15)])


def _make_mock_pr(
    number: int = 1,
    title: str = "Test PR",
    login: str = "testuser",
    html_url: str = "https://github.com/o/r/pull/1",
    draft: bool = False,
    base_ref: str = "main",
    head_ref: str = "feature",
):
    """Create a mock github3 pull request object."""
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.user.login = login
    pr.html_url = html_url
    pr.draft = draft
    pr.base.ref = base_ref
    pr.head.ref = head_ref
    return pr


class TestGetOpenPrs(unittest.TestCase):
    """Tests for get_open_prs()."""

    def test_basic_pr_listing(self):
        """Should return PullRequestData objects for all open PRs."""
        mock_repo = MagicMock()
        mock_repo.pull_requests.return_value = [
            _make_mock_pr(number=1, title="First PR"),
            _make_mock_pr(number=2, title="Second PR"),
        ]

        result = get_open_prs(mock_repo)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].number, 1)
        self.assertEqual(result[0].title, "First PR")
        self.assertEqual(result[1].number, 2)
        mock_repo.pull_requests.assert_called_once_with(state="open")

    def test_filter_drafts(self):
        """When include_drafts=False, draft PRs should be excluded."""
        mock_repo = MagicMock()
        mock_repo.pull_requests.return_value = [
            _make_mock_pr(number=1, draft=False),
            _make_mock_pr(number=2, draft=True),
            _make_mock_pr(number=3, draft=False),
        ]

        result = get_open_prs(mock_repo, include_drafts=False)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].number, 1)
        self.assertEqual(result[1].number, 3)

    def test_include_drafts(self):
        """When include_drafts=True (default), drafts should be included."""
        mock_repo = MagicMock()
        mock_repo.pull_requests.return_value = [
            _make_mock_pr(number=1, draft=True),
            _make_mock_pr(number=2, draft=True),
        ]

        result = get_open_prs(mock_repo, include_drafts=True)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].is_draft)
        self.assertTrue(result[1].is_draft)

    def test_empty_repo(self):
        """A repo with no open PRs should return an empty list."""
        mock_repo = MagicMock()
        mock_repo.pull_requests.return_value = []

        result = get_open_prs(mock_repo)

        self.assertEqual(result, [])

    def test_pr_data_fields(self):
        """All PullRequestData fields should be correctly populated."""
        mock_repo = MagicMock()
        mock_repo.pull_requests.return_value = [
            _make_mock_pr(
                number=42,
                title="Add feature X",
                login="octocat",
                html_url="https://github.com/o/r/pull/42",
                draft=True,
                base_ref="main",
                head_ref="feature-x",
            )
        ]

        result = get_open_prs(mock_repo)

        pr = result[0]
        self.assertEqual(pr.number, 42)
        self.assertEqual(pr.title, "Add feature X")
        self.assertEqual(pr.author, "octocat")
        self.assertEqual(pr.html_url, "https://github.com/o/r/pull/42")
        self.assertTrue(pr.is_draft)
        self.assertEqual(pr.base_branch, "main")
        self.assertEqual(pr.head_branch, "feature-x")
        self.assertEqual(pr.changed_files, [])


def _make_mock_file(
    filename: str = "file.py",
    additions: int = 5,
    deletions: int = 2,
    changes: int = 7,
    patch_str: str | None = "@@ -1,3 +1,5 @@\n+new line",
):
    """Create a mock github3 pull request file object."""
    f = MagicMock()
    f.filename = filename
    f.additions = additions
    f.deletions = deletions
    f.changes = changes
    f.patch = patch_str
    return f


class TestGetPrChangedFiles(unittest.TestCase):
    """Tests for get_pr_changed_files()."""

    def test_basic_changed_files(self):
        """Should return ChangedFile objects with parsed line ranges."""
        mock_pr = MagicMock()
        mock_pr.files.return_value = [
            _make_mock_file(
                filename="src/main.py",
                additions=3,
                deletions=1,
                changes=4,
                patch_str="@@ -10,5 +10,7 @@\n+added",
            ),
        ]

        result = get_pr_changed_files(mock_pr, MagicMock(), "owner", "repo")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].filename, "src/main.py")
        self.assertEqual(result[0].additions, 3)
        self.assertEqual(result[0].deletions, 1)
        self.assertEqual(result[0].changes, 4)
        self.assertEqual(result[0].patch_lines, [(10, 16)])

    def test_binary_file_no_patch(self):
        """Binary files with no patch should have empty patch_lines."""
        mock_pr = MagicMock()
        mock_pr.files.return_value = [
            _make_mock_file(filename="image.png", patch_str=None),
        ]

        result = get_pr_changed_files(mock_pr, MagicMock(), "owner", "repo")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].filename, "image.png")
        self.assertEqual(result[0].patch_lines, [])

    def test_multiple_files(self):
        """Should handle multiple changed files."""
        mock_pr = MagicMock()
        mock_pr.files.return_value = [
            _make_mock_file(filename="a.py", patch_str="@@ -1,2 +1,3 @@\n+x"),
            _make_mock_file(filename="b.py", patch_str="@@ -5,4 +5,6 @@\n+y"),
            _make_mock_file(filename="c.bin", patch_str=None),
        ]

        result = get_pr_changed_files(mock_pr, MagicMock(), "owner", "repo")

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].filename, "a.py")
        self.assertEqual(result[1].filename, "b.py")
        self.assertEqual(result[2].filename, "c.bin")

    def test_empty_files_list(self):
        """A PR with no changed files should return empty list."""
        mock_pr = MagicMock()
        mock_pr.files.return_value = []

        result = get_pr_changed_files(mock_pr, MagicMock(), "owner", "repo")

        self.assertEqual(result, [])


class TestFetchAllPrData(unittest.TestCase):
    """Tests for fetch_all_pr_data()."""

    @patch("pr_data.get_open_prs")
    def test_basic_orchestration(self, mock_get_open_prs):
        """Should fetch files for each PR and populate changed_files."""
        pr1 = PullRequestData(
            number=1,
            title="PR 1",
            author="user1",
            html_url="https://github.com/o/r/pull/1",
            is_draft=False,
            base_branch="main",
            head_branch="feat-1",
        )
        pr2 = PullRequestData(
            number=2,
            title="PR 2",
            author="user2",
            html_url="https://github.com/o/r/pull/2",
            is_draft=False,
            base_branch="main",
            head_branch="feat-2",
        )
        mock_get_open_prs.return_value = [pr1, pr2]

        mock_repo = MagicMock()
        mock_full_pr = MagicMock()
        mock_full_pr.files.return_value = [
            _make_mock_file(filename="test.py", patch_str="@@ -1,2 +1,3 @@\n+x"),
        ]
        mock_repo.pull_request.return_value = mock_full_pr

        result = fetch_all_pr_data(mock_repo, True, MagicMock(), "owner", "repo")

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0].changed_files), 1)
        self.assertEqual(result[0].changed_files[0].filename, "test.py")
        self.assertEqual(mock_repo.pull_request.call_count, 2)

    @patch("pr_data.get_open_prs")
    def test_empty_repo(self, mock_get_open_prs):
        """An empty repo should return empty list without errors."""
        mock_get_open_prs.return_value = []

        result = fetch_all_pr_data(MagicMock(), True, MagicMock(), "owner", "repo")

        self.assertEqual(result, [])

    @patch("pr_data.get_open_prs")
    def test_api_error_handling(self, mock_get_open_prs):
        """If fetching files for a PR fails, it should be skipped gracefully."""
        pr1 = PullRequestData(
            number=1,
            title="Good PR",
            author="user1",
            html_url="url1",
            is_draft=False,
            base_branch="main",
            head_branch="feat-1",
        )
        pr2 = PullRequestData(
            number=2,
            title="Bad PR",
            author="user2",
            html_url="url2",
            is_draft=False,
            base_branch="main",
            head_branch="feat-2",
        )
        mock_get_open_prs.return_value = [pr1, pr2]

        mock_repo = MagicMock()
        mock_full_pr_good = MagicMock()
        mock_full_pr_good.files.return_value = [
            _make_mock_file(filename="good.py"),
        ]

        def side_effect(number):
            if number == 2:
                raise RuntimeError("API rate limit exceeded")
            return mock_full_pr_good

        mock_repo.pull_request.side_effect = side_effect

        result = fetch_all_pr_data(mock_repo, True, MagicMock(), "owner", "repo")

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0].changed_files), 1)
        # PR #2 failed but is still in the list with empty changed_files
        self.assertEqual(result[1].changed_files, [])

    @patch("pr_data.get_open_prs")
    @patch("builtins.print")
    def test_progress_reporting(self, mock_print, mock_get_open_prs):
        """Should print progress for repos with >= 50 PRs."""
        prs = [
            PullRequestData(
                number=i,
                title=f"PR {i}",
                author="user",
                html_url=f"url{i}",
                is_draft=False,
                base_branch="main",
                head_branch=f"feat-{i}",
            )
            for i in range(1, 101)
        ]
        mock_get_open_prs.return_value = prs

        mock_repo = MagicMock()
        mock_full_pr = MagicMock()
        mock_full_pr.files.return_value = []
        mock_repo.pull_request.return_value = mock_full_pr

        fetch_all_pr_data(mock_repo, True, MagicMock(), "owner", "repo")

        progress_calls = [
            call for call in mock_print.call_args_list if "Progress:" in str(call)
        ]
        # Should have progress at 50 and 100
        self.assertEqual(len(progress_calls), 2)

    @patch("pr_data.get_open_prs")
    def test_include_drafts_passed_through(self, mock_get_open_prs):
        """The include_drafts parameter should be forwarded to get_open_prs."""
        mock_get_open_prs.return_value = []

        fetch_all_pr_data(MagicMock(), False, MagicMock(), "owner", "repo")

        mock_get_open_prs.assert_called_once()
        args = mock_get_open_prs.call_args
        self.assertFalse(args[0][1])  # include_drafts=False


class TestDataClasses(unittest.TestCase):
    """Tests for the data classes."""

    def test_changed_file_defaults(self):
        """ChangedFile should have an empty patch_lines by default."""
        cf = ChangedFile(filename="f.py", additions=1, deletions=0, changes=1)
        self.assertEqual(cf.patch_lines, [])

    def test_pull_request_data_defaults(self):
        """PullRequestData should have empty changed_files by default."""
        pr = PullRequestData(
            number=1,
            title="t",
            author="a",
            html_url="u",
            is_draft=False,
            base_branch="main",
            head_branch="feat",
        )
        self.assertEqual(pr.changed_files, [])


if __name__ == "__main__":
    unittest.main()
