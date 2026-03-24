"""Tests for conflict pruning and timezone safety."""

import unittest
from datetime import datetime, timedelta, timezone

import deduplication


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
