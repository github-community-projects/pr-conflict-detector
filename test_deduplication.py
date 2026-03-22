"""Tests for the deduplication module."""

import json
import os
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

    def test_save_state_atomic_no_temp_file_left(self):
        """After a successful save, no .tmp file should remain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"conflicts": []}
            deduplication.save_state(state, tmpdir)

            tmp_file = Path(tmpdir) / ".pr-conflict-state.json.tmp"
            self.assertFalse(tmp_file.exists())

            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            self.assertTrue(state_file.exists())

    def test_save_state_atomic_replaces_existing(self):
        """Atomic save should replace an existing state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            # Write initial state
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"conflicts": [], "last_run": "old"}, f)

            # Save new state
            new_state = {
                "conflicts": [
                    {
                        "repo": "org/repo",
                        "pr_a": 1,
                        "pr_b": 2,
                        "files": ["f.py"],
                        "first_seen": "2026-01-01T00:00:00+00:00",
                    }
                ]
            }
            deduplication.save_state(new_state, tmpdir)

            with open(state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded["conflicts"]), 1)

    def test_save_state_permission_error(self):
        """Save to unwritable path should print warning."""
        state = {"conflicts": []}
        # Try to save to a path that doesn't exist
        deduplication.save_state(state, "/nonexistent/path")
        # Should not raise, just print warning

    def test_save_state_permission_error_cleans_tmp(self):
        """Save failure should attempt to clean up temp file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"conflicts": []}
            # Saving to a nonexistent subdirectory should fail
            deduplication.save_state(state, os.path.join(tmpdir, "nonexistent"))
            # No temp files should be left in tmpdir
            tmp_file = Path(tmpdir) / "nonexistent" / ".pr-conflict-state.json.tmp"
            self.assertFalse(tmp_file.exists())


class TestPruneExpiredConflicts(unittest.TestCase):
    """Test pruning of expired conflict fingerprints."""

    def test_prune_no_conflicts(self):
        """Empty state should remain empty."""
        state = {"conflicts": []}
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(pruned, {"conflicts": [], "resolved_conflicts": []})

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

    def test_update_state_includes_last_run(self):
        """Updated state should include a last_run timestamp."""
        state = {"conflicts": []}
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertIn("last_run", updated)
        # Should be a valid ISO timestamp
        datetime.fromisoformat(updated["last_run"])

    def test_update_state_last_run_is_recent(self):
        """last_run timestamp should be close to current time."""
        state = {"conflicts": []}
        conflicts = {}
        before = datetime.now(timezone.utc)
        updated = deduplication.update_state_with_current(conflicts, state)
        after = datetime.now(timezone.utc)

        last_run = datetime.fromisoformat(updated["last_run"])
        self.assertGreaterEqual(last_run, before)
        self.assertLessEqual(last_run, after)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with state files missing last_run."""

    def test_load_state_without_last_run(self):
        """State files without last_run should load successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            old_state = {
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
                json.dump(old_state, f)

            state = deduplication.load_state(tmpdir)
            self.assertEqual(len(state["conflicts"]), 1)
            self.assertNotIn("last_run", state)

    def test_load_state_with_last_run(self):
        """State files with last_run should preserve it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".pr-conflict-state.json"
            state_data = {
                "conflicts": [],
                "last_run": "2026-03-15T10:00:00+00:00",
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f)

            state = deduplication.load_state(tmpdir)
            self.assertEqual(state["last_run"], "2026-03-15T10:00:00+00:00")

    def test_compare_conflicts_ignores_last_run(self):
        """compare_conflicts should work with or without last_run in state."""
        state_with_last_run = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["README.md"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                }
            ],
            "last_run": "2026-03-15T10:00:00+00:00",
        }
        conflicts = {"org/repo": [_make_conflict(1, 2, ["README.md"])]}
        result = deduplication.compare_conflicts(conflicts, state_with_last_run)

        self.assertEqual(len(result.unchanged_conflicts), 1)
        self.assertEqual(len(result.new_conflicts), 0)

    def test_prune_preserves_last_run(self):
        """prune_expired_conflicts should not strip last_run from state."""
        now = datetime.now(timezone.utc)
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["f.py"],
                    "first_seen": (now - timedelta(days=10)).isoformat(),
                }
            ],
            "last_run": "2026-03-15T10:00:00+00:00",
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertIn("last_run", pruned)
        self.assertEqual(pruned["last_run"], "2026-03-15T10:00:00+00:00")


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

    def test_conflict_to_fingerprint_populates_pr_info(self):
        """Should populate pr_info from the ConflictResult."""
        conflict = _make_conflict(1, 2, ["file.py"])
        fp = deduplication.conflict_to_fingerprint(conflict, "org/repo")

        # _make_conflict uses PRInfo(num, "http://prN", "PR N", author)
        # PRInfo fields: number, title, author, url
        # So: title="http://pr1", author="PR 1", url="alice"
        self.assertEqual(fp.pr_info[0].title, "http://pr1")
        self.assertEqual(fp.pr_info[0].url, "alice")
        self.assertEqual(fp.pr_info[0].author, "PR 1")
        self.assertEqual(fp.pr_info[1].title, "http://pr2")
        self.assertEqual(fp.pr_info[1].url, "bob")
        self.assertEqual(fp.pr_info[1].author, "PR 2")

    def test_fingerprint_to_dict(self):
        """Should convert ConflictFingerprint to dict including PR display info."""
        fp = deduplication.ConflictFingerprint(
            repo="org/repo",
            pr_a=1,
            pr_b=2,
            files=["test.py"],
            first_seen="2026-01-01T00:00:00+00:00",
            pr_info=(
                deduplication.PRDisplayInfo(
                    title="PR 1", url="http://pr1", author="alice"
                ),
                deduplication.PRDisplayInfo(
                    title="PR 2", url="http://pr2", author="bob"
                ),
            ),
        )
        fp_dict = deduplication.fingerprint_to_dict(fp)

        self.assertEqual(fp_dict["repo"], "org/repo")
        self.assertEqual(fp_dict["pr_a"], 1)
        self.assertEqual(fp_dict["pr_b"], 2)
        self.assertEqual(fp_dict["files"], ["test.py"])
        self.assertEqual(fp_dict["first_seen"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(fp_dict["pr_a_title"], "PR 1")
        self.assertEqual(fp_dict["pr_a_url"], "http://pr1")
        self.assertEqual(fp_dict["pr_b_title"], "PR 2")
        self.assertEqual(fp_dict["pr_b_url"], "http://pr2")
        self.assertEqual(fp_dict["pr_a_author"], "alice")
        self.assertEqual(fp_dict["pr_b_author"], "bob")

    def test_fingerprint_to_dict_includes_resolved_at(self):
        """resolved_at should appear in dict when set."""
        fp = deduplication.ConflictFingerprint(
            repo="org/repo",
            pr_a=1,
            pr_b=2,
            files=["test.py"],
            first_seen="2026-01-01T00:00:00+00:00",
            resolved_at="2026-03-01T00:00:00+00:00",
        )
        fp_dict = deduplication.fingerprint_to_dict(fp)
        self.assertEqual(fp_dict["resolved_at"], "2026-03-01T00:00:00+00:00")

    def test_fingerprint_to_dict_omits_resolved_at_when_empty(self):
        """resolved_at should not appear in dict when empty."""
        fp = deduplication.ConflictFingerprint(
            repo="org/repo",
            pr_a=1,
            pr_b=2,
            files=["test.py"],
            first_seen="2026-01-01T00:00:00+00:00",
        )
        fp_dict = deduplication.fingerprint_to_dict(fp)
        self.assertNotIn("resolved_at", fp_dict)

    def test_dict_to_fingerprint(self):
        """Should convert dict to ConflictFingerprint with all fields."""
        fp_dict = {
            "repo": "org/repo",
            "pr_a": 1,
            "pr_b": 2,
            "files": ["test.py"],
            "first_seen": "2026-01-01T00:00:00+00:00",
            "pr_a_title": "PR 1",
            "pr_a_url": "http://pr1",
            "pr_b_title": "PR 2",
            "pr_b_url": "http://pr2",
            "pr_a_author": "alice",
            "pr_b_author": "bob",
            "resolved_at": "2026-03-01T00:00:00+00:00",
        }
        fp = deduplication.dict_to_fingerprint(fp_dict)

        self.assertEqual(fp.repo, "org/repo")
        self.assertEqual(fp.pr_a, 1)
        self.assertEqual(fp.pr_b, 2)
        self.assertEqual(fp.files, ["test.py"])
        self.assertEqual(fp.first_seen, "2026-01-01T00:00:00+00:00")
        self.assertEqual(fp.pr_info[0].title, "PR 1")
        self.assertEqual(fp.pr_info[0].url, "http://pr1")
        self.assertEqual(fp.pr_info[0].author, "alice")
        self.assertEqual(fp.pr_info[1].title, "PR 2")
        self.assertEqual(fp.pr_info[1].url, "http://pr2")
        self.assertEqual(fp.pr_info[1].author, "bob")
        self.assertEqual(fp.resolved_at, "2026-03-01T00:00:00+00:00")

    def test_dict_to_fingerprint_backward_compat(self):
        """Old dicts without PR display fields should still work."""
        fp_dict = {
            "repo": "org/repo",
            "pr_a": 1,
            "pr_b": 2,
            "files": ["test.py"],
            "first_seen": "2026-01-01T00:00:00+00:00",
        }
        fp = deduplication.dict_to_fingerprint(fp_dict)

        self.assertEqual(fp.repo, "org/repo")
        self.assertEqual(fp.pr_info[0].title, "")
        self.assertEqual(fp.pr_info[0].url, "")
        self.assertEqual(fp.pr_info[0].author, "")
        self.assertEqual(fp.pr_info[1].title, "")
        self.assertEqual(fp.pr_info[1].url, "")
        self.assertEqual(fp.pr_info[1].author, "")
        self.assertEqual(fp.resolved_at, "")


class TestPruneResolvedConflicts(unittest.TestCase):
    """Test pruning of resolved conflicts in prune_expired_conflicts."""

    def test_prune_keeps_recent_resolved(self):
        """Resolved entries within RESOLVED_MAX_AGE_DAYS should be kept."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=3)
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": recent.isoformat(),
                }
            ],
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["resolved_conflicts"]), 1)

    def test_prune_removes_old_resolved(self):
        """Resolved entries older than RESOLVED_MAX_AGE_DAYS should be removed."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": old.isoformat(),
                }
            ],
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["resolved_conflicts"]), 0)

    def test_prune_mixed_resolved(self):
        """Should keep recent and remove old resolved entries."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=2)
        old = now - timedelta(days=10)
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["recent.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": recent.isoformat(),
                },
                {
                    "repo": "org/repo",
                    "pr_a": 3,
                    "pr_b": 4,
                    "files": ["old.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": old.isoformat(),
                },
            ],
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["resolved_conflicts"]), 1)
        self.assertEqual(pruned["resolved_conflicts"][0]["pr_a"], 1)

    def test_prune_skips_malformed_resolved(self):
        """Malformed resolved entries (missing resolved_at) should be skipped."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=2)
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["good.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": recent.isoformat(),
                },
                {
                    "repo": "org/repo",
                    "pr_a": 3,
                    "pr_b": 4,
                    "files": ["bad.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    # Missing resolved_at
                },
            ],
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertEqual(len(pruned["resolved_conflicts"]), 1)
        self.assertEqual(pruned["resolved_conflicts"][0]["pr_a"], 1)


