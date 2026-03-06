"""Tests for the conflict_detector module."""

import unittest
from unittest.mock import MagicMock

from conflict_detector import (
    ConflictResult,
    FileOverlap,
    detect_conflicts,
    find_file_overlaps,
    find_overlapping_ranges,
    ranges_overlap,
    verify_conflict,
)
from pr_data import ChangedFile, PullRequestData


class TestRangesOverlap(unittest.TestCase):
    """Test the ranges_overlap function."""

    def test_overlapping_ranges(self):
        """Test that overlapping ranges are detected."""
        assert ranges_overlap((1, 10), (5, 15)) is True

    def test_non_overlapping_ranges(self):
        """Test that non-overlapping ranges return False."""
        assert ranges_overlap((1, 5), (10, 15)) is False

    def test_adjacent_ranges(self):
        """Test that adjacent ranges sharing a boundary overlap."""
        assert ranges_overlap((1, 5), (5, 10)) is True

    def test_contained_range(self):
        """Test that a fully contained range is detected as overlapping."""
        assert ranges_overlap((1, 20), (5, 10)) is True

    def test_same_range(self):
        """Test that identical ranges overlap."""
        assert ranges_overlap((5, 10), (5, 10)) is True

    def test_single_line_overlap(self):
        """Test that single-line ranges on the same line overlap."""
        assert ranges_overlap((5, 5), (5, 5)) is True

    def test_reversed_non_overlapping(self):
        """Test non-overlapping ranges in reversed order."""
        assert ranges_overlap((10, 15), (1, 5)) is False

    def test_reversed_overlapping(self):
        """Test overlapping ranges in reversed order."""
        assert ranges_overlap((5, 15), (1, 10)) is True


class TestFindOverlappingRanges(unittest.TestCase):
    """Test the find_overlapping_ranges function."""

    def test_single_overlap(self):
        """Test that a single overlapping range pair is found."""
        result = find_overlapping_ranges([(1, 10)], [(5, 15)])
        assert result == [(5, 10)]

    def test_no_overlap(self):
        """Test that non-overlapping ranges return empty."""
        result = find_overlapping_ranges([(1, 5)], [(10, 15)])
        assert not result

    def test_multiple_overlaps(self):
        """Test that multiple overlapping ranges are all found."""
        result = find_overlapping_ranges([(1, 10), (20, 30)], [(5, 25)])
        assert len(result) == 2
        assert (5, 10) in result
        assert (20, 25) in result

    def test_empty_ranges(self):
        """Test that empty input ranges return empty results."""
        assert not find_overlapping_ranges([], [(1, 10)])
        assert not find_overlapping_ranges([(1, 10)], [])
        assert not find_overlapping_ranges([], [])

    def test_contained_overlap(self):
        """Test overlap when one range fully contains the other."""
        result = find_overlapping_ranges([(1, 20)], [(5, 10)])
        assert result == [(5, 10)]

    def test_identical_ranges(self):
        """Test overlap of identical ranges."""
        result = find_overlapping_ranges([(5, 10)], [(5, 10)])
        assert result == [(5, 10)]


def _make_file(filename: str, patch_lines: list[tuple[int, int]]) -> ChangedFile:
    """Helper to create a ChangedFile for tests."""
    return ChangedFile(
        filename=filename,
        additions=0,
        deletions=0,
        changes=0,
        patch_lines=patch_lines,
    )


def _make_pr(
    number: int,
    files: list[ChangedFile] | None = None,
    title: str = "",
    author: str = "user",
) -> PullRequestData:
    """Helper to create a PullRequestData for tests."""
    return PullRequestData(
        number=number,
        title=title or f"PR #{number}",
        author=author,
        html_url=f"https://github.com/owner/repo/pull/{number}",
        is_draft=False,
        base_branch="main",
        head_branch=f"feature-{number}",
        changed_files=files or [],
    )


