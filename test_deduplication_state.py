"""Tests for state file I/O and backward compatibility."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import deduplication
from test_helpers import _make_dedup_conflict as _make_conflict


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


if __name__ == "__main__":
    unittest.main()
