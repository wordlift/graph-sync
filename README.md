# graph-sync GitHub Action

GitHub Action to install `worai`, install Python Playwright + Chromium, and run:

- `worai --profile <name> graph sync run [--debug]`
- `worai --config <path> --profile <name> graph sync run [--debug]`

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
| `worai_version` | No | `6.12.12` | Exact `worai` version installed by the action. |
| `install_playwright` | No | `true` | Installs Playwright Python package and browser binaries when truthy (`true/1/yes`). |
| `playwright_version` | No | `1.55.0` | Exact Playwright Python package version installed when Playwright install is enabled. |
| `playwright_browser` | No | `chromium` | Browser passed to `python -m playwright install`. |
| `cache_enabled` | No | `true` | Enables dependency cache for pip and Playwright browser binaries when truthy (`true/1/yes`). |
| `cache_key_suffix` | No | `''` | Optional cache key suffix. When empty, action derives `<worai_version>-<playwright_version>-<playwright_browser>`. |

## Behavior

- If `config_path` is set, command is:
  - `worai --config <path> --profile <name> graph sync run [--debug]`
- If `config_path` is not set, command is:
  - `worai --profile <name> graph sync run [--debug]`
- The action always passes the root `--profile` option (the recommended form in current `worai` docs for `graph sync run`).

Without root `--config`, standard `worai` config discovery applies:

- `WORAI_CONFIG`
- `./worai.toml`
- `~/.config/worai/config.toml`
- `~/.worai.toml`

For `graph sync run`, current `worai` profile resolution order is:

- root `--profile`
- `WORAI_PROFILE`
- `default`

## Notes

- Supported input sources are managed by `worai` config: `urls`, `sitemap_url` (+ optional `sitemap_url_pattern`), and Google Sheets (`sheets_url` + `sheets_name` + `oauth.service_account`).
- Configure exactly one input source mode per run.
- `oauth.service_account` accepts inline JSON object content or a file path.
- For Google Sheets source, `oauth.service_account` is required and the command fails when:
  - value is missing or empty
  - value is neither valid JSON object content nor an existing file path
  - value is valid JSON but not an object
- `google_search_console` can be global or profile-level in `worai.toml`; profile value overrides global value; default is `false` when unset; maps to SDK setting `GOOGLE_SEARCH_CONSOLE`.
- The command fails when selected profile does not define `api_key`.
- By default, the action installs `playwright==1.55.0` and Chromium. Set `install_playwright: false` to skip this step.
- By default, cache is enabled for `~/.cache/pip` and `~/.cache/ms-playwright`.
- Default cache key format is `<runner.os>-graph-sync-<worai_version>-<playwright_version>-<playwright_browser>`.
- Set `cache_enabled: false` to disable cache or set `cache_key_suffix` to control the key suffix directly.

`worai` references:

- Install & quickstart: <https://docs.wordlift.io/worai/install/>
- Configuration: <https://docs.wordlift.io/worai/configuration/>
- Graph command: <https://docs.wordlift.io/worai/commands/graph/>

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
- GitHub-hosted Ubuntu runners typically satisfy Chromium runtime dependencies. On custom/self-hosted runners, install required OS packages before using Playwright.

## worai Config Examples

The `graph sync run` workflow expects one source mode per profile.

Sitemap source example:

```toml
[profiles.acme_sitemap]
api_key = "${WORDLIFT_API_KEY}"
sitemap_url = "https://example.com/sitemap.xml"
ingest_source = "sitemap"
ingest_loader = "web_scrape_api"
ingest_passthrough_when_html = true
web_page_import_timeout = "60s"
```

Google Sheets source example:

```toml
[profiles.acme_sheets]
api_key = "${WORDLIFT_API_KEY}"
sheets_url = "https://docs.google.com/spreadsheets/d/ACME_SPREADSHEET_ID"
sheets_name = "URLs"
ingest_source = "sheets"
[profiles.acme_sheets.oauth]
service_account = "${SHEETS_SERVICE_ACCOUNT}"
```

Optional local default profile selection:

```bash
export WORAI_PROFILE="acme_sitemap"
```

## Release and Pinning

- Publish immutable releases and move alias tags only by creating new immutable release tags.
- Consumers should pin this action to a full commit SHA for maximum integrity.
- If using tags, use managed aliases:
  - major alias (`@v6`) tracks latest `v6.x.y`
- minor alias (`@v6.5`) tracks latest `v6.5.z`
- The release workflow force-updates both alias tags on each release tag push.
- This repository includes automated release workflow `.github/workflows/release.yml` triggered by pushing tags like `v6.0.0`.
- Marketplace publication itself is still a manual GitHub UI step; the release workflow adds a summary with a direct release link and checklist.
- Versioning strategy and compatibility policy are documented in `VERSIONING.md`.

## Migration from `@v1`

- Replace `uses: wordlift/graph-sync@v1` with `uses: wordlift/graph-sync@v6`.
- Action `v6` defaults to installing `worai` `6.12.12`.

## Development

Run tests locally:

```bash
./tests/run-worai.sh
./tests/install-worai.sh
./tests/install-playwright.sh
./tests/resolve-cache-key.sh
```
