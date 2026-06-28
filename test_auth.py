"""Test cases for the auth module."""

import unittest
from unittest.mock import MagicMock, patch

import auth


class TestAuth(unittest.TestCase):
    """
    Test case for the auth module.
    """

    @patch("auth.Github")
    def test_auth_to_github_with_token(self, mock_github_cls):
        """
        Test the auth_to_github function when the token is provided.
        """
        mock_github_cls.return_value = MagicMock()

        result = auth.auth_to_github("token", "", "", b"", "", False)

        self.assertEqual(result, mock_github_cls.return_value)
        mock_github_cls.assert_called_once()

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

    @patch("auth.Github")
    def test_auth_to_github_with_ghe(self, mock_github_cls):
        """
        Test the auth_to_github function when the GitHub Enterprise URL is provided.
        """
        mock_github_cls.return_value = MagicMock()
        result = auth.auth_to_github(
            "token", "", "", b"", "https://github.example.com", False
        )

        self.assertEqual(result, mock_github_cls.return_value)
        call_kwargs = mock_github_cls.call_args[1]
        self.assertEqual(call_kwargs["base_url"], "https://github.example.com/api/v3")

    @patch("auth.Github")
    @patch("auth.Auth.AppAuth")
    def test_auth_to_github_with_ghe_and_ghe_app(
        self, mock_app_auth_cls, mock_github_cls
    ):
        """
        Test the auth_to_github function when the GitHub Enterprise URL is provided
        and the app was created in GitHub Enterprise URL.
        """
        mock_app_auth = MagicMock()
        mock_app_auth_cls.return_value = mock_app_auth
        mock_installation_auth = MagicMock()
        mock_app_auth.get_installation_auth.return_value = mock_installation_auth
        mock_github_cls.return_value = MagicMock()

        result = auth.auth_to_github(
            "", 123, 456, b"123", "https://github.example.com", True
        )

        mock_app_auth_cls.assert_called_once_with(123, "123")
        mock_app_auth.get_installation_auth.assert_called_once_with(456)
        call_kwargs = mock_github_cls.call_args[1]
        self.assertEqual(call_kwargs["base_url"], "https://github.example.com/api/v3")
        self.assertEqual(call_kwargs["auth"], mock_installation_auth)
        self.assertEqual(result, mock_github_cls.return_value)

    @patch("auth.Github")
    @patch("auth.Auth.AppAuth")
    def test_auth_to_github_with_app(self, mock_app_auth_cls, mock_github_cls):
        """
        Test the auth_to_github function when app credentials are provided
        without GHE enterprise-only flag.
        """
        mock_app_auth = MagicMock()
        mock_app_auth_cls.return_value = mock_app_auth
        mock_installation_auth = MagicMock()
        mock_app_auth.get_installation_auth.return_value = mock_installation_auth
        mock_github_cls.return_value = MagicMock()

        result = auth.auth_to_github("", 123, 456, b"123", "", False)

        mock_app_auth_cls.assert_called_once_with(123, "123")
        mock_app_auth.get_installation_auth.assert_called_once_with(456)
        self.assertEqual(result, mock_github_cls.return_value)

    @patch("auth.GithubIntegration")
    @patch("auth.Auth.AppAuth")
    def test_get_github_app_installation_token(
        self, mock_app_auth_cls, mock_integration_cls
    ):
        """
        Test the get_github_app_installation_token function.
        """
        dummy_token = "dummytoken"
        mock_app_auth = MagicMock()
        mock_app_auth_cls.return_value = mock_app_auth

        mock_integration = MagicMock()
        mock_integration_cls.return_value = mock_integration
        mock_access_token = MagicMock()
        mock_access_token.token = dummy_token
        mock_integration.get_access_token.return_value = mock_access_token

        result = auth.get_github_app_installation_token(
            "", "12345", b"gh_private_token", "67890"
        )

        mock_app_auth_cls.assert_called_once_with(12345, "gh_private_token")
        mock_integration_cls.assert_called_once_with(auth=mock_app_auth)
        mock_integration.get_access_token.assert_called_once_with(67890)
        self.assertEqual(result, dummy_token)

    @patch("auth.GithubIntegration")
    @patch("auth.Auth.AppAuth")
    def test_get_github_app_installation_token_with_ghe(
        self, mock_app_auth_cls, mock_integration_cls
    ):
        """
        Test the get_github_app_installation_token function with a GHE URL.
        """
        dummy_token = "ghetoken"
        mock_app_auth = MagicMock()
        mock_app_auth_cls.return_value = mock_app_auth

        mock_integration = MagicMock()
        mock_integration_cls.return_value = mock_integration
        mock_access_token = MagicMock()
        mock_access_token.token = dummy_token
        mock_integration.get_access_token.return_value = mock_access_token

        result = auth.get_github_app_installation_token(
            "https://github.example.com", "12345", b"gh_private_token", "67890"
        )

        mock_app_auth_cls.assert_called_once_with(12345, "gh_private_token")
        mock_integration_cls.assert_called_once_with(
            auth=mock_app_auth, base_url="https://github.example.com/api/v3"
        )
        mock_integration.get_access_token.assert_called_once_with(67890)
        self.assertEqual(result, dummy_token)

    @patch("auth.Auth.AppAuth")
    def test_get_github_app_installation_token_request_failure(self, mock_app_auth_cls):
        """
        Test the get_github_app_installation_token function returns None when the request fails.
        """
        mock_app_auth_cls.side_effect = Exception("Request failed")

        result = auth.get_github_app_installation_token(
            ghe="https://api.github.com",
            gh_app_id="12345",
            gh_app_private_key_bytes=b"private_key",
            gh_app_installation_id="678910",
        )

        self.assertIsNone(result)


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
        mock_team.get_members.return_value = [member1, member2]

        mock_org.get_team_by_slug.return_value = mock_team
        mock_gh.get_organization.return_value = mock_org

        result = auth.get_team_members(mock_gh, "my-org", "my-team")

        self.assertEqual(result, ["alice", "bob"])
        mock_gh.get_organization.assert_called_once_with("my-org")
        mock_org.get_team_by_slug.assert_called_once_with("my-team")

    def test_get_team_members_team_not_found(self):
        """Test that a missing team returns an empty list."""
        mock_gh = MagicMock()
        mock_org = MagicMock()
        mock_org.get_team_by_slug.return_value = None
        mock_gh.get_organization.return_value = mock_org

        result = auth.get_team_members(mock_gh, "my-org", "nonexistent-team")

        self.assertEqual(result, [])

    def test_get_team_members_org_not_found(self):
        """Test that a missing organization returns an empty list."""
        mock_gh = MagicMock()
        mock_gh.get_organization.return_value = None

        result = auth.get_team_members(mock_gh, "nonexistent-org", "my-team")

        self.assertEqual(result, [])

    def test_get_team_members_api_error(self):
        """Test that API errors are caught and return an empty list."""
        mock_gh = MagicMock()
        mock_gh.get_organization.side_effect = Exception("API rate limit exceeded")

        result = auth.get_team_members(mock_gh, "my-org", "my-team")

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
