#!/usr/bin/env bash
# Forge hook: pre-task
# CC Event: PreToolUse (on task start)
# Action: Validate task spec exists, check lock, load standards
set -euo pipefail

FORGE_DIR="${FORGE_PROJECT_DIR:-.}/.forge"

# Check .forge directory exists
if [ ! -d "$FORGE_DIR" ]; then
    echo "BLOCK: .forge/ directory not found. Run 'forge init' first." >&2
    exit 1
fi

# Check for active session
if [ -f "$FORGE_DIR/state.yaml" ]; then
    SESSION_ACTIVE=$(python3 -c "
import yaml
with open('$FORGE_DIR/state.yaml') as f:
    data = yaml.safe_load(f) or {}
session = data.get('current_session')
print('yes' if session else 'no')
" 2>/dev/null || echo "no")
    if [ "$SESSION_ACTIVE" = "no" ]; then
        echo "WARNING: No active session. Run 'forge session start' first." >&2
    fi
fi

# Check for lock file (another agent working on this project)
LOCK_FILE="$FORGE_DIR/.lock"
if [ -f "$LOCK_FILE" ]; then
    LOCK_OWNER=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
    echo "WARNING: Project locked by: $LOCK_OWNER" >&2
fi

exit 0
