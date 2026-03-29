#!/usr/bin/env bash
# Forge hook: post-implement
# CC Event: PostToolUse (after Edit/Write)
# Action: Run applicable standards checks on modified files
set -euo pipefail

PROJECT_DIR="${FORGE_PROJECT_DIR:-.}"

# Get list of modified files from git
MODIFIED_FILES=$(cd "$PROJECT_DIR" && git diff --name-only HEAD 2>/dev/null || echo "")

if [ -z "$MODIFIED_FILES" ]; then
    exit 0
fi

# Run ruff lint on Python files
PY_FILES=$(echo "$MODIFIED_FILES" | grep '\.py$' || true)
if [ -n "$PY_FILES" ]; then
    cd "$PROJECT_DIR"
    echo "$PY_FILES" | xargs ruff check --quiet 2>/dev/null || {
        echo "WARNING: ruff found lint issues in modified files" >&2
    }
fi

exit 0