class TestFindFileOverlaps(unittest.TestCase):
    """Test the find_file_overlaps function."""

    def test_two_prs_overlapping_lines(self):
        """Test that two PRs with overlapping lines produce a conflict."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(5, 15)])])

        results = find_file_overlaps([pr_a, pr_b])

        assert len(results) == 1
        assert results[0].pr_a_number == 1
        assert results[0].pr_b_number == 2
        assert len(results[0].conflicting_files) == 1
        assert results[0].conflicting_files[0].filename == "file.py"
        assert (5, 10) in results[0].conflicting_files[0].overlapping_ranges

    def test_two_prs_same_file_different_lines(self):
        """Test that two PRs touching different lines have no conflict."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 5)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(50, 60)])])

        results = find_file_overlaps([pr_a, pr_b])
        assert len(results) == 0

    def test_two_prs_different_files(self):
        """Test that two PRs touching different files have no conflict."""
        pr_a = _make_pr(1, [_make_file("a.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("b.py", [(1, 10)])])

        results = find_file_overlaps([pr_a, pr_b])
        assert len(results) == 0

    def test_three_prs_same_file(self):
        """Test that three PRs overlapping on one file produce all conflict pairs."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(5, 15)])])
        pr_c = _make_pr(3, [_make_file("file.py", [(8, 20)])])

        results = find_file_overlaps([pr_a, pr_b, pr_c])

        # Expect 3 conflict pairs: (1,2), (1,3), (2,3)
        pair_numbers = {(r.pr_a_number, r.pr_b_number) for r in results}
        assert (1, 2) in pair_numbers
        assert (1, 3) in pair_numbers
        assert (2, 3) in pair_numbers

    def test_pr_with_no_changed_files(self):
        """Test that a PR with no changed files produces no conflicts."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [])

        results = find_file_overlaps([pr_a, pr_b])
        assert len(results) == 0

    def test_empty_pr_list(self):
        """Test that an empty PR list returns no conflicts."""
        results = find_file_overlaps([])
        assert not results

    def test_single_pr(self):
        """Test that a single PR cannot conflict with itself."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        results = find_file_overlaps([pr_a])
        assert not results

    def test_multiple_files_same_pair(self):
        """Two PRs conflicting on multiple files should produce one ConflictResult."""
        pr_a = _make_pr(
            1,
            [
                _make_file("a.py", [(1, 10)]),
                _make_file("b.py", [(20, 30)]),
            ],
        )
        pr_b = _make_pr(
            2,
            [
                _make_file("a.py", [(5, 15)]),
                _make_file("b.py", [(25, 35)]),
            ],
        )

        results = find_file_overlaps([pr_a, pr_b])

        assert len(results) == 1
        assert len(results[0].conflicting_files) == 2
        filenames = {f.filename for f in results[0].conflicting_files}
        assert filenames == {"a.py", "b.py"}

    def test_pr_pair_ordering_is_consistent(self):
        """pr_a_number should always be less than pr_b_number."""
        pr_a = _make_pr(10, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(5, [_make_file("file.py", [(5, 15)])])

        results = find_file_overlaps([pr_a, pr_b])

        assert len(results) == 1
        assert results[0].pr_a_number == 5
        assert results[0].pr_b_number == 10


class TestDetectConflicts(unittest.TestCase):
    """Test the detect_conflicts integration function."""

    def test_basic_detection(self):
        """Test basic conflict detection between two PRs."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(5, 15)])])

        results = detect_conflicts([pr_a, pr_b])

        assert len(results) == 1
        assert results[0].verified is False

    def test_sorted_by_conflicting_files_count(self):
        """Results should be sorted with most conflicting files first."""
        pr_a = _make_pr(1, [_make_file("x.py", [(1, 10)])])
        pr_b = _make_pr(
            2,
            [
                _make_file("x.py", [(5, 15)]),
                _make_file("y.py", [(1, 10)]),
            ],
        )
        pr_c = _make_pr(
            3,
            [
                _make_file("x.py", [(3, 8)]),
                _make_file("y.py", [(5, 15)]),
            ],
        )

        results = detect_conflicts([pr_a, pr_b, pr_c])

        # The pair with the most conflicting files should be first
        file_counts = [len(r.conflicting_files) for r in results]
        assert file_counts == sorted(file_counts, reverse=True)

    def test_no_conflicts(self):
        """Test that non-overlapping PRs produce no conflicts."""
        pr_a = _make_pr(1, [_make_file("a.py", [(1, 5)])])
        pr_b = _make_pr(2, [_make_file("b.py", [(1, 5)])])

        results = detect_conflicts([pr_a, pr_b])
        assert not results

    def test_empty_input(self):
        """Test that empty input returns no conflicts."""
        assert not detect_conflicts([])

    def test_with_verify_flag(self):
        """When verify=True, verify_conflict should be called for each conflict."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(5, 15)])])

        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_gh.repository.return_value = mock_repo
        mock_pr = MagicMock()
        mock_pr.mergeable = False
        mock_repo.pull_request.return_value = mock_pr

        results = detect_conflicts(
            [pr_a, pr_b],
            verify=True,
            github_connection=mock_gh,
            owner="owner",
            repo_name="repo",
        )

        assert len(results) == 1
        assert results[0].verified is True

    def test_verify_without_connection_skips(self):
        """When verify=True but no connection, verification is skipped."""
        pr_a = _make_pr(1, [_make_file("file.py", [(1, 10)])])
        pr_b = _make_pr(2, [_make_file("file.py", [(5, 15)])])

        results = detect_conflicts([pr_a, pr_b], verify=True)

        assert len(results) == 1
        assert results[0].verified is False


class TestVerifyConflict(unittest.TestCase):
    """Test the verify_conflict function with mocked API."""

    def _make_conflict(self) -> ConflictResult:
        return ConflictResult(
            pr_a_number=1,
            pr_a_title="PR #1",
            pr_a_author="alice",
            pr_a_url="https://github.com/owner/repo/pull/1",
            pr_b_number=2,
            pr_b_title="PR #2",
            pr_b_author="bob",
            pr_b_url="https://github.com/owner/repo/pull/2",
            conflicting_files=[FileOverlap("file.py", [(1, 10)], [(5, 15)], [(5, 10)])],
        )

    def test_verify_returns_true_when_not_mergeable(self):
        """Test that verify returns True when PR is not mergeable."""
        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_gh.repository.return_value = mock_repo
        mock_pr = MagicMock()
        mock_pr.mergeable = False
        mock_repo.pull_request.return_value = mock_pr

        conflict = self._make_conflict()
        result = verify_conflict(conflict, mock_gh, "owner", "repo")

        assert result is True

    def test_verify_returns_false_when_mergeable(self):
        """Test that verify returns False when PR is mergeable."""
        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_gh.repository.return_value = mock_repo
        mock_pr = MagicMock()
        mock_pr.mergeable = True
        mock_repo.pull_request.return_value = mock_pr

        conflict = self._make_conflict()
        result = verify_conflict(conflict, mock_gh, "owner", "repo")

        assert result is False

    def test_verify_returns_false_on_api_error(self):
        """Test that verify returns False when the API raises an error."""
        mock_gh = MagicMock()
        mock_gh.repository.side_effect = Exception("API error")

        conflict = self._make_conflict()
        result = verify_conflict(conflict, mock_gh, "owner", "repo")

        assert result is False

    def test_verify_returns_false_when_mergeable_is_none(self):
        """When GitHub hasn't computed mergeability yet, mergeable is None."""
        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_gh.repository.return_value = mock_repo
        mock_pr = MagicMock()
        mock_pr.mergeable = None
        mock_repo.pull_request.return_value = mock_pr

        conflict = self._make_conflict()
        result = verify_conflict(conflict, mock_gh, "owner", "repo")

        assert result is False


if __name__ == "__main__":
    unittest.main()
