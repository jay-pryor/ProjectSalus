#!/usr/bin/env bash
# Forge hook: post-review
# CC Event: PostToolUse (after review agent)
# Action: Aggregate findings into gate-proof YAML
set -euo pipefail

FORGE_DIR="${FORGE_PROJECT_DIR:-.}/.forge"
GATE_PROOFS_DIR="$FORGE_DIR/gate-proofs"

# Ensure gate-proofs directory exists
mkdir -p "$GATE_PROOFS_DIR"

# This hook is primarily informational — the actual gate-proof writing
# is done by the forge-review skill which has access to agent output.
# This hook validates the gate-proofs directory is writable.

if [ ! -w "$GATE_PROOFS_DIR" ]; then
    echo "BLOCK: gate-proofs directory not writable: $GATE_PROOFS_DIR" >&2
    exit 1
fi

exit 0
