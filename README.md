# graph-sync GitHub Action

GitHub Action to install `worai` and run:

- `worai graph sync --profile <name> [--debug]`
- `worai --config <path> graph sync --profile <name> [--debug]`

## Requirements

- Python (`python3` or `python`) must be available on the runner.
- `profile` is required and must exist in the selected `worai` config.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `profile` | Yes | - | Profile name passed to `--profile`. Must exist in selected config. |
| `config_path` | No | `''` | If set, action runs `worai --config <path> ...`. |
| `debug` | No | `false` | When truthy (`true/1/yes`), appends `--debug`. |
| `working_directory` | No | `.` | Directory where `worai` runs. |
| `worai_version` | No | `6.0.0` | Exact `worai` version installed by the action. |

## Behavior

- If `config_path` is set, command is:
  - `worai --config <path> graph sync --profile <name> [--debug]`
- If `config_path` is not set, command is:
  - `worai graph sync --profile <name> [--debug]`

Without root `--config`, standard `worai` config discovery applies:

- `WORAI_CONFIG`
- `./worai.toml`
- `~/.config/worai/config.toml`
- `~/.worai.toml`

## Notes

- Supported input sources are managed by `worai` config: `urls`, `sitemap_url` (+ optional `sitemap_url_pattern`), and Google Sheets (`sheets_url` + `sheets_name` + `sheets_service_account`).
- `sheets_service_account` accepts inline JSON object content or a file path.
- For Google Sheets source, `sheets_service_account` is required and the command fails when:
  - value is missing or empty
  - value is neither valid JSON object content nor an existing file path
  - value is valid JSON but not an object
- `google_search_console` can be global or profile-level in `worai.toml`; profile value overrides global value; default is `false` when unset; maps to SDK setting `GOOGLE_SEARCH_CONSOLE`.
- The command fails when selected profile does not define `api_key`.

## Minimal Usage

```yaml
name: Sync graph
on:
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: wordlift/graph-sync@v6
        with:
          profile: production
```

## Typical Usage (Repo Config File)

Use this when `worai.toml` is in your repository.

```yaml
name: Sync graph
on:
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: wordlift/graph-sync@v6
        with:
          profile: production
          config_path: ./worai.toml
          debug: false
```

## Optional Runner Setup

- `actions/checkout` is required only if your config file is in the repo workspace.
- `actions/setup-python` is optional on GitHub-hosted runners (Python is usually preinstalled), but recommended if you want a fixed Python version.

## worai Config Examples

Multi-market Google Sheets setup (anonymized as `acme`):

```toml
[profiles._base]
sheets_url = "https://docs.google.com/spreadsheets/d/ACME_SPREADSHEET_ID"
sheets_service_account = "${SHEETS_SERVICE_ACCOUNT}"
concurrency = 8
overwrite = true

[profiles.de]
api_key = "${WORDLIFT_API_KEY_DE}"
sheets_name = "URLs_DE"

[profiles.at]
api_key = "${WORDLIFT_API_KEY_AT}"
sheets_name = "URLs_AT"

[profiles.ch]
api_key = "${WORDLIFT_API_KEY_CH}"
sheets_name = "URLs_CH"

[profiles.us]
api_key = "${WORDLIFT_API_KEY_US}"
sheets_name = "URLs_US"
```

## Release and Pinning

- Publish immutable releases and move major tags (`v1`, `v2`) only by creating new immutable release tags.
- Consumers should pin this action to a full commit SHA for maximum integrity.
- If using tags, prefer stable major tags (`@v6`) and keep them mapped to immutable release commits.
- This repository includes automated release workflow `.github/workflows/release.yml` triggered by pushing tags like `v6.0.0`.
- Marketplace publication itself is still a manual GitHub UI step; the release workflow adds a summary with a direct release link and checklist.
- Versioning strategy and compatibility policy are documented in `VERSIONING.md`.

## Migration from `@v1`

- Replace `uses: wordlift/graph-sync@v1` with `uses: wordlift/graph-sync@v6`.
- Action `v6` defaults to installing `worai` `6.0.0`.

## Development

Run tests locally:

```bash
./tests/run-worai.sh
./tests/install-worai.sh
```
