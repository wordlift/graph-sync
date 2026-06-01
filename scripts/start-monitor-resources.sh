#!/usr/bin/env bash
set -euo pipefail

profile="${INPUT_PROFILE:-}"
working_directory="${INPUT_WORKING_DIRECTORY:-.}"
output_dir="${INPUT_OUTPUT_DIR:-${GITHUB_WORKSPACE}/output/${INPUT_PROFILE}}"
memory_gib="${INPUT_MEMORY_GIB:-}"

if [[ -z "$memory_gib" ]]; then
  if [[ -f /proc/meminfo ]]; then
    memory_gib=$(awk '/MemTotal/ { printf "%.1f\n", $2/1024/1024 }' /proc/meminfo)
  elif command -v sysctl >/dev/null 2>&1; then
    memory_gib=$(sysctl -n hw.memsize 2>/dev/null | awk '{ printf "%.1f\n", $1/1024/1024/1024 }')
  else
    memory_gib="4"
  fi
fi

mkdir -p "$output_dir"

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
  echo "warning: resource monitor requires Python 3.11+; $(python3 --version 2>&1) found — skipping" >&2
  exit 0
fi

python3 "$GITHUB_ACTION_PATH/scripts/monitor_resources.py" \
  --root "$working_directory" \
  --watch "graph sync run" \
  --watch-timeout 300 \
  --memory-gib "$memory_gib" \
  --profile "$profile" \
  --output "$output_dir/memory_report.json" \
  --markdown-output "$output_dir/memory_report.md" \
  >> "$output_dir/memory_monitor.log" 2>&1 &

echo "$!" > "$RUNNER_TEMP/monitor-${profile}.pid"