class TestUpdateStateResolvedTracking(unittest.TestCase):
    """Test resolved conflict tracking in update_state_with_current."""

    def test_disappeared_conflict_becomes_resolved(self):
        """When a conflict disappears from current, it should appear in resolved_conflicts."""
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
        # Current has no conflicts - PR 1-2 resolved
        updated = deduplication.update_state_with_current({}, state)

        self.assertEqual(len(updated["conflicts"]), 0)
        self.assertEqual(len(updated["resolved_conflicts"]), 1)
        resolved = updated["resolved_conflicts"][0]
        self.assertEqual(resolved["pr_a"], 1)
        self.assertEqual(resolved["pr_b"], 2)
        self.assertIn("resolved_at", resolved)
        # resolved_at should be a valid ISO timestamp
        datetime.fromisoformat(resolved["resolved_at"])

    def test_existing_resolved_carried_forward(self):
        """Existing resolved_conflicts from state should be preserved."""
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 5,
                    "pr_b": 6,
                    "files": ["old.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": "2026-03-01T00:00:00+00:00",
                }
            ],
        }
        updated = deduplication.update_state_with_current({}, state)

        self.assertEqual(len(updated["resolved_conflicts"]), 1)
        self.assertEqual(updated["resolved_conflicts"][0]["pr_a"], 5)
        self.assertEqual(
            updated["resolved_conflicts"][0]["resolved_at"],
            "2026-03-01T00:00:00+00:00",
        )

    def test_new_resolved_added_alongside_existing(self):
        """New resolved conflicts should be appended to existing resolved list."""
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                }
            ],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 5,
                    "pr_b": 6,
                    "files": ["old.py"],
                    "first_seen": "2026-01-01T00:00:00+00:00",
                    "resolved_at": "2026-03-01T00:00:00+00:00",
                }
            ],
        }
        # PR 1-2 disappears from current
        updated = deduplication.update_state_with_current({}, state)

        self.assertEqual(len(updated["resolved_conflicts"]), 2)
        pr_pairs = [(r["pr_a"], r["pr_b"]) for r in updated["resolved_conflicts"]]
        self.assertIn((5, 6), pr_pairs)
        self.assertIn((1, 2), pr_pairs)

    def test_update_state_returns_resolved_conflicts_key(self):
        """Updated state should always include resolved_conflicts key."""
        state = {"conflicts": []}
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertIn("resolved_conflicts", updated)
        self.assertEqual(len(updated["resolved_conflicts"]), 0)


