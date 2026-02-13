#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/install-worai.sh"
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

# Case 1: missing version
code=$(run_case missing_version "${BASE_ENV[@]}" "$SCRIPT")
assert_eq "1" "$code" "missing version should fail"

# Case 2: whitespace in version
code=$(run_case bad_version "${BASE_ENV[@]}" INPUT_WORAI_VERSION="1.2 3" "$SCRIPT")
assert_eq "1" "$code" "version with whitespace should fail"

# Case 3: install with python3
rm -f "$TMP_DIR/python_calls.txt"
code=$(run_case install_python3 "${BASE_ENV[@]}" INPUT_WORAI_VERSION="1.16.2" "$SCRIPT")
assert_eq "0" "$code" "python3 install should succeed"
first_call=$(sed -n '1p' "$TMP_DIR/python_calls.txt")
second_call=$(sed -n '2p' "$TMP_DIR/python_calls.txt")
assert_eq "-m pip install --upgrade pip" "$first_call" "first command upgrades pip"
assert_eq "-m pip install worai==1.16.2" "$second_call" "second command installs pinned worai"

# Case 4: missing python interpreters
EMPTY_BIN="$TMP_DIR/empty-bin"
mkdir -p "$EMPTY_BIN"
code=$(run_case no_python /usr/bin/env PATH="$EMPTY_BIN" INPUT_WORAI_VERSION="1.16.2" /bin/bash "$SCRIPT")
assert_eq "1" "$code" "missing python should fail"

if [[ "$fail_count" -ne 0 ]]; then
  echo "\n$fail_count test(s) failed, $pass_count passed"
  exit 1
fi

echo "$pass_count test(s) passed"
