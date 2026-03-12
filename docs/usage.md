# Usage Reference

## Command Forms

- `worai --profile <name> graph sync run [--debug]`
- `worai --config <path> --profile <name> graph sync run [--debug]`
- The action sets `WORAI_LOG_LEVEL` to `warning` by default; supported values are `debug|info|warning|error`

## Source Types

- `urls`
- `sitemap_url` (optional `sitemap_url_pattern`)
- Google Sheets (`sheets_url`, `sheets_name`, `oauth.service_account`)
- Configure exactly one source mode per run.

## Config Example (Acme)

```toml
[profiles._base]
sheets_url = "https://docs.google.com/spreadsheets/d/ACME_SPREADSHEET_ID"
concurrency = 8
overwrite = true
[profiles._base.oauth]
service_account = "${SHEETS_SERVICE_ACCOUNT}"

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

## Config Discovery

When `config_path` is not provided, `worai` discovers config in this order:

- `WORAI_CONFIG`
- `./worai.toml`
- `~/.config/worai/config.toml`
- `~/.worai.toml`

## Google Search Console Flag

- `google_search_console` can be set globally or per profile.
- Profile value overrides global value.
- Defaults to `false` when unset.
- Mapped to SDK setting `GOOGLE_SEARCH_CONSOLE`.

## Google Sheets Service Account

- `oauth.service_account` accepts:
  - inline JSON object content
  - path to an existing credentials file
- When using Google Sheets source (`sheets_url` + `sheets_name`), `oauth.service_account` is required.
- `graph sync run` fails for Google Sheets source when:
  - value is missing or empty
  - value is neither valid JSON object content nor an existing file path
  - value is valid JSON but not an object

## Installer Behavior

- The action installs a pinned `worai` version via input `worai_version` (default `6.16.0`).
- The action installs Playwright by default via:
  - Python package input `playwright_version` (default `1.58.0`)
  - Browser input `playwright_browser` (default `chromium`)
- Set `install_playwright: false` to skip Playwright and browser installation.
- Python interpreter resolution order is:
  - `python3`
  - `python`
- The action fails if neither executable is available in `PATH`.

## Cache Behavior

- Caching is enabled by default via `cache_enabled` input.
- Cached paths:
  - `~/.cache/pip`
  - `~/.cache/ms-playwright`
- If `cache_key_suffix` is empty, the action builds it as:
  - `<worai_version>-<playwright_version>-<playwright_browser>`
- Effective cache key is:
  - `<runner.os>-graph-sync-<cache_key_suffix>`
- With cache enabled, self-hosted runners must use GitHub Actions Runner `2.327.1` or newer because the action uses `actions/cache` `v5.0.3`.
