"""Tests for issue_writer module."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from issue_writer import ISSUE_HEADER, ISSUE_TAG, create_or_update_issue


def _make_file_overlap(filename="file.py", ranges=None):
    """Create a stub FileOverlap-like object."""
    return SimpleNamespace(
        filename=filename,
        overlapping_ranges=ranges or [(10, 25)],
    )


def _make_pr(number, title, author, url=None):
    """Create a stub PR info object."""
    return SimpleNamespace(
        number=number,
        title=title,
        author=author,
        url=url or f"https://github.com/owner/repo/pull/{number}",
    )


def _make_conflict(pr_a, pr_b, files=None):
    """Create a stub ConflictResult-like object."""
    return SimpleNamespace(
        pr_a=pr_a,
        pr_b=pr_b,
        conflicting_files=files or [_make_file_overlap()],
    )


def _make_mock_repo(existing_issues=None):
    """Create a mock github3.py repository."""
    repo = MagicMock()
    repo.full_name = "owner/repo"
    repo.issues.return_value = existing_issues or []
    new_issue = MagicMock()
    new_issue.html_url = "https://github.com/owner/repo/issues/99"
    repo.create_issue.return_value = new_issue
    return repo


class TestCreateOrUpdateIssue:
    """Tests for create_or_update_issue()."""

    def test_no_conflicts_returns_none(self):
        """Return None and create no issue when there are no conflicts."""
        repo = _make_mock_repo()
        result = create_or_update_issue(repo, [])

        assert result is None
        repo.create_issue.assert_not_called()

    def test_creates_new_issue(self):
        """Create a new issue when no existing conflict report is found."""
        repo = _make_mock_repo()
        conflict = _make_conflict(
            _make_pr(1, "Feature A", "alice"),
            _make_pr(2, "Feature B", "bob"),
        )

        result = create_or_update_issue(repo, [conflict])

        assert result == "https://github.com/owner/repo/issues/99"
        repo.create_issue.assert_called_once()

        _, kwargs = repo.create_issue.call_args
        assert kwargs["title"] == "PR Conflict Report"
        assert ISSUE_TAG in kwargs["body"]
        assert ISSUE_HEADER in kwargs["body"]
        assert "[#1]" in kwargs["body"]
        assert "[#2]" in kwargs["body"]

    def test_updates_existing_issue(self):
        """Update an existing conflict report issue instead of creating a new one."""
        existing_issue = MagicMock()
        existing_issue.title = "PR Conflict Report"
        existing_issue.body = f"{ISSUE_TAG}\nold content"
        existing_issue.html_url = "https://github.com/owner/repo/issues/42"

        repo = _make_mock_repo(existing_issues=[existing_issue])
        conflict = _make_conflict(
            _make_pr(5, "New PR", "carol"),
            _make_pr(6, "Other PR", "dave"),
        )

        result = create_or_update_issue(repo, [conflict])

        assert result == "https://github.com/owner/repo/issues/42"
        existing_issue.edit.assert_called_once()
        repo.create_issue.assert_not_called()

        body = existing_issue.edit.call_args[1]["body"]
        assert "[#5]" in body
        assert "[#6]" in body

    def test_does_not_match_wrong_title(self):
        """Create a new issue when existing issues have a different title."""
        existing_issue = MagicMock()
        existing_issue.title = "Unrelated Issue"
        existing_issue.body = f"{ISSUE_TAG}\ncontent"
        existing_issue.html_url = "https://github.com/owner/repo/issues/10"

        repo = _make_mock_repo(existing_issues=[existing_issue])
        conflict = _make_conflict(_make_pr(1, "A", "alice"), _make_pr(2, "B", "bob"))

        create_or_update_issue(repo, [conflict])

        # Should create a new issue, not update the unrelated one
        repo.create_issue.assert_called_once()
        existing_issue.edit.assert_not_called()

    def test_does_not_match_issue_without_tag(self):
        """Create a new issue when existing issue lacks the conflict tag."""
        existing_issue = MagicMock()
        existing_issue.title = "PR Conflict Report"
        existing_issue.body = "Manual issue without our tag"
        existing_issue.html_url = "https://github.com/owner/repo/issues/10"

        repo = _make_mock_repo(existing_issues=[existing_issue])
        conflict = _make_conflict(_make_pr(1, "A", "alice"), _make_pr(2, "B", "bob"))

        create_or_update_issue(repo, [conflict])

        repo.create_issue.assert_called_once()
        existing_issue.edit.assert_not_called()

    def test_dry_run_does_not_create(self):
        """Return None and skip issue creation in dry-run mode."""
        repo = _make_mock_repo()
        conflict = _make_conflict(_make_pr(1, "A", "alice"), _make_pr(2, "B", "bob"))

        result = create_or_update_issue(repo, [conflict], dry_run=True)

        assert result is None
        repo.create_issue.assert_not_called()

    def test_dry_run_does_not_update(self):
        """Return None and skip issue update in dry-run mode."""
        existing_issue = MagicMock()
        existing_issue.title = "PR Conflict Report"
        existing_issue.body = f"{ISSUE_TAG}\nold content"

        repo = _make_mock_repo(existing_issues=[existing_issue])
        conflict = _make_conflict(_make_pr(1, "A", "alice"), _make_pr(2, "B", "bob"))

        result = create_or_update_issue(repo, [conflict], dry_run=True)

        assert result is None
        existing_issue.edit.assert_not_called()
        repo.create_issue.assert_not_called()

    def test_custom_report_title(self):
        """Use a custom title when report_title is provided."""
        repo = _make_mock_repo()
        conflict = _make_conflict(_make_pr(1, "A", "alice"), _make_pr(2, "B", "bob"))

        create_or_update_issue(repo, [conflict], report_title="Custom Conflict Report")

        _, kwargs = repo.create_issue.call_args
        assert kwargs["title"] == "Custom Conflict Report"

    def test_issue_body_contains_conflict_details(self):
        """Include file names, line ranges, and author mentions in the body."""
        files = [
            _make_file_overlap("src/app.py", [(1, 5)]),
            _make_file_overlap("README.md", [(10, 20)]),
        ]
        conflict = _make_conflict(
            _make_pr(7, "Big change", "eve"),
            _make_pr(8, "Another change", "frank"),
            files=files,
        )

        repo = _make_mock_repo()
        create_or_update_issue(repo, [conflict])

        body = repo.create_issue.call_args[1]["body"]
        assert "`src/app.py`" in body
        assert "`README.md`" in body
        assert "L1-L5" in body
        assert "L10-L20" in body
        assert "@eve" in body
        assert "@frank" in body
