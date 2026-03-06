"""Tests for json_writer module."""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from json_writer import write_to_json


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


def _make_conflict(pr_a, pr_b, files=None, verified=False):
    """Create a stub ConflictResult-like object."""
    return SimpleNamespace(
        pr_a=pr_a,
        pr_b=pr_b,
        conflicting_files=files or [_make_file_overlap()],
        verified=verified,
    )


class TestWriteToJson:
    """Tests for write_to_json()."""

    def test_empty_conflicts(self, tmp_path):
        """Test JSON output for empty conflicts."""
        output_file = str(tmp_path / "report.json")
        result = write_to_json({}, output_file=output_file)

        data = json.loads(result)
        assert data["total_repositories_scanned"] == 0
        assert data["total_conflicts_found"] == 0
        assert data["repositories"] == []

    def test_output_structure(self, tmp_path):
        """Test the overall JSON structure for a single conflict."""
        pr_a = _make_pr(1, "Add feature", "alice")
        pr_b = _make_pr(2, "Fix bug", "bob")
        conflict = _make_conflict(pr_a, pr_b)

        output_file = str(tmp_path / "report.json")
        result = write_to_json({"owner/repo": [conflict]}, output_file=output_file)

        data = json.loads(result)
        assert data["total_repositories_scanned"] == 1
        assert data["total_conflicts_found"] == 1

        repo = data["repositories"][0]
        assert repo["name"] == "owner/repo"
        assert repo["total_conflicts"] == 1

        cluster = repo["clusters"][0]
        assert len(cluster["prs"]) == 2
        c = cluster["conflicts"][0]
        assert c["pr_a"]["number"] == 1
        assert c["pr_a"]["title"] == "Add feature"
        assert c["pr_a"]["author"] == "alice"
        assert c["pr_b"]["number"] == 2
        assert c["verified"] is False

    def test_conflicting_files_in_output(self, tmp_path):
        """Test that conflicting files and ranges appear in JSON output."""
        files = [
            _make_file_overlap("src/main.py", [(1, 10), (20, 30)]),
            _make_file_overlap("src/utils.py", [(50, 60)]),
        ]
        conflict = _make_conflict(
            _make_pr(1, "A", "alice"),
            _make_pr(2, "B", "bob"),
            files=files,
        )

        output_file = str(tmp_path / "report.json")
        write_to_json({"owner/repo": [conflict]}, output_file=output_file)

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        cf = data["repositories"][0]["clusters"][0]["conflicts"][0]["conflicting_files"]
        assert len(cf) == 2
        assert cf[0]["filename"] == "src/main.py"
        assert cf[0]["overlapping_ranges"] == [[1, 10], [20, 30]]
        assert cf[1]["filename"] == "src/utils.py"

    def test_multiple_repos(self, tmp_path):
        """Test JSON output with conflicts across multiple repositories."""
        c1 = _make_conflict(_make_pr(1, "A", "a"), _make_pr(2, "B", "b"))
        c2 = _make_conflict(_make_pr(3, "C", "c"), _make_pr(4, "D", "d"))
        c3 = _make_conflict(_make_pr(5, "E", "e"), _make_pr(6, "F", "f"))

        output_file = str(tmp_path / "report.json")
        result = write_to_json(
            {"repo1": [c1], "repo2": [c2, c3]},
            output_file=output_file,
        )

        data = json.loads(result)
        assert data["total_repositories_scanned"] == 2
        assert data["total_conflicts_found"] == 3

    def test_verified_flag(self, tmp_path):
        """Test that the verified flag is correctly reflected in output."""
        conflict = _make_conflict(
            _make_pr(1, "A", "a"), _make_pr(2, "B", "b"), verified=True
        )

        output_file = str(tmp_path / "report.json")
        result = write_to_json({"owner/repo": [conflict]}, output_file=output_file)

        data = json.loads(result)
        assert (
            data["repositories"][0]["clusters"][0]["conflicts"][0]["verified"] is True
        )

    def test_file_written_to_disk(self, tmp_path):
        """Test that the JSON report file is written to disk."""
        output_file = str(tmp_path / "out.json")
        write_to_json({}, output_file=output_file)

        assert os.path.exists(output_file)
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        assert "repositories" in data

    def test_github_output_written(self, tmp_path):
        """Test that conflicts_json is written to GITHUB_OUTPUT."""
        gh_output_file = str(tmp_path / "github_output")
        with open(gh_output_file, "w", encoding="utf-8"):
            pass

        output_file = str(tmp_path / "report.json")
        with patch.dict(os.environ, {"GITHUB_OUTPUT": gh_output_file}):
            write_to_json({}, output_file=output_file)

        with open(gh_output_file, encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("conflicts_json<<EOF")
        assert content.strip().endswith("EOF")

    def test_repos_with_empty_conflicts(self, tmp_path):
        """Test JSON output when a repo has an empty conflict list."""
        output_file = str(tmp_path / "report.json")
        result = write_to_json({"owner/repo": []}, output_file=output_file)

        data = json.loads(result)
        assert data["total_repositories_scanned"] == 1
        assert data["total_conflicts_found"] == 0
        assert data["repositories"][0]["total_conflicts"] == 0
