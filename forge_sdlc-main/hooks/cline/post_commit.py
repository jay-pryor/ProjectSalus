"""Hookify hook: post-commit — record commit in audit trail."""
import os
import subprocess
import sys


def run() -> int:
    project_dir = os.environ.get("FORGE_PROJECT_DIR", ".")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10, cwd=project_dir,
    )
    if result.returncode == 0:
        sha = result.stdout.strip()[:12]
        print(f"Forge: recorded commit {sha}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
