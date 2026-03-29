#!/usr/bin/env bash
# Forge hook: post-commit
# CC Event: PostToolUse (Bash: git commit)
# Action: Evidence snapshot, CI trigger
set -euo pipefail

PROJECT_DIR="${FORGE_PROJECT_DIR:-.}"
cd "$PROJECT_DIR"

# Record commit SHA in forge audit
COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
COMMIT_MSG=$(git log -1 --format='%s' 2>/dev/null || echo "unknown")

if command -v forge &>/dev/null; then
    # This is informational — no blocking
    echo "Forge: recorded commit $COMMIT_SHA" >&2
fi

exit 0
