"""Tests for comment content building and conflict grouping."""

import unittest

import comment_rendering
from conflict_detector import FileOverlap, PRInfo
from conftest import _make_comment_conflict
from pr_comment import ConflictEntry, ResolvedConflictEntry


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

        comment = comment_rendering.build_consolidated_comment(entries)

        self.assertIn(comment_rendering.COMMENT_SIGNATURE, comment)
        self.assertIn("**1**", comment)
        self.assertIn("#456", comment)
        self.assertIn("Refactor auth", comment)
        self.assertIn("@bob", comment)
        self.assertIn("`src/auth.py`", comment)
        self.assertIn("L15-L20", comment)
        # Banner text
        self.assertIn("🔄 **This comment updates automatically**", comment)
        # 3-column table header
        self.assertIn("| | Conflicting PR | Conflicting Files (Lines) |", comment)

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

        comment = comment_rendering.build_consolidated_comment(entries)

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
        # Banner text
        self.assertIn("🔄 **This comment updates automatically**", comment)
        # 3-column table header
        self.assertIn("| | Conflicting PR | Conflicting Files (Lines) |", comment)


class TestGroupConflictsByPR(unittest.TestCase):
    """Tests for the _group_conflicts_by_pr function."""

    def test_single_conflict(self):
        """Should create entries for both PRs in a conflict."""
        conflict = _make_comment_conflict(pr_a_number=1, pr_b_number=2)
        grouped = comment_rendering.group_conflicts_by_pr([conflict])

        self.assertIn(1, grouped)
        self.assertIn(2, grouped)
        self.assertEqual(len(grouped[1]), 1)
        self.assertEqual(grouped[1][0].other_pr.number, 2)
        self.assertEqual(grouped[2][0].other_pr.number, 1)

    def test_multiple_conflicts_same_pr(self):
        """PR appearing in multiple conflicts should have all entries grouped."""
        conflict1 = _make_comment_conflict(pr_a_number=1, pr_b_number=2)
        conflict2 = _make_comment_conflict(pr_a_number=1, pr_b_number=3)
        grouped = comment_rendering.group_conflicts_by_pr([conflict1, conflict2])

        self.assertEqual(len(grouped[1]), 2)
        other_numbers = {e.other_pr.number for e in grouped[1]}
        self.assertEqual(other_numbers, {2, 3})


class TestGroupResolvedByPR(unittest.TestCase):
    """Tests for _group_resolved_by_pr."""

    def test_groups_by_pr_number(self):
        """Resolved entries should be grouped by both PR A and PR B."""
        entries = [
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
        grouped = comment_rendering.group_resolved_by_pr(entries, "org/repo")

        # PR 1 should see PR 2 as resolved
        self.assertIn(1, grouped)
        self.assertEqual(grouped[1][0].pr_number, 2)
        self.assertEqual(grouped[1][0].pr_title, "PR 2")
        # PR 2 should see PR 1 as resolved
        self.assertIn(2, grouped)
        self.assertEqual(grouped[2][0].pr_number, 1)
        self.assertEqual(grouped[2][0].pr_title, "PR 1")

    def test_filters_by_repo(self):
        """Should only include entries matching the given repo_name."""
        entries = [
            {
                "repo": "org/repo",
                "pr_a": 1,
                "pr_b": 2,
                "pr_a_title": "PR 1",
                "pr_b_title": "PR 2",
                "resolved_at": "2026-03-15T10:00:00+00:00",
            },
            {
                "repo": "other/repo",
                "pr_a": 3,
                "pr_b": 4,
                "pr_a_title": "PR 3",
                "pr_b_title": "PR 4",
                "resolved_at": "2026-03-15T10:00:00+00:00",
            },
        ]
        grouped = comment_rendering.group_resolved_by_pr(entries, "org/repo")

        self.assertIn(1, grouped)
        self.assertIn(2, grouped)
        self.assertNotIn(3, grouped)
        self.assertNotIn(4, grouped)

    def test_empty_entries(self):
        """Empty entries should produce empty grouping."""
        grouped = comment_rendering.group_resolved_by_pr([], "org/repo")
        self.assertEqual(grouped, {})


class TestBuildResolvedSection(unittest.TestCase):
    """Tests for _build_resolved_section."""

    def test_empty_resolved_returns_empty(self):
        """No resolved entries should produce empty string."""
        result = comment_rendering.build_resolved_section([])
        self.assertEqual(result, "")

    def test_collapsed_html_structure(self):
        """Should produce details/summary HTML structure."""
        entries = [
            ResolvedConflictEntry(
                pr_number=10,
                pr_title="PR 10",
                pr_url="http://pr10",
                resolved_at="2026-03-15T10:00:00+00:00",
            ),
        ]
        result = comment_rendering.build_resolved_section(entries)

        self.assertIn("<details>", result)
        self.assertIn("</details>", result)
        self.assertIn("<summary>", result)
        self.assertIn("1 previously resolved conflict", result)
        self.assertIn("~", result)  # strikethrough

    def test_plural_summary(self):
        """Should use plural form for multiple resolved entries."""
        entries = [
            ResolvedConflictEntry(
                pr_number=10,
                pr_title="PR 10",
                pr_url="",
                resolved_at="2026-03-15T10:00:00+00:00",
            ),
            ResolvedConflictEntry(
                pr_number=20,
                pr_title="PR 20",
                pr_url="",
                resolved_at="2026-03-14T10:00:00+00:00",
            ),
        ]
        result = comment_rendering.build_resolved_section(entries)
        self.assertIn("2 previously resolved conflicts", result)

    def test_date_formatting_in_section(self):
        """Resolved date should be formatted as readable date."""
        entries = [
            ResolvedConflictEntry(
                pr_number=10,
                pr_title="PR 10",
                pr_url="http://pr10",
                resolved_at="2026-03-15T10:00:00+00:00",
            ),
        ]
        result = comment_rendering.build_resolved_section(entries)
        self.assertIn("Mar 15, 2026", result)

    def test_max_display_cap(self):
        """Should cap the number of resolved entries displayed."""
        entries = [
            ResolvedConflictEntry(
                pr_number=i,
                pr_title=f"PR {i}",
                pr_url=f"http://pr{i}",
                resolved_at=f"2026-03-{15 - (i % 15):02d}T10:00:00+00:00",
            )
            for i in range(15)
        ]
        result = comment_rendering.build_resolved_section(entries)
        # Should cap at MAX_RESOLVED_DISPLAY (10)
        self.assertIn(
            f"{comment_rendering.MAX_RESOLVED_DISPLAY} previously resolved conflicts",
            result,
        )


if __name__ == "__main__":
    unittest.main()
