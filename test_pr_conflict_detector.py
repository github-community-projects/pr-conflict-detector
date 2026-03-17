"""Tests for the main PR conflict detector orchestrator."""

# pylint: disable=too-many-lines

import unittest
from unittest.mock import MagicMock, patch

from env import EnvVars
from pr_conflict_detector import get_repos_iterator, main
from pr_data import PullRequestData


# Mock deduplication module for all tests
@patch("pr_conflict_detector.deduplication")
class _BaseIntegrationTest:
    """Base class that mocks deduplication for integration tests."""

    def setup_dedup_mock(self, mock_dedup, conflicts):
        """Configure deduplication mock to pass through all conflicts as new."""
        mock_dedup.load_state.return_value = {
            "conflicts": [],
            "last_run": "2026-01-01T00:00:00+00:00",
        }
        mock_dedup.prune_expired_conflicts.return_value = {
            "conflicts": [],
            "last_run": "2026-01-01T00:00:00+00:00",
        }

        dedup_result = MagicMock()
        dedup_result.new_conflicts = conflicts
        dedup_result.changed_conflicts = []
        dedup_result.unchanged_conflicts = []
        dedup_result.resolved_fingerprints = []
        mock_dedup.compare_conflicts.return_value = dedup_result

        mock_dedup.update_state_with_current.return_value = {"conflicts": []}


def _make_env_vars(**overrides):
    """Build an EnvVars dataclass with sensible defaults, allowing overrides."""
    defaults = {
        "gh_app_id": None,
        "gh_app_installation_id": None,
        "gh_app_private_key_bytes": b"",
        "gh_app_enterprise_only": False,
        "token": "ghp_test",
        "ghe": "",
        "organization": "test-org",
        "repository_list": [],
        "include_drafts": True,
        "verify_conflicts": False,
        "exempt_repos": [],
        "exempt_prs": [],
        "dry_run": False,
        "report_title": "PR Conflict Report",
        "output_file": "pr_conflict_report.md",
        "slack_webhook_url": "",
        "slack_channel": "",
        "enable_github_actions_step_summary": False,
        "filter_authors": [],
        "filter_teams": [],
        "enable_pr_comments": False,
        "enable_report_issues": True,
    }
    defaults.update(overrides)
    return EnvVars(**defaults)


def _make_repo(full_name="test-org/repo-a", archived=False):
    """Create a mock repository object."""
    repo = MagicMock()
    repo.full_name = full_name
    repo.name = full_name.split("/")[-1]
    repo.archived = archived
    return repo


def _make_pr(number, title="PR title", author="dev"):
    """Create a minimal PullRequestData for testing."""
    return PullRequestData(
        number=number,
        title=title,
        author=author,
        html_url=f"https://github.com/test-org/repo-a/pull/{number}",
        is_draft=False,
        base_branch="main",
        head_branch=f"feature-{number}",
        changed_files=[],
    )


def _mock_dedup_passthrough():
    """Create a mock deduplication module that passes conflicts through.

    Note: load_state returns state WITH last_run to simulate a normal run
    (not a first run / cache eviction). Tests that need to verify suppression
    behavior should use their own dedup mock without last_run.
    """
    mock = MagicMock()
    mock.load_state.return_value = {
        "conflicts": [],
        "last_run": "2026-01-01T00:00:00+00:00",
    }
    mock.prune_expired_conflicts.return_value = {
        "conflicts": [],
        "last_run": "2026-01-01T00:00:00+00:00",
    }

    def compare_conflicts_side_effect(
        current_conflicts, state
    ):  # pylint: disable=unused-argument
        """Return all conflicts as new."""
        result = MagicMock()
        # Flatten dict of conflicts to a single list
        all_conf_list = []
        for conflicts in current_conflicts.values():
            all_conf_list.extend(conflicts)
        result.new_conflicts = all_conf_list
        result.changed_conflicts = []
        result.unchanged_conflicts = []
        result.resolved_fingerprints = []
        return result

    mock.compare_conflicts.side_effect = compare_conflicts_side_effect
    mock.update_state_with_current.return_value = {"conflicts": []}
    mock.save_state.return_value = None
    return mock


