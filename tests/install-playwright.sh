#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/install-playwright.sh"
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

cat > "$FAKE_BIN/python3" <<'EOS'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PYTHON_CALLS_FILE"
EOS
chmod +x "$FAKE_BIN/python3"

BASE_ENV=(env PATH="$FAKE_BIN:/usr/bin:/bin" PYTHON_CALLS_FILE="$TMP_DIR/python_calls.txt")

# Case 1: missing install_playwright
code=$(run_case missing_flag "${BASE_ENV[@]}" "$SCRIPT")
assert_eq "1" "$code" "missing install flag should fail"

# Case 2: invalid install_playwright value
code=$(run_case bad_flag "${BASE_ENV[@]}" INPUT_INSTALL_PLAYWRIGHT="maybe" "$SCRIPT")
assert_eq "1" "$code" "invalid install flag should fail"

# Case 3: disabled install should short-circuit
rm -f "$TMP_DIR/python_calls.txt"
code=$(run_case disabled "${BASE_ENV[@]}" INPUT_INSTALL_PLAYWRIGHT="false" "$SCRIPT")
assert_eq "0" "$code" "disabled install should succeed"
if [[ -f "$TMP_DIR/python_calls.txt" ]]; then
  call_count=$(wc -l < "$TMP_DIR/python_calls.txt")
else
  call_count="0"
fi
assert_eq "0" "$call_count" "disabled install should not call python"

# Case 4: enabled install executes pip install and browser install
rm -f "$TMP_DIR/python_calls.txt"
code=$(run_case install_chromium "${BASE_ENV[@]}" INPUT_INSTALL_PLAYWRIGHT="true" INPUT_PLAYWRIGHT_VERSION="1.55.0" INPUT_PLAYWRIGHT_BROWSER="chromium" "$SCRIPT")
assert_eq "0" "$code" "enabled install should succeed"
first_call=$(sed -n '1p' "$TMP_DIR/python_calls.txt")
second_call=$(sed -n '2p' "$TMP_DIR/python_calls.txt")
assert_eq "-m pip install playwright==1.55.0" "$first_call" "first command installs pinned playwright"
assert_eq "-m playwright install chromium" "$second_call" "second command installs chromium browser"

# Case 5: whitespace in browser should fail
code=$(run_case bad_browser "${BASE_ENV[@]}" INPUT_INSTALL_PLAYWRIGHT="true" INPUT_PLAYWRIGHT_VERSION="1.55.0" INPUT_PLAYWRIGHT_BROWSER="chrome stable" "$SCRIPT")
assert_eq "1" "$code" "browser with whitespace should fail"

if [[ "$fail_count" -ne 0 ]]; then
  echo "\n$fail_count test(s) failed, $pass_count passed"
  exit 1
fi

echo "$pass_count test(s) passed"
