#!/usr/bin/env bash
set -euo pipefail

cache_enabled_raw="${INPUT_CACHE_ENABLED:-}"
cache_key_suffix_raw="${INPUT_CACHE_KEY_SUFFIX:-}"
worai_version="${INPUT_WORAI_VERSION:-}"
playwright_version="${INPUT_PLAYWRIGHT_VERSION:-}"
playwright_browser="${INPUT_PLAYWRIGHT_BROWSER:-}"

if [[ -z "$cache_enabled_raw" ]]; then
  echo "error: input 'cache_enabled' is required" >&2
  exit 1
fi

if [[ "$cache_enabled_raw" =~ [[:space:]] ]]; then
  echo "error: input 'cache_enabled' must not contain whitespace" >&2
  exit 1
fi

cache_enabled_lc="$(printf '%s' "$cache_enabled_raw" | tr '[:upper:]' '[:lower:]')"
case "$cache_enabled_lc" in
  true|1|yes)
    cache_enabled="true"
    ;;
  false|0|no)
    cache_enabled="false"
    ;;
  *)
    echo "error: input 'cache_enabled' must be one of true/false/1/0/yes/no" >&2
    exit 1
    ;;
esac

if [[ "$cache_enabled" == "false" ]]; then
  {
    echo "cache_enabled=false"
    echo "cache_key_suffix="
  } >> "$GITHUB_OUTPUT"
  exit 0
fi

if [[ "$cache_key_suffix_raw" =~ [[:space:]] ]]; then
  echo "error: input 'cache_key_suffix' must not contain whitespace" >&2
  exit 1
fi

if [[ -n "$cache_key_suffix_raw" ]]; then
  cache_key_suffix="$cache_key_suffix_raw"
else
  if [[ -z "$worai_version" ]]; then
    echo "error: input 'worai_version' is required when cache_key_suffix is empty" >&2
    exit 1
  fi
  if [[ -z "$playwright_version" ]]; then
    echo "error: input 'playwright_version' is required when cache_key_suffix is empty" >&2
    exit 1
  fi
  if [[ -z "$playwright_browser" ]]; then
    echo "error: input 'playwright_browser' is required when cache_key_suffix is empty" >&2
    exit 1
  fi

  cache_key_suffix="${worai_version}-${playwright_version}-${playwright_browser}"
fi

{
  echo "cache_enabled=true"
  echo "cache_key_suffix=$cache_key_suffix"
} >> "$GITHUB_OUTPUT"
