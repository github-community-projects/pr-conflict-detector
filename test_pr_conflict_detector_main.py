"""Tests for the main orchestration flow in the PR conflict detector."""

import unittest
from unittest.mock import MagicMock, patch

from conftest import _make_env_vars, _make_pr, _make_repo, _mock_dedup_passthrough
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
        mock_fetch.assert_called_once_with(
            repo, True, gh, "test-org", "repo-a", filter_authors=None
        )
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
