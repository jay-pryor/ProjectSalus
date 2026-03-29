"""Hookify hook: pre-review — verify implementation complete."""
import os
import subprocess
import sys


def run() -> int:
    project_dir = os.environ.get("FORGE_PROJECT_DIR", ".")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10, cwd=project_dir,
    )
    if result.returncode == 0:
        count = len([l for l in result.stdout.strip().splitlines() if l])
        if count > 0:
            print(f"WARNING: {count} uncommitted changes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
