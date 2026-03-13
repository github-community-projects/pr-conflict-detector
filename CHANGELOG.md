# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-03-14

### Initial stable release

PR Conflict Detector is now considered stable and ready for production use.

### Features

- **Cross-repository conflict detection** - Scan an entire organization, a single repository, or a list of repositories for overlapping PR changes
- **Line-level analysis** - Detects conflicts at the line range level, not just file overlap
- **Same-author filtering** - Automatically excludes conflicts where both PRs are authored by the same person
- **Conflict deduplication** - Tracks conflict history via GitHub Issues to only notify on new or changed conflicts
- **Merge simulation verification** - Optionally verifies conflicts using GitHub's merge API (`VERIFY_CONFLICTS`)
- **Draft PR support** - Optionally includes draft PRs in analysis (`INCLUDE_DRAFTS`)
- **Author and team filtering** - Filter analysis to specific authors (`FILTER_AUTHORS`) or teams (`FILTER_TEAMS`)
- **Multiple output formats**:
  - Markdown report with GitHub Actions step summary
  - JSON report for programmatic consumption
  - GitHub Issues opened in affected repositories
  - PR comments posted directly on conflicting PRs (`ENABLE_PR_COMMENTS`)
  - Per-conflict Slack notifications with @mentions (`SLACK_WEBHOOK_URL`, `SLACK_CHANNEL`)
- **Flexible authentication** - Supports GitHub App credentials, personal access tokens, and `GITHUB_TOKEN`
- **GitHub Enterprise Server support** via `GH_ENTERPRISE_URL`
- **Scalable** - Handles organizations with hundreds of open pull requests via pagination and rate limit awareness
