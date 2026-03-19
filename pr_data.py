"""Module for fetching and structuring pull request data from GitHub repositories."""

import re
from dataclasses import dataclass, field


@dataclass
class ChangedFile:
    """A file changed in a PR with line range information."""

    filename: str
    additions: int
    deletions: int
    changes: int
    patch_lines: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class PullRequestData:  # pylint: disable=too-many-instance-attributes
    """Data about an open pull request."""

    number: int
    title: str
    author: str
    html_url: str
    is_draft: bool
    base_branch: str
    head_branch: str
    changed_files: list[ChangedFile] = field(default_factory=list)


def parse_patch_line_ranges(patch: str | None) -> list[tuple[int, int]]:
    """
    Parse a unified diff patch string to extract modified line ranges.

    Looks for @@ -a,b +c,d @@ hunk headers and extracts the new file
    line ranges (the +c,d part) as (start, end) tuples.

    Args:
        patch: A unified diff patch string, or None for binary files.

    Returns:
        A list of (start_line, end_line) tuples for each hunk.
    """
    if not patch:
        return []

    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", patch):
        start = int(match.group(1))
        length = int(match.group(2)) if match.group(2) is not None else 1
        if length == 0:
            continue
        end = start + length - 1
        ranges.append((start, end))

    return ranges


def get_open_prs(repo: object, include_drafts: bool = True) -> list[PullRequestData]:
    """
    Fetch all open PRs from a github3-py repository object.

    Args:
        repo: A github3-py repository object.
        include_drafts: If False, filter out draft PRs.

    Returns:
        A list of PullRequestData objects (without changed files populated).
    """
    prs: list[PullRequestData] = []
    for pr in repo.pull_requests(state="open"):  # type: ignore[attr-defined]
        is_draft = getattr(pr, "draft", False) or False
        if not include_drafts and is_draft:
            continue
        author = pr.user.login if pr.user else "unknown"
        prs.append(
            PullRequestData(
                number=pr.number,
                title=pr.title,
                author=author,
                html_url=pr.html_url,
                is_draft=is_draft,
                base_branch=pr.base.ref if pr.base else "",
                head_branch=pr.head.ref if pr.head else "",
            )
        )
    return prs


def get_pr_changed_files(  # pylint: disable=unused-argument
    pull_request: object,
    github_connection: object,
    owner: str,
    repo_name: str,
) -> list[ChangedFile]:
    """
    Fetch the list of changed files for a given pull request.

    Uses the github3-py pull request's files() method, then parses
    each file's patch to extract modified line ranges.

    Args:
        pull_request: A github3-py ShortPullRequest or PullRequest object.
        github_connection: The github3-py GitHub connection (unused but kept
            for API consistency with other OSPO actions).
        owner: The repository owner.
        repo_name: The repository name.

    Returns:
        A list of ChangedFile objects.
    """
    changed_files: list[ChangedFile] = []
    for f in pull_request.files():  # type: ignore[attr-defined]
        patch = getattr(f, "patch", None)
        changed_files.append(
            ChangedFile(
                filename=f.filename,
                additions=f.additions,
                deletions=f.deletions,
                changes=f.changes,
                patch_lines=parse_patch_line_ranges(patch),
            )
        )
    return changed_files


def fetch_all_pr_data(
    repo: object,
    include_drafts: bool,
    github_connection: object,
    owner: str,
    repo_name: str,
    filter_authors: set[str] | None = None,
) -> list[PullRequestData]:
    """
    Fetch all open PRs and their changed files from a repository.

    Args:
        repo: A github3-py repository object.
        include_drafts: If False, filter out draft PRs.
        github_connection: The github3-py GitHub connection.
        owner: The repository owner.
        repo_name: The repository name.
        filter_authors: If provided, only fetch file changes for PRs authored
            by users in this set. PRs from other authors are excluded from the
            returned list entirely. This avoids expensive per-PR API calls for
            PRs that would be filtered out later.

    Returns:
        A list of PullRequestData objects with changed files populated.
    """
    prs = get_open_prs(repo, include_drafts)

    if filter_authors:
        before_count = len(prs)
        prs = [pr for pr in prs if pr.author in filter_authors]
        print(
            f"  Filtered to {len(prs)} of {before_count} PRs "
            f"by author ({len(filter_authors)} authors configured)"
        )

    total = len(prs)
    if total == 0:
        return prs

    print(f"Fetching file changes for {total} open PRs in {owner}/{repo_name}...")

    for i, pr_data in enumerate(prs):
        if total >= 50 and (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{total} PRs processed")

        try:
            # Re-fetch the full PR object to call files()
            full_pr = repo.pull_request(pr_data.number)  # type: ignore[attr-defined]
            pr_data.changed_files = get_pr_changed_files(
                full_pr, github_connection, owner, repo_name
            )
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  Warning: Failed to fetch files for PR #{pr_data.number}: {exc}")
            continue

    print(f"  Done: {total} PRs processed for {owner}/{repo_name}")
    return prs
