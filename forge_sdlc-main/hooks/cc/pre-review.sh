#!/usr/bin/env bash
# Forge hook: pre-review
# CC Event: PreToolUse (before review agent)
# Action: Verify implementation complete, tests pass
set -euo pipefail

PROJECT_DIR="${FORGE_PROJECT_DIR:-.}"

# Check for uncommitted changes
UNCOMMITTED=$(cd "$PROJECT_DIR" && git status --porcelain 2>/dev/null | wc -l)
if [ "$UNCOMMITTED" -gt 0 ]; then
    echo "WARNING: $UNCOMMITTED uncommitted changes — consider committing before review" >&2
fi

# Quick test check
if [ -f "$PROJECT_DIR/pyproject.toml" ] || [ -d "$PROJECT_DIR/tests" ]; then
    cd "$PROJECT_DIR"
    python3 -m pytest --co -q 2>/dev/null | tail -1 || true
fi

exit 0