class TestResolvedFlipFlopDedup(unittest.TestCase):
    """Test that resolved entries are cleaned up when conflicts reappear."""

    def test_reappearing_conflict_removed_from_resolved(self):
        """If a resolved conflict reappears, it should be removed from resolved list."""
        now = datetime.now(timezone.utc)
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": (now - timedelta(hours=5)).isoformat(),
                    "resolved_at": (now - timedelta(hours=1)).isoformat(),
                }
            ],
        }
        # Conflict 1-2 reappears
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, state)

        self.assertEqual(len(updated["conflicts"]), 1)
        self.assertEqual(len(updated["resolved_conflicts"]), 0)

    def test_flip_flop_no_duplicates(self):
        """A conflict that flip-flops should not create duplicate resolved entries."""
        now = datetime.now(timezone.utc)

        # Run 1: conflict is active
        state_run1 = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": (now - timedelta(hours=5)).isoformat(),
                }
            ],
            "resolved_conflicts": [],
        }

        # Run 2: conflict resolves
        updated = deduplication.update_state_with_current({}, state_run1)
        self.assertEqual(len(updated["resolved_conflicts"]), 1)

        # Run 3: conflict reappears
        conflicts = {"org/repo": [_make_conflict(1, 2, ["file.py"])]}
        updated = deduplication.update_state_with_current(conflicts, updated)
        self.assertEqual(len(updated["conflicts"]), 1)
        self.assertEqual(len(updated["resolved_conflicts"]), 0)

        # Run 4: conflict resolves again
        updated = deduplication.update_state_with_current({}, updated)
        self.assertEqual(len(updated["resolved_conflicts"]), 1)


class TestTimezoneNaiveSafety(unittest.TestCase):
    """Test that timezone-naive timestamps don't crash pruning."""

    def test_prune_handles_naive_active_timestamp(self):
        """Naive timestamps in active conflicts should not crash."""
        state = {
            "conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00",
                }
            ]
        }
        # Should not raise TypeError
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertIsInstance(pruned, dict)

    def test_prune_handles_naive_resolved_timestamp(self):
        """Naive timestamps in resolved conflicts should not crash."""
        state = {
            "conflicts": [],
            "resolved_conflicts": [
                {
                    "repo": "org/repo",
                    "pr_a": 1,
                    "pr_b": 2,
                    "files": ["file.py"],
                    "first_seen": "2026-01-01T00:00:00",
                    "resolved_at": "2026-01-01T00:00:00",
                }
            ],
        }
        pruned = deduplication.prune_expired_conflicts(state)
        self.assertIsInstance(pruned, dict)


if __name__ == "__main__":
    unittest.main()
