"""
A GitHub Action that detects potential merge conflicts between open pull requests
by analyzing overlapping file and line changes across repositories.
"""

import auth
import deduplication
import env
from conflict_detector import detect_conflicts
from issue_writer import create_or_update_issue
from json_writer import write_to_json
from markdown_writer import write_to_markdown
from pr_comment import post_pr_comments
from pr_data import fetch_all_pr_data
from slack_notify import send_slack_notification


def main():
    """Run the PR conflict detector."""

    # 1. Get environment variables
    env_vars = env.get_env_vars()

    # 2. Authenticate to GitHub
    github_connection = auth.auth_to_github(
        env_vars.token,
        env_vars.gh_app_id,
        env_vars.gh_app_installation_id,
        env_vars.gh_app_private_key_bytes,
        env_vars.ghe,
        env_vars.gh_app_enterprise_only,
    )

    # 2b. Resolve FILTER_TEAMS into usernames and merge with FILTER_AUTHORS
    combined_filter_authors = set(env_vars.filter_authors)
    if env_vars.filter_teams:
        print("\nResolving FILTER_TEAMS...")
        for team_ref in env_vars.filter_teams:
            parts = team_ref.split("/", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                print(
                    f"  ⚠️  Invalid team format '{team_ref}', expected 'org/team-slug'"
                )
                continue
            org, team_slug = parts
            members = auth.get_team_members(github_connection, org, team_slug)
            combined_filter_authors.update(members)

        if env_vars.filter_authors:
            print(
                f"Combined {len(env_vars.filter_authors)} FILTER_AUTHORS + "
                f"team members = {len(combined_filter_authors)} unique author(s)"
            )
        else:
            print(
                f"Resolved {len(combined_filter_authors)} unique author(s) from teams"
            )

    # Build the effective filter list
    effective_filter_authors = sorted(combined_filter_authors)

    # 3. Get repositories to scan
    repos = get_repos_iterator(github_connection, env_vars)

    # 4. For each repo, fetch PRs and detect conflicts
    all_conflicts = {}  # {repo_full_name: list[ConflictResult]}

    for repo in repos:
        # Skip exempt repos
        if (
            repo.full_name in env_vars.exempt_repos
            or repo.name in env_vars.exempt_repos
        ):
            print(f"Skipping exempt repo: {repo.full_name}")
            continue

        if repo.archived:
            print(f"Skipping archived repo: {repo.full_name}")
            continue

        print(f"\nScanning {repo.full_name}...")

        # Fetch all open PR data
        owner, repo_name = repo.full_name.split("/")
        prs = fetch_all_pr_data(
            repo, env_vars.include_drafts, github_connection, owner, repo_name
        )

        # Filter exempt PRs
        if env_vars.exempt_prs:
            prs = [pr for pr in prs if pr.number not in env_vars.exempt_prs]

        # Filter by author if configured (FILTER_AUTHORS and/or FILTER_TEAMS)
        if effective_filter_authors:
            prs = [pr for pr in prs if pr.author in effective_filter_authors]
            if not prs:
                print(f"  No PRs from filtered authors: {effective_filter_authors}")
                continue

        if len(prs) < 2:
            print(f"  {len(prs)} open PR(s) - need at least 2 to detect conflicts")
            continue

        print(f"  Found {len(prs)} open PRs, analyzing for conflicts...")

        # Detect conflicts
        conflicts = detect_conflicts(
            prs,
            verify=env_vars.verify_conflicts,
            github_connection=github_connection,
            owner=owner,
            repo_name=repo_name,
        )

        # Filter out conflicts where both PRs have the same author
        if conflicts:
            original_count = len(conflicts)
            conflicts = [c for c in conflicts if c.pr_a.author != c.pr_b.author]
            filtered_count = original_count - len(conflicts)
            if filtered_count > 0:
                print(
                    f"  Filtered {filtered_count} same-author conflict(s) "
                    f"({len(conflicts)} remaining)"
                )

        if conflicts:
            all_conflicts[repo.full_name] = conflicts
            print(f"  ⚠️  Found {len(conflicts)} potential conflict(s)")
        else:
            print("  ✅ No conflicts detected")

    # 5. Apply deduplication
    print(f"\n{'='*50}")
    total = sum(len(c) for c in all_conflicts.values())
    print(f"Total: {total} potential conflict(s) across {len(all_conflicts)} repo(s)")

    # Load and prune state
    state = deduplication.load_state()
    state = deduplication.prune_expired_conflicts(state)

    # Compare current vs historical
    dedup_result = deduplication.compare_conflicts(all_conflicts, state)

    print(
        f"Deduplication: {len(dedup_result.new_conflicts)} new, "
        f"{len(dedup_result.changed_conflicts)} changed, "
        f"{len(dedup_result.unchanged_conflicts)} unchanged, "
        f"{len(dedup_result.resolved_fingerprints)} resolved"
    )

    # Update state with current conflicts (skip saving in dry run)
    updated_state = deduplication.update_state_with_current(all_conflicts, state)
    if not env_vars.dry_run:
        deduplication.save_state(updated_state)
    else:
        print("DRY RUN: Skipping state file save")

    # Conflicts to notify about (new + changed)
    notify_conflicts: dict[str, list] = {}
    for conflict in dedup_result.new_conflicts + dedup_result.changed_conflicts:
        # Find which repo this conflict belongs to
        for repo_name, conflicts in all_conflicts.items():
            if conflict in conflicts:
                if repo_name not in notify_conflicts:
                    notify_conflicts[repo_name] = []
                notify_conflicts[repo_name].append(conflict)
                break

    # 6. Generate outputs
    # Write markdown report (always generated, full results)
    write_to_markdown(
        all_conflicts,
        output_file=env_vars.output_file,
        report_title=env_vars.report_title,
        enable_step_summary=env_vars.enable_github_actions_step_summary,
    )

    # Write JSON report
    json_output = env_vars.output_file.replace(".md", ".json")
    write_to_json(all_conflicts, output_file=json_output)

    # Create/update issues in repos (all conflicts, not just new)
    if not env_vars.dry_run:
        for repo_full_name, conflicts in all_conflicts.items():
            owner, rname = repo_full_name.split("/")
            repo_obj = github_connection.repository(owner, rname)
            issue_url = create_or_update_issue(
                repo_obj, conflicts, env_vars.report_title, env_vars.dry_run
            )
            if issue_url:
                print(f"  Created/updated issue: {issue_url}")
    else:
        print("DRY RUN: Skipping issue creation")

    # Send Slack notification (only for new + changed conflicts)
    if notify_conflicts:
        print(
            f"Sending Slack notifications for {sum(len(c) for c in notify_conflicts.values())} conflict(s)"
        )
        send_slack_notification(
            env_vars.slack_webhook_url,
            notify_conflicts,
            channel=env_vars.slack_channel,
            dry_run=env_vars.dry_run,
        )
    else:
        print("No new or changed conflicts — skipping Slack notifications")

    # Post PR comments (only for new + changed conflicts)
    if env_vars.enable_pr_comments and notify_conflicts:
        print(
            f"Posting PR comments for {sum(len(c) for c in notify_conflicts.values())} conflict(s)"
        )
        post_pr_comments(
            notify_conflicts,
            github_connection,
            dry_run=env_vars.dry_run,
        )
    elif env_vars.enable_pr_comments:
        print("No new or changed conflicts — skipping PR comments")


def get_repos_iterator(github_connection, env_vars):
    """Get an iterator of repositories to scan.

    Args:
        github_connection: Authenticated github3 connection.
        env_vars: Environment variables dataclass.

    Returns:
        Iterator of github3 repository objects.
    """
    if env_vars.organization and not env_vars.repository_list:
        return github_connection.organization(env_vars.organization).repositories()

    repos = []
    for repo_full_name in env_vars.repository_list:
        owner, repo_name = repo_full_name.split("/")
        repos.append(github_connection.repository(owner, repo_name))
    return repos


if __name__ == "__main__":  # pragma: no cover
    main()
