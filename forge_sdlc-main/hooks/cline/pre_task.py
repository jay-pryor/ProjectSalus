"""Hookify hook: pre-task — validate task spec exists, check lock."""
import os
import sys
from pathlib import Path

import yaml


def run() -> int:
    forge_dir = Path(os.environ.get("FORGE_PROJECT_DIR", ".")) / ".forge"
    if not forge_dir.is_dir():
        print("BLOCK: .forge/ directory not found. Run 'forge init' first.", file=sys.stderr)
        return 1

    state_file = forge_dir / "state.yaml"
    if state_file.is_file():
        with open(state_file) as f:
            data = yaml.safe_load(f) or {}
        if not data.get("current_session"):
            print("WARNING: No active session.", file=sys.stderr)

    lock_file = forge_dir / ".lock"
    if lock_file.is_file():
        owner = lock_file.read_text().strip()
        print(f"WARNING: Project locked by: {owner}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(run())
