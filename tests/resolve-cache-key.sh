#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/resolve-cache-key.sh"
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

read_output_value() {
  local key="$1"
  local file="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

# Case 1: missing cache_enabled
out_file="$TMP_DIR/missing.out"
code=$(run_case missing env GITHUB_OUTPUT="$out_file" "$SCRIPT")
assert_eq "1" "$code" "missing cache_enabled should fail"

# Case 2: cache disabled
out_file="$TMP_DIR/disabled.out"
code=$(run_case disabled env GITHUB_OUTPUT="$out_file" INPUT_CACHE_ENABLED="false" "$SCRIPT")
assert_eq "0" "$code" "disabled cache should succeed"
value=$(read_output_value "cache_enabled" "$out_file")
assert_eq "false" "$value" "disabled cache output flag"
suffix=$(read_output_value "cache_key_suffix" "$out_file")
assert_eq "" "$suffix" "disabled cache suffix should be empty"

# Case 3: explicit suffix
out_file="$TMP_DIR/explicit.out"
code=$(run_case explicit env GITHUB_OUTPUT="$out_file" INPUT_CACHE_ENABLED="true" INPUT_CACHE_KEY_SUFFIX="custom-key" "$SCRIPT")
assert_eq "0" "$code" "explicit suffix should succeed"
value=$(read_output_value "cache_enabled" "$out_file")
assert_eq "true" "$value" "explicit suffix output flag"
suffix=$(read_output_value "cache_key_suffix" "$out_file")
assert_eq "custom-key" "$suffix" "explicit suffix output"

# Case 4: fallback suffix generation
out_file="$TMP_DIR/fallback.out"
code=$(run_case fallback env GITHUB_OUTPUT="$out_file" INPUT_CACHE_ENABLED="yes" INPUT_WORAI_VERSION="6.8.0" INPUT_PLAYWRIGHT_VERSION="1.55.0" INPUT_PLAYWRIGHT_BROWSER="chromium" "$SCRIPT")
assert_eq "0" "$code" "fallback suffix should succeed"
suffix=$(read_output_value "cache_key_suffix" "$out_file")
assert_eq "6.8.0-1.55.0-chromium" "$suffix" "fallback suffix value"

# Case 5: invalid cache_enabled
out_file="$TMP_DIR/invalid.out"
code=$(run_case invalid env GITHUB_OUTPUT="$out_file" INPUT_CACHE_ENABLED="maybe" "$SCRIPT")
assert_eq "1" "$code" "invalid cache_enabled should fail"

if [[ "$fail_count" -ne 0 ]]; then
  echo "\n$fail_count test(s) failed, $pass_count passed"
  exit 1
fi

echo "$pass_count test(s) passed"
