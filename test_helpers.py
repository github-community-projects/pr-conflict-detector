"""Shared test helpers for pytest."""

from unittest.mock import MagicMock, patch

from conflict_detector import ConflictResult, FileOverlap, PRInfo
from env import EnvVars
from pr_data import PullRequestData


def _make_comment_conflict(
    pr_a_number=1,
    pr_a_url="https://github.com/org/repo/pull/1",
    pr_a_title="Fix auth",
    pr_a_author="alice",
    pr_b_number=2,
    pr_b_url="https://github.com/org/repo/pull/2",
    pr_b_title="Add tests",
    pr_b_author="bob",
    filenames=None,
):
    """Helper to build a ConflictResult for PR comment tests."""
    files = [
        FileOverlap(
            filename=f,
            pr_a_lines=[(10, 20)],
            pr_b_lines=[(15, 25)],
            overlapping_ranges=[(15, 20)],
        )
        for f in (filenames or ["README.md"])
    ]
    return ConflictResult(
        pr_a=PRInfo(
            number=pr_a_number, url=pr_a_url, title=pr_a_title, author=pr_a_author
        ),
        pr_b=PRInfo(
            number=pr_b_number, url=pr_b_url, title=pr_b_title, author=pr_b_author
        ),
        conflicting_files=files,
    )


def _make_dedup_conflict(pr_a_num=1, pr_b_num=2, files=None):
    """Helper to create a ConflictResult for deduplication testing."""
    if files is None:
        files = ["README.md"]

    return ConflictResult(
        pr_a=PRInfo(pr_a_num, f"http://pr{pr_a_num}", f"PR {pr_a_num}", "alice"),
        pr_b=PRInfo(pr_b_num, f"http://pr{pr_b_num}", f"PR {pr_b_num}", "bob"),
        conflicting_files=[
            FileOverlap(f, [(10, 20)], [(15, 25)], [(15, 20)]) for f in files
        ],
    )


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


def _mock_fetch_with_filter(prs):
    """Create a side_effect for fetch_all_pr_data that applies filter_authors.

    This simulates the real fetch_all_pr_data behavior where filter_authors
    is applied before fetching file changes.
    """

    def side_effect(*_args, **kwargs):
        filter_authors = kwargs.get("filter_authors")
        if filter_authors:
            return [pr for pr in prs if pr.author in filter_authors]
        return list(prs)

    return side_effect


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
