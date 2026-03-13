"""This is the module that contains functions related to authenticating to GitHub with a personal access token."""

import github3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Retry strategy: 5 retries with exponential backoff for transient errors
RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=1,  # 1s, 2s, 4s, 8s, 16s
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False,
)
REQUEST_TIMEOUT = 30  # seconds


def _configure_session(github_connection: github3.GitHub) -> None:
    """Mount retry adapter and set timeout on the github3 session."""
    session = getattr(github_connection, "session", None)
    if session is None:
        return
    adapter = HTTPAdapter(max_retries=RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.request = _timeout_wrapper(session.request, REQUEST_TIMEOUT)  # type: ignore[method-assign]


def _timeout_wrapper(original_request, default_timeout):
    """Wrap a session.request method to inject a default timeout."""

    def wrapper(*args, **kwargs):
        kwargs.setdefault("timeout", default_timeout)
        return original_request(*args, **kwargs)

    return wrapper


def auth_to_github(
    token: str,
    gh_app_id: int | None,
    gh_app_installation_id: int | None,
    gh_app_private_key_bytes: bytes,
    ghe: str,
    gh_app_enterprise_only: bool,
) -> github3.GitHub:
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
        github3.GitHub: the GitHub connection object
    """
    if gh_app_id and gh_app_private_key_bytes and gh_app_installation_id:
        if ghe and gh_app_enterprise_only:
            gh = github3.github.GitHubEnterprise(url=ghe)
        else:
            gh = github3.github.GitHub()
        gh.login_as_app_installation(
            gh_app_private_key_bytes, gh_app_id, gh_app_installation_id
        )
        github_connection = gh
    elif ghe and token:
        github_connection = github3.github.GitHubEnterprise(url=ghe, token=token)
    elif token:
        github_connection = github3.login(token=token)
    else:
        raise ValueError(
            "GH_TOKEN or the set of [GH_APP_ID, GH_APP_INSTALLATION_ID, GH_APP_PRIVATE_KEY] environment variables are not set"
        )

    if not github_connection:
        raise ValueError("Unable to authenticate to GitHub")
    _configure_session(github_connection)
    return github_connection  # type: ignore


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
    jwt_headers = github3.apps.create_jwt_headers(gh_app_private_key_bytes, gh_app_id)
    api_endpoint = f"{ghe}/api/v3" if ghe else "https://api.github.com"
    url = f"{api_endpoint}/app/installations/{gh_app_installation_id}/access_tokens"

    try:
        response = requests.post(url, headers=jwt_headers, json=None, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None
    return response.json().get("token")


def get_team_members(
    github_connection: github3.GitHub,
    org: str,
    team_slug: str,
) -> list[str]:
    """
    Fetch the members of a GitHub team by slug.

    Args:
        github_connection: Authenticated github3 connection.
        org: The organization that owns the team.
        team_slug: The team slug (e.g., "nux-reviewers").

    Returns:
        A list of GitHub usernames (logins) who are members of the team.
        Returns an empty list if the team is not found or an error occurs.
    """
    try:
        organization = github_connection.organization(org)
        if not organization:
            print(f"  ⚠️  Organization '{org}' not found, skipping team '{team_slug}'")
            return []

        team = organization.team_by_slug(team_slug)
        if not team:
            print(
                f"  ⚠️  Team '{team_slug}' not found in '{org}', "
                "skipping (check token permissions: read:org)"
            )
            return []

        members = [m.login for m in team.members()]
        print(f"  Resolved team {org}/{team_slug}: {len(members)} member(s)")
        return members
    except Exception as e:  # pylint: disable=broad-except
        print(
            f"  ⚠️  Error fetching team '{org}/{team_slug}': {e} "
            "(check token permissions: read:org)"
        )
        return []
