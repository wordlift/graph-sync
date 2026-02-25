#!/usr/bin/env bash
set -euo pipefail

install_playwright="${INPUT_INSTALL_PLAYWRIGHT:-}"
playwright_version="${INPUT_PLAYWRIGHT_VERSION:-}"
playwright_browser="${INPUT_PLAYWRIGHT_BROWSER:-}"

if [[ -z "$install_playwright" ]]; then
  echo "error: input 'install_playwright' is required" >&2
  exit 1
fi

if [[ "$install_playwright" =~ [[:space:]] ]]; then
  echo "error: input 'install_playwright' must not contain whitespace" >&2
  exit 1
fi

install_playwright_lc="$(printf '%s' "$install_playwright" | tr '[:upper:]' '[:lower:]')"

case "$install_playwright_lc" in
  true|1|yes)
    should_install=true
    ;;
  false|0|no)
    should_install=false
    ;;
  *)
    echo "error: input 'install_playwright' must be one of true/false/1/0/yes/no" >&2
    exit 1
    ;;
esac

if [[ "$should_install" == "false" ]]; then
  echo "Playwright installation disabled via input 'install_playwright'"
  exit 0
fi

if [[ -z "$playwright_version" ]]; then
  echo "error: input 'playwright_version' is required when install_playwright is enabled" >&2
  exit 1
fi

if [[ "$playwright_version" =~ [[:space:]] ]]; then
  echo "error: input 'playwright_version' must not contain whitespace" >&2
  exit 1
fi

if [[ -z "$playwright_browser" ]]; then
  echo "error: input 'playwright_browser' is required when install_playwright is enabled" >&2
  exit 1
fi

if [[ "$playwright_browser" =~ [[:space:]] ]]; then
  echo "error: input 'playwright_browser' must not contain whitespace" >&2
  exit 1
fi

python_cmd=""
if command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
else
  echo "error: Python is required but neither 'python3' nor 'python' was found in PATH" >&2
  exit 1
fi

# Install pinned Python Playwright package and then browser binaries.
"$python_cmd" -m pip install "playwright==$playwright_version"
"$python_cmd" -m playwright install "$playwright_browser"
