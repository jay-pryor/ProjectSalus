"""Hookify hook: pre-complete — validate gate-proofs exist and passed."""
import os
import sys
from pathlib import Path

import yaml


def run() -> int:
    forge_dir = Path(os.environ.get("FORGE_PROJECT_DIR", ".")) / ".forge"
    task_id = os.environ.get("FORGE_TASK_ID", "")

    if not task_id:
        return 0

    if os.environ.get("FORGE_SKIP_REVIEW") == "true":
        print(f"WARNING: Review gate bypassed for {task_id}", file=sys.stderr)
        return 0

    proof_file = forge_dir / "gate-proofs" / f"{task_id}.yaml"
    if not proof_file.is_file():
        print(f"BLOCK: Gate-proof missing for task {task_id}", file=sys.stderr)
        return 1

    with open(proof_file) as f:
        data = yaml.safe_load(f) or {}
    overall = data.get("overall", "unknown")
    if overall != "pass":
        print(f"BLOCK: Gate-proof status: {overall} (need: pass)", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run())
