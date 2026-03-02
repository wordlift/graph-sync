# Usage Reference

## Command Forms

- `worai --profile <name> graph sync run [--debug]`
- `worai --config <path> --profile <name> graph sync run [--debug]`

## Source Types

- `urls`
- `sitemap_url` (optional `sitemap_url_pattern`)
- Google Sheets (`sheets_url`, `sheets_name`, `sheets_service_account`)

## Config Example (Acme)

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

## Installer Behavior

- The action installs a pinned `worai` version via input `worai_version` (default `6.9.4`).
- The action installs Playwright by default via:
  - Python package input `playwright_version` (default `1.55.0`)
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
