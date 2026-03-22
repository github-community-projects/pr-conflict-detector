"""Tests for the pr_comment module."""

# pylint: disable=protected-access

import unittest
from unittest.mock import MagicMock, patch

import pr_comment
from conflict_detector import ConflictResult, FileOverlap, PRInfo
from pr_comment import ConflictEntry, ResolvedConflictEntry


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
        # Banner text
        self.assertIn("🔄 **This comment updates automatically**", comment)
        # 3-column table header
        self.assertIn("| | Conflicting PR | Conflicting Files (Lines) |", comment)


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
        comment = pr_comment._build_consolidated_comment(entries, new_pr_numbers={456})
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
        comment = pr_comment._build_consolidated_comment(entries, new_pr_numbers={999})
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
        comment = pr_comment._build_consolidated_comment(entries)
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
        comment = pr_comment._build_consolidated_comment(
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
        comment = pr_comment._build_consolidated_comment(entries, resolved_entries=[])
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
        comment = pr_comment._build_consolidated_comment([], resolved_entries=resolved)

        self.assertIn("✅ All Merge Conflicts Resolved", comment)
        self.assertIn("🔄 **This comment updates automatically**", comment)
        self.assertIn("<details>", comment)
        self.assertIn("#20", comment)


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
        grouped = pr_comment._group_resolved_by_pr(entries, "org/repo")

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
        grouped = pr_comment._group_resolved_by_pr(entries, "org/repo")

        self.assertIn(1, grouped)
        self.assertIn(2, grouped)
        self.assertNotIn(3, grouped)
        self.assertNotIn(4, grouped)

    def test_empty_entries(self):
        """Empty entries should produce empty grouping."""
        grouped = pr_comment._group_resolved_by_pr([], "org/repo")
        self.assertEqual(grouped, {})


class TestBuildResolvedSection(unittest.TestCase):
    """Tests for _build_resolved_section."""

    def test_empty_resolved_returns_empty(self):
        """No resolved entries should produce empty string."""
        result = pr_comment._build_resolved_section([])
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
        result = pr_comment._build_resolved_section(entries)

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
        result = pr_comment._build_resolved_section(entries)
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
        result = pr_comment._build_resolved_section(entries)
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
        result = pr_comment._build_resolved_section(entries)
        # Should cap at MAX_RESOLVED_DISPLAY (10)
        self.assertIn(
            f"{pr_comment.MAX_RESOLVED_DISPLAY} previously resolved conflicts", result
        )


class TestFormatResolvedDate(unittest.TestCase):
    """Tests for _format_resolved_date."""

    def test_valid_iso_timestamp(self):
        """Valid ISO timestamp should return formatted date."""
        result = pr_comment._format_resolved_date("2026-03-15T10:00:00+00:00")
        self.assertEqual(result, "Mar 15, 2026")

    def test_invalid_timestamp(self):
        """Invalid timestamp should return 'Unknown'."""
        result = pr_comment._format_resolved_date("not-a-date")
        self.assertEqual(result, "Unknown")

    def test_empty_timestamp(self):
        """Empty string should return 'Unknown'."""
        result = pr_comment._format_resolved_date("")
        self.assertEqual(result, "Unknown")


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
