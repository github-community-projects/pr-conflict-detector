"""Tests for feature flags and behavioral controls in the PR conflict detector."""

import unittest
from unittest.mock import MagicMock, patch

from pr_conflict_detector import main
from test_helpers import _make_env_vars, _make_pr, _make_repo, _mock_dedup_passthrough


@patch("pr_conflict_detector.deduplication")
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestDryRunSkipsIssues(unittest.TestCase):
    """Test that dry_run mode skips issue creation and state saving."""

    def test_dry_run_skips_issues(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        mock_issue,
        _mock_slack,
        mock_dedup,
    ):
        """Verify that dry_run mode skips issue creation and state file saving."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(dry_run=True)
        mock_get_env.return_value = env_vars

        # Setup deduplication mock (with last_run to avoid suppression)
        mock_dedup.load_state.return_value = {
            "conflicts": [],
            "last_run": "2026-01-01T00:00:00+00:00",
        }
        mock_dedup.prune_expired_conflicts.return_value = {
            "conflicts": [],
            "last_run": "2026-01-01T00:00:00+00:00",
        }
        dedup_result = MagicMock()
        dedup_result.new_conflicts = [MagicMock()]
        dedup_result.changed_conflicts = []
        dedup_result.unchanged_conflicts = []
        dedup_result.resolved_fingerprints = []
        mock_dedup.compare_conflicts.return_value = dedup_result
        mock_dedup.update_state_with_current.return_value = {"conflicts": []}

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_fetch.return_value = [_make_pr(1), _make_pr(2)]
        mock_detect.return_value = [MagicMock()]

        main()

        mock_detect.assert_called_once()
        # Issue creation is skipped in dry_run mode
        mock_issue.assert_not_called()
        # State file saving is skipped in dry_run mode
        mock_dedup.save_state.assert_not_called()


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestEnableReportIssues(unittest.TestCase):
    """Test the ENABLE_REPORT_ISSUES flag."""

    def test_issues_not_created_when_disabled(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        mock_md,
        mock_json,
        mock_issue,
        _mock_slack,
    ):
        """Verify issues are NOT created when ENABLE_REPORT_ISSUES is false."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(enable_report_issues=False)
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr1, pr2 = _make_pr(1), _make_pr(2)
        mock_fetch.return_value = [pr1, pr2]
        conflict = MagicMock()
        mock_detect.return_value = [conflict]

        main()

        mock_md.assert_called_once()
        mock_json.assert_called_once()
        mock_issue.assert_not_called()

    def test_issues_created_when_enabled(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        mock_md,
        mock_json,
        mock_issue,
        _mock_slack,
    ):
        """Verify issues ARE created when ENABLE_REPORT_ISSUES is true (default)."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(enable_report_issues=True)
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr1, pr2 = _make_pr(1), _make_pr(2)
        mock_fetch.return_value = [pr1, pr2]
        conflict = MagicMock()
        mock_detect.return_value = [conflict]
        mock_issue.return_value = "https://github.com/test-org/repo-a/issues/99"

        main()

        mock_md.assert_called_once()
        mock_json.assert_called_once()
        mock_issue.assert_called_once()


@patch("pr_conflict_detector.deduplication")
@patch("pr_conflict_detector.post_pr_comments")
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestNotificationSuppression(unittest.TestCase):
    """Test that notifications are suppressed on state rebuild (first run / cache eviction)."""

    def _setup_mocks(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        mock_dedup,
        *,
        state,
        enable_pr_comments=True,
    ):
        """Common mock setup for suppression tests."""
        env_vars = _make_env_vars(enable_pr_comments=enable_pr_comments)
        mock_get_env.return_value = env_vars

        mock_dedup.load_state.return_value = state
        mock_dedup.prune_expired_conflicts.return_value = state

        # All conflicts are "new" (worst case for suppression testing)
        conflict = MagicMock()
        dedup_result = MagicMock()
        dedup_result.new_conflicts = [conflict]
        dedup_result.changed_conflicts = []
        dedup_result.unchanged_conflicts = []
        dedup_result.resolved_fingerprints = []
        mock_dedup.compare_conflicts.return_value = dedup_result
        mock_dedup.update_state_with_current.return_value = {
            "conflicts": [],
            "last_run": "2026-03-17T00:00:00+00:00",
        }

        gh = MagicMock()
        mock_auth.return_value = gh
        repo = _make_repo("test-org/repo-a")
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_fetch.return_value = [_make_pr(1), _make_pr(2)]
        mock_detect.return_value = [conflict]

        return conflict

    def test_suppressed_when_no_state_and_no_last_run(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        mock_slack,
        mock_pr_comments,
        mock_dedup,
    ):
        """First run or cache eviction: empty state + no last_run → no notifications."""
        self._setup_mocks(
            mock_get_env,
            mock_auth,
            mock_fetch,
            mock_detect,
            mock_dedup,
            state={"conflicts": []},  # No last_run key
        )

        main()

        mock_slack.assert_not_called()
        mock_pr_comments.assert_not_called()
        # State should still be saved
        mock_dedup.save_state.assert_called_once()

    def test_not_suppressed_when_state_has_last_run(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        mock_slack,
        mock_pr_comments,
        mock_dedup,
    ):
        """Normal run with last_run in state → notifications sent."""
        self._setup_mocks(
            mock_get_env,
            mock_auth,
            mock_fetch,
            mock_detect,
            mock_dedup,
            state={"conflicts": [], "last_run": "2026-03-15T10:00:00+00:00"},
        )

        main()

        mock_slack.assert_called_once()
        mock_pr_comments.assert_called_once()

    def test_not_suppressed_when_state_has_conflicts_no_last_run(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        mock_slack,
        mock_pr_comments,
        mock_dedup,
    ):
        """Old state file with conflicts but no last_run → not suppressed (backward compat)."""
        self._setup_mocks(
            mock_get_env,
            mock_auth,
            mock_fetch,
            mock_detect,
            mock_dedup,
            state={
                "conflicts": [
                    {
                        "repo": "org/repo",
                        "pr_a": 10,
                        "pr_b": 20,
                        "files": ["f.py"],
                        "first_seen": "2026-01-01T00:00:00+00:00",
                    }
                ]
            },  # Has conflicts but no last_run (pre-upgrade state file)
        )

        main()

        mock_slack.assert_called_once()
        mock_pr_comments.assert_called_once()

    def test_suppressed_still_saves_state(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
        _mock_pr_comments,
        mock_dedup,
    ):
        """Even when suppressed, state and reports are still generated."""
        self._setup_mocks(
            mock_get_env,
            mock_auth,
            mock_fetch,
            mock_detect,
            mock_dedup,
            state={"conflicts": []},
        )

        main()

        # State is saved (so next run has last_run)
        mock_dedup.save_state.assert_called_once()
        # Reports are still written
        _mock_md.assert_called_once()
        _mock_json.assert_called_once()

    def test_suppressed_does_not_skip_pr_comments_when_disabled(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        mock_slack,
        mock_pr_comments,
        mock_dedup,
    ):
        """PR comments disabled + suppressed → pr_comments not called regardless."""
        self._setup_mocks(
            mock_get_env,
            mock_auth,
            mock_fetch,
            mock_detect,
            mock_dedup,
            state={"conflicts": []},
            enable_pr_comments=False,
        )

        main()

        mock_slack.assert_not_called()
        mock_pr_comments.assert_not_called()


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestSameAuthorConflictsFiltered(unittest.TestCase):
    """Test that conflicts between PRs by the same author are filtered out."""

    def test_same_author_conflicts_filtered(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify conflicts where pr_a.author == pr_b.author are filtered out."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars()
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr1 = _make_pr(1, author="alice")
        pr2 = _make_pr(2, author="alice")
        pr3 = _make_pr(3, author="bob")
        mock_fetch.return_value = [pr1, pr2, pr3]

        # Create conflicts: alice vs alice (should be filtered), alice vs bob (should stay)
        same_author_conflict = MagicMock()
        same_author_conflict.pr_a.author = "alice"
        same_author_conflict.pr_b.author = "alice"

        diff_author_conflict = MagicMock()
        diff_author_conflict.pr_a.author = "alice"
        diff_author_conflict.pr_b.author = "bob"

        mock_detect.return_value = [same_author_conflict, diff_author_conflict]

        main()

        mock_detect.assert_called_once()
        # Markdown writer should only get the diff-author conflict
        mock_write_md = _mock_md
        self.assertTrue(mock_write_md.called)
        written_conflicts = mock_write_md.call_args[0][0]
        self.assertEqual(len(written_conflicts["test-org/repo-a"]), 1)
        self.assertEqual(written_conflicts["test-org/repo-a"][0], diff_author_conflict)