class TestGetReposIteratorOrg(unittest.TestCase):
    """Test get_repos_iterator when an organization is provided."""

    def test_get_repos_iterator_org(self):
        """Verify repos are fetched from the organization."""
        env_vars = _make_env_vars(organization="test-org", repository_list=[])
        gh = MagicMock()
        org_mock = MagicMock()
        org_mock.repositories.return_value = ["repo1", "repo2"]
        gh.organization.return_value = org_mock

        result = get_repos_iterator(gh, env_vars)

        gh.organization.assert_called_once_with("test-org")
        org_mock.repositories.assert_called_once()
        self.assertEqual(result, ["repo1", "repo2"])


class TestGetReposIteratorRepoList(unittest.TestCase):
    """Test get_repos_iterator when a repository list is provided."""

    def test_get_repos_iterator_repo_list(self):
        """Verify repos are fetched from an explicit repository list."""
        env_vars = _make_env_vars(
            organization=None,
            repository_list=["owner/repo-a", "owner/repo-b"],
        )
        gh = MagicMock()
        repo_a = MagicMock()
        repo_b = MagicMock()
        gh.repository.side_effect = [repo_a, repo_b]

        result = get_repos_iterator(gh, env_vars)

        self.assertEqual(gh.repository.call_count, 2)
        gh.repository.assert_any_call("owner", "repo-a")
        gh.repository.assert_any_call("owner", "repo-b")
        self.assertEqual(result, [repo_a, repo_b])


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestMainWithOrganization(unittest.TestCase):
    """Test the main() flow using an organization."""

    def test_main_with_organization(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        mock_md,
        mock_json,
        mock_issue,
        mock_slack,
    ):
        """Verify main() orchestrates all steps for an organization."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars()
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

        mock_get_env.assert_called_once()
        mock_auth.assert_called_once()
        mock_fetch.assert_called_once_with(repo, True, gh, "test-org", "repo-a")
        mock_detect.assert_called_once_with(
            [pr1, pr2],
            verify=False,
            github_connection=gh,
            owner="test-org",
            repo_name="repo-a",
        )
        mock_md.assert_called_once()
        mock_json.assert_called_once()
        mock_issue.assert_called_once()
        mock_slack.assert_called_once()


@patch("pr_conflict_detector.deduplication", new=_mock_dedup_passthrough())
@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestMainWithRepositoryList(unittest.TestCase):
    """Test the main() flow using a repository list."""

    def test_main_with_repository_list(
        self,
        mock_get_env,
        mock_auth,
        mock_fetch,
        mock_detect,
        _mock_md,
        _mock_json,
        mock_issue,
        _mock_slack,
    ):
        """Verify main() orchestrates all steps for a repository list."""
        env_vars = _make_env_vars(
            organization=None,
            repository_list=["owner/repo-x"],
        )
        mock_get_env.return_value = env_vars

        gh = MagicMock()
        mock_auth.return_value = gh
        repo = _make_repo("owner/repo-x")
        gh.repository.return_value = repo

        pr1, pr2 = _make_pr(1), _make_pr(2)
        mock_fetch.return_value = [pr1, pr2]
        mock_detect.return_value = []

        main()

        gh.repository.assert_called_once_with("owner", "repo-x")
        mock_fetch.assert_called_once()
        mock_detect.assert_called_once()
        # No conflicts → no issue created
        mock_issue.assert_not_called()


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
            normal_repo, True, gh, "test-org", "normal-repo"
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
        mock_fetch.assert_called_once_with(active, True, gh, "test-org", "active-repo")


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
        mock_fetch.return_value = [pr_alice, pr_bob, pr_charlie]
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
        mock_fetch.return_value = [pr_bob, pr_charlie]

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
        mock_fetch.return_value = [pr_alice, pr_bob, pr_charlie]
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
        mock_fetch.return_value = [pr_alice, pr_bob, pr_charlie, pr_dana]
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
        mock_fetch.return_value = [pr_alice, pr_bob, pr_charlie, pr_dana]
        mock_detect.return_value = []

        main()

        self.assertEqual(mock_get_team.call_count, 2)
        mock_detect.assert_called_once()
        detected_prs = mock_detect.call_args[0][0]
        # alice, bob, charlie included; dana excluded
        self.assertEqual(len(detected_prs), 3)
        self.assertNotIn(pr_dana, detected_prs)


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


if __name__ == "__main__":
    unittest.main()


# ──────────────────────────────────────────────────────────────────────────────
# Notification suppression tests (state rebuild detection)
# ──────────────────────────────────────────────────────────────────────────────


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
