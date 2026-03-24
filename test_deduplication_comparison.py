"""Tests for conflict comparison and state update logic."""

import unittest
from datetime import datetime, timezone

import deduplication
from conftest import _make_dedup_conflict as _make_conflict


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


if __name__ == "__main__":
    unittest.main()
