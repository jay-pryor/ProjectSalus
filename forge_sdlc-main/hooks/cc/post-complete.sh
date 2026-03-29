#!/usr/bin/env bash
# Forge hook: post-complete
# CC Event: PostToolUse (after completion)
# Action: Update state machine, audit log, notify
set -euo pipefail

PROJECT_DIR="${FORGE_PROJECT_DIR:-.}"
TASK_ID="${FORGE_TASK_ID:-}"

if [ -z "$TASK_ID" ]; then
    exit 0
fi

# Log completion to audit trail
cd "$PROJECT_DIR"
if command -v forge &>/dev/null; then
    forge tracker complete "$TASK_ID" --validation "hook-verified" 2>/dev/null || true
fi

exit 0
