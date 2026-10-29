# Action Behavior Spec

## Inputs

- `profile` (required)
- `config_path` (optional)
- `debug` (optional, default `false`)
- `log_level` (optional, default `warning`)
- `working_directory` (optional, default `.`)
- `worai_version` (optional, default `6.20.15`)
- `output_dir` (optional, default empty)
- `install_playwright` (optional, default `true`)
- `playwright_version` (optional, default `1.58.0`)
- `playwright_browser` (optional, default `chromium`)
- `cache_enabled` (optional, default `true`)
- `cache_key_suffix` (optional, default empty string)
- `graph_kpis_enabled` (optional, default `false`)
- `graph_kpis_snapshot_date` (optional, default current UTC date)
- `graph_kpis_api_url` (optional, default `https://api.wordlift.io`)
- `graph_kpis_allowed_hosts` (optional, default `api.wordlift.io`)
- `graph_kpis_export_endpoint` (optional, default empty)
- `graph_kpis_timeout_seconds` (optional, default `300`)
- `graph_kpis_shacl_workers` (optional, default `4`)
- `graph_kpis_shape` (optional, default empty)
- `graph_kpis_no_builtin_shapes` (optional, default `false`)
- `graph_kpis_fail_on_error` (optional, default `false`)
- `graph_kpis_retry_attempts` (deprecated; native `worai graph kpis push` owns upload behavior)

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
   - optional: `--output-dir <path>` — only appended when `output_dir` is non-empty AND `worai graph sync run --help` advertises `--output-dir` (guards against pre-6.19.0 installs)
   - optional: `--debug`
6. Execute `worai` with `WORAI_LOG_LEVEL=<value>` in the process environment.
7. Execute command from `working_directory`.
8. When `output_dir` is set, publish `graph_sync_report.md` to the job summary and upload all files under `output_dir` as a `graph-sync-report-<profile>` artifact.

## Graph KPI Upload

When `graph_kpis_enabled` is true and `graph sync run` succeeds:

1. Validate `snapshot_date` as a strict `YYYY-MM-DD` calendar date.
2. Reject WordLift API or export endpoint URLs unless they use HTTPS and a host listed in `graph_kpis_allowed_hosts`.
   - `graph_kpis_api_url` must be an origin URL without path, params, query, or fragment.
3. Export the current graph to a temporary JSON-LD file under `RUNNER_TEMP`:
   - `worai [--config <path>] --profile <name> graph export [--endpoint <endpoint>] <temp-file>`
4. Calculate and upload the KPI snapshot with native `worai`:
   - `worai [--config <path>] --profile <name> graph kpis push <temp-file> --snapshot-date <date> --api-url <url> --timeout <seconds> --shacl-workers <n> --output <payload-json> --details-output <details-json>`
   - append `--no-builtin-shapes` when `graph_kpis_no_builtin_shapes` is truthy.
   - append each comma-separated `graph_kpis_shape` value as `--shape <path>`.
5. `worai graph kpis push` resolves the selected profile API key, calls `/accounts/me`, derives website URL scope from the account URL, calculates URL-rooted SHACL compliance, and uploads with `PUT /accounts/{account_id}/graph-kpis/{snapshot_date}`.
6. Remove the raw temporary graph export on exit.
7. Write `graph_kpi_payload.json`, `graph_kpis.json`, and `graph_kpi_report.md` to `output_dir/graph-kpis/`.

## Failure Semantics

The wrapper fails if inputs are invalid or `worai` is unavailable in `PATH`.
`worai` itself is expected to enforce profile and source-specific config constraints, including:

- missing `api_key` in selected profile
- Google Sheets `oauth.service_account` validation failures:
  - missing or empty value when Sheets source is used
  - value is neither valid JSON object content nor an existing file path
  - value is valid JSON but not an object

Graph KPI upload failures are warning-only by default. When `graph_kpis_fail_on_error` is truthy, graph KPI export, calculation, report generation, or upload failures fail the action.

## Release Automation

- Workflow `.github/workflows/release.yml` is triggered on semantic version tag pushes (`vMAJOR.MINOR.PATCH`).
- The workflow:
  - validates tag format (`vMAJOR.MINOR.PATCH`)
  - force-updates major alias tag (`v<major>`)
  - force-updates minor alias tag (`v<major>.<minor>`)
  - publishes GitHub Release with generated notes (skips if already present)
  - writes a post-release summary for required manual Marketplace publication fields
