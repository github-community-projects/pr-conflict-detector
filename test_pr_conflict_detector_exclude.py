"""Tests for EXCLUDE_AUTHORS functionality in the PR conflict detector."""

import unittest
from unittest.mock import MagicMock, patch

from pr_conflict_detector import main
from test_helpers import (
    _make_env_vars,
    _make_pr,
    _make_repo,
    _mock_dedup_passthrough,
    _mock_fetch_with_filter,
)


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestExcludeAuthors(unittest.TestCase):
    """Test that exclude_authors removes specific users from conflict detection."""

    def _setup_org(self, mock_auth, repo):
        """Wire up a mock GitHub org that returns `repo`."""
        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_exclude_removes_team_member(
        self, mock_get_team, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """EXCLUDE_AUTHORS removes users resolved from FILTER_TEAMS."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(
            filter_teams=["test-org/my-team"],
            exclude_authors=["bob"],
        )
        self._setup_org(mock_auth, repo)
        mock_get_team.return_value = ["alice", "bob", "charlie"]
        pr_a, pr_b, pr_c = (
            _make_pr(1, author="alice"),
            _make_pr(2, author="bob"),
            _make_pr(3, author="charlie"),
        )
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_a, pr_b, pr_c])
        mock_detect.return_value = []
        main()
        detected = mock_detect.call_args[0][0]
        self.assertEqual(len(detected), 2)
        self.assertNotIn(pr_b, detected)

    def test_exclude_removes_filter_author(
        self, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """EXCLUDE_AUTHORS removes users listed in FILTER_AUTHORS."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(
            filter_authors=["alice", "bob", "charlie"],
            exclude_authors=["bob"],
        )
        self._setup_org(mock_auth, repo)
        pr_a, pr_b, pr_c = (
            _make_pr(1, author="alice"),
            _make_pr(2, author="bob"),
            _make_pr(3, author="charlie"),
        )
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_a, pr_b, pr_c])
        mock_detect.return_value = []
        main()
        detected = mock_detect.call_args[0][0]
        self.assertEqual(len(detected), 2)
        self.assertNotIn(pr_b, detected)

    def test_exclude_no_match_prints_message(
        self, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """Message logged when EXCLUDE_AUTHORS doesn't match any included user."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(
            filter_authors=["alice", "bob"],
            exclude_authors=["nobody"],
        )
        self._setup_org(mock_auth, repo)
        pr_a, pr_b = _make_pr(1, author="alice"), _make_pr(2, author="bob")
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_a, pr_b])
        mock_detect.return_value = []
        with patch("builtins.print") as mock_print:
            main()
        no_match = [
            c
            for c in mock_print.call_args_list
            if "no matching authors found" in str(c)
        ]
        self.assertEqual(len(no_match), 1)
        self.assertEqual(len(mock_detect.call_args[0][0]), 2)

    def test_exclude_all_authors_yields_zero_prs(
        self, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """Excluding all filtered authors should scan zero PRs, not all."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(
            filter_authors=["alice"], exclude_authors=["alice"]
        )
        self._setup_org(mock_auth, repo)
        mock_fetch.side_effect = _mock_fetch_with_filter(
            [_make_pr(1, author="alice"), _make_pr(2, author="bob")]
        )
        mock_detect.return_value = []
        main()
        mock_detect.assert_not_called()

    def test_exclude_without_filters_warns(
        self, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """EXCLUDE_AUTHORS without FILTER_AUTHORS/FILTER_TEAMS logs a warning."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(exclude_authors=["alice"])
        self._setup_org(mock_auth, repo)
        mock_fetch.side_effect = _mock_fetch_with_filter(
            [_make_pr(1, author="alice"), _make_pr(2, author="bob")]
        )
        mock_detect.return_value = []
        with patch("builtins.print") as mock_print:
            main()
        warns = [c for c in mock_print.call_args_list if "no effect" in str(c)]
        self.assertEqual(len(warns), 1)
        self.assertEqual(len(mock_detect.call_args[0][0]), 2)

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_empty_team_resolution_scans_all_prs(
        self, mock_get_team, mock_get_env, mock_auth, mock_fetch, mock_detect, *_
    ):
        """When FILTER_TEAMS resolves to zero members, all PRs are scanned."""
        repo = _make_repo("test-org/repo-a")
        mock_get_env.return_value = _make_env_vars(filter_teams=["test-org/empty-team"])
        self._setup_org(mock_auth, repo)
        mock_get_team.return_value = []

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_alice, pr_bob])
        mock_detect.return_value = []

        with patch("builtins.print") as mock_print:
            main()

        # filter_authors should be None (scan all), not empty set
        mock_fetch.assert_called_once()
        _, kwargs = mock_fetch.call_args
        self.assertIsNone(kwargs.get("filter_authors"))

        # Warning should have fired
        warns = [c for c in mock_print.call_args_list if "No valid teams" in str(c)]
        self.assertEqual(len(warns), 1)

        # All PRs should be scanned
        mock_detect.assert_called_once()
        self.assertEqual(len(mock_detect.call_args[0][0]), 2)
