#!/usr/bin/env bash
# Forge hook: pre-commit
# CC Event: PreToolUse (Bash: git commit)
# Action: Lint, format, detect-secrets, conventional commit
set -euo pipefail

PROJECT_DIR="${FORGE_PROJECT_DIR:-.}"
cd "$PROJECT_DIR"

# Run ruff on staged Python files
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACMR | grep '\.py$' || true)
if [ -n "$STAGED_PY" ]; then
    echo "$STAGED_PY" | xargs ruff check --quiet 2>/dev/null || {
        echo "BLOCK: ruff lint errors in staged files" >&2
        exit 1
    }
    echo "$STAGED_PY" | xargs ruff format --check --quiet 2>/dev/null || {
        echo "WARNING: ruff format issues in staged files" >&2
    }
fi

# Run detect-secrets if available
if command -v detect-secrets &>/dev/null; then
    git diff --cached --diff-filter=ACMR -p | detect-secrets-hook --baseline .secrets.baseline 2>/dev/null || {
        echo "BLOCK: detect-secrets found potential secrets in staged changes" >&2
        exit 1
    }
fi

exit 0
