"""Markdown report generation for PR conflict detection results."""

import os


def write_to_markdown(
    conflicts_by_repo: dict,
    output_file: str = "pr_conflict_report.md",
    report_title: str = "PR Conflict Report",
    enable_step_summary: bool = True,
) -> None:
    """Write conflict results to a markdown file and optionally to GitHub Actions step summary.

    Args:
        conflicts_by_repo: Mapping of repo full name to list of ConflictResult objects.
        output_file: Path for the output markdown file.
        report_title: Title to use in the report header.
        enable_step_summary: Whether to also write to GITHUB_STEP_SUMMARY.

    """
    markdown_content = generate_markdown(conflicts_by_repo, report_title)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    if enable_step_summary:
        write_step_summary(markdown_content)


def generate_markdown(
    conflicts_by_repo: dict,
    report_title: str = "PR Conflict Report",
) -> str:
    """Generate markdown content from conflict results.

    Args:
        conflicts_by_repo: Mapping of repo full name to list of ConflictResult objects.
        report_title: Title to use in the report header.

    Returns:
        The generated markdown string.

    """
    content = f"# {report_title}\n\n"

    # Collect only repos that have conflicts
    repos_with_conflicts = {
        repo: conflicts for repo, conflicts in conflicts_by_repo.items() if conflicts
    }

    if not repos_with_conflicts:
        content += "✅ No potential merge conflicts detected!\n"
        return content

    total_conflicts = sum(len(c) for c in repos_with_conflicts.values())
    content += (
        f"Found **{total_conflicts}** potential conflict(s) "
        f"across **{len(repos_with_conflicts)}** repositor"
        f"{'y' if len(repos_with_conflicts) == 1 else 'ies'}.\n\n"
    )

    for repo_name, conflicts in repos_with_conflicts.items():
        content += f"## {repo_name}\n\n"
        content += (
            "| PR A | PR B | Conflicting Files " "| Overlapping Lines | Authors |\n"
        )
        content += (
            "|------|------|-------------------" "|-------------------|---------|\n"
        )

        for conflict in conflicts:
            pr_a_link = (
                f"[#{conflict.pr_a.number}]({conflict.pr_a.url}) {conflict.pr_a.title}"
            )
            pr_b_link = (
                f"[#{conflict.pr_b.number}]({conflict.pr_b.url}) {conflict.pr_b.title}"
            )

            file_parts = []
            line_parts = []
            for file_overlap in conflict.conflicting_files:
                file_parts.append(f"`{file_overlap.filename}`")
                ranges = ", ".join(
                    f"L{start}-L{end}" for start, end in file_overlap.overlapping_ranges
                )
                line_parts.append(ranges)

            files_str = ", ".join(file_parts)
            lines_str = ", ".join(line_parts)

            authors = _format_authors(conflict)

            content += (
                f"| {pr_a_link} | {pr_b_link} "
                f"| {files_str} | {lines_str} | {authors} |\n"
            )

        content += "\n"

    return content


def _format_authors(conflict) -> str:
    """Return a deduplicated, sorted string of @-mentioned authors."""
    authors: set[str] = set()
    if conflict.pr_a.author:
        authors.add(f"@{conflict.pr_a.author}")
    if conflict.pr_b.author:
        authors.add(f"@{conflict.pr_b.author}")
    return ", ".join(sorted(authors))


def write_step_summary(markdown_content: str) -> None:
    """Write markdown to GitHub Actions step summary.

    Args:
        markdown_content: The markdown string to append to the step summary.

    """
    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(markdown_content)
