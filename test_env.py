"""Test the get_env_vars function"""

import os
import unittest
from unittest.mock import patch

from env import EnvVars, get_env_vars, get_int_env_var


class TestEnv(unittest.TestCase):
    """Test the get_env_vars function"""

    def setUp(self):
        env_keys = [
            "DRY_RUN",
            "ENABLE_GITHUB_ACTIONS_STEP_SUMMARY",
            "EXEMPT_PRS",
            "EXEMPT_REPOS",
            "GH_APP_ID",
            "GH_APP_INSTALLATION_ID",
            "GH_APP_PRIVATE_KEY",
            "GH_ENTERPRISE_URL",
            "GH_TOKEN",
            "GITHUB_APP_ENTERPRISE_ONLY",
            "INCLUDE_DRAFTS",
            "ORGANIZATION",
            "OUTPUT_FILE",
            "REPORT_TITLE",
            "REPOSITORY",
            "SLACK_CHANNEL",
            "SLACK_WEBHOOK_URL",
            "VERIFY_CONFLICTS",
            "FILTER_AUTHORS",
            "FILTER_TEAMS",
        ]
        for key in env_keys:
            if key in os.environ:
                del os.environ[key]

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "EXEMPT_REPOS": "repo4,repo5",
            "EXEMPT_PRS": "10,20,30",
            "INCLUDE_DRAFTS": "false",
            "VERIFY_CONFLICTS": "true",
            "DRY_RUN": "true",
            "REPORT_TITLE": "Custom Report",
            "OUTPUT_FILE": "custom_report.md",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
            "SLACK_CHANNEL": "#alerts",
            "ENABLE_GITHUB_ACTIONS_STEP_SUMMARY": "false",
        },
        clear=True,
    )
    def test_get_env_vars_with_org(self):
        """Test that all environment variables are set correctly using an organization"""
        expected_result = EnvVars(
            gh_app_id=None,
            gh_app_installation_id=None,
            gh_app_private_key_bytes=b"",
            gh_app_enterprise_only=False,
            token="my_token",
            ghe="",
            organization="my_organization",
            repository_list=[],
            include_drafts=False,
            verify_conflicts=True,
            exempt_repos=["repo4", "repo5"],
            exempt_prs=[10, 20, 30],
            dry_run=True,
            report_title="Custom Report",
            output_file="custom_report.md",
            slack_webhook_url="https://hooks.slack.com/test",
            slack_channel="#alerts",
            enable_github_actions_step_summary=False,
            enable_pr_comments=False,
            filter_authors=[],
            filter_teams=[],
        )
        result = get_env_vars(True)
        self.assertEqual(result, expected_result)

    @patch.dict(
        os.environ,
        {
            "REPOSITORY": "org/repo1,org2/repo2",
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_with_repos(self):
        """Test that all environment variables are set correctly using a list of repositories"""
        expected_result = EnvVars(
            gh_app_id=None,
            gh_app_installation_id=None,
            gh_app_private_key_bytes=b"",
            gh_app_enterprise_only=False,
            token="my_token",
            ghe="",
            organization=None,
            repository_list=["org/repo1", "org2/repo2"],
            include_drafts=True,
            verify_conflicts=False,
            exempt_repos=[],
            exempt_prs=[],
            dry_run=False,
            report_title="PR Conflict Report",
            output_file="pr_conflict_report.md",
            slack_webhook_url="",
            slack_channel="",
            enable_github_actions_step_summary=True,
            filter_authors=[],
            filter_teams=[],
            enable_pr_comments=False,
        )
        result = get_env_vars(True)
        self.assertEqual(result, expected_result)

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_optional_values(self):
        """Test that optional values are set to their default values if not provided"""
        expected_result = EnvVars(
            gh_app_id=None,
            gh_app_installation_id=None,
            gh_app_private_key_bytes=b"",
            gh_app_enterprise_only=False,
            token="my_token",
            ghe="",
            organization="my_organization",
            repository_list=[],
            include_drafts=True,
            verify_conflicts=False,
            exempt_repos=[],
            exempt_prs=[],
            dry_run=False,
            report_title="PR Conflict Report",
            output_file="pr_conflict_report.md",
            slack_webhook_url="",
            slack_channel="",
            enable_github_actions_step_summary=True,
            filter_authors=[],
            filter_teams=[],
            enable_pr_comments=False,
        )
        result = get_env_vars(True)
        self.assertEqual(result, expected_result)

    @patch.dict(
        os.environ,
        {
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_missing_org_and_repo(self):
        """Test that an error is raised if neither ORGANIZATION nor REPOSITORY is set"""
        with self.assertRaises(ValueError) as cm:
            get_env_vars(True)
        self.assertEqual(
            str(cm.exception),
            "ORGANIZATION and REPOSITORY environment variables were not set. "
            "Please set one",
        )

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
        },
        clear=True,
    )
    def test_get_env_vars_missing_token(self):
        """Test that an error is raised if GH_TOKEN is not set and no app credentials"""
        with self.assertRaises(ValueError) as cm:
            get_env_vars(True)
        self.assertEqual(
            str(cm.exception),
            "GH_TOKEN environment variable not set",
        )

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_APP_ID": "12345",
            "GH_APP_PRIVATE_KEY": "my_private_key",
            "GH_APP_INSTALLATION_ID": "67890",
        },
        clear=True,
    )
    def test_get_env_vars_with_gh_app(self):
        """Test that GitHub App credentials are parsed correctly"""
        result = get_env_vars(True)
        self.assertEqual(result.gh_app_id, 12345)
        self.assertEqual(result.gh_app_installation_id, 67890)
        self.assertEqual(result.gh_app_private_key_bytes, b"my_private_key")
        self.assertEqual(result.token, "")

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_APP_ID": "12345",
        },
        clear=True,
    )
    def test_get_env_vars_gh_app_missing_installation_id(self):
        """Test error when GH_APP_ID is set but installation ID or private key is missing"""
        with self.assertRaises(ValueError) as cm:
            get_env_vars(True)
        self.assertEqual(
            str(cm.exception),
            "GH_APP_ID set and GH_APP_INSTALLATION_ID or GH_APP_PRIVATE_KEY "
            "variable not set",
        )

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "GH_ENTERPRISE_URL": "  https://ghe.example.com  ",
        },
        clear=True,
    )
    def test_get_env_vars_ghe_url_stripped(self):
        """Test that GH_ENTERPRISE_URL is stripped of whitespace"""
        result = get_env_vars(True)
        self.assertEqual(result.ghe, "https://ghe.example.com")

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "GITHUB_APP_ENTERPRISE_ONLY": "true",
        },
        clear=True,
    )
    def test_get_env_vars_enterprise_only(self):
        """Test that GITHUB_APP_ENTERPRISE_ONLY is parsed correctly"""
        result = get_env_vars(True)
        self.assertTrue(result.gh_app_enterprise_only)

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "EXEMPT_PRS": "1,abc,3",
        },
        clear=True,
    )
    def test_get_env_vars_exempt_prs_invalid(self):
        """Test that an error is raised if EXEMPT_PRS contains non-integer values"""
        with self.assertRaises(ValueError) as cm:
            get_env_vars(True)
        self.assertIn("non-integer value", str(cm.exception))

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "EXEMPT_REPOS": " repo1 , repo2 , repo3 ",
        },
        clear=True,
    )
    def test_get_env_vars_exempt_repos_whitespace(self):
        """Test that EXEMPT_REPOS handles whitespace correctly"""
        result = get_env_vars(True)
        self.assertEqual(result.exempt_repos, ["repo1", "repo2", "repo3"])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "EXEMPT_PRS": " 10 , 20 , 30 ",
        },
        clear=True,
    )
    def test_get_env_vars_exempt_prs_whitespace(self):
        """Test that EXEMPT_PRS handles whitespace correctly"""
        result = get_env_vars(True)
        self.assertEqual(result.exempt_prs, [10, 20, 30])

    @patch.dict(
        os.environ,
        {
            "REPOSITORY": " org/repo1 , org/repo2 ",
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_repository_whitespace(self):
        """Test that REPOSITORY handles whitespace correctly"""
        result = get_env_vars(True)
        self.assertEqual(result.repository_list, ["org/repo1", "org/repo2"])

    def test_get_int_env_var_invalid_value(self):
        """Test get_int_env_var with a non-integer value."""
        with patch.dict(os.environ, {"TEST_VAR": "not_a_number"}):
            result = get_int_env_var("TEST_VAR")
            self.assertIsNone(result)

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_AUTHORS": "alice, @bob , charlie",
        },
        clear=True,
    )
    def test_get_env_vars_filter_authors(self):
        """Test that FILTER_AUTHORS parses correctly with @ prefix stripping"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_authors, ["alice", "bob", "charlie"])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_AUTHORS": "",
        },
        clear=True,
    )
    def test_get_env_vars_filter_authors_empty(self):
        """Test that empty FILTER_AUTHORS results in empty list"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_authors, [])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_filter_authors_not_set(self):
        """Test that unset FILTER_AUTHORS defaults to empty list"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_authors, [])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_TEAMS": "my-org/team-a, my-org/team-b",
        },
        clear=True,
    )
    def test_get_env_vars_filter_teams(self):
        """Test that FILTER_TEAMS parses correctly with whitespace handling"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_teams, ["my-org/team-a", "my-org/team-b"])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_TEAMS": "",
        },
        clear=True,
    )
    def test_get_env_vars_filter_teams_empty(self):
        """Test that empty FILTER_TEAMS results in empty list"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_teams, [])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
        },
        clear=True,
    )
    def test_get_env_vars_filter_teams_not_set(self):
        """Test that unset FILTER_TEAMS defaults to empty list"""
        result = get_env_vars(True)
        self.assertEqual(result.filter_teams, [])

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_TEAMS": "invalid-no-slash",
        },
        clear=True,
    )
    def test_get_env_vars_filter_teams_invalid_format(self):
        """Test that malformed FILTER_TEAMS entries raise ValueError"""
        with self.assertRaises(ValueError) as ctx:
            get_env_vars(True)
        self.assertIn("invalid-no-slash", str(ctx.exception))
        self.assertIn("org/team-slug", str(ctx.exception))

    @patch.dict(
        os.environ,
        {
            "ORGANIZATION": "my_organization",
            "GH_TOKEN": "my_token",
            "FILTER_TEAMS": "valid-org/team-a, /missing-org",
        },
        clear=True,
    )
    def test_get_env_vars_filter_teams_empty_org_raises(self):
        """Test that team entries with empty org part raise ValueError"""
        with self.assertRaises(ValueError):
            get_env_vars(True)


if __name__ == "__main__":
    unittest.main()
