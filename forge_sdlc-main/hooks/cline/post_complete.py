"""Hookify hook: post-complete — update tracker."""
import os
import subprocess
import sys


def run() -> int:
    task_id = os.environ.get("FORGE_TASK_ID", "")
    if not task_id:
        return 0

    project_dir = os.environ.get("FORGE_PROJECT_DIR", ".")
    subprocess.run(
        ["forge", "tracker", "complete", task_id, "--validation", "hook-verified"],
        capture_output=True, timeout=10, cwd=project_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
