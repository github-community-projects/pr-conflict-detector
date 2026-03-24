"""Tests for PR and repository filtering in the PR conflict detector."""

import unittest
from unittest.mock import MagicMock, patch

from conftest import (
    _make_env_vars,
    _make_pr,
    _make_repo,
    _mock_dedup_passthrough,
    _mock_fetch_with_filter,
)
from pr_conflict_detector import main


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestSkipsExemptRepos(unittest.TestCase):
    """Test that exempt repos are skipped."""

    def test_skips_exempt_repos(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        _mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify that repos in the exempt list are not processed."""
        exempt_repo = _make_repo("test-org/exempt-repo")
        normal_repo = _make_repo("test-org/normal-repo")
        env_vars = _make_env_vars(exempt_repos=["test-org/exempt-repo"])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [exempt_repo, normal_repo]
        gh.organization.return_value = org_mock

        mock_fetch.return_value = [_make_pr(1)]  # only 1 PR, won't detect

        main()

        # fetch_all_pr_data should only be called for the normal repo
        self.assertEqual(mock_fetch.call_count, 1)
        mock_fetch.assert_called_once_with(
            normal_repo, True, gh, "test-org", "normal-repo", filter_authors=None
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
class TestSkipsArchivedRepos(unittest.TestCase):
    """Test that archived repos are skipped."""

    def test_skips_archived_repos(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        _mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify that archived repos are not processed."""
        archived = _make_repo("test-org/old-repo", archived=True)
        active = _make_repo("test-org/active-repo")
        env_vars = _make_env_vars()
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [archived, active]
        gh.organization.return_value = org_mock

        mock_fetch.return_value = [_make_pr(1)]

        main()

        self.assertEqual(mock_fetch.call_count, 1)
        mock_fetch.assert_called_once_with(
            active, True, gh, "test-org", "active-repo", filter_authors=None
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
class TestSkipsReposWithFewerThan2PRs(unittest.TestCase):
    """Test that repos with fewer than 2 PRs are skipped."""

    def test_skips_repos_with_fewer_than_2_prs(
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
        """Verify that repos with fewer than 2 PRs skip conflict detection."""
        repo = _make_repo("test-org/lonely-repo")
        env_vars = _make_env_vars()
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_fetch.return_value = [_make_pr(1)]  # Only 1 PR

        main()

        mock_fetch.assert_called_once()
        mock_detect.assert_not_called()


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestExemptPRsFiltered(unittest.TestCase):
    """Test that exempt PRs are filtered out before conflict detection."""

    def test_exempt_prs_filtered(
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
        """Verify that exempt PRs are excluded before conflict detection."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(exempt_prs=[2])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr1, pr2, pr3 = _make_pr(1), _make_pr(2), _make_pr(3)
        mock_fetch.return_value = [pr1, pr2, pr3]
        mock_detect.return_value = []

        main()

        # PR #2 should be filtered out; detect_conflicts sees only pr1 and pr3
        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        self.assertEqual(len(detected_prs), 2)
        self.assertNotIn(pr2, detected_prs)
        self.assertIn(pr1, detected_prs)
        self.assertIn(pr3, detected_prs)


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestFilterAuthors(unittest.TestCase):
    """Test that filter_authors restricts which PRs are analyzed."""

    def test_filter_authors_keeps_matching_prs(
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
        """Verify that only PRs from matching authors are passed to detect_conflicts."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(filter_authors=["alice", "bob"])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        pr_charlie = _make_pr(3, author="charlie")
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_alice, pr_bob, pr_charlie])
        mock_detect.return_value = []

        main()

        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        self.assertEqual(len(detected_prs), 2)
        self.assertIn(pr_alice, detected_prs)
        self.assertIn(pr_bob, detected_prs)
        self.assertNotIn(pr_charlie, detected_prs)

    def test_filter_authors_no_matching_prs_skips_repo(
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
        """Verify that when no PRs match the filter, conflict detection is skipped."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(filter_authors=["alice"])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        pr_bob = _make_pr(1, author="bob")
        pr_charlie = _make_pr(2, author="charlie")
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_bob, pr_charlie])

        main()

        mock_detect.assert_not_called()


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestFilterTeams(unittest.TestCase):
    """Test that filter_teams resolves team members and filters PRs."""

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_filter_teams_resolves_members(
        self,
        mock_get_team,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify that team slugs are resolved to members and used to filter PRs."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(filter_teams=["test-org/my-team"])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_get_team.return_value = ["alice", "bob"]

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        pr_charlie = _make_pr(3, author="charlie")
        mock_fetch.side_effect = _mock_fetch_with_filter([pr_alice, pr_bob, pr_charlie])
        mock_detect.return_value = []

        main()

        mock_get_team.assert_called_once_with(gh, "test-org", "my-team")
        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        self.assertEqual(len(detected_prs), 2)
        self.assertIn(pr_alice, detected_prs)
        self.assertIn(pr_bob, detected_prs)
        self.assertNotIn(pr_charlie, detected_prs)

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_filter_teams_combined_with_filter_authors(
        self,
        mock_get_team,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify that FILTER_TEAMS and FILTER_AUTHORS are combined (union)."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(
            filter_authors=["charlie"],
            filter_teams=["test-org/my-team"],
        )
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_get_team.return_value = ["alice", "bob"]

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        pr_charlie = _make_pr(3, author="charlie")
        pr_dana = _make_pr(4, author="dana")
        mock_fetch.side_effect = _mock_fetch_with_filter(
            [pr_alice, pr_bob, pr_charlie, pr_dana]
        )
        mock_detect.return_value = []

        main()

        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        self.assertEqual(len(detected_prs), 3)
        self.assertIn(pr_alice, detected_prs)
        self.assertIn(pr_bob, detected_prs)
        self.assertIn(pr_charlie, detected_prs)
        self.assertNotIn(pr_dana, detected_prs)

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_filter_teams_empty_resolution_warns(
        self,
        mock_get_team,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify warning when FILTER_TEAMS resolves to no members."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(filter_teams=["test-org/empty-team"])
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        mock_get_team.return_value = []

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        mock_fetch.return_value = [pr_alice, pr_bob]
        mock_detect.return_value = []

        with patch("builtins.print") as mock_print:
            main()

        # Should warn that no filtering will be applied
        warning_calls = [
            str(c) for c in mock_print.call_args_list if "No valid teams" in str(c)
        ]
        self.assertEqual(len(warning_calls), 1)
        # All PRs should pass through (no filter applied)
        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        self.assertEqual(len(detected_prs), 2)

    @patch("pr_conflict_detector.auth.get_team_members")
    def test_filter_teams_overlapping_members_deduplicated(
        self,
        mock_get_team,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        _mock_issue,
        _mock_slack,
    ):
        """Verify that overlapping members across multiple teams are deduplicated."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(
            filter_teams=["test-org/team-a", "test-org/team-b"],
        )
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        org_mock = MagicMock()
        org_mock.repositories.return_value = [repo]
        gh.organization.return_value = org_mock

        # alice is in both teams
        mock_get_team.side_effect = [["alice", "bob"], ["alice", "charlie"]]

        pr_alice = _make_pr(1, author="alice")
        pr_bob = _make_pr(2, author="bob")
        pr_charlie = _make_pr(3, author="charlie")
        pr_dana = _make_pr(4, author="dana")
        mock_fetch.side_effect = _mock_fetch_with_filter(
            [pr_alice, pr_bob, pr_charlie, pr_dana]
        )
        mock_detect.return_value = []

        main()

        self.assertEqual(mock_get_team.call_count, 2)
        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        # alice, bob, charlie included; dana excluded
        self.assertEqual(len(detected_prs), 3)
        self.assertNotIn(pr_dana, detected_prs)
