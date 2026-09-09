#!/bin/sh
set -u

operation_id="astrid-canonical-pack-beta-20260831-a1"
container_workspace="/workspace/astrid-canonical-pack-beta-20260831-a1"
repo="$container_workspace/Astrid"
session="$operation_id-orchestrator"
log="$container_workspace/orchestrator-run.log"
brief="$repo/.oracle/cloud/orchestrator-brief.md"
launcher="/root/.codex/skills/subagent-launcher/launch_hermes_agent.py"
status="$repo/.oracle/status.md"

export PYTHONPATH="/workspace/arnold"

while :; do
  if grep -Eiq 'Goal state:.*COMPLETE|^phase: COMPLETE|COMPLETED:' "$status" 2>/dev/null; then
    exit 0
  fi

  if ! tmux has-session -t "$session" 2>/dev/null; then
    tmux new-session -d -s "$session" \
      "cd '$repo' && PYTHONPATH=/workspace/arnold python3 '$launcher' --model=codex:gpt-5.6-sol --query-file='$brief' --project-dir='$repo' --timeout=7200 2>&1 | tee -a '$log'"
  fi

  sleep 45
done
