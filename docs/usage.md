# Usage Reference

## Command Forms

- `worai graph sync --profile <name> [--debug]`
- `worai --config <path> graph sync --profile <name> [--debug]`

## Source Types

- `urls`
- `sitemap_url` (optional `sitemap_url_pattern`)
- Google Sheets (`sheets_url`, `sheets_name`, `sheets_service_account`)

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

- The action installs a pinned `worai` version via input `worai_version` (default `1.16.2`).
- Python interpreter resolution order is:
  - `python3`
  - `python`
- The action fails if neither executable is available in `PATH`.
