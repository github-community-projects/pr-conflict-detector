"""Tests for the deduplication module."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import deduplication
from conflict_detector import ConflictResult, FileOverlap, PRInfo


def _make_conflict(pr_a_num=1, pr_b_num=2, files=None):
    """Helper to create a ConflictResult for testing."""
    if files is None:
        files = ["README.md"]

    return ConflictResult(
        pr_a=PRInfo(pr_a_num, f"http://pr{pr_a_num}", f"PR {pr_a_num}", "alice"),
        pr_b=PRInfo(pr_b_num, f"http://pr{pr_b_num}", f"PR {pr_b_num}", "bob"),
        conflicting_files=[
            FileOverlap(f, [(10, 20)], [(15, 25)], [(15, 20)]) for f in files
        ],
    )


class TestLoadAndSaveState(unittest.TestCase):
    """Test state file loading and saving."""

    def test_load_state_file_not_found(self):
        """If state file doesn't exist, should return empty state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = deduplication.load_state(tmpdir)
            self.assertEqual(state, {"conflicts": []})

    def test_load_state_success(self):
        """Should successfully load an existing state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            state_data = {
                "conflicts": [
                    {
                        "repo": "org/repo",
                        "pr_a": 1,
                        "pr_b": 2,
                        "files": ["main.py"],
                        "first_seen": "2026-01-01T00:00:00+00:00",
                    }
                ]
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f)

            state = deduplication.load_state(tmpdir)
            self.assertEqual(len(state["conflicts"]), 1)
            self.assertEqual(state["conflicts"][0]["repo"], "org/repo")

    def test_load_state_invalid_json(self):
        """Malformed JSON should return empty state with warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            with open(state_file, "w", encoding="utf-8") as f:
                f.write("not valid json")

            state = deduplication.load_state(tmpdir)
            self.assertEqual(state, {"conflicts": []})

    def test_save_state(self):
        """Should save state to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "conflicts": [
                    {
                        "repo": "org/repo",
                        "pr_a": 1,
                        "pr_b": 2,
                        "files": ["test.py"],
                        "first_seen": "2026-01-01T00:00:00+00:00",
                    }
                ]
            }
            deduplication.save_state(state, tmpdir)

            # Verify file was written
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            with open(state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["conflicts"][0]["pr_a"], 1)

    def test_save_state_permission_error(self):
        """Save to unwritable path should print warning."""
        state = {"conflicts": []}
        # Try to save to a path that doesn't exist
        deduplication.save_state(state, "/nonexistent/path")
        # Should not raise, just print warning


class TestPruneExpiredConflicts(unittest.TestCase):
    """Test pruning of expired conflict fingerprints."""

    def test_prune_no_conflicts(self):
        """Empty state should remain empty."""
        state = {"conflicts": []}
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(pruned, {"conflicts": []})

    def test_prune_keeps_recent(self):
        """Recent conflicts should be kept."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": recent.isoformat(),
                }
            ]
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["conflicts"]), 1)

    def test_prune_removes_old(self):
        """Conflicts older than EXPIRY_DAYS should be removed."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=50)  # Older than 42 days
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": old.isoformat(),
                }
            ]
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["conflicts"]), 0)

    def test_prune_mixed(self):
        """Should keep recent and remove old."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        old = now - timedelta(days=50)
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["recent.py"],
                    "first_seen": recent.isoformat(),
                },
                {
                    "repo": "org/repo",
                    "pr_a": 3,
                    "pr_b": 4,
                    "files": ["old.py"],
                    "first_seen": old.isoformat(),
                },
            ]
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["conflicts"]), 1)
        self.assertEqual(pruned["conflicts"][0]["pr_a"], 1)

    def test_prune_malformed_entry(self):
        """Malformed conflict entries should be skipped."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=10)
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["good.py"],
                    "first_seen": recent.isoformat(),
                },
                {
                    # Missing first_seen
                    "repo": "org/repo",
                    "pr_a": 3,
                    "pr_b": 4,
                    "files": ["bad.py"],
                },
            ]
        }
        pruned = deduplication.prune_expired_conflicts(state)
        # Should keep the good one, skip the bad one
        self.assertEqual(len(pruned["conflicts"]), 1)
        self.assertEqual(pruned["conflicts"][0]["pr_a"], 1)


class TestCompareConflicts(unittest.TestCase):
    """Test conflict comparison logic."""

    def test_compare_empty_state_all_new(self):
        """If state is empty, all conflicts should be new."""
        conflicts = {"org/repo": [_make_conflict(1, 2)]}
        state = {"conflicts": []}
        result = deduplication.compare_conflicts(conflicts, state)

        self.assertEqual(len(result.new_conflicts), 1)
        self.assertEqual(len(result.changed_conflicts), 0)
        self.assertEqual(len(result.unchanged_conflicts), 0)
        self.assertEqual(len(result.resolved_fingerprints), 0)

    def test_compare_unchanged_conflict(self):
        """If conflict exists with same files, should be unchanged."""
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["README.md"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        conflicts = {"org/repo": [_make_conflict(1, 2, ["README.md"])]}
        result = deduplication.compare_conflicts(conflicts, state)

        self.assertEqual(len(result.new_conflicts), 0)
        self.assertEqual(len(result.changed_conflicts), 0)
        self.assertEqual(len(result.unchanged_conflicts), 1)
        self.assertEqual(len(result.resolved_fingerprints), 0)

    def test_compare_changed_conflict(self):
        """If conflict exists but files changed, should be changed."""
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["old_file.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        conflicts = {"org/repo": [_make_conflict(1, 2, ["new_file.py"])]}
        result = deduplication.compare_conflicts(conflicts, state)

        self.assertEqual(len(result.new_conflicts), 0)
        self.assertEqual(len(result.changed_conflicts), 1)
        self.assertEqual(len(result.unchanged_conflicts), 0)
        self.assertEqual(len(result.resolved_fingerprints), 0)

    def test_compare_resolved_conflict(self):
        """If conflict was in state but not in current, should be resolved."""
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        conflicts = {"org/repo": [_make_conflict(3, 4)]}  # Different PRs
        result = deduplication.compare_conflicts(conflicts, state)

        self.assertEqual(len(result.new_conflicts), 1)  # PR 3-4 is new
        self.assertEqual(len(result.changed_conflicts), 0)
        self.assertEqual(len(result.unchanged_conflicts), 0)
        self.assertEqual(len(result.resolved_fingerprints), 1)  # PR 1-2 resolved


class TestUpdateStateWithCurrent(unittest.TestCase):
    """Test state update logic."""

    def test_update_state_with_new_conflicts(self):
        """New conflicts should be added to state."""
        state = {"conflicts": []}
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertEqual(len(updated["conflicts"]), 1)
        self.assertEqual(updated["conflicts"][0]["pr_a"], 1)
        self.assertEqual(updated["conflicts"][0]["pr_b"], 2)
        self.assertEqual(updated["conflicts"][0]["files"], ["file.py"])

    def test_update_state_preserves_timestamp(self):
        """Unchanged conflicts should keep original timestamp."""
        original_time = "2026-01-01T00:00:00+00:00"
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": original_time,
                }
            ]
        }
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertEqual(updated["conflicts"][0]["first_seen"], original_time)

    def test_update_state_updates_changed_files(self):
        """Changed conflicts should update files but keep timestamp."""
        original_time = "2026-01-01T00:00:00+00:00"
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["old.py"],
                    "first_seen": original_time,
                }
            ]
        }
        conflicts = {"org/repo": [_make_conflict(1, 2, ["new.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertEqual(updated["conflicts"][0]["files"], ["new.py"])
        self.assertEqual(updated["conflicts"][0]["first_seen"], original_time)


class TestFingerprintConversion(unittest.TestCase):
    """Test fingerprint conversion helpers."""

    def test_conflict_to_fingerprint(self):
        """Should convert ConflictResult to ConflictFingerprint."""
        conflict = _make_conflict(1, 2, ["fileA.py", "fileB.py"])
        fp = deduplication.conflict_to_fingerprint(conflict, "org/repo")

        self.assertEqual(fp.repo, "org/repo")
        self.assertEqual(fp.pr_a, 1)
        self.assertEqual(fp.pr_b, 2)
        self.assertEqual(fp.files, ["fileA.py", "fileB.py"])
        # Should have a timestamp
        datetime.fromisoformat(fp.first_seen)  # Should not raise

    def test_fingerprint_to_dict(self):
        """Should convert ConflictFingerprint to dict."""
        fp = deduplication.ConflictFingerprint(
            repo="org/repo",
            pr_a=1,
            pr_b=2,
            files=["test.py"],
            first_seen="2026-01-01T00:00:00+00:00",
        )
        fp_dict = deduplication.fingerprint_to_dict(fp)

        self.assertEqual(fp_dict["repo"], "org/repo")
        self.assertEqual(fp_dict["pr_a"], 1)
        self.assertEqual(fp_dict["pr_b"], 2)
        self.assertEqual(fp_dict["files"], ["test.py"])
        self.assertEqual(fp_dict["first_seen"], "2026-01-01T00:00:00+00:00")

    def test_dict_to_fingerprint(self):
        """Should convert dict to ConflictFingerprint."""
        fp_dict = {
            "repo": "org/repo",
            "pr_a": 1,
            "pr_b": 2,
            "files": ["test.py"],
            "first_seen": "2026-01-01T00:00:00+00:00",
        }
        fp = deduplication.dict_to_fingerprint(fp_dict)

        self.assertEqual(fp.repo, "org/repo")
        self.assertEqual(fp.pr_a, 1)
        self.assertEqual(fp.pr_b, 2)
        self.assertEqual(fp.files, ["test.py"])
        self.assertEqual(fp.first_seen, "2026-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
