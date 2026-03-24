"""Comment rendering and formatting for PR conflict notifications."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from conflict_detector import ConflictResult, FileOverlap, PRInfo

# Bot signature to identify our comments
COMMENT_SIGNATURE = "<!-- pr-conflict-detector-bot -->"

MAX_RESOLVED_DISPLAY = 10


@dataclass
class ConflictEntry:
    """A single conflict entry for a PR, pairing the other PR with overlapping files."""

    other_pr: PRInfo
    files: list[FileOverlap]


@dataclass
class ResolvedConflictEntry:
    """A resolved conflict for display in the comment's resolved section."""

    pr_number: int
    pr_title: str
    pr_url: str
    resolved_at: str


def group_conflicts_by_pr(
    conflicts: list[ConflictResult],
) -> dict[int, list[ConflictEntry]]:
    """Group conflicts so each PR number maps to its list of conflicting PRs.

    Each conflict pair contributes an entry to both PRs involved.

    Args:
        conflicts: List of ConflictResult objects.

    Returns:
        Dict mapping PR number to a list of ConflictEntry objects.
    """
    grouped: dict[int, list[ConflictEntry]] = defaultdict(list)
    for conflict in conflicts:
        grouped[conflict.pr_a.number].append(
            ConflictEntry(other_pr=conflict.pr_b, files=conflict.conflicting_files)
        )
        grouped[conflict.pr_b.number].append(
            ConflictEntry(other_pr=conflict.pr_a, files=conflict.conflicting_files)
        )
    return dict(grouped)


def group_resolved_by_pr(
    resolved_entries: list[dict], repo_name: str
) -> dict[int, list[ResolvedConflictEntry]]:
    """Group resolved conflict entries by PR number for a specific repo.

    Each resolved conflict pair contributes an entry to both PRs involved.

    Args:
        resolved_entries: List of resolved conflict dicts from state.
        repo_name: Repository full name to filter by.

    Returns:
        Dict mapping PR number to a list of ResolvedConflictEntry objects.
    """
    grouped: dict[int, list[ResolvedConflictEntry]] = defaultdict(list)
    for entry in resolved_entries:
        if entry.get("repo") != repo_name:
            continue

        # PR A sees PR B as resolved
        grouped[entry["pr_a"]].append(
            ResolvedConflictEntry(
                pr_number=entry["pr_b"],
                pr_title=entry.get("pr_b_title", "") or f"#{entry['pr_b']}",
                pr_url=entry.get("pr_b_url", ""),
                resolved_at=entry.get("resolved_at", ""),
            )
        )
        # PR B sees PR A as resolved
        grouped[entry["pr_b"]].append(
            ResolvedConflictEntry(
                pr_number=entry["pr_a"],
                pr_title=entry.get("pr_a_title", "") or f"#{entry['pr_a']}",
                pr_url=entry.get("pr_a_url", ""),
                resolved_at=entry.get("resolved_at", ""),
            )
        )
    return dict(grouped)


def build_consolidated_comment(
    conflict_entries: list[ConflictEntry],
    new_pr_numbers: set[int] | None = None,
    resolved_entries: list[ResolvedConflictEntry] | None = None,
) -> str:
    """Build a single consolidated comment listing all conflicts for a PR.

    Args:
        conflict_entries: List of active ConflictEntry objects.
        new_pr_numbers: PR numbers that are newly detected (for 🆕 badge).
        resolved_entries: List of resolved conflict entries for the details section.

    Returns:
        Formatted comment body with active conflicts table and resolved section.
    """
    resolved_section = build_resolved_section(resolved_entries or [])
    footer = (
        "\nThis is an automated notification from "
        "[pr-conflict-detector](https://github.com/github-community-projects/pr-conflict-detector)."
    )
    banner = (
        "\n*🔄 **This comment updates automatically** "
        "as conflicts are detected and resolved.*\n"
    )

    if not conflict_entries:
        return (
            f"{COMMENT_SIGNATURE}\n"
            f"## ✅ All Merge Conflicts Resolved\n"
            f"{banner}\n"
            f"All previously detected conflicts for this PR have been resolved. 🎉\n"
            f"{resolved_section}\n"
            f"{footer}"
        )

    count = len(conflict_entries)

    table_rows = []
    authors: list[str] = []
    for entry in conflict_entries:
        if entry.other_pr.author not in authors:
            authors.append(entry.other_pr.author)

        badge = (
            "🆕" if new_pr_numbers and entry.other_pr.number in new_pr_numbers else ""
        )
        file_details = ", ".join(
            f"`{fo.filename}` ({format_ranges(fo.overlapping_ranges)})"
            for fo in entry.files
        )
        table_rows.append(
            f"| {badge} | [#{entry.other_pr.number}]({entry.other_pr.url})"
            f" ({entry.other_pr.title}) | {file_details} |"
        )

    table = "\n".join(table_rows)
    author_mentions = ", ".join(f"@{a}" for a in authors)

    return (
        f"{COMMENT_SIGNATURE}\n"
        f"## ⚠️ Potential Merge Conflicts Detected\n"
        f"{banner}\n"
        f"This PR may conflict with **{count}** other PR(s):\n\n"
        f"| | Conflicting PR | Conflicting Files (Lines) |\n"
        f"|---|---|---|\n"
        f"{table}\n\n"
        f"**What to do:** Review the overlapping changes and coordinate "
        f"with {author_mentions} to resolve conflicts.\n"
        f"{resolved_section}\n"
        f"{footer}"
    )


def format_ranges(ranges: list[tuple[int, int]]) -> str:
    """Format line ranges for display.

    Args:
        ranges: List of (start, end) line number tuples

    Returns:
        Formatted string like "L10-L25, L42-L55"
    """
    return ", ".join(f"L{start}-L{end}" for start, end in ranges)


def build_resolved_section(
    resolved_entries: list[ResolvedConflictEntry],
) -> str:
    """Build the collapsed resolved conflicts section.

    Args:
        resolved_entries: List of resolved conflict entries.

    Returns:
        Markdown string with collapsed details section, or empty string.
    """
    if not resolved_entries:
        return ""

    # Sort by resolved date, most recent first
    sorted_entries = sorted(resolved_entries, key=lambda e: e.resolved_at, reverse=True)
    # Cap display count
    sorted_entries = sorted_entries[:MAX_RESOLVED_DISPLAY]

    count = len(sorted_entries)
    rows = []
    for entry in sorted_entries:
        date_str = format_resolved_date(entry.resolved_at)
        if entry.pr_url:
            pr_ref = f"[#{entry.pr_number}]({entry.pr_url}) ({entry.pr_title})"
        else:
            pr_ref = f"#{entry.pr_number} ({entry.pr_title})"
        rows.append(f"| ~{pr_ref}~ | {date_str} |")

    table = "\n".join(rows)
    suffix = "s" if count != 1 else ""

    return (
        f"\n<details>\n"
        f"<summary>✅ {count} previously resolved conflict{suffix}</summary>\n\n"
        f"| Conflicting PR | Resolved |\n"
        f"|---|---|\n"
        f"{table}\n\n"
        f"</details>"
    )


def format_resolved_date(iso_timestamp: str) -> str:
    """Format an ISO 8601 timestamp as a readable date.

    Args:
        iso_timestamp: ISO 8601 formatted timestamp string.

    Returns:
        Formatted date string like 'Mar 19, 2026'.
    """
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return "Unknown"
