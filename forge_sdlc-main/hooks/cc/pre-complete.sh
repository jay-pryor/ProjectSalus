#!/usr/bin/env bash
# Forge hook: pre-complete
# CC Event: PreToolUse (before completion)
# Action: Validate all gate-proofs exist and passed
set -euo pipefail

FORGE_DIR="${FORGE_PROJECT_DIR:-.}/.forge"
GATE_PROOFS_DIR="$FORGE_DIR/gate-proofs"
TASK_ID="${FORGE_TASK_ID:-}"

# If no task ID set, skip gate-proof check
if [ -z "$TASK_ID" ]; then
    exit 0
fi

# Check if escape hatch flag is set
if [ "${FORGE_SKIP_REVIEW:-}" = "true" ]; then
    echo "WARNING: Review gate bypassed via escape hatch for $TASK_ID" >&2
    exit 0
fi

# Check gate-proof exists
PROOF_FILE="$GATE_PROOFS_DIR/${TASK_ID}.yaml"
if [ ! -f "$PROOF_FILE" ]; then
    echo "BLOCK: Gate-proof missing for task $TASK_ID" >&2
    echo "Run review agents first, or use --force-skip-review with --reason" >&2
    exit 1
fi

# Check gate-proof overall status
OVERALL=$(python3 -c "
import yaml
with open('$PROOF_FILE') as f:
    data = yaml.safe_load(f) or {}
print(data.get('overall', 'unknown'))
" 2>/dev/null || echo "unknown")

if [ "$OVERALL" != "pass" ]; then
    echo "BLOCK: Gate-proof for $TASK_ID has status: $OVERALL (need: pass)" >&2
    exit 1
fi

exit 0
