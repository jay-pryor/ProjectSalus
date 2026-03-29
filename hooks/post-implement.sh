#!/usr/bin/env bash
# Salus hook: post-implement
# Trigger: PostToolUse on Write or Edit
# Action: Run ruff lint on modified Python files, warn on issues

set -uo pipefail

PROJECT_DIR="${SALUS_PROJECT_DIR:-/workspaces/ProjectSalus}"

# Get modified Python files from git
MODIFIED=$(cd "$PROJECT_DIR" && git diff --name-only HEAD 2>/dev/null | grep '\.py$' || true)

if [ -z "$MODIFIED" ]; then
    exit 0
fi

cd "$PROJECT_DIR"
LINT_OUT=$(echo "$MODIFIED" | xargs ruff check --quiet 2>&1 || true)

if [ -n "$LINT_OUT" ]; then
    echo "⚠ Salus/ruff: lint issues in modified files:" >&2
    echo "$LINT_OUT" >&2
    echo "Run 'ruff check src/ tests/' to see all issues before committing." >&2
fi

exit 0
