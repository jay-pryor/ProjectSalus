#!/usr/bin/env bash
# Salus hook: pre-commit
# Trigger: PreToolUse on Bash (intercepts git commit commands)
# Action: Run ruff lint + format check on staged Python files. Block on failures.

set -uo pipefail

PROJECT_DIR="${SALUS_PROJECT_DIR:-/workspaces/ProjectSalus}"

# Read stdin to check if this is a git commit command
STDIN_DATA=$(cat)
if ! echo "$STDIN_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cmd = data.get('tool_input', {}).get('command', '')
    if 'git commit' in cmd:
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    # Not a git commit — nothing to do
    exit 0
fi

cd "$PROJECT_DIR"

# Get staged Python files
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | grep '\.py$' || true)

if [ -z "$STAGED_PY" ]; then
    exit 0
fi

echo "Salus pre-commit: checking staged Python files..." >&2

# G1: Lint check (blocks on failure)
LINT_OUT=$(echo "$STAGED_PY" | xargs ruff check --quiet 2>&1)
LINT_EXIT=$?
if [ $LINT_EXIT -ne 0 ]; then
    echo "BLOCK: G1 lint failed — fix ruff errors before committing:" >&2
    echo "$LINT_OUT" >&2
    echo "" >&2
    echo "Run: ruff check src/ tests/" >&2
    exit 1
fi

# G2: Format check (warns but does not block)
FORMAT_OUT=$(echo "$STAGED_PY" | xargs ruff format --check --quiet 2>&1 || true)
if [ -n "$FORMAT_OUT" ]; then
    echo "WARNING: G2 format issues (run 'ruff format src/ tests/' to fix):" >&2
    echo "$FORMAT_OUT" >&2
fi

# Detect secrets (if available)
if command -v detect-secrets &>/dev/null && [ -f "$PROJECT_DIR/.secrets.baseline" ]; then
    git diff --cached --diff-filter=ACMR -p | detect-secrets-hook --baseline "$PROJECT_DIR/.secrets.baseline" 2>/dev/null || {
        echo "BLOCK: detect-secrets found potential secrets in staged changes" >&2
        exit 1
    }
fi

echo "Salus pre-commit: staged files OK." >&2
exit 0
