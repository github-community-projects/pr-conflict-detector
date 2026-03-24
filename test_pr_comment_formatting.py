"""Tests for comment formatting, badges, and resolved section rendering."""

import unittest

import comment_rendering
from conflict_detector import FileOverlap, PRInfo
from pr_comment import ConflictEntry, ResolvedConflictEntry


class TestFormatRanges(unittest.TestCase):
    """Tests for the _format_ranges function."""

    def test_format_ranges_single(self):
        """Should format a single range correctly."""
        result = comment_rendering.format_ranges([(10, 25)])
        self.assertEqual(result, "L10-L25")

    def test_format_ranges_multiple(self):
        """Should format multiple ranges correctly."""
        result = comment_rendering.format_ranges([(10, 25), (42, 55), (100, 120)])
        self.assertEqual(result, "L10-L25, L42-L55, L100-L120")


class TestNewBadge(unittest.TestCase):
    """Tests for the 🆕 badge on newly detected conflicts."""

    def test_new_badge_shown_for_new_pr(self):
        """When new_pr_numbers includes a PR number, comment should contain 🆕."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=456,
                    url="https://github.com/org/repo/pull/456",
                    title="New PR",
                    author="bob",
                ),
                files=[FileOverlap("file.py", [(10, 20)], [(15, 25)], [(15, 20)])],
            )
        ]
        comment = comment_rendering.build_consolidated_comment(
            entries, new_pr_numbers={456}
        )
        self.assertIn("🆕", comment)

    def test_no_badge_when_not_new(self):
        """When new_pr_numbers doesn't include the PR, no 🆕 should appear."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=456,
                    url="https://github.com/org/repo/pull/456",
                    title="Old PR",
                    author="bob",
                ),
                files=[FileOverlap("file.py", [(10, 20)], [(15, 25)], [(15, 20)])],
            )
        ]
        comment = comment_rendering.build_consolidated_comment(
            entries, new_pr_numbers={999}
        )
        self.assertNotIn("🆕", comment)

    def test_no_badge_when_none(self):
        """When new_pr_numbers is None, no 🆕 should appear."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=456,
                    url="https://github.com/org/repo/pull/456",
                    title="PR",
                    author="bob",
                ),
                files=[FileOverlap("file.py", [(10, 20)], [(15, 25)], [(15, 20)])],
            )
        ]
        comment = comment_rendering.build_consolidated_comment(entries)
        self.assertNotIn("🆕", comment)


class TestResolvedSection(unittest.TestCase):
    """Tests for the resolved conflicts section in comments."""

    def test_resolved_section_appears(self):
        """When resolved_entries are provided, details section should appear."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=10,
                    url="https://github.com/org/repo/pull/10",
                    title="Active",
                    author="alice",
                ),
                files=[FileOverlap("file.py", [(10, 20)], [(15, 25)], [(15, 20)])],
            )
        ]
        resolved = [
            ResolvedConflictEntry(
                pr_number=20,
                pr_title="Old PR",
                pr_url="https://github.com/org/repo/pull/20",
                resolved_at="2026-03-15T10:00:00+00:00",
            ),
        ]
        comment = comment_rendering.build_consolidated_comment(
            entries, resolved_entries=resolved
        )

        self.assertIn("<details>", comment)
        self.assertIn("previously resolved", comment)
        self.assertIn("#20", comment)
        self.assertIn("Old PR", comment)

    def test_no_resolved_section_when_empty(self):
        """When resolved_entries is empty, no details section should appear."""
        entries = [
            ConflictEntry(
                other_pr=PRInfo(
                    number=10,
                    url="https://github.com/org/repo/pull/10",
                    title="Active",
                    author="alice",
                ),
                files=[FileOverlap("file.py", [(10, 20)], [(15, 25)], [(15, 20)])],
            )
        ]
        comment = comment_rendering.build_consolidated_comment(
            entries, resolved_entries=[]
        )
        self.assertNotIn("<details>", comment)


class TestAllResolvedComment(unittest.TestCase):
    """Tests for the all-resolved comment when no active conflicts remain."""

    def test_all_resolved_comment(self):
        """Empty conflict_entries with resolved_entries should show all-resolved header."""
        resolved = [
            ResolvedConflictEntry(
                pr_number=20,
                pr_title="Old PR",
                pr_url="https://github.com/org/repo/pull/20",
                resolved_at="2026-03-15T10:00:00+00:00",
            ),
        ]
        comment = comment_rendering.build_consolidated_comment(
            [], resolved_entries=resolved
        )

        self.assertIn("✅ All Merge Conflicts Resolved", comment)
        self.assertIn("🔄 **This comment updates automatically**", comment)
        self.assertIn("<details>", comment)
        self.assertIn("#20", comment)


class TestFormatResolvedDate(unittest.TestCase):
    """Tests for _format_resolved_date."""

    def test_valid_iso_timestamp(self):
        """Valid ISO timestamp should return formatted date."""
        result = comment_rendering.format_resolved_date("2026-03-15T10:00:00+00:00")
        self.assertEqual(result, "Mar 15, 2026")

    def test_invalid_timestamp(self):
        """Invalid timestamp should return 'Unknown'."""
        result = comment_rendering.format_resolved_date("not-a-date")
        self.assertEqual(result, "Unknown")

    def test_empty_timestamp(self):
        """Empty string should return 'Unknown'."""
        result = comment_rendering.format_resolved_date("")
        self.assertEqual(result, "Unknown")


if __name__ == "__main__":
    unittest.main()
