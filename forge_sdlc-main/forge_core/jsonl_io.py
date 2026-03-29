"""Shared JSONL read/append helpers with fsync and lock-timeout handling."""

import json
import os
from pathlib import Path

from filelock import FileLock, Timeout as FileLockTimeout

from forge_core.log import safe_log


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, skipping corrupt lines."""
    if not path.is_file():
        return []
    events: list[dict] = []
    try:
        f = open(path)
    except FileNotFoundError:
        return []
    with f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                safe_log(
                    "jsonl_corrupt_line_skipped",
                    level="warning",
                    path=str(path),
                    line_num=line_num,
                )
                continue
    return events


def append_jsonl(path: Path, event: dict, lock_timeout: float = 5.0) -> None:
    """Append a JSON event to a JSONL file with file locking and fsync."""
    lock = FileLock(str(path) + ".lock", timeout=lock_timeout)
    try:
        with lock:
            with open(path, "a") as f:
                f.write(json.dumps(event, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except FileLockTimeout:
        raise RuntimeError(
            f"Could not acquire lock on {path}.lock within {lock_timeout}s. "
            f"Another process may be holding the lock."
        )
