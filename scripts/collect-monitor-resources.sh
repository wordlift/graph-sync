#!/usr/bin/env bash
set -euo pipefail

profile="${INPUT_PROFILE:-}"
output_dir="${INPUT_OUTPUT_DIR:-${GITHUB_WORKSPACE}/output/${profile}}"
pid_file="$RUNNER_TEMP/monitor-${profile}.pid"

if [[ -f "$pid_file" ]]; then
  sleep 3
  kill -INT "$(cat "$pid_file")" 2>/dev/null || true
  sleep 2
fi

log_file="$output_dir/memory_monitor.log"
if [[ -f "$log_file" ]]; then
  echo "--- resource monitor log ---"
  cat "$log_file"
else
  echo "resource monitor log not found at $log_file"
fi
