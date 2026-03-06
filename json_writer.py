"""JSON output generation for PR conflict detection results."""

import json
import os


def write_to_json(
    conflicts_by_repo: dict,
    output_file: str = "pr_conflict_report.json",
) -> str:
    """Write conflict results to a JSON file.

    Args:
        conflicts_by_repo: Mapping of repo full name to list of ConflictResult objects.
        output_file: Path for the output JSON file.

    Returns:
        The JSON string that was written to the file.

    """
    repositories = []
    total_conflicts_found = 0

    for repo_name, conflicts in conflicts_by_repo.items():
        repo_conflicts = []
        for conflict in conflicts:
            conflicting_files = [
                {
                    "filename": fo.filename,
                    "overlapping_ranges": list(fo.overlapping_ranges),
                }
                for fo in conflict.conflicting_files
            ]
            repo_conflicts.append(
                {
                    "pr_a": {
                        "number": conflict.pr_a.number,
                        "title": conflict.pr_a.title,
                        "author": conflict.pr_a.author,
                        "url": conflict.pr_a.url,
                    },
                    "pr_b": {
                        "number": conflict.pr_b.number,
                        "title": conflict.pr_b.title,
                        "author": conflict.pr_b.author,
                        "url": conflict.pr_b.url,
                    },
                    "conflicting_files": conflicting_files,
                    "verified": (
                        conflict.verified if hasattr(conflict, "verified") else False
                    ),
                }
            )

        total_conflicts_found += len(repo_conflicts)
        repositories.append(
            {
                "name": repo_name,
                "conflicts": repo_conflicts,
                "total_conflicts": len(repo_conflicts),
            }
        )

    output = {
        "repositories": repositories,
        "total_repositories_scanned": len(conflicts_by_repo),
        "total_conflicts_found": total_conflicts_found,
    }

    metrics_json = json.dumps(output, indent=4)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    # Write to GITHUB_OUTPUT if available (multiline requires delimiter)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            print("conflicts_json<<EOF", file=fh)
            print(metrics_json, file=fh)
            print("EOF", file=fh)

    return metrics_json
