"""Core logic for detecting potential merge conflicts between open pull requests."""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from pr_data import ChangedFile, PullRequestData


@dataclass
class FileOverlap:
    """Details about a file overlap between two PRs."""

    filename: str
    pr_a_lines: list[tuple[int, int]]
    pr_b_lines: list[tuple[int, int]]
    overlapping_ranges: list[tuple[int, int]]


@dataclass
class PRInfo:
    """Minimal PR information stored within a ConflictResult."""

    number: int
    title: str
    author: str
    url: str


@dataclass
class ConflictResult:
    """A potential conflict between two PRs."""

    pr_a: PRInfo
    pr_b: PRInfo
    conflicting_files: list[FileOverlap] = field(default_factory=list)
    verified: bool = False


@dataclass
class ConflictCluster:
    """A group of PRs that are transitively connected by conflicts."""

    prs: list[PRInfo] = field(default_factory=list)
    conflicts: list[ConflictResult] = field(default_factory=list)
    shared_files: list[str] = field(default_factory=list)


def ranges_overlap(range_a: tuple[int, int], range_b: tuple[int, int]) -> bool:
    """Check if two line ranges (start, end) overlap.

    Returns True if there is any intersection between the two ranges,
    including when they share a single boundary point.
    """
    return range_a[0] <= range_b[1] and range_b[0] <= range_a[1]


def find_overlapping_ranges(
    ranges_a: list[tuple[int, int]], ranges_b: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Given two lists of line ranges, find all overlapping regions.

    Returns the intersection ranges where both lists have coverage.
    """
    overlaps: list[tuple[int, int]] = []
    for a in ranges_a:
        for b in ranges_b:
            if ranges_overlap(a, b):
                overlap_start = max(a[0], b[0])
                overlap_end = min(a[1], b[1])
                overlaps.append((overlap_start, overlap_end))
    return overlaps


def find_file_overlaps(prs: list[PullRequestData]) -> list[ConflictResult]:
    """Find PR pairs with overlapping file and line changes.

    Builds an index of filename -> list of (pr, ChangedFile) tuples, then checks
    line range overlaps only within file groups. This is O(n) for building the index,
    then pairwise only within file groups — much more efficient than O(n²) full
    pairwise comparison.
    """
    # Build file index: filename -> list of (pr, changed_file)
    file_index: dict[str, list[tuple[PullRequestData, ChangedFile]]] = defaultdict(list)
    for pr in prs:
        for changed_file in pr.changed_files:
            file_index[changed_file.filename].append((pr, changed_file))

    # Track conflicts by PR pair to group multiple file overlaps together
    pair_conflicts: dict[tuple[int, int], ConflictResult] = {}

    for filename, pr_file_pairs in file_index.items():
        if len(pr_file_pairs) < 2:
            continue

        for (pr_a, file_a), (pr_b, file_b) in combinations(pr_file_pairs, 2):
            overlapping = find_overlapping_ranges(
                file_a.patch_lines, file_b.patch_lines
            )
            if not overlapping:
                continue

            # Ensure consistent ordering by PR number
            if pr_a.number > pr_b.number:
                pr_a, pr_b = pr_b, pr_a
                file_a, file_b = file_b, file_a

            pair_key = (pr_a.number, pr_b.number)

            if pair_key not in pair_conflicts:
                pair_conflicts[pair_key] = ConflictResult(
                    pr_a=PRInfo(
                        number=pr_a.number,
                        title=pr_a.title,
                        author=pr_a.author,
                        url=pr_a.html_url,
                    ),
                    pr_b=PRInfo(
                        number=pr_b.number,
                        title=pr_b.title,
                        author=pr_b.author,
                        url=pr_b.html_url,
                    ),
                )

            pair_conflicts[pair_key].conflicting_files.append(
                FileOverlap(
                    filename=filename,
                    pr_a_lines=file_a.patch_lines,
                    pr_b_lines=file_b.patch_lines,
                    overlapping_ranges=overlapping,
                )
            )

    return list(pair_conflicts.values())


def verify_conflict(
    conflict: ConflictResult,
    github_connection: object,
    owner: str,
    repo_name: str,
) -> bool:
    """Try to verify a conflict using the GitHub API.

    This is a best-effort check that uses the repository's merge endpoint
    or checks mergeable status. Returns False if the API call fails.

    Note: This makes additional API calls, so it should only be used
    when VERIFY_CONFLICTS=true.
    """
    try:
        repo = github_connection.repository(owner, repo_name)  # type: ignore[union-attr]
        pr_a = repo.pull_request(conflict.pr_a.number)
        pr_b = repo.pull_request(conflict.pr_b.number)

        # If either PR is not mergeable on its own, they likely conflict
        if pr_a.mergeable is False or pr_b.mergeable is False:
            return True

        return False
    except Exception:  # pylint: disable=broad-except
        return False


def detect_conflicts(
    prs: list[PullRequestData],
    verify: bool = False,
    github_connection: object = None,
    owner: str = "",
    repo_name: str = "",
) -> list[ConflictResult]:
    """Detect potential merge conflicts between open pull requests.

    Phase 1: Find PR pairs with overlapping file and line changes.
    Phase 2 (if verify=True): Use the GitHub API to confirm conflicts.

    Returns a list of ConflictResult objects sorted by number of conflicting
    files (most first).
    """
    # Phase 1: File and line overlap analysis
    conflicts = find_file_overlaps(prs)

    # Phase 2: Optional API-based verification
    if verify and github_connection:
        for conflict in conflicts:
            conflict.verified = verify_conflict(
                conflict, github_connection, owner, repo_name
            )

    # Sort by number of conflicting files, most first
    conflicts.sort(key=lambda c: len(c.conflicting_files), reverse=True)

    return conflicts


def cluster_conflicts(conflicts: list[ConflictResult]) -> list[ConflictCluster]:
    """Group pairwise conflicts into clusters of transitively connected PRs.

    Uses union-find to merge PR pairs that share conflicts into connected
    components. Each cluster contains all PRs and all pairwise conflicts
    within the group.
    """
    if not conflicts:
        return []

    # Union-Find
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Build PR info lookup and union all pairs
    pr_lookup: dict[int, PRInfo] = {}
    for conflict in conflicts:
        pr_lookup[conflict.pr_a.number] = conflict.pr_a
        pr_lookup[conflict.pr_b.number] = conflict.pr_b
        union(conflict.pr_a.number, conflict.pr_b.number)

    # Group conflicts by cluster root
    cluster_conflicts_map: dict[int, list[ConflictResult]] = defaultdict(list)
    cluster_prs: dict[int, set[int]] = defaultdict(set)

    for conflict in conflicts:
        root = find(conflict.pr_a.number)
        cluster_conflicts_map[root].append(conflict)
        cluster_prs[root].add(conflict.pr_a.number)
        cluster_prs[root].add(conflict.pr_b.number)

    # Build ConflictCluster objects
    clusters = []
    for root, pr_numbers in cluster_prs.items():
        prs = sorted([pr_lookup[n] for n in pr_numbers], key=lambda p: p.number)
        cluster_conflict_list = cluster_conflicts_map[root]

        # Collect all filenames involved in this cluster
        all_files: set[str] = set()
        for conflict in cluster_conflict_list:
            for fo in conflict.conflicting_files:
                all_files.add(fo.filename)

        clusters.append(
            ConflictCluster(
                prs=prs,
                conflicts=cluster_conflict_list,
                shared_files=sorted(all_files),
            )
        )

    # Sort clusters: largest first
    clusters.sort(key=lambda c: len(c.prs), reverse=True)
    return clusters
