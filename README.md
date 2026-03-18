# PR Conflict Detector

[![CodeQL](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/github-code-scanning/codeql)
[![Docker Image CI](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/docker-ci.yml/badge.svg)](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/docker-ci.yml)
[![Python package](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/python-ci.yml/badge.svg)](https://github.com/github-community-projects/pr-conflict-detector/actions/workflows/python-ci.yml)

This is a GitHub Action that detects potential merge conflicts between open pull requests by analyzing overlapping file and line changes across repositories. It scans your organization or specified repositories, identifies PRs that modify the same files and overlapping line ranges, and generates detailed reports so authors can resolve conflicts before they become a problem.

This action, developed by GitHub OSPO for our internal use, is open-sourced for your potential benefit. Feel free to inquire about its usage by creating an issue in this repository.

## How it works

1. **Scans open pull requests** (including drafts) in the specified organization or repositories
2. **Fetches changed files and line ranges** for each PR
3. **Performs pairwise comparison** to find PRs that modify overlapping lines in the same files
4. **Filters out same-author conflicts** - PRs by the same developer conflicting with each other are excluded
5. **Deduplicates alerts** - Tracks conflict history to only notify on new or changed conflicts
6. **Optionally verifies conflicts** using GitHub's merge simulation API
7. **Generates reports** in Markdown and JSON format
8. **Opens issues** in affected repositories to notify teams
9. **Posts PR comments** - Optionally comments directly on conflicting PRs with details
10. **Sends targeted Slack notifications** - One message per conflict with @mentions for affected authors

## Example use cases

- As an OSPO team managing a large organization, I want early warning of merge conflicts across many active pull requests so that I can reduce developer friction.
- As a development team, I want to know when two PRs are modifying the same code before either one is merged so that we can coordinate our changes.
- As a CI/CD pipeline owner, I want to proactively detect cross-PR conflicts so that merge failures are caught before they block deployments.
- As a maintainer, I want authors to be notified of potential conflicts via Slack so that they can resolve overlapping changes promptly.

## Example output

The action generates a Markdown report with a table of detected conflicts:

### owner/repo-name

| PR A                                                           | PR B                                                           | Conflicting Files     | Overlapping Lines | Authors      |
| -------------------------------------------------------------- | -------------------------------------------------------------- | --------------------- | ----------------- | ------------ |
| [#123](https://github.com/owner/repo/pull/123) Add new feature | [#456](https://github.com/owner/repo/pull/456) Refactor module | `src/main.py`         | L10-L25           | @alice, @bob |
| [#789](https://github.com/owner/repo/pull/789) Update config   | [#456](https://github.com/owner/repo/pull/456) Refactor module | `config/settings.yml` | L3-L8             | @carol, @bob |

## Support

If you need support using this project or have questions about it, please [open up an issue in this repository](https://github.com/github-community-projects/pr-conflict-detector/issues). Requests made directly to GitHub staff or support team will be redirected here to open an issue. GitHub SLAs and support/services contracts do not apply to this repository.

### OSPO GitHub Actions as a Whole

All feedback regarding our GitHub Actions, as a whole, should be communicated through [issues on our github-ospo repository](https://github.com/github/github-ospo/issues/new).

## Use as a GitHub Action

1. Create a repository to host this GitHub Action or select an existing repository.
2. Select a best fit workflow file from the [examples below](#example-workflows).
3. Copy that example into your repository (from step 1) and into the proper directory for GitHub Actions: `.github/workflows/` directory with the file extension `.yml` (ie. `.github/workflows/pr-conflict-detector.yml`)
4. Edit the environment variables from the sample workflow with your information. See the [Configuration](#configuration) section for details on each option.
5. Update the value of `GH_TOKEN`. Do this by creating a [GitHub API token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token-classic) with the required permissions, then [create a repository secret](https://docs.github.com/en/actions/security-guides/encrypted-secrets) where the name of the secret is `GH_TOKEN` and the value is the API token.
6. Commit the workflow file to the default branch (often `master` or `main`).
7. Wait for the action to trigger based on the `schedule` entry or manually trigger the workflow as shown in the [documentation](https://docs.github.com/en/actions/using-workflows/manually-running-a-workflow).

### Configuration

Below are the allowed configuration options:

#### Authentication

This action can be configured to authenticate with GitHub App Installation or Personal Access Token (PAT). If all configuration options are provided, the GitHub App Installation configuration has precedence. You can choose one of the following methods to authenticate:

##### GitHub App Installation

| field                        | required | default | description                                                                                                                                                                                             |
| ---------------------------- | -------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GH_APP_ID`                  | True     | `""`    | GitHub Application ID. See [documentation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app) for more details.              |
| `GH_APP_INSTALLATION_ID`     | True     | `""`    | GitHub Application Installation ID. See [documentation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app) for more details. |
| `GH_APP_PRIVATE_KEY`         | True     | `""`    | GitHub Application Private Key. See [documentation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app) for more details.     |
| `GITHUB_APP_ENTERPRISE_ONLY` | False    | `false` | Set this input to `true` if your app is created in GHE and communicates with GHE.                                                                                                                       |

The required GitHub App permissions under `Repository permissions` are:

- `Pull Requests` - Read and Write (Read: scan open pull requests and their changed files; Write: post PR comments when `ENABLE_PR_COMMENTS` is enabled)
- `Contents` - Read (needed to fetch file diffs and line ranges)
- `Issues` - Read and Write (needed to create conflict report issues)
- `Members` - Read (needed for `FILTER_TEAMS` to resolve team membership; only required if using `FILTER_TEAMS`)

##### Personal Access Token (PAT)

| field      | required | default | description                                                                                                                                                                  |
| ---------- | -------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GH_TOKEN` | True     | `""`    | The GitHub Token used to scan repositories. Must have read access to pull requests and contents, and write access to issues and pull requests for all repositories in scope. |

#### Other Configuration Options

| field                                | required | default                 | description                                                                                                                                                                                               |
| ------------------------------------ | -------- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GH_ENTERPRISE_URL`                  | False    | `""`                    | The URL of a GitHub Enterprise instance to use for authentication instead of github.com. Example: `https://github.example.com`                                                                            |
| `ORGANIZATION`                       | True\*   | `""`                    | The name of the GitHub organization to scan for open pull requests. ie. github.com/github would be `github`                                                                                               |
| `REPOSITORY`                         | True\*   | `""`                    | A comma-separated list of repositories to scan in `owner/repo` format. ie. `github-community-projects/pr-conflict-detector` or `owner/repo1,owner/repo2`                                                  |
| `INCLUDE_DRAFTS`                     | False    | `true`                  | If set to `true`, draft pull requests will be included in the conflict analysis. Set to `false` to skip draft PRs.                                                                                        |
| `VERIFY_CONFLICTS`                   | False    | `false`                 | If set to `true`, enables merge simulation verification using GitHub's API. Provides higher confidence results but requires additional API calls.                                                         |
| `EXEMPT_REPOS`                       | False    | `""`                    | A comma-separated list of repositories to exclude from scanning. Example: `owner/repo-to-skip,owner/another-repo`                                                                                         |
| `EXEMPT_PRS`                         | False    | `""`                    | A comma-separated list of PR numbers to exclude from conflict analysis. Example: `123,456,789`                                                                                                            |
| `DRY_RUN`                            | False    | `false`                 | If set to `true`, the action will generate reports but skip issue creation, Slack notifications, PR comments, and state file modifications. Useful for testing.                                           |
| `REPORT_TITLE`                       | False    | `PR Conflict Report`    | The title used for the generated conflict report and any issues created.                                                                                                                                  |
| `OUTPUT_FILE`                        | False    | `pr_conflict_report.md` | The filename for the generated Markdown report.                                                                                                                                                           |
| `SLACK_WEBHOOK_URL`                  | False    | `""`                    | Slack incoming webhook URL for sending conflict notifications. See the [Slack Integration](#slack-integration) section for setup instructions.                                                            |
| `SLACK_CHANNEL`                      | False    | `""`                    | Override the default Slack channel configured in the webhook. Example: `#pr-conflicts`                                                                                                                    |
| `ENABLE_GITHUB_ACTIONS_STEP_SUMMARY` | False    | `true`                  | If set to `true`, the conflict report will be written to the GitHub Actions workflow summary for easy viewing in the Actions UI.                                                                          |
| `FILTER_AUTHORS`                     | False    | `""`                    | A comma-separated list of GitHub usernames. When set, only PRs authored by these users will be analyzed for conflicts. Useful for incremental rollout to specific teams. Example: `alice,bob,charlie`     |
| `FILTER_TEAMS`                       | False    | `""`                    | A comma-separated list of GitHub teams (`org/team-slug`). Members are resolved at runtime and merged with `FILTER_AUTHORS`. Requires `read:org` scope. Example: `my-org/frontend,my-org/backend`          |
| `ENABLE_PR_COMMENTS`                 | False    | `false`                 | If set to `true`, the action will post comments on PRs about detected conflicts. Comments include conflicting files, line ranges, and links to the other PR. See [PR Comments](#pr-comments) for details. |
| `ENABLE_REPORT_ISSUES`               | False    | `true`                  | If set to `true`, the action will create/update conflict report issues in each repository. Set to `false` to disable issue creation while keeping PR comments and step summaries.                         |

\*One of `ORGANIZATION` or `REPOSITORY` must be set.

### Example workflows

#### Organization-wide scan

This workflow runs on weekdays at 9 AM UTC and scans all repositories in the specified organization:

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5" # Weekdays at 9 AM UTC
  workflow_dispatch:

permissions:
  issues: write
  pull-requests: write

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Restore conflict state
        uses: actions/cache/restore@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: pr-conflict-state-

      - name: Detect PR Conflicts
        id: detect
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          ORGANIZATION: my-org
          INCLUDE_DRAFTS: "true"
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}

      - name: Save conflict state
        if: steps.detect.outcome == 'success'
        uses: actions/cache/save@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
```

#### Single repository

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  issues: write
  pull-requests: write

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Restore conflict state
        uses: actions/cache/restore@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: pr-conflict-state-

      - name: Detect PR Conflicts
        id: detect
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          REPOSITORY: owner/repo-name

      - name: Save conflict state
        if: steps.detect.outcome == 'success'
        uses: actions/cache/save@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
```

#### Multiple repositories with GitHub App authentication

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  issues: write
  pull-requests: write

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Restore conflict state
        uses: actions/cache/restore@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: pr-conflict-state-

      - name: Detect PR Conflicts
        id: detect
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_APP_ID: ${{ secrets.GH_APP_ID }}
          GH_APP_INSTALLATION_ID: ${{ secrets.GH_APP_INSTALLATION_ID }}
          GH_APP_PRIVATE_KEY: ${{ secrets.GH_APP_PRIVATE_KEY }}
          REPOSITORY: "owner/repo1,owner/repo2,owner/repo3"
          EXEMPT_REPOS: "owner/repo-to-skip"
          VERIFY_CONFLICTS: "true"

      - name: Save conflict state
        if: steps.detect.outcome == 'success'
        uses: actions/cache/save@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
```

#### Incremental rollout to a specific team

If you have a large monorepo with many contributors, you can use `FILTER_AUTHORS` or `FILTER_TEAMS` to limit conflict detection to your team's PRs. This lets you roll out the action incrementally without affecting other teams:

```yaml
name: PR Conflict Detection (My Team)
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  issues: write
  pull-requests: write

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Restore conflict state
        uses: actions/cache/restore@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
          restore-keys: pr-conflict-state-

      - name: Detect PR Conflicts
        id: detect
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          REPOSITORY: my-org/company-monolith
          FILTER_TEAMS: "my-org/frontend-team,my-org/backend-team"
          DRY_RUN: "true"

      - name: Save conflict state
        if: steps.detect.outcome == 'success'
        uses: actions/cache/save@v4
        with:
          path: .pr-conflict-state.json
          key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
```

You can also combine `FILTER_TEAMS` with `FILTER_AUTHORS` — the members are merged (union):

```yaml
env:
  FILTER_TEAMS: "my-org/frontend-team"
  FILTER_AUTHORS: "alice,bob" # Additional individual users
```

As confidence grows, expand the team list or remove the filters entirely to cover all PRs.

> **Note:** `FILTER_TEAMS` requires the token to have `read:org` scope to resolve team membership. If a team is not found or the token lacks permissions, the action logs a warning and skips that team.

## How conflict detection works

The action uses a hybrid approach combining efficient file-based grouping with optional merge simulation:

### Phase 1 — File and line overlap analysis

For each open pull request, the action fetches the list of changed files and their modified line ranges. It then groups PRs by the files they modify and checks for overlapping line ranges within each group. This approach is efficient — grouping is O(n) and pairwise comparison only occurs within file groups — avoiding the cost of comparing every PR against every other PR.

### Phase 2 — Merge simulation (optional)

When `VERIFY_CONFLICTS` is set to `true`, the action uses GitHub's API to attempt merge simulations for candidate conflicts identified in Phase 1. This provides higher confidence results by confirming that the overlapping changes would actually produce a merge conflict, but requires additional API calls.

### Performance

- Scales to hundreds of open PRs per repository
- File grouping algorithm avoids O(n²) pairwise comparison across all PRs
- Rate limit aware with graceful handling of GitHub API limits

## Deduplication and alert fatigue prevention

The action tracks conflict history in a `.pr-conflict-state.json` state file. This prevents alert fatigue by only notifying about new or changed conflicts.

### How it works - details

Each conflict is fingerprinted by:

- Repository name
- PR numbers (A and B)
- List of conflicting files
- First detection timestamp

On each run, the action:

1. Loads the previous state file
2. Compares current conflicts against historical state
3. Categorizes conflicts as:
   - **New** - Not seen before → Slack notification sent
   - **Changed** - Same PR pair but different files → Slack notification sent
   - **Unchanged** - Same PRs, same files → No notification (already alerted)
   - **Resolved** - Was in state but not detected now → Logged for reference
4. Updates the state file with current conflicts
5. Auto-prunes fingerprints older than 42 days

### Example behavior

```markdown
Run 1: Detects 10 conflicts → All are new → 10 Slack messages sent
Run 2: Same 10 conflicts → All unchanged → No Slack messages
Run 3: 9 unchanged, 1 changed files → 1 Slack message for the changed conflict
Run 4: 2 conflicts resolved, 1 new → 1 Slack message for the new conflict
```

### Same-author filtering

Conflicts where both PRs are authored by the same person are automatically filtered out. If Alice has PR #123 and PR #456 that conflict, she likely already knows about both and can manage the conflict herself when merging.

### State file management

- **Location:** `.pr-conflict-state.json` in the workspace
- **Format:** JSON with conflict fingerprints and a `last_run` timestamp
- **Atomic writes:** The state file is written atomically (via temp file + rename) to prevent corruption if the action is interrupted
- **Dry run:** When `DRY_RUN=true`, the state file is not modified

#### Persisting state across runs

The action writes the state file to the workspace during each run. To preserve state between runs (required for deduplication to work), you need to persist the file using one of the strategies below.

> **Important:** If state is lost (e.g., cache eviction, first run), the action automatically detects this and suppresses notifications for that run while rebuilding state. This prevents a flood of duplicate alerts. On the next run, notifications resume normally.

#### Option 1: GitHub Actions cache (recommended)

The simplest and most compatible approach. Works with any branch protection configuration and requires no special permissions.

```yaml
permissions: {} # no special permissions needed

steps:
  - name: Restore conflict state
    uses: actions/cache/restore@v4
    with:
      path: .pr-conflict-state.json
      key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
      restore-keys: pr-conflict-state-

  - name: Detect PR Conflicts
    id: detect
    uses: github-community-projects/pr-conflict-detector@v1
    env:
      GH_TOKEN: ${{ secrets.GH_TOKEN }}
      ORGANIZATION: "my-org"

  - name: Save conflict state
    if: steps.detect.outcome == 'success'
    uses: actions/cache/save@v4
    with:
      path: .pr-conflict-state.json
      key: pr-conflict-state-${{ github.run_id }}-${{ github.run_attempt }}
```

**How it works:**

- `restore-keys` prefix matching always finds the most recent saved state
- Each run saves with a unique key (`run_id` + `run_attempt`), so entries are never overwritten and re-runs create their own cache entry
- Old entries are evicted automatically by LRU within GitHub's 10GB cache limit

**Note:** GitHub evicts cache entries not accessed within 7 days. If your workflow only triggers infrequently (e.g., on push to the default branch), state may be lost during quiet periods. For reliable deduplication, use a scheduled trigger:

```yaml
on:
  schedule:
    - cron: "0,30 * * * 1-5" # every 30 min on weekdays
```

**Best practices for scheduled workflows:**

If your detection step takes longer than your schedule interval (e.g., scanning large repos with `VERIFY_CONFLICTS: "true"`), overlapping runs can restore the same stale state and send duplicate notifications. Add a `concurrency` group to queue runs instead of running them in parallel:

```yaml
concurrency:
  group: pr-conflict-detection
  cancel-in-progress: false
```

With `cancel-in-progress: false`, the queued run waits for the current run to finish and save its state. When the queued run starts, it restores the freshly saved state and deduplicates correctly. GitHub automatically cancels the oldest pending run if a third one queues, so at most one run is waiting at any time.

#### Option 2: Git commit-back

Commit the state file directly to the repository. This makes state visible in git history and avoids cache eviction concerns, but requires the workflow to have push access to the target branch.

```yaml
permissions:
  contents: write

steps:
  - name: Checkout repository
    uses: actions/checkout@v4

  - name: Detect PR Conflicts
    id: detect
    uses: github-community-projects/pr-conflict-detector@v1
    env:
      GH_TOKEN: ${{ secrets.GH_TOKEN }}
      ORGANIZATION: "my-org"

  - name: Commit state file
    if: steps.detect.outcome == 'success'
    run: |
      if [ -f .pr-conflict-state.json ]; then
        git config user.name "github-actions[bot]"
        git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
        git add .pr-conflict-state.json
        if ! git diff --staged --quiet; then
          git commit -m "chore: update pr-conflict-detector state [skip ci]"
          git push
        fi
      fi
```

**⚠️ Limitations:**

- **Branch protection:** Repositories with required PR reviews will block the push unless `github-actions[bot]` is added to the bypass list
- **Permissions:** Requires `contents: write`, which may not be acceptable for security-conscious organizations
- **Race conditions:** Concurrent runs may conflict on push if one takes longer than the schedule interval

#### Option 3: No persistence

If you don't need deduplication (e.g., you only run the action on-demand via `workflow_dispatch`), you can skip state persistence entirely. The action will treat every detected conflict as new and send notifications for all of them on each run.

## Slack integration

The action sends targeted Slack notifications with @mentions to alert PR authors about conflicts. Each conflict gets its own message to avoid notification overload.

### Setup

1. Create a [Slack incoming webhook](https://api.slack.com/messaging/webhooks) for your workspace
2. Add the webhook URL as a repository secret (e.g., `SLACK_WEBHOOK_URL`)
3. Set the `SLACK_WEBHOOK_URL` environment variable in your workflow
4. Optionally set `SLACK_CHANNEL` to override the default channel configured in the webhook

### Notification format

**For simple 2-PR conflicts:**

```markdown
<@alice> <@bob> Your PRs may conflict:

github/repo-name
#123 (Add authentication) ↔ #456 (Refactor auth module)

Files:
• `src/auth.py` (L10-L25, L42-L55)
• `src/middleware.py` (L100-L120)
```

**For multi-PR clusters (3+ PRs conflicting on same files):**

```markdown
<@alice> <@bob> <@charlie> Your PRs may conflict:

github/repo-name — Cluster: 3 PRs, 3 conflict pair(s)

PRs:
• #123 Add authentication
• #456 Refactor auth module
• #789 Update auth tests

Shared files: `src/auth.py`, `src/middleware.py`
```

### Key features of slack integration

- **One message per conflict** - Users only see conflicts relevant to them
- **@mentions** - Authors are mentioned (assumes GitHub username = Slack username)
- **Line ranges** - Shows exactly where overlaps occur
- **Deduplication** - Only sends for new or changed conflicts (see [Deduplication](#deduplication-and-alert-fatigue-prevention))
- **Same-author filtering** - No notifications for conflicts between your own PRs

## PR Comments

The action can post comments directly on pull requests to notify authors about conflicts. This provides in-context notifications that developers see when reviewing their PRs.

### Getting Setup

1. Ensure your GitHub token has write access to pull requests
2. Set `ENABLE_PR_COMMENTS=true` in your workflow environment variables
3. The action will automatically post comments on both PRs in each conflict pair

### Comment format

Each PR receives a comment like this:

```markdown
## ⚠️ Potential Merge Conflict Detected

This PR may conflict with [#456](https://github.com/org/repo/pull/456) (Refactor auth module).

### Conflicting Files

- `src/auth.py` (lines: L10-L25, L42-L55)
- `src/middleware.py` (lines: L100-L120)

### What to do

- Review the overlapping changes in the files above
- Coordinate with @bob to resolve conflicts
- Consider rebasing or merging to test compatibility

This is an automated notification from pr-conflict-detector.
```

### Duplicate prevention

- Each comment includes a hidden bot signature (`<!-- pr-conflict-detector-bot -->`)
- Before posting, the action checks if a comment already exists for this specific conflict
- If found (signature + other PR number present), the comment is skipped
- Works with deduplication: only comments on new or changed conflicts

### Key features of PR comments

- **Two-way notification** - Both PRs in the conflict get a comment
- **Detailed context** - Shows exact files and line ranges
- **Smart deduplication** - Won't spam PRs with duplicate comments
- **Actionable guidance** - Tells developers what to do next
- **Graceful error handling** - If comment check fails, assumes no duplicate to avoid blocking

### Example workflow

```yaml
env:
  GH_TOKEN: ${{ secrets.GH_TOKEN }}
  ORGANIZATION: my-org
  ENABLE_PR_COMMENTS: "true" # Enable PR comments
  SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Local development

```bash
# Clone the repository
git clone https://github.com/github-community-projects/pr-conflict-detector.git
cd pr-conflict-detector

# Set up environment
cp .env-example .env
# Edit .env with your configuration

# Install dependencies
uv sync

# Run locally
uv run pr_conflict_detector.py

# Run tests
make test

# Run linting
make lint
```

## Contributing

Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for details on how to contribute to this project, including information on reporting bugs, suggesting enhancements, and submitting pull requests.

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## License

[MIT](./LICENSE)
