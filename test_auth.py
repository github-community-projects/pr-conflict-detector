"""Test cases for the auth module."""

# pylint: disable=protected-access

import unittest
from unittest.mock import MagicMock, patch

import auth
import github3
import requests


class TestAuth(unittest.TestCase):
    """
    Test case for the auth module.
    """

    @patch("github3.login")
    def test_auth_to_github_with_token(self, mock_login):
        """
        Test the auth_to_github function when the token is provided.
        """
        mock_login.return_value = "Authenticated to GitHub.com"

        result = auth.auth_to_github("token", "", "", b"", "", False)

        self.assertEqual(result, "Authenticated to GitHub.com")

    def test_auth_to_github_without_token(self):
        """
        Test the auth_to_github function when the token is not provided.
        Expect a ValueError to be raised.
        """
        with self.assertRaises(ValueError) as context_manager:
            auth.auth_to_github("", "", "", b"", "", False)
        the_exception = context_manager.exception
        self.assertEqual(
            str(the_exception),
            "GH_TOKEN or the set of [GH_APP_ID, GH_APP_INSTALLATION_ID, GH_APP_PRIVATE_KEY] environment variables are not set",
        )

    @patch("github3.github.GitHubEnterprise")
    def test_auth_to_github_with_ghe(self, mock_ghe):
        """
        Test the auth_to_github function when the GitHub Enterprise URL is provided.
        """
        mock_ghe.return_value = "Authenticated to GitHub Enterprise"
        result = auth.auth_to_github(
            "token", "", "", b"", "https://github.example.com", False
        )

        self.assertEqual(result, "Authenticated to GitHub Enterprise")

    @patch("github3.github.GitHubEnterprise")
    def test_auth_to_github_with_ghe_and_ghe_app(self, mock_ghe):
        """
        Test the auth_to_github function when the GitHub Enterprise URL is provided and the app was created in GitHub Enterprise URL.
        """
        mock = mock_ghe.return_value
        mock.login_as_app_installation = MagicMock(return_value=True)
        result = auth.auth_to_github(
            "", 123, 456, b"123", "https://github.example.com", True
        )
        mock.login_as_app_installation.assert_called_once_with(b"123", "123", 456)
        self.assertEqual(result, mock)

    @patch("github3.github.GitHub")
    def test_auth_to_github_with_app(self, mock_gh):
        """
        Test the auth_to_github function when app credentials are provided
        """
        mock = mock_gh.return_value
        mock.login_as_app_installation = MagicMock(return_value=True)
        result = auth.auth_to_github(
            "", 123, 456, b"123", "https://github.example.com", False
        )
        mock.login_as_app_installation.assert_called_once_with(b"123", "123", 456)
        self.assertEqual(result, mock)

    @patch("github3.apps.create_jwt_headers", MagicMock(return_value="gh_token"))
    @patch("requests.post")
    def test_get_github_app_installation_token(self, mock_post):
        """
        Test the get_github_app_installation_token function.
        """
        dummy_token = "dummytoken"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"token": dummy_token}
        mock_post.return_value = mock_response

        result = auth.get_github_app_installation_token(
            b"ghe", "gh_private_token", "gh_app_id", "gh_installation_id"
        )

        self.assertEqual(result, dummy_token)

    @patch("github3.apps.create_jwt_headers", MagicMock(return_value="gh_token"))
    @patch("auth.requests.post")
    def test_get_github_app_installation_token_request_failure(self, mock_post):
        """
        Test the get_github_app_installation_token function returns None when the request fails.
        """
        mock_post.side_effect = requests.exceptions.RequestException("Request failed")

        result = auth.get_github_app_installation_token(
            ghe="https://api.github.com",
            gh_app_id=12345,
            gh_app_private_key_bytes=b"private_key",
            gh_app_installation_id=678910,
        )

        self.assertIsNone(result)

    @patch("github3.login")
    def test_auth_to_github_invalid_credentials(self, mock_login):
        """
        Test the auth_to_github function raises correct ValueError
        when credentials are present but incorrect.
        """
        mock_login.return_value = None
        with self.assertRaises(ValueError) as context_manager:
            auth.auth_to_github("not_a_valid_token", "", "", b"", "", False)

        the_exception = context_manager.exception
        self.assertEqual(
            str(the_exception),
            "Unable to authenticate to GitHub",
        )

    @patch("github3.login")
    def test_auth_configures_retry_session(self, mock_login):
        """Test that auth configures retry adapter and timeout on the session."""
        mock_gh = MagicMock()
        mock_session = MagicMock()
        mock_gh.session = mock_session
        mock_login.return_value = mock_gh

        result = auth.auth_to_github("token", "", "", b"", "", False)

        self.assertEqual(result, mock_gh)
        # Retry adapter should be mounted
        mock_session.mount.assert_any_call("https://", unittest.mock.ANY)
        mock_session.mount.assert_any_call("http://", unittest.mock.ANY)

    def test_timeout_wrapper_injects_default(self):
        """Test that the timeout wrapper injects a default timeout."""
        original = MagicMock(return_value="response")
        wrapped = auth._timeout_wrapper(
            original, 30
        )  # pylint: disable=protected-access

        wrapped("GET", "https://api.github.com")

        original.assert_called_once_with("GET", "https://api.github.com", timeout=30)

    def test_timeout_wrapper_respects_explicit_timeout(self):
        """Test that an explicit timeout is not overridden."""
        original = MagicMock(return_value="response")
        wrapped = auth._timeout_wrapper(
            original, 30
        )  # pylint: disable=protected-access

        wrapped("GET", "https://api.github.com", timeout=60)

        original.assert_called_once_with("GET", "https://api.github.com", timeout=60)


