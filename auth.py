"""This is the module that contains functions related to authenticating to GitHub with a personal access token."""

from github import Auth, Github, GithubIntegration
from urllib3.util.retry import Retry

# Retry strategy: 5 retries with exponential backoff for transient errors
RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=1,  # 1s, 2s, 4s, 8s, 16s
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False,
)
REQUEST_TIMEOUT = 30  # seconds


def auth_to_github(
    token: str,
    gh_app_id: int | None,
    gh_app_installation_id: int | None,
    gh_app_private_key_bytes: bytes,
    ghe: str,
    gh_app_enterprise_only: bool,
) -> Github:
    """
    Connect to GitHub.com or GitHub Enterprise, depending on env variables.

    Args:
        token (str): the GitHub personal access token
        gh_app_id (int | None): the GitHub App ID
        gh_app_installation_id (int | None): the GitHub App Installation ID
        gh_app_private_key_bytes (bytes): the GitHub App Private Key
        ghe (str): the GitHub Enterprise URL
        gh_app_enterprise_only (bool): Set this to true if the GH APP is created on GHE and needs to communicate with GHE api only

    Returns:
        Github: the GitHub connection object
    """
    if gh_app_id and gh_app_private_key_bytes and gh_app_installation_id:
        app_auth = Auth.AppAuth(int(gh_app_id), gh_app_private_key_bytes.decode())
        installation_auth = app_auth.get_installation_auth(int(gh_app_installation_id))
        if ghe and gh_app_enterprise_only:
            github_connection = Github(
                base_url=f"{ghe}/api/v3",
                auth=installation_auth,
                retry=RETRY_STRATEGY,
                timeout=REQUEST_TIMEOUT,
            )
        else:
            github_connection = Github(
                auth=installation_auth,
                retry=RETRY_STRATEGY,
                timeout=REQUEST_TIMEOUT,
            )
    elif ghe and token:
        github_connection = Github(
            base_url=f"{ghe}/api/v3",
            auth=Auth.Token(token),
            retry=RETRY_STRATEGY,
            timeout=REQUEST_TIMEOUT,
        )
    elif token:
        github_connection = Github(
            auth=Auth.Token(token),
            retry=RETRY_STRATEGY,
            timeout=REQUEST_TIMEOUT,
        )
    else:
        raise ValueError(
            "GH_TOKEN or the set of [GH_APP_ID, GH_APP_INSTALLATION_ID, "
            "GH_APP_PRIVATE_KEY] environment variables are not set"
        )

    return github_connection


def get_github_app_installation_token(
    ghe: str,
    gh_app_id: str,
    gh_app_private_key_bytes: bytes,
    gh_app_installation_id: str,
) -> str | None:
    """
    Get a GitHub App Installation token.
    API: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation

    Args:
        ghe (str): the GitHub Enterprise endpoint
        gh_app_id (str): the GitHub App ID
        gh_app_private_key_bytes (bytes): the GitHub App Private Key
        gh_app_installation_id (str): the GitHub App Installation ID

    Returns:
        str: the GitHub App token
    """
    try:
        app_auth = Auth.AppAuth(int(gh_app_id), gh_app_private_key_bytes.decode())
        if ghe:
            gi = GithubIntegration(auth=app_auth, base_url=f"{ghe}/api/v3")
        else:
            gi = GithubIntegration(auth=app_auth)
        installation_token = gi.get_access_token(int(gh_app_installation_id))
        return installation_token.token
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Request failed: {e}")
        return None


def get_team_members(
    github_connection: Github,
    org: str,
    team_slug: str,
) -> list[str]:
    """
    Fetch the members of a GitHub team by slug.

    Args:
        github_connection: Authenticated GitHub connection.
        org: The organization that owns the team.
        team_slug: The team slug (e.g., "nux-reviewers").

    Returns:
        A list of GitHub usernames (logins) who are members of the team.
        Returns an empty list if the team is not found or an error occurs.
    """
    try:
        organization = github_connection.get_organization(org)
        if not organization:
            print(f"  ⚠️  Organization '{org}' not found, skipping team '{team_slug}'")
            return []

        team = organization.get_team_by_slug(team_slug)
        if not team:
            print(
                f"  ⚠️  Team '{team_slug}' not found in '{org}', "
                "skipping (check token permissions: read:org)"
            )
            return []

        members = [m.login for m in team.get_members()]
        print(f"  Resolved team {org}/{team_slug}: {len(members)} member(s)")
        return members
    except Exception as e:  # pylint: disable=broad-except
        print(
            f"  ⚠️  Error fetching team '{org}/{team_slug}': {e} "
            "(check token permissions: read:org)"
        )
        return []
