"""
A GitHub Action that detects potential merge conflicts between open pull requests
by analyzing overlapping file and line changes across repositories.
"""

import auth
import env
from conflict_detector import detect_conflicts
from issue_writer import create_or_update_issue
from json_writer import write_to_json
from markdown_writer import write_to_markdown
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

        # Filter by author if configured
        if env_vars.filter_authors:
            prs = [pr for pr in prs if pr.author in env_vars.filter_authors]
            if not prs:
                print(f"  No PRs from filtered authors: {env_vars.filter_authors}")
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

        if conflicts:
            all_conflicts[repo.full_name] = conflicts
            print(f"  ⚠️  Found {len(conflicts)} potential conflict(s)")
        else:
            print("  ✅ No conflicts detected")

    # 5. Generate outputs
    print(f"\n{'='*50}")
    total = sum(len(c) for c in all_conflicts.values())
    print(f"Total: {total} potential conflict(s) across {len(all_conflicts)} repo(s)")

    # Write markdown report
    write_to_markdown(
        all_conflicts,
        output_file=env_vars.output_file,
        report_title=env_vars.report_title,
        enable_step_summary=env_vars.enable_github_actions_step_summary,
    )

    # Write JSON report
    json_output = env_vars.output_file.replace(".md", ".json")
    write_to_json(all_conflicts, output_file=json_output)

    # Create/update issues in repos
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

    # Send Slack notification
    send_slack_notification(
        env_vars.slack_webhook_url,
        all_conflicts,
        channel=env_vars.slack_channel,
        dry_run=env_vars.dry_run,
    )


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
