"""Markdown report generation for PR conflict detection results."""

import os

from conflict_detector import ConflictCluster, cluster_conflicts


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
        clusters = cluster_conflicts(conflicts)
        content += _render_clusters(clusters)

    return content


def _render_clusters(clusters: list[ConflictCluster]) -> str:
    """Render conflict clusters as markdown."""
    content = ""
    for i, cluster in enumerate(clusters, 1):
        if len(cluster.prs) == 2:
            # Simple pair — render inline without cluster wrapper
            conflict = cluster.conflicts[0]
            content += _render_pair_row(conflict)
        else:
            # Multi-PR cluster — render as a grouped section
            content += _render_cluster_section(cluster, i)
    return content


def _render_pair_row(conflict) -> str:
    """Render a single pairwise conflict as a compact section."""
    pr_a_link = f"[#{conflict.pr_a.number}]({conflict.pr_a.url})"
    pr_b_link = f"[#{conflict.pr_b.number}]({conflict.pr_b.url})"
    authors = _format_authors_from_conflict(conflict)

    file_parts = []
    for fo in conflict.conflicting_files:
        ranges = ", ".join(f"L{start}-L{end}" for start, end in fo.overlapping_ranges)
        file_parts.append(f"`{fo.filename}` ({ranges})")

    files_str = ", ".join(file_parts)

    return f"**{pr_a_link}** ↔ **{pr_b_link}** — " f"{files_str} — {authors}\n\n"


def _render_cluster_section(cluster: ConflictCluster, index: int) -> str:
    """Render a multi-PR cluster with summary and collapsible detail."""
    pr_links = []
    authors: set[str] = set()
    for pr in cluster.prs:
        pr_links.append(f"[#{pr.number}]({pr.url}) {pr.title}")
        if pr.author:
            authors.add(f"@{pr.author}")

    files_str = ", ".join(f"`{f}`" for f in cluster.shared_files)
    authors_str = ", ".join(sorted(authors))

    content = (
        f"### Cluster {index} — {len(cluster.prs)} PRs, "
        f"{len(cluster.conflicts)} conflict(s)\n\n"
    )
    content += f"**Authors:** {authors_str}\n\n"
    content += f"**Files:** {files_str}\n\n"
    content += "**PRs:**\n"
    for link in pr_links:
        content += f"- {link}\n"
    content += "\n"

    content += "<details>\n<summary>Pairwise details</summary>\n\n"
    content += "| PR A | PR B | Conflicting Files " "| Overlapping Lines | Authors |\n"
    content += "|------|------|-------------------" "|-------------------|---------|\n"

    for conflict in cluster.conflicts:
        pr_a_link = (
            f"[#{conflict.pr_a.number}]({conflict.pr_a.url}) {conflict.pr_a.title}"
        )
        pr_b_link = (
            f"[#{conflict.pr_b.number}]({conflict.pr_b.url}) {conflict.pr_b.title}"
        )

        file_parts = []
        line_parts = []
        for fo in conflict.conflicting_files:
            file_parts.append(f"`{fo.filename}`")
            ranges = ", ".join(
                f"L{start}-L{end}" for start, end in fo.overlapping_ranges
            )
            line_parts.append(ranges)

        pair_authors = _format_authors_from_conflict(conflict)

        content += (
            f"| {pr_a_link} | {pr_b_link} "
            f"| {', '.join(file_parts)} | {', '.join(line_parts)} "
            f"| {pair_authors} |\n"
        )

    content += "\n</details>\n\n"
    return content


def _format_authors_from_conflict(conflict) -> str:
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
