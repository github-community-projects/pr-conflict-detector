"""Tests for pr_data data classes."""

import unittest

from pr_data import ChangedFile, PullRequestData


class TestDataClasses(unittest.TestCase):
    """Tests for the data classes."""

    def test_changed_file_defaults(self):
        """ChangedFile should have an empty patch_lines by default."""
        cf = ChangedFile(filename="f.py", additions=1, deletions=0, changes=1)
        self.assertEqual(cf.patch_lines, [])

    def test_pull_request_data_defaults(self):
        """PullRequestData should have empty changed_files by default."""
        pr = PullRequestData(
            number=1,
            title="t",
            author="a",
            html_url="u",
            is_draft=False,
            base_branch="main",
            head_branch="feat",
        )
        self.assertEqual(pr.changed_files, [])
