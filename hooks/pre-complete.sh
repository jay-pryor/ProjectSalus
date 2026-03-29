#!/usr/bin/env bash
# Salus hook: pre-complete
# Trigger: PreToolUse on Bash (intercepts task-complete signals)
# Action: Validate gate-proof exists for the current task. Block if missing.

set -uo pipefail

PROJECT_DIR="${SALUS_PROJECT_DIR:-/workspaces/ProjectSalus}"
FORGE_DIR="$PROJECT_DIR/.forge"
GATE_PROOFS_DIR="$FORGE_DIR/gate-proofs"

# Skip if escape hatch set
if [ "${SALUS_SKIP_REVIEW:-}" = "true" ]; then
    echo "WARNING: Review gate bypassed via SALUS_SKIP_REVIEW escape hatch" >&2
    exit 0
fi

# Check if gate-proofs directory has any recent proofs
if [ ! -d "$GATE_PROOFS_DIR" ]; then
    echo "BLOCK: .forge/gate-proofs/ directory missing — cannot verify gate-proof." >&2
    echo "Complete the review sequence and write a gate-proof before marking task done." >&2
    exit 1
fi

PROOF_COUNT=$(find "$GATE_PROOFS_DIR" -name "*.yaml" 2>/dev/null | wc -l)
if [ "$PROOF_COUNT" -eq 0 ]; then
    echo "BLOCK: No gate-proofs found in .forge/gate-proofs/" >&2
    echo "You must complete the full review sequence (gates G1-G8 + L1 + L2 agents)" >&2
    echo "and write a gate-proof YAML before this task can be marked complete." >&2
    echo "" >&2
    echo "See CLAUDE.md → Gate-Proof Format for the required structure." >&2
    exit 1
fi

# If a specific task ID is set, check for that proof specifically
TASK_ID="${SALUS_TASK_ID:-}"
if [ -n "$TASK_ID" ]; then
    PROOF_FILE="$GATE_PROOFS_DIR/${TASK_ID}.yaml"
    if [ ! -f "$PROOF_FILE" ]; then
        echo "BLOCK: Gate-proof missing for task $TASK_ID" >&2
        echo "Expected: $PROOF_FILE" >&2
        exit 1
    fi

    OVERALL=$(python3 -c "
import yaml, sys
with open('$PROOF_FILE') as f:
    data = yaml.safe_load(f) or {}
print(data.get('overall', 'unknown'))
" 2>/dev/null || echo "unknown")

    if [ "$OVERALL" != "pass" ]; then
        echo "BLOCK: Gate-proof for $TASK_ID has overall: $OVERALL (need: pass)" >&2
        exit 1
    fi
fi

echo "Salus pre-complete: gate-proof verified OK." >&2
exit 0
