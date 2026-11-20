#!/usr/bin/env bash
set -euo pipefail

enabled="${INPUT_GRAPH_KPIS_ENABLED:-false}"
profile="${INPUT_PROFILE:-}"
config_path="${INPUT_CONFIG_PATH:-}"
working_directory="${INPUT_WORKING_DIRECTORY:-.}"
output_dir="${INPUT_OUTPUT_DIR:-${GITHUB_WORKSPACE}/output/${INPUT_PROFILE}}"
api_url="${INPUT_GRAPH_KPIS_API_URL:-}"
allowed_hosts="${INPUT_GRAPH_KPIS_ALLOWED_HOSTS:-api.wordlift.io}"
snapshot_date="${INPUT_GRAPH_KPIS_SNAPSHOT_DATE:-}"
export_endpoint="${INPUT_GRAPH_KPIS_EXPORT_ENDPOINT:-}"
fail_on_error="${INPUT_GRAPH_KPIS_FAIL_ON_ERROR:-false}"
log_level="${INPUT_LOG_LEVEL:-warning}"
timeout_seconds="${INPUT_GRAPH_KPIS_TIMEOUT_SECONDS:-300}"
shacl_workers="${INPUT_GRAPH_KPIS_SHACL_WORKERS:-4}"
shape="${INPUT_GRAPH_KPIS_SHAPE:-}"
no_builtin_shapes="${INPUT_GRAPH_KPIS_NO_BUILTIN_SHAPES:-false}"

enabled_lower="$(printf '%s' "$enabled" | tr '[:upper:]' '[:lower:]')"
fail_on_error_lower="$(printf '%s' "$fail_on_error" | tr '[:upper:]' '[:lower:]')"
log_level_lower="$(printf '%s' "$log_level" | tr '[:upper:]' '[:lower:]')"
no_builtin_shapes_lower="$(printf '%s' "$no_builtin_shapes" | tr '[:upper:]' '[:lower:]')"

handle_failure() {
  local message="$1"
  if [[ "$fail_on_error_lower" == "true" || "$fail_on_error_lower" == "1" || "$fail_on_error_lower" == "yes" ]]; then
    echo "error: $message" >&2
    exit 1
  fi
  echo "::warning::$message"
  exit 0
}

case "$enabled_lower" in
  true|1|yes)
    ;;
  false|0|no|'')
    echo "Graph KPI upload is disabled."
    exit 0
    ;;
  *)
    echo "error: input 'graph_kpis_enabled' must be true or false" >&2
    exit 1
    ;;
esac

case "$fail_on_error_lower" in
  true|1|yes|false|0|no|'')
    ;;
  *)
    echo "error: input 'graph_kpis_fail_on_error' must be true or false" >&2
    exit 1
    ;;
esac

case "$no_builtin_shapes_lower" in
  true|1|yes|false|0|no|'')
    ;;
  *)
    echo "error: input 'graph_kpis_no_builtin_shapes' must be true or false" >&2
    exit 1
    ;;
esac

if [[ -z "$profile" ]]; then
  echo "error: input 'profile' is required" >&2
  exit 1
fi

if [[ ! "$timeout_seconds" =~ ^[0-9]+$ || "$timeout_seconds" -lt 1 ]]; then
  echo "error: input 'graph_kpis_timeout_seconds' must be a positive integer" >&2
  exit 1
fi

if [[ ! "$shacl_workers" =~ ^[0-9]+$ || "$shacl_workers" -lt 1 ]]; then
  echo "error: input 'graph_kpis_shacl_workers' must be a positive integer" >&2
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

python_cmd=""
if command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
else
  echo "error: python3 or python is required" >&2
  exit 1
fi

if [[ -z "$snapshot_date" ]]; then
  snapshot_date="$(date -u +%F)"
fi

helper="$GITHUB_ACTION_PATH/scripts/graph-kpis.py"
"$python_cmd" "$helper" validate-date "$snapshot_date" || handle_failure "Graph KPI upload failed because snapshot date is invalid."

