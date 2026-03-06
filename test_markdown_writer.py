"""Tests for markdown_writer module."""

import os
from types import SimpleNamespace
from unittest.mock import patch

from markdown_writer import generate_markdown, write_step_summary, write_to_markdown


def _make_file_overlap(filename="file.py", ranges=None):
    """Create a stub FileOverlap-like object."""
    return SimpleNamespace(
        filename=filename,
        overlapping_ranges=ranges or [(10, 25)],
    )


def _make_pr(number, title, author, url=None):
    """Create a stub PR info object."""
    return SimpleNamespace(
        number=number,
        title=title,
        author=author,
        url=url or f"https://github.com/owner/repo/pull/{number}",
    )


def _make_conflict(pr_a, pr_b, files=None):
    """Create a stub ConflictResult-like object."""
    return SimpleNamespace(
        pr_a=pr_a,
        pr_b=pr_b,
        conflicting_files=files or [_make_file_overlap()],
    )


class TestGenerateMarkdown:
    """Tests for generate_markdown()."""

    def test_no_conflicts_shows_success_message(self):
        """Test that no conflicts produces a success message."""
        result = generate_markdown({})
        assert "✅ No potential merge conflicts detected!" in result

    def test_empty_conflict_lists_shows_success_message(self):
        """Test that empty conflict lists produce a success message."""
        result = generate_markdown({"owner/repo": []})
        assert "✅ No potential merge conflicts detected!" in result

    def test_single_conflict(self):
        """Test markdown output for a single conflict between two PRs."""
        pr_a = _make_pr(1, "Add feature", "alice")
        pr_b = _make_pr(2, "Fix bug", "bob")
        conflict = _make_conflict(pr_a, pr_b)

        result = generate_markdown({"owner/repo": [conflict]})

        assert "## owner/repo" in result
        assert "[#1]" in result
        assert "[#2]" in result
        assert "`file.py`" in result
        assert "L10-L25" in result
        assert "@alice" in result
        assert "@bob" in result

    def test_multiple_repos_with_conflicts(self):
        """Test markdown output with conflicts across multiple repositories."""
        pr_a = _make_pr(10, "PR A", "alice")
        pr_b = _make_pr(20, "PR B", "bob")
        conflict = _make_conflict(pr_a, pr_b)

        pr_c = _make_pr(30, "PR C", "carol", "https://github.com/org/other/pull/30")
        pr_d = _make_pr(40, "PR D", "dave", "https://github.com/org/other/pull/40")
        conflict2 = _make_conflict(pr_c, pr_d)

        result = generate_markdown(
            {
                "owner/repo": [conflict],
                "org/other": [conflict2],
            }
        )

        assert "## owner/repo" in result
        assert "## org/other" in result
        assert "2** repositor" in result

    def test_multiple_conflicting_files(self):
        """Test markdown output when a conflict involves multiple files."""
        pr_a = _make_pr(1, "Big PR", "alice")
        pr_b = _make_pr(2, "Also big", "bob")
        files = [
            _make_file_overlap("src/main.py", [(1, 10)]),
            _make_file_overlap("src/utils.py", [(50, 60), (100, 110)]),
        ]
        conflict = _make_conflict(pr_a, pr_b, files)

        result = generate_markdown({"owner/repo": [conflict]})

        assert "`src/main.py`" in result
        assert "`src/utils.py`" in result
        assert "L1-L10" in result
        assert "L50-L60" in result
        assert "L100-L110" in result

    def test_custom_report_title(self):
        """Test that a custom report title is used in the header."""
        result = generate_markdown({}, report_title="Custom Title")
        assert "# Custom Title" in result

    def test_same_author_on_both_prs(self):
        """Test that a duplicate author is only listed once."""
        pr_a = _make_pr(1, "Part 1", "alice")
        pr_b = _make_pr(2, "Part 2", "alice")
        conflict = _make_conflict(pr_a, pr_b)

        result = generate_markdown({"owner/repo": [conflict]})

        # Author should only appear once
        assert result.count("@alice") == 1

    def test_summary_line_singular_repo(self):
        """Test that singular 'repository' wording is used for one repo."""
        conflict = _make_conflict(_make_pr(1, "A", "a"), _make_pr(2, "B", "b"))
        result = generate_markdown({"owner/repo": [conflict]})
        assert "1** repository" in result

    def test_header_contains_title(self):
        """Test that the report starts with the expected title header."""
        result = generate_markdown({}, report_title="My Report")
        assert result.startswith("# My Report\n")

    def test_cluster_with_three_prs(self):
        """Test that 3+ PR clusters render with grouped headings."""
        pr1 = _make_pr(1, "Feature A", "alice")
        pr2 = _make_pr(2, "Feature B", "bob")
        pr3 = _make_pr(3, "Feature C", "charlie")
        c12 = _make_conflict(pr1, pr2)
        c13 = _make_conflict(pr1, pr3)
        c23 = _make_conflict(pr2, pr3)

        result = generate_markdown({"owner/repo": [c12, c13, c23]})

        assert "### Cluster 1" in result
        assert "3 PRs" in result
        assert "3 conflict(s)" in result
        assert "<details>" in result
        assert "Pairwise details" in result
        assert "@alice" in result
        assert "@bob" in result
        assert "@charlie" in result

    def test_mix_of_pairs_and_clusters(self):
        """Test output with both a simple pair and a multi-PR cluster."""
        pr1 = _make_pr(1, "A", "alice")
        pr2 = _make_pr(2, "B", "bob")
        pr3 = _make_pr(3, "C", "charlie")
        # Cluster: 1-2, 2-3
        c12 = _make_conflict(pr1, pr2, [_make_file_overlap("shared.py")])
        c23 = _make_conflict(pr2, pr3, [_make_file_overlap("shared.py")])
        # Separate pair: 10-11
        pr10 = _make_pr(10, "X", "xavier")
        pr11 = _make_pr(11, "Y", "yvette")
        c1011 = _make_conflict(pr10, pr11, [_make_file_overlap("other.py")])

        result = generate_markdown({"owner/repo": [c12, c23, c1011]})

        # Should have a cluster section and a pair section
        assert "Cluster" in result
        assert "[#10]" in result
        assert "[#11]" in result


