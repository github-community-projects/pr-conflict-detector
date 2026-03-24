"""Fingerprint data types and conversion for conflict deduplication."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from conflict_detector import ConflictResult


@dataclass
class PRDisplayInfo:
    """Display metadata for a PR, stored in fingerprints for comment rendering."""

    title: str = ""
    url: str = ""
    author: str = ""


@dataclass
class ConflictFingerprint:
    """A fingerprint representing a conflict for deduplication tracking."""

    repo: str
    pr_a: int
    pr_b: int
    files: list[str]
    first_seen: str  # ISO 8601 timestamp
    # (pr_a_info, pr_b_info) - display metadata for comment rendering
    pr_info: tuple[PRDisplayInfo, PRDisplayInfo] = field(
        default_factory=lambda: (PRDisplayInfo(), PRDisplayInfo())
    )
    resolved_at: str = ""


@dataclass
class DeduplicationResult:
    """Results of comparing current conflicts against historical state."""

    new_conflicts: list[ConflictResult] = field(default_factory=list)
    changed_conflicts: list[ConflictResult] = field(default_factory=list)
    unchanged_conflicts: list[ConflictResult] = field(default_factory=list)
    resolved_fingerprints: list[ConflictFingerprint] = field(default_factory=list)


def conflict_to_fingerprint(
    conflict: ConflictResult, repo: str, timestamp: str | None = None
) -> ConflictFingerprint:
    """Convert a ConflictResult to a ConflictFingerprint.

    Args:
        conflict: The ConflictResult object.
        repo: Repository full name.
        timestamp: ISO 8601 timestamp, or None to use current time.

    Returns:
        ConflictFingerprint for this conflict.
    """
    files = sorted({fo.filename for fo in conflict.conflicting_files})
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    return ConflictFingerprint(
        repo=repo,
        pr_a=conflict.pr_a.number,
        pr_b=conflict.pr_b.number,
        files=files,
        first_seen=timestamp,
        pr_info=(
            PRDisplayInfo(
                title=conflict.pr_a.title,
                url=conflict.pr_a.url,
                author=conflict.pr_a.author,
            ),
            PRDisplayInfo(
                title=conflict.pr_b.title,
                url=conflict.pr_b.url,
                author=conflict.pr_b.author,
            ),
        ),
    )


def fingerprint_to_dict(fp: ConflictFingerprint) -> dict[str, Any]:
    """Convert a ConflictFingerprint to a JSON-serializable dict."""
    d: dict[str, Any] = {
        "repo": fp.repo,
        "pr_a": fp.pr_a,
        "pr_b": fp.pr_b,
        "files": fp.files,
        "first_seen": fp.first_seen,
        "pr_a_title": fp.pr_info[0].title,
        "pr_a_url": fp.pr_info[0].url,
        "pr_b_title": fp.pr_info[1].title,
        "pr_b_url": fp.pr_info[1].url,
        "pr_a_author": fp.pr_info[0].author,
        "pr_b_author": fp.pr_info[1].author,
    }
    if fp.resolved_at:
        d["resolved_at"] = fp.resolved_at
    return d


def dict_to_fingerprint(data: dict[str, Any]) -> ConflictFingerprint:
    """Convert a dict back to a ConflictFingerprint."""
    return ConflictFingerprint(
        repo=data["repo"],
        pr_a=data["pr_a"],
        pr_b=data["pr_b"],
        files=data["files"],
        first_seen=data["first_seen"],
        pr_info=(
            PRDisplayInfo(
                title=data.get("pr_a_title", ""),
                url=data.get("pr_a_url", ""),
                author=data.get("pr_a_author", ""),
            ),
            PRDisplayInfo(
                title=data.get("pr_b_title", ""),
                url=data.get("pr_b_url", ""),
                author=data.get("pr_b_author", ""),
            ),
        ),
        resolved_at=data.get("resolved_at", ""),
    )
