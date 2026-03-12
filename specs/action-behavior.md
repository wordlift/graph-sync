# Action Behavior Spec

## Inputs

- `profile` (required)
- `config_path` (optional)
- `debug` (optional, default `false`)
- `log_level` (optional, default `warning`)
- `working_directory` (optional, default `.`)
- `worai_version` (optional, default `6.16.0`)
- `install_playwright` (optional, default `true`)
- `playwright_version` (optional, default `1.58.0`)
- `playwright_browser` (optional, default `chromium`)
- `cache_enabled` (optional, default `true`)
- `cache_key_suffix` (optional, default empty string)

## Installation

The action installs `worai` via:

1. Resolve Python interpreter:
   - `python3` if available
   - otherwise `python` if available
   - fail if neither exists
2. Validate `worai_version` is not empty and contains no whitespace.
3. `<python_cmd> -m pip install --upgrade pip`
4. `<python_cmd> -m pip install worai==<worai_version>`

The action installs Playwright via:

1. Validate `install_playwright` is boolean-like (`true/false/1/0/yes/no`).
2. If false, skip Playwright installation.
3. Validate `playwright_version` is not empty and contains no whitespace.
4. Validate `playwright_browser` is not empty and contains no whitespace.
5. Resolve Python interpreter with the same `python3` then `python` rule.
6. `<python_cmd> -m pip install playwright==<playwright_version>`
7. `<python_cmd> -m playwright install <playwright_browser>`

## Caching

1. Validate `cache_enabled` is boolean-like (`true/false/1/0/yes/no`).
2. If `cache_enabled` is false, skip caching.
3. If `cache_key_suffix` is non-empty, use it as cache suffix.
4. If `cache_key_suffix` is empty, build suffix as:
   - `<worai_version>-<playwright_version>-<playwright_browser>`
5. Restore/save cache with key:
   - `<runner.os>-graph-sync-<resolved_cache_key_suffix>`
6. Cache paths:
   - `~/.cache/pip`
   - `~/.cache/ms-playwright`
7. Self-hosted runners must use GitHub Actions Runner `2.327.1` or newer because the action uses `actions/cache` `v5.0.3`.

## Execution

1. Validate required `profile`.
2. Validate `working_directory` exists.
3. Validate `debug` is boolean-like (`true/false/1/0/yes/no`).
4. Validate `log_level` is one of `debug|info|warning|error`.
5. Build command:
   - base: `worai`
   - optional root config: `--config <path>`
   - root profile option: `--profile <name>`
   - subcommand: `graph sync run`
   - optional: `--debug`
6. Execute `worai` with `WORAI_LOG_LEVEL=<value>` in the process environment.
7. Execute command from `working_directory`.

## Failure Semantics

The wrapper fails if inputs are invalid or `worai` is unavailable in `PATH`.
`worai` itself is expected to enforce profile and source-specific config constraints, including:

- missing `api_key` in selected profile
- Google Sheets `oauth.service_account` validation failures:
  - missing or empty value when Sheets source is used
  - value is neither valid JSON object content nor an existing file path
  - value is valid JSON but not an object

## Release Automation

- Workflow `.github/workflows/release.yml` is triggered on semantic version tag pushes (`vMAJOR.MINOR.PATCH`).
- The workflow:
  - validates tag format (`vMAJOR.MINOR.PATCH`)
  - force-updates major alias tag (`v<major>`)
  - force-updates minor alias tag (`v<major>.<minor>`)
  - publishes GitHub Release with generated notes (skips if already present)
  - writes a post-release summary for required manual Marketplace publication fields
