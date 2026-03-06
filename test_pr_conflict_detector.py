"""Tests for the main PR conflict detector orchestrator."""

import unittest
from unittest.mock import MagicMock, patch

from env import EnvVars
from pr_conflict_detector import get_repos_iterator, main
from pr_data import PullRequestData


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


def _make_pr(number, title="PR title"):
    """Create a minimal PullRequestData for testing."""
    return PullRequestData(
        number=number,
        title=title,
        author="dev",
        html_url=f"https://github.com/test-org/repo-a/pull/{number}",
        is_draft=False,
        base_branch="main",
        head_branch=f"feature-{number}",
        changed_files=[],
    )


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


@patch("pr_conflict_detector.send_slack_notification")
@patch("pr_conflict_detector.create_or_update_issue")
@patch("pr_conflict_detector.write_to_json")
@patch("pr_conflict_detector.write_to_markdown")
@patch("pr_conflict_detector.detect_conflicts")
@patch("pr_conflict_detector.fetch_all_pr_data")
@patch("pr_conflict_detector.auth.auth_to_github")
@patch("pr_conflict_detector.env.get_env_vars")
class TestDryRunSkipsIssues(unittest.TestCase):
    """Test that dry_run mode skips issue creation."""

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
    ):
        """Verify that dry_run mode skips issue creation."""
        repo = _make_repo("test-org/repo-a")
        env_vars = _make_env_vars(dry_run=True)
        mock_get_env.return_value = env_vars

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


if __name__ == "__main__":
    unittest.main()
