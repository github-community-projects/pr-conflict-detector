"""
Sets up the environment variables for the action.
"""

import os
from dataclasses import dataclass
from os.path import dirname, join

from dotenv import load_dotenv


@dataclass
class EnvVars:  # pylint: disable=too-many-instance-attributes
    """Environment variables for the pr-conflict-detector action."""

    gh_app_id: int | None
    gh_app_installation_id: int | None
    gh_app_private_key_bytes: bytes
    gh_app_enterprise_only: bool
    token: str
    ghe: str
    organization: str | None
    repository_list: list[str]
    include_drafts: bool
    verify_conflicts: bool
    exempt_repos: list[str]
    exempt_prs: list[int]
    dry_run: bool
    report_title: str
    output_file: str
    slack_webhook_url: str
    slack_channel: str
    enable_github_actions_step_summary: bool
    filter_authors: list[str]
    filter_teams: list[str]
    enable_pr_comments: bool
    enable_report_issues: bool


def get_bool_env_var(env_var_name: str, default: bool = False) -> bool:
    """Get a boolean environment variable.

    Args:
        env_var_name: The name of the environment variable to retrieve.
        default: The default value to return if the environment variable is not set.

    Returns:
        The value of the environment variable as a boolean.
    """
    ev = os.environ.get(env_var_name, "")
    if ev == "" and default:
        return default
    return ev.strip().lower() == "true"


def get_int_env_var(env_var_name: str) -> int | None:
    """Get an integer environment variable.

    Args:
        env_var_name: The name of the environment variable to retrieve.

    Returns:
        The value of the environment variable as an integer or None.
    """
    env_var = os.environ.get(env_var_name)
    if env_var is None or not env_var.strip():
        return None
    try:
        return int(env_var)
    except ValueError:
        return None


def get_env_vars(test: bool = False) -> EnvVars:
    """Get the environment variables for use in the action.

    Args:
        test: If True, skip loading from .env file.

    Returns:
        EnvVars dataclass with all parsed environment variables.

    Raises:
        ValueError: If required environment variables are missing or invalid.
    """
    if not test:  # pragma: no cover
        dotenv_path = join(dirname(__file__), ".env")
        load_dotenv(dotenv_path)

    organization = os.getenv("ORGANIZATION")
    repositories_str = os.getenv("REPOSITORY")

    # Either organization or repository must be set
    if not organization and not repositories_str:
        raise ValueError(
            "ORGANIZATION and REPOSITORY environment variables were not set. "
            "Please set one"
        )

    # Parse repository list
    repository_list: list[str] = []
    if repositories_str:
        repository_list = [
            repo.strip() for repo in repositories_str.split(",") if repo.strip()
        ]

    # GitHub App authentication
    gh_app_id = get_int_env_var("GH_APP_ID")
    gh_app_private_key_bytes = os.environ.get("GH_APP_PRIVATE_KEY", "").encode("utf8")
    gh_app_installation_id = get_int_env_var("GH_APP_INSTALLATION_ID")
    gh_app_enterprise_only = get_bool_env_var("GITHUB_APP_ENTERPRISE_ONLY")

    if gh_app_id and (not gh_app_private_key_bytes or not gh_app_installation_id):
        raise ValueError(
            "GH_APP_ID set and GH_APP_INSTALLATION_ID or GH_APP_PRIVATE_KEY "
            "variable not set"
        )

    token = os.getenv("GH_TOKEN", "")
    if (
        not gh_app_id
        and not gh_app_private_key_bytes
        and not gh_app_installation_id
        and not token
    ):
        raise ValueError("GH_TOKEN environment variable not set")

    ghe = os.getenv("GH_ENTERPRISE_URL", default="").strip()

    # Parse exempt repos
    exempt_repos_str = os.getenv("EXEMPT_REPOS")
    exempt_repos: list[str] = []
    if exempt_repos_str:
        exempt_repos = [
            repo.strip() for repo in exempt_repos_str.split(",") if repo.strip()
        ]

    # Parse exempt PRs
    exempt_prs_str = os.getenv("EXEMPT_PRS")
    exempt_prs: list[int] = []
    if exempt_prs_str:
        for pr in exempt_prs_str.split(","):
            pr = pr.strip()
            if pr:
                try:
                    exempt_prs.append(int(pr))
                except ValueError as err:
                    raise ValueError(
                        f"EXEMPT_PRS environment variable contains non-integer value: {pr}"
                    ) from err

    include_drafts = get_bool_env_var("INCLUDE_DRAFTS", default=True)
    verify_conflicts = get_bool_env_var("VERIFY_CONFLICTS")
    dry_run = get_bool_env_var("DRY_RUN")
    report_title = os.getenv("REPORT_TITLE", "PR Conflict Report")
    output_file = os.getenv("OUTPUT_FILE", "pr_conflict_report.md")
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_channel = os.getenv("SLACK_CHANNEL", "")
    enable_github_actions_step_summary = get_bool_env_var(
        "ENABLE_GITHUB_ACTIONS_STEP_SUMMARY", default=True
    )

    # Parse filter authors
    filter_authors_str = os.getenv("FILTER_AUTHORS")
    filter_authors: list[str] = []
    if filter_authors_str:
        filter_authors = [
            author.strip().lstrip("@")
            for author in filter_authors_str.split(",")
            if author.strip()
        ]

    # Parse filter teams (org/team-slug format)
    filter_teams_str = os.getenv("FILTER_TEAMS")
    filter_teams: list[str] = []
    if filter_teams_str:
        for team in filter_teams_str.split(","):
            team = team.strip()
            if not team:
                continue
            parts = team.split("/", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(
                    f"FILTER_TEAMS entry '{team}' is invalid, "
                    "expected 'org/team-slug' format"
                )
            filter_teams.append(team)

    enable_pr_comments = get_bool_env_var("ENABLE_PR_COMMENTS")
    enable_report_issues = get_bool_env_var("ENABLE_REPORT_ISSUES", default=True)

    return EnvVars(
        gh_app_id=gh_app_id,
        gh_app_installation_id=gh_app_installation_id,
        gh_app_private_key_bytes=gh_app_private_key_bytes,
        gh_app_enterprise_only=gh_app_enterprise_only,
        token=token,
        ghe=ghe,
        organization=organization,
        repository_list=repository_list,
        include_drafts=include_drafts,
        verify_conflicts=verify_conflicts,
        exempt_repos=exempt_repos,
        exempt_prs=exempt_prs,
        dry_run=dry_run,
        report_title=report_title,
        output_file=output_file,
        slack_webhook_url=slack_webhook_url,
        slack_channel=slack_channel,
        enable_github_actions_step_summary=enable_github_actions_step_summary,
        filter_authors=filter_authors,
        filter_teams=filter_teams,
        enable_pr_comments=enable_pr_comments,
        enable_report_issues=enable_report_issues,
    )
