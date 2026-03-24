"""Tests for fingerprint conversion and flip-flop deduplication."""

import unittest
from datetime import datetime, timedelta, timezone

import deduplication
from test_helpers import _make_dedup_conflict as _make_conflict


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


if __name__ == "__main__":
    unittest.main()
