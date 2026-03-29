"""Hookify hook: post-review — validate gate-proofs directory."""
import os
import sys
from pathlib import Path


def run() -> int:
    forge_dir = Path(os.environ.get("FORGE_PROJECT_DIR", ".")) / ".forge"
    gate_proofs = forge_dir / "gate-proofs"
    gate_proofs.mkdir(parents=True, exist_ok=True)
    if not os.access(gate_proofs, os.W_OK):
        print(f"BLOCK: gate-proofs not writable: {gate_proofs}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
