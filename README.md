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
4. **Optionally verifies conflicts** using GitHub's merge simulation API
5. **Generates reports** in Markdown and JSON format
6. **Opens issues** in affected repositories to notify teams
7. **Sends Slack notifications** to PR authors

## Example use cases

- As an OSPO team managing a large organization, I want early warning of merge conflicts across many active pull requests so that I can reduce developer friction.
- As a development team, I want to know when two PRs are modifying the same code before either one is merged so that we can coordinate our changes.
- As a CI/CD pipeline owner, I want to proactively detect cross-PR conflicts so that merge failures are caught before they block deployments.
- As a maintainer, I want authors to be notified of potential conflicts via Slack so that they can resolve overlapping changes promptly.

## Example output

The action generates a Markdown report with a table of detected conflicts:

### owner/repo-name

| PR A | PR B | Conflicting Files | Overlapping Lines | Authors |
|------|------|-------------------|-------------------|---------|
| [#123](https://github.com/owner/repo/pull/123) Add new feature | [#456](https://github.com/owner/repo/pull/456) Refactor module | `src/main.py` | L10-L25 | @alice, @bob |
| [#789](https://github.com/owner/repo/pull/789) Update config | [#456](https://github.com/owner/repo/pull/456) Refactor module | `config/settings.yml` | L3-L8 | @carol, @bob |

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

- `Pull Requests` - Read (needed to scan open pull requests and their changed files)
- `Contents` - Read (needed to fetch file diffs and line ranges)
- `Issues` - Read and Write (needed to create conflict report issues)

##### Personal Access Token (PAT)

| field      | required | default | description                                                                                                                                              |
| ---------- | -------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GH_TOKEN` | True     | `""`    | The GitHub Token used to scan repositories. Must have read access to pull requests and contents, and write access to issues for all repositories in scope. |

#### Other Configuration Options

| field                                  | required | default                  | description                                                                                                                                                                                              |
| -------------------------------------- | -------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GH_ENTERPRISE_URL`                    | False    | `""`                     | The URL of a GitHub Enterprise instance to use for authentication instead of github.com. Example: `https://github.example.com`                                                                           |
| `ORGANIZATION`                         | True\*   | `""`                     | The name of the GitHub organization to scan for open pull requests. ie. github.com/github would be `github`                                                                                              |
| `REPOSITORY`                           | True\*   | `""`                     | A comma-separated list of repositories to scan in `owner/repo` format. ie. `github-community-projects/pr-conflict-detector` or `owner/repo1,owner/repo2`                                                |
| `INCLUDE_DRAFTS`                       | False    | `true`                   | If set to `true`, draft pull requests will be included in the conflict analysis. Set to `false` to skip draft PRs.                                                                                       |
| `VERIFY_CONFLICTS`                     | False    | `false`                  | If set to `true`, enables merge simulation verification using GitHub's API. Provides higher confidence results but requires additional API calls.                                                         |
| `EXEMPT_REPOS`                         | False    | `""`                     | A comma-separated list of repositories to exclude from scanning. Example: `owner/repo-to-skip,owner/another-repo`                                                                                        |
| `EXEMPT_PRS`                           | False    | `""`                     | A comma-separated list of PR numbers to exclude from conflict analysis. Example: `123,456,789`                                                                                                           |
| `DRY_RUN`                              | False    | `false`                  | If set to `true`, the action will generate reports but skip issue creation and Slack notifications. Useful for testing.                                                                                   |
| `REPORT_TITLE`                         | False    | `PR Conflict Report`     | The title used for the generated conflict report and any issues created.                                                                                                                                 |
| `OUTPUT_FILE`                          | False    | `pr_conflict_report.md`  | The filename for the generated Markdown report.                                                                                                                                                          |
| `SLACK_WEBHOOK_URL`                    | False    | `""`                     | Slack incoming webhook URL for sending conflict notifications. See the [Slack Integration](#slack-integration) section for setup instructions.                                                            |
| `SLACK_CHANNEL`                        | False    | `""`                     | Override the default Slack channel configured in the webhook. Example: `#pr-conflicts`                                                                                                                   |
| `ENABLE_GITHUB_ACTIONS_STEP_SUMMARY`   | False    | `true`                   | If set to `true`, the conflict report will be written to the GitHub Actions workflow summary for easy viewing in the Actions UI.                                                                          |
| `FILTER_AUTHORS`                       | False    | `""`                     | A comma-separated list of GitHub usernames. When set, only PRs authored by these users will be analyzed for conflicts. Useful for incremental rollout to specific teams. Example: `alice,bob,charlie`     |

\*One of `ORGANIZATION` or `REPOSITORY` must be set.

### Example workflows

#### Organization-wide scan

This workflow runs on weekdays at 9 AM UTC and scans all repositories in the specified organization:

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5"  # Weekdays at 9 AM UTC
  workflow_dispatch:

permissions:
  contents: read

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Detect PR Conflicts
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          ORGANIZATION: my-org
          INCLUDE_DRAFTS: "true"
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

#### Single repository

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Detect PR Conflicts
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          REPOSITORY: owner/repo-name
```

#### Multiple repositories with GitHub App authentication

```yaml
name: PR Conflict Detection
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Detect PR Conflicts
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_APP_ID: ${{ secrets.GH_APP_ID }}
          GH_APP_INSTALLATION_ID: ${{ secrets.GH_APP_INSTALLATION_ID }}
          GH_APP_PRIVATE_KEY: ${{ secrets.GH_APP_PRIVATE_KEY }}
          REPOSITORY: "owner/repo1,owner/repo2,owner/repo3"
          EXEMPT_REPOS: "owner/repo-to-skip"
          VERIFY_CONFLICTS: "true"
```

#### Incremental rollout to a specific team

If you have a large monorepo with many contributors, you can use `FILTER_AUTHORS` to limit conflict detection to your team's PRs. This lets you roll out the action incrementally without affecting other teams:

```yaml
name: PR Conflict Detection (My Team)
on:
  schedule:
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  detect-conflicts:
    name: Detect PR conflicts
    runs-on: ubuntu-latest
    steps:
      - name: Detect PR Conflicts
        uses: github-community-projects/pr-conflict-detector@v1
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          REPOSITORY: my-org/company-monolith
          FILTER_AUTHORS: "alice,bob,charlie,dana"
          DRY_RUN: "true"
```

As confidence grows, expand the author list or remove `FILTER_AUTHORS` entirely to cover all PRs.

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

## Slack integration

The action can send Slack notifications to alert PR authors about detected conflicts.

### Setup

1. Create a [Slack incoming webhook](https://api.slack.com/messaging/webhooks) for your workspace
2. Add the webhook URL as a repository secret (e.g., `SLACK_WEBHOOK_URL`)
3. Set the `SLACK_WEBHOOK_URL` environment variable in your workflow
4. Optionally set `SLACK_CHANNEL` to override the default channel configured in the webhook

### Example notification

When conflicts are detected, a Slack message is sent with the following format:

> **🔀 PR Conflict Detected**
>
> **Repository:** owner/repo-name
> **PR A:** #123 — Add new feature (@alice)
> **PR B:** #456 — Refactor module (@bob)
> **Conflicting files:** `src/main.py` (lines 10-25)

## Local development

```bash
# Clone the repository
git clone https://github.com/github-community-projects/pr-conflict-detector.git
cd pr-conflict-detector

# Set up a virtual environment
python3 -m venv venv
source venv/bin/activate

# Set up environment
cp .env-example .env
# Edit .env with your configuration

# Install dependencies
pip install -r requirements.txt -r requirements-test.txt

# Run locally
python3 pr_conflict_detector.py

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
