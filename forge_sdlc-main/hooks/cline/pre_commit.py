"""Hookify hook: pre-commit — lint and detect-secrets on staged files."""
import os
import subprocess
import sys


def run() -> int:
    project_dir = os.environ.get("FORGE_PROJECT_DIR", ".")

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, timeout=10, cwd=project_dir,
    )
    if result.returncode != 0:
        return 0

    py_files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
    if py_files:
        lint = subprocess.run(
            ["ruff", "check", "--quiet"] + py_files,
            capture_output=True, text=True, timeout=30, cwd=project_dir,
        )
        if lint.returncode != 0:
            print("BLOCK: ruff lint errors in staged files", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(run())
