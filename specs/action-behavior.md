# Action Behavior Spec

## Inputs

- `profile` (required)
- `config_path` (optional)
- `debug` (optional, default `false`)
- `working_directory` (optional, default `.`)
- `worai_version` (optional, default `1.17.0`)

## Installation

The action installs `worai` via:

1. Resolve Python interpreter:
   - `python3` if available
   - otherwise `python` if available
   - fail if neither exists
2. Validate `worai_version` is not empty and contains no whitespace.
3. `<python_cmd> -m pip install --upgrade pip`
4. `<python_cmd> -m pip install worai==<worai_version>`

## Execution

1. Validate required `profile`.
2. Validate `working_directory` exists.
3. Validate `debug` is boolean-like (`true/false/1/0/yes/no`).
4. Build command:
   - base: `worai`
   - optional root config: `--config <path>`
   - subcommand: `graph sync --profile <name>`
   - optional: `--debug`
5. Execute command from `working_directory`.

## Failure Semantics

The wrapper fails if inputs are invalid or `worai` is unavailable in `PATH`.
`worai` itself is expected to enforce profile and source-specific config constraints, including:

- missing `api_key` in selected profile
- Google Sheets `sheets_service_account` validation failures

## Release Automation

- Workflow `.github/workflows/release.yml` is triggered on semantic version tag pushes (`vMAJOR.MINOR.PATCH`).
- The workflow:
  - validates tag format (`vMAJOR.MINOR.PATCH`)
  - force-updates major alias tag (`v<major>`)
  - publishes GitHub Release with generated notes (skips if already present)
  - writes a post-release summary for required manual Marketplace publication fields