class TestGetTeamMembers(unittest.TestCase):
    """Test the get_team_members function."""

    def test_get_team_members_success(self):
        """Test successful team member resolution."""
        mock_gh = MagicMock()
        mock_org = MagicMock()
        mock_team = MagicMock()

        member1 = MagicMock()
        member1.login = "alice"
        member2 = MagicMock()
        member2.login = "bob"
        mock_team.members.return_value = [member1, member2]

        mock_org.team_by_name.return_value = mock_team
        mock_gh.organization.return_value = mock_org

        result = auth.get_team_members(mock_gh, "my-org", "my-team")

        self.assertEqual(result, ["alice", "bob"])
        mock_gh.organization.assert_called_once_with("my-org")
        mock_org.team_by_name.assert_called_once_with("my-team")

    def test_get_team_members_team_not_found(self):
        """Test that a missing team returns an empty list."""
        mock_gh = MagicMock()
        mock_org = MagicMock()
        mock_org.team_by_name.return_value = None
        mock_gh.organization.return_value = mock_org

        result = auth.get_team_members(mock_gh, "my-org", "nonexistent-team")

        self.assertEqual(result, [])

    def test_get_team_members_org_not_found(self):
        """Test that a missing organization returns an empty list."""
        mock_gh = MagicMock()
        mock_gh.organization.return_value = None

        result = auth.get_team_members(mock_gh, "nonexistent-org", "my-team")

        self.assertEqual(result, [])

    def test_get_team_members_api_error(self):
        """Test that API errors are caught and return an empty list."""
        mock_gh = MagicMock()
        mock_gh.organization.side_effect = Exception("API rate limit exceeded")

        result = auth.get_team_members(mock_gh, "my-org", "my-team")

        self.assertEqual(result, [])

    def test_team_by_name_exists_on_organization(self):
        """Verify that github3.py Organization actually has team_by_name.

        This guards against calling a method that doesn't exist on the real
        class, which MagicMock would silently allow. See PR #25 for context:
        the original code called team_by_slug which never existed in github3.py
        v4.0.1, and MagicMock-based tests couldn't catch it.
        """
        self.assertTrue(
            hasattr(github3.orgs.Organization, "team_by_name"),
            "github3.orgs.Organization is missing team_by_name - "
            "check github3.py version compatibility",
        )


if __name__ == "__main__":
    unittest.main()