if [[ -z "$api_url" ]]; then
  api_url="https://api.wordlift.io"
fi
base_url="${api_url%/}"
"$python_cmd" "$helper" validate-url \
  --url "$base_url" \
  --allowed-hosts "$allowed_hosts" \
  --base-url || handle_failure "Graph KPI upload failed because the WordLift API URL is not allowed."

if [[ -n "$export_endpoint" ]]; then
  "$python_cmd" "$helper" validate-url \
    --url "$export_endpoint" \
    --allowed-hosts "$allowed_hosts" || handle_failure "Graph KPI upload failed because the export endpoint is not allowed."
fi

output_dir="$("$python_cmd" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$output_dir")"
mkdir -p "$output_dir/graph-kpis"
temp_root="${RUNNER_TEMP:-/tmp}"
mkdir -p "$temp_root"
temp_dir="$(mktemp -d "$temp_root/graph-kpis.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT

payload_json="$output_dir/graph-kpis/graph_kpi_payload.json"
details_json="$output_dir/graph-kpis/graph_kpis.json"
report_md="$output_dir/graph-kpis/graph_kpi_report.md"
export_file="$temp_dir/export-${profile}-${snapshot_date}.jsonld"

cmd=("worai")
if [[ -n "$config_path" ]]; then
  cmd+=("--config" "$config_path")
fi
cmd+=("--profile" "$profile" "graph" "export")
if [[ -n "$export_endpoint" ]]; then
  cmd+=("--endpoint" "$export_endpoint")
fi
cmd+=("--timeout" "$timeout_seconds" "$export_file")

cd "$working_directory"
printf 'Running graph export for KPI calculation.\n'
if [[ -n "$log_level_lower" ]]; then
  WORAI_LOG_LEVEL="$log_level_lower" "${cmd[@]}" || handle_failure "Graph KPI export failed."
else
  "${cmd[@]}" || handle_failure "Graph KPI export failed."
fi

push_cmd=("worai")
if [[ -n "$config_path" ]]; then
  push_cmd+=("--config" "$config_path")
fi
push_cmd+=(
  "--profile" "$profile"
  "graph" "kpis" "push" "$export_file"
  "--snapshot-date" "$snapshot_date"
  "--api-url" "$base_url"
  "--timeout" "$timeout_seconds"
  "--shacl-workers" "$shacl_workers"
  "--output" "$payload_json"
  "--details-output" "$details_json"
)

case "$no_builtin_shapes_lower" in
  true|1|yes)
    push_cmd+=("--no-builtin-shapes")
    ;;
esac

if [[ -n "$shape" ]]; then
  IFS=',' read -r -a shapes <<< "$shape"
  for item in "${shapes[@]}"; do
    trimmed="$(printf '%s' "$item" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [[ -n "$trimmed" ]]; then
      push_cmd+=("--shape" "$trimmed")
    fi
  done
fi

printf 'Calculating and uploading graph KPI snapshot.\n'
if command -v timeout >/dev/null 2>&1; then
  if [[ -n "$log_level_lower" ]]; then
    WORAI_LOG_LEVEL="$log_level_lower" timeout "${timeout_seconds}s" "${push_cmd[@]}" || handle_failure "Graph KPI calculation or upload failed."
  else
    timeout "${timeout_seconds}s" "${push_cmd[@]}" || handle_failure "Graph KPI calculation or upload failed."
  fi
else
  if [[ -n "$log_level_lower" ]]; then
    WORAI_LOG_LEVEL="$log_level_lower" "${push_cmd[@]}" || handle_failure "Graph KPI calculation or upload failed."
  else
    "${push_cmd[@]}" || handle_failure "Graph KPI calculation or upload failed."
  fi
fi

"$python_cmd" "$helper" render-report \
  --details-json "$details_json" \
  --payload-json "$payload_json" \
  --report-md "$report_md" || handle_failure "Graph KPI report generation failed."
