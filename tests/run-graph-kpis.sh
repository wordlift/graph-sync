#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/run-graph-kpis.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

pass_count=0
fail_count=0

assert_eq() {
  local expected="$1"
  local actual="$2"
  local message="$3"
  if [[ "$expected" == "$actual" ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $message"
    echo "  expected: $expected"
    echo "  actual:   $actual"
  fi
}

assert_contains() {
  local needle="$1"
  local haystack="$2"
  local message="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $message"
    echo "  expected to contain: $needle"
    echo "  actual:              $haystack"
  fi
}

assert_not_contains() {
  local needle="$1"
  local haystack="$2"
  local message="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $message"
    echo "  expected not to contain: $needle"
    echo "  actual:                  $haystack"
  fi
}

run_case() {
  local name="$1"
  shift
  local out_file="$TMP_DIR/${name}.out"
  local err_file="$TMP_DIR/${name}.err"
  set +e
  "$@" >"$out_file" 2>"$err_file"
  local code=$?
  set -e
  echo "$code"
}

FAKE_BIN="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN"

cat > "$FAKE_BIN/worai" <<'EOS'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$WORAI_ARGS_FILE"
if [[ "$*" == *" graph export "* ]]; then
  output="${@: -1}"
  printf '{"@graph":[]}\n' > "$output"
  exit 0
fi
if [[ "$*" == *" graph kpis push "* ]]; then
  if [[ "${WORAI_KPIS_PUSH_FAIL:-}" == "1" ]]; then
    echo "kpi push failed" >&2
    exit 1
  fi
  output=""
  details=""
  args=("$@")
  for ((i=0; i<${#args[@]}; i++)); do
    case "${args[$i]}" in
      --output)
        i=$((i + 1))
        output="${args[$i]}"
        ;;
      --details-output)
        i=$((i + 1))
        details="${args[$i]}"
        ;;
    esac
  done
  mkdir -p "$(dirname "$output")" "$(dirname "$details")"
  cat > "$output" <<'JSON'
{
  "snapshot_date": "2026-06-23",
  "calculated_at": "2026-06-23T10:00:00Z",
  "snapshot_origin": "worai_graph_kpis",
  "total_triples": 40,
  "schema_compliance": {"urls_checked": 1, "urls_with_errors": 1, "urls_with_warnings": 0, "errors": 2, "warnings": 0}
}
JSON
  cat > "$details" <<'JSON'
{
  "totals": {"total_triples": 40, "unique_urls_within_website_scope": 4},
  "rich_snippet_candidate_entities": {"total": 3, "by_type": {"Article": 3}},
  "schema_compliance": {"urls_checked": 1, "urls_with_errors": 1, "urls_with_warnings": 0, "errors": 2, "warnings": 0}
}
JSON
  echo "Graph KPI snapshot uploaded for account 1506805 on 2026-06-23."
  exit 0
fi
exit 0
EOS
chmod +x "$FAKE_BIN/worai"

WORK_DIR="$TMP_DIR/work"
mkdir -p "$WORK_DIR"
cat > "$WORK_DIR/worai.toml" <<'EOF_TOML'
[profiles._base]
api_key = "${WORDLIFT_API_KEY}"

[profiles.prod]
EOF_TOML
cat > "$WORK_DIR/custom.toml" <<'EOF_TOML'
[profiles.custom]
api_key = "${WORDLIFT_API_KEY}"
EOF_TOML

BASE_ENV=(
  env
  PATH="$FAKE_BIN:$PATH"
  GITHUB_ACTION_PATH="$ROOT_DIR"
  GITHUB_WORKSPACE="$TMP_DIR/workspace"
  RUNNER_TEMP="$TMP_DIR/runner"
  WORAI_ARGS_FILE="$TMP_DIR/worai-args.txt"
  WORDLIFT_API_KEY="secret-key-123"
)
mkdir -p "$TMP_DIR/runner"

# Case 1: disabled is a no-op.
code=$(run_case disabled "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="false" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" "$SCRIPT")
assert_eq "0" "$code" "disabled graph KPIs should succeed"
assert_eq "0" "$(test ! -f "$TMP_DIR/worai-args.txt"; echo $?)" "disabled graph KPIs should not run worai"

# Case 2: enabled exports, calculates, and uploads through native worai graph kpis push.
rm -f "$TMP_DIR/worai-args.txt"
code=$(run_case enabled "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="prod" INPUT_CONFIG_PATH="./worai.toml" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23" INPUT_GRAPH_KPIS_API_URL="https://api.wordlift.io/" INPUT_GRAPH_KPIS_NO_BUILTIN_SHAPES="true" INPUT_GRAPH_KPIS_SHAPE="profiles/_base/shapes/graph-kpis-url-roots.shacl.ttl" "$SCRIPT")
assert_eq "0" "$code" "enabled graph KPIs should succeed"
args="$(cat "$TMP_DIR/worai-args.txt")"
assert_contains "--config ./worai.toml --profile prod graph export" "$args" "should run graph export"
assert_contains "--config ./worai.toml --profile prod graph kpis push" "$args" "should run graph kpis push"
assert_contains "--api-url https://api.wordlift.io" "$args" "should pass API URL to worai"
assert_contains "--no-builtin-shapes" "$args" "should pass no builtin shapes option"
assert_contains "--shape profiles/_base/shapes/graph-kpis-url-roots.shacl.ttl" "$args" "should pass custom shape"
assert_not_contains "--website-host" "$args" "action should not pass website host"
assert_contains "graph export --timeout 300 " "$args" "should pass default timeout to graph export"
payload_check="$(python3 - "$TMP_DIR/out/graph-kpis/graph_kpi_payload.json" "$TMP_DIR/out/graph-kpis/graph_kpis.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
details = json.load(open(sys.argv[2]))
checks = [
    payload["snapshot_date"] == "2026-06-23",
    payload["snapshot_origin"] == "worai_graph_kpis",
    payload["total_triples"] == 40,
    details["totals"]["unique_urls_within_website_scope"] == 4,
    details["schema_compliance"]["errors"] == 2,
]
print("ok" if all(checks) else payload)
PY
)"
assert_eq "ok" "$payload_check" "native KPI payload and details should be written"
stdout_logs="$(cat "$TMP_DIR/enabled.out")"
stderr_logs="$(cat "$TMP_DIR/enabled.err")"
assert_not_contains "secret-key-123" "$stderr_logs" "stderr should not print the resolved key"
assert_not_contains "secret-key-123" "$stdout_logs" "stdout should not print the resolved key"
assert_eq "0" "$(test ! -f "$TMP_DIR/out/graph-kpis/graph_kpi_audit.json"; echo $?)" "legacy audit JSON should not be stored in uploaded output"

# Case 3: native worai KPI failures are warning-only by default.
code=$(run_case kpi_push_failure "${BASE_ENV[@]}" WORAI_KPIS_PUSH_FAIL="1" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-fail" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23" "$SCRIPT")
assert_eq "0" "$code" "kpi push failure should be non-blocking by default"
kpi_fail_out="$(cat "$TMP_DIR/kpi_push_failure.out")"
assert_contains "::warning::Graph KPI calculation or upload failed." "$kpi_fail_out" "kpi push failure should warn"

# Case 4: strict mode fails on native worai KPI failures.
code=$(run_case strict_kpi_push_failure "${BASE_ENV[@]}" WORAI_KPIS_PUSH_FAIL="1" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_GRAPH_KPIS_FAIL_ON_ERROR="true" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-strict" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23" "$SCRIPT")
assert_eq "1" "$code" "kpi push failure should fail in strict mode"

# Case 5: untrusted non-HTTPS URL is rejected before running worai.
code=$(run_case http_url "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-http" INPUT_GRAPH_KPIS_API_URL="http://api.wordlift.io" "$SCRIPT")
assert_eq "0" "$code" "non-HTTPS WordLift API URL should be warning-only by default"
http_out="$(cat "$TMP_DIR/http_url.out")"
assert_contains "WordLift API URL is not allowed" "$http_out" "non-HTTPS URL should warn"

# Case 6: snapshot date must be a strict calendar date before it reaches worai.
code=$(run_case bad_snapshot_date "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-bad-date" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23/extra" "$SCRIPT")
assert_eq "0" "$code" "malformed snapshot date should be warning-only by default"
bad_date_out="$(cat "$TMP_DIR/bad_snapshot_date.out")"
assert_contains "snapshot date is invalid" "$bad_date_out" "malformed snapshot date should warn"

# Case 7: WordLift API base URL must be an origin, not a URL with query/path content.
code=$(run_case base_url_query "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-base-query" INPUT_GRAPH_KPIS_API_URL="https://api.wordlift.io?debug=true" "$SCRIPT")
assert_eq "0" "$code" "base URL with query should be warning-only by default"
base_query_out="$(cat "$TMP_DIR/base_url_query.out")"
assert_contains "WordLift API URL is not allowed" "$base_query_out" "base URL with query should warn"

# Case 8: relative WORAI_CONFIG is left for worai execution from working_directory.
code=$(run_case worai_config_relative "${BASE_ENV[@]}" WORAI_CONFIG="./custom.toml" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_PROFILE="custom" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-worai-config" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23" "$SCRIPT")
assert_eq "0" "$code" "relative WORAI_CONFIG should resolve from working_directory"

# Case 9: graph_kpis_timeout_seconds also applies to the graph export request.
rm -f "$TMP_DIR/worai-args.txt"
code=$(run_case export_timeout "${BASE_ENV[@]}" INPUT_GRAPH_KPIS_ENABLED="true" INPUT_GRAPH_KPIS_TIMEOUT_SECONDS="1200" INPUT_PROFILE="prod" INPUT_WORKING_DIRECTORY="$WORK_DIR" INPUT_OUTPUT_DIR="$TMP_DIR/out-export-timeout" INPUT_GRAPH_KPIS_SNAPSHOT_DATE="2026-06-23" "$SCRIPT")
assert_eq "0" "$code" "custom KPI timeout should succeed"
export_args="$(grep ' graph export ' "$TMP_DIR/worai-args.txt")"
assert_contains "graph export --timeout 1200 " "$export_args" "should pass custom timeout to graph export"

if [[ "$fail_count" -ne 0 ]]; then
  echo "\n$fail_count test(s) failed, $pass_count passed"
  exit 1
fi

echo "$pass_count test(s) passed"
