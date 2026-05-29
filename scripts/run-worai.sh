#!/usr/bin/env bash
set -euo pipefail

profile="${INPUT_PROFILE:-}"
config_path="${INPUT_CONFIG_PATH:-}"
debug="${INPUT_DEBUG:-false}"
log_level="${INPUT_LOG_LEVEL:-warning}"
working_directory="${INPUT_WORKING_DIRECTORY:-.}"
output_dir="${INPUT_OUTPUT_DIR:-}"
debug_lower="$(printf '%s' "$debug" | tr '[:upper:]' '[:lower:]')"
log_level_lower="$(printf '%s' "$log_level" | tr '[:upper:]' '[:lower:]')"

if [[ -z "$profile" ]]; then
  echo "error: input 'profile' is required" >&2
  exit 1
fi

if [[ ! -d "$working_directory" ]]; then
  echo "error: working directory does not exist: $working_directory" >&2
  exit 1
fi

if ! command -v worai >/dev/null 2>&1; then
  echo "error: worai not found in PATH" >&2
  exit 1
fi

cmd=("worai")

if [[ -n "$config_path" ]]; then
  cmd+=("--config" "$config_path")
fi

cmd+=("--profile" "$profile" "graph" "sync" "run")

# Guard against older worai versions that predate --output-dir (pre-6.19.0):
# passing an unknown flag would cause a hard failure, so skip silently when
# the installed worai does not advertise the flag.
if [[ -n "$output_dir" ]] && "${cmd[@]}" --help 2>&1 | grep -q -- "--output-dir"; then
  cmd+=("--output-dir" "$output_dir")
fi

case "$debug_lower" in
  true|1|yes)
    cmd+=("--debug")
    ;;
  false|0|no|'')
    ;;
  *)
    echo "error: input 'debug' must be true or false" >&2
    exit 1
    ;;
esac

case "$log_level_lower" in
  ''|debug|info|warning|error)
    ;;
  *)
    echo "error: input 'log_level' must be one of: debug, info, warning, error" >&2
    exit 1
    ;;
esac

cd "$working_directory"
printf 'Running:'
printf ' %q' "${cmd[@]}"
printf '\n'

if [[ -n "$log_level_lower" ]]; then
  WORAI_LOG_LEVEL="$log_level_lower" "${cmd[@]}"
else
  "${cmd[@]}"
fi