class TestWriteToMarkdown:
    """Tests for write_to_markdown()."""

    def test_writes_file(self, tmp_path):
        """Test that a markdown report file is written to disk."""
        output_file = str(tmp_path / "report.md")
        write_to_markdown({}, output_file=output_file, enable_step_summary=False)

        assert os.path.exists(output_file)
        with open(output_file, encoding="utf-8") as f:
            content = f.read()
        assert "✅ No potential merge conflicts detected!" in content

    def test_writes_step_summary(self, tmp_path):
        """Test that a step summary is written when enabled."""
        output_file = str(tmp_path / "report.md")
        summary_file = str(tmp_path / "summary.md")

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_file}):
            # Create the summary file so we can append
            with open(summary_file, "w", encoding="utf-8"):
                pass
            write_to_markdown({}, output_file=output_file, enable_step_summary=True)

        with open(summary_file, encoding="utf-8") as f:
            summary = f.read()
        assert "PR Conflict Report" in summary

    def test_step_summary_disabled(self, tmp_path):
        """Test that the step summary file stays empty when disabled."""
        output_file = str(tmp_path / "report.md")
        summary_file = str(tmp_path / "summary.md")

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_file}):
            with open(summary_file, "w", encoding="utf-8"):
                pass
            write_to_markdown({}, output_file=output_file, enable_step_summary=False)

        with open(summary_file, encoding="utf-8") as f:
            summary = f.read()
        assert summary == ""


class TestWriteStepSummary:
    """Tests for write_step_summary()."""

    def test_no_env_var_does_nothing(self):
        """Test that missing GITHUB_STEP_SUMMARY env var causes no error."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise
            write_step_summary("some content")

    def test_appends_to_summary_file(self, tmp_path):
        """Test that content is appended to the step summary file."""
        summary_file = str(tmp_path / "summary.md")
        with open(summary_file, "w", encoding="utf-8"):
            pass

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_file}):
            write_step_summary("## Hello\n")

        with open(summary_file, encoding="utf-8") as f:
            content = f.read()
        assert "## Hello" in content
