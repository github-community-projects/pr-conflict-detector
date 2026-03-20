"""Deduplication logic for tracking and comparing conflict states across runs."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from conflict_detector import ConflictResult

RESOLVED_MAX_AGE_DAYS = 7
MAX_RESOLVED_PER_PR = 10


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


STATE_FILE = ".pr-conflict-state.json"
EXPIRY_DAYS = 42


def load_state(repo_path: str = ".") -> dict[str, Any]:
    """Load the conflict state file from the repository.

    Args:
        repo_path: Path to the repository root.

    Returns:
        Dictionary with 'conflicts' list, or empty structure if file doesn't exist.
    """
    state_path = os.path.join(repo_path, STATE_FILE)
    if not os.path.exists(state_path):
        return {"conflicts": []}

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Failed to load state file: {e}")
        return {"conflicts": []}


def save_state(state: dict[str, Any], repo_path: str = ".") -> None:
    """Save the conflict state file to the repository using atomic writes.

    Writes to a temporary file first, then atomically renames it to the
    target path. This prevents partial/corrupt state files if the process
    is interrupted mid-write (e.g., job cancellation, timeout).

    Args:
        state: State dictionary with 'conflicts' list.
        repo_path: Path to the repository root.
    """
    state_path = os.path.join(repo_path, STATE_FILE)
    tmp_path = state_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, state_path)  # atomic on POSIX
    except OSError as e:
        print(f"Warning: Failed to save state file: {e}")
        # Clean up partial temp file if it exists
        try:
            os.remove(tmp_path)
        except OSError:
            # Best-effort cleanup; safe to ignore if temp file is already gone
            pass


def prune_expired_conflicts(
    state: dict[str, Any], expiry_days: int = EXPIRY_DAYS
) -> dict[str, Any]:
    """Remove conflicts older than the expiry threshold.

    Args:
        state: State dictionary with 'conflicts' list.
        expiry_days: Number of days after which to expire active conflicts.

    Returns:
        Updated state with expired conflicts removed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=expiry_days)
    pruned_conflicts = []

    for conflict in state.get("conflicts", []):
        try:
            first_seen = datetime.fromisoformat(conflict["first_seen"])
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
            if first_seen >= cutoff:
                pruned_conflicts.append(conflict)
        except (ValueError, KeyError):
            # Skip malformed entries
            continue

    state["conflicts"] = pruned_conflicts

    # Prune resolved conflicts older than RESOLVED_MAX_AGE_DAYS
    resolved_cutoff = datetime.now(timezone.utc) - timedelta(days=RESOLVED_MAX_AGE_DAYS)
    pruned_resolved = []
    for resolved in state.get("resolved_conflicts", []):
        try:
            resolved_at = datetime.fromisoformat(resolved["resolved_at"])
            if resolved_at.tzinfo is None:
                resolved_at = resolved_at.replace(tzinfo=timezone.utc)
            if resolved_at >= resolved_cutoff:
                pruned_resolved.append(resolved)
        except (ValueError, KeyError):
            continue
    state["resolved_conflicts"] = pruned_resolved

    return state


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


def compare_conflicts(
    current_conflicts: dict[str, list[ConflictResult]], state: dict[str, Any]
) -> DeduplicationResult:
    """Compare current conflicts against historical state.

    Args:
        current_conflicts: Dict mapping repo name to list of ConflictResult objects.
        state: State dictionary with 'conflicts' list of fingerprints.

    Returns:
        DeduplicationResult categorizing conflicts as new, changed, or unchanged.
    """
    result = DeduplicationResult()

    # Build lookup of existing fingerprints by (repo, pr_a, pr_b)
    existing: dict[tuple[str, int, int], ConflictFingerprint] = {}
    for fp_dict in state.get("conflicts", []):
        fp = dict_to_fingerprint(fp_dict)
        key = (fp.repo, fp.pr_a, fp.pr_b)
        existing[key] = fp

    # Track which existing conflicts we've seen in current run
    seen_keys: set[tuple[str, int, int]] = set()

    for repo, conflicts in current_conflicts.items():
        for conflict in conflicts:
            key = (repo, conflict.pr_a.number, conflict.pr_b.number)
            seen_keys.add(key)

            if key not in existing:
                # New conflict
                result.new_conflicts.append(conflict)
            else:
                # Exists — check if files changed
                old_fp = existing[key]
                new_files = sorted({fo.filename for fo in conflict.conflicting_files})
                if new_files != old_fp.files:
                    result.changed_conflicts.append(conflict)
                else:
                    result.unchanged_conflicts.append(conflict)

    # Find resolved conflicts (in state but not in current)
    for key, fp in existing.items():
        if key not in seen_keys:
            result.resolved_fingerprints.append(fp)

    return result


def update_state_with_current(
    current_conflicts: dict[str, list[ConflictResult]], state: dict[str, Any]
) -> dict[str, Any]:
    """Update state with current conflicts, preserving timestamps for unchanged.

    Also tracks newly resolved conflicts by moving them from the active list
    to the resolved list with a resolved_at timestamp.

    Args:
        current_conflicts: Dict mapping repo name to list of ConflictResult objects.
        state: Existing state dictionary.

    Returns:
        Updated state dictionary with 'conflicts', 'resolved_conflicts',
        and 'last_run' timestamp.
    """
    # Build lookup of existing timestamps
    existing_timestamps: dict[tuple[str, int, int], str] = {}
    for fp_dict in state.get("conflicts", []):
        fp = dict_to_fingerprint(fp_dict)
        key = (fp.repo, fp.pr_a, fp.pr_b)
        existing_timestamps[key] = fp.first_seen

    # Build new state with current conflicts
    new_fingerprints = []
    current_keys: set[tuple[str, int, int]] = set()
    for repo, conflicts in current_conflicts.items():
        for conflict in conflicts:
            key = (repo, conflict.pr_a.number, conflict.pr_b.number)
            current_keys.add(key)
            # Preserve timestamp if conflict existed before, otherwise use current time
            timestamp = existing_timestamps.get(key)
            fp = conflict_to_fingerprint(conflict, repo, timestamp)
            new_fingerprints.append(fingerprint_to_dict(fp))

    # Carry forward existing resolved conflicts, excluding any that reappeared
    resolved = [
        r
        for r in state.get("resolved_conflicts", [])
        if (r.get("repo", ""), r.get("pr_a"), r.get("pr_b")) not in current_keys
    ]

    # Add newly resolved conflicts (in previous state but not in current)
    now = datetime.now(timezone.utc).isoformat()
    for fp_dict in state.get("conflicts", []):
        fp = dict_to_fingerprint(fp_dict)
        key = (fp.repo, fp.pr_a, fp.pr_b)
        if key not in current_keys:
            fp.resolved_at = now
            resolved.append(fingerprint_to_dict(fp))

    return {
        "conflicts": new_fingerprints,
        "resolved_conflicts": resolved,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }
