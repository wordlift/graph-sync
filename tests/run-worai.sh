#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/run-worai.sh"
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
if [[ "$*" == *"--help"* ]]; then
  echo "  --output-dir TEXT"
  exit 0
fi
printf '%s\n' "$*" > "$WORAI_ARGS_FILE"
printf '%s\n' "${WORAI_LOG_LEVEL:-}" > "$WORAI_LOG_LEVEL_FILE"
EOS
chmod +x "$FAKE_BIN/worai"

FAKE_BIN_OLD="$TMP_DIR/bin-old"
mkdir -p "$FAKE_BIN_OLD"
cat > "$FAKE_BIN_OLD/worai" <<'EOS'
#!/usr/bin/env bash
if [[ "$*" == *"--help"* ]]; then
  echo "  --debug / --no-debug"
  exit 0
fi
printf '%s\n' "$*" > "$WORAI_ARGS_FILE"
printf '%s\n' "${WORAI_LOG_LEVEL:-}" > "$WORAI_LOG_LEVEL_FILE"
EOS
chmod +x "$FAKE_BIN_OLD/worai"

BASE_ENV=(env PATH="$FAKE_BIN:$PATH" WORAI_ARGS_FILE="$TMP_DIR/args.txt" WORAI_LOG_LEVEL_FILE="$TMP_DIR/log-level.txt")
BASE_ENV_OLD=(env PATH="$FAKE_BIN_OLD:$PATH" WORAI_ARGS_FILE="$TMP_DIR/args.txt" WORAI_LOG_LEVEL_FILE="$TMP_DIR/log-level.txt")

# Case 1: missing profile
code=$(run_case missing_profile "${BASE_ENV[@]}" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "1" "$code" "missing profile should fail"

# Case 2: standard invocation without config
rm -f "$TMP_DIR/args.txt" "$TMP_DIR/log-level.txt"
code=$(run_case no_config "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_DEBUG="false" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "0" "$code" "no config should succeed"
args=$(cat "$TMP_DIR/args.txt")
assert_eq "--profile demo graph sync run" "$args" "command without config/debug"
log_level=$(cat "$TMP_DIR/log-level.txt")
assert_eq "warning" "$log_level" "default log level should be warning"

# Case 3: with config and debug
rm -f "$TMP_DIR/args.txt"
code=$(run_case with_config_debug "${BASE_ENV[@]}" INPUT_PROFILE="prod" INPUT_CONFIG_PATH="./worai.toml" INPUT_DEBUG="true" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "0" "$code" "config+debug should succeed"
args=$(cat "$TMP_DIR/args.txt")
assert_eq "--config ./worai.toml --profile prod graph sync run --debug" "$args" "command with config/debug"

# Case 4: invalid debug
code=$(run_case invalid_debug "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_DEBUG="maybe" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "1" "$code" "invalid debug should fail"

# Case 5: valid log level
rm -f "$TMP_DIR/args.txt" "$TMP_DIR/log-level.txt"
code=$(run_case valid_log_level "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_LOG_LEVEL="WARNING" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "0" "$code" "valid log level should succeed"
args=$(cat "$TMP_DIR/args.txt")
assert_eq "--profile demo graph sync run" "$args" "command with log level should not add extra args"
log_level=$(cat "$TMP_DIR/log-level.txt")
assert_eq "warning" "$log_level" "explicit log level should be exported via WORAI_LOG_LEVEL"

# Case 6: invalid log level
code=$(run_case invalid_log_level "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_LOG_LEVEL="trace" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "1" "$code" "invalid log level should fail"

# Case 7: missing working directory
code=$(run_case bad_workdir "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_WORKING_DIRECTORY="$ROOT_DIR/nope" "$SCRIPT")
assert_eq "1" "$code" "invalid working directory should fail"

# Case 8: output_dir passed to new worai (--help advertises --output-dir)
rm -f "$TMP_DIR/args.txt"
code=$(run_case output_dir_new "${BASE_ENV[@]}" INPUT_PROFILE="demo" INPUT_OUTPUT_DIR="/tmp/out" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "0" "$code" "output_dir with new worai should succeed"
args=$(cat "$TMP_DIR/args.txt")
assert_eq "--profile demo graph sync run --output-dir /tmp/out" "$args" "output_dir should be passed when worai supports it"

# Case 9: output_dir silently skipped for old worai (--help does not advertise --output-dir)
rm -f "$TMP_DIR/args.txt"
code=$(run_case output_dir_old "${BASE_ENV_OLD[@]}" INPUT_PROFILE="demo" INPUT_OUTPUT_DIR="/tmp/out" INPUT_WORKING_DIRECTORY="$ROOT_DIR" "$SCRIPT")
assert_eq "0" "$code" "output_dir with old worai should still succeed"
args=$(cat "$TMP_DIR/args.txt")
assert_eq "--profile demo graph sync run" "$args" "output_dir should be silently skipped for old worai"

if [[ "$fail_count" -ne 0 ]]; then
  echo "\n$fail_count test(s) failed, $pass_count passed"
  exit 1
fi

echo "$pass_count test(s) passed"
