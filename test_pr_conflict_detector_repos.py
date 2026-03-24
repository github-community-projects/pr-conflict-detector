"""Tests for repository source selection in the PR conflict detector."""

import unittest
from unittest.mock import MagicMock

from conftest import _make_env_vars
from pr_conflict_detector import get_repos_iterator


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
