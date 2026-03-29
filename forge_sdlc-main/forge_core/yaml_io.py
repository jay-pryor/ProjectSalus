"""Forge YAML I/O — atomic save and safe load for state files."""

import copy
import os
import tempfile
from pathlib import Path
from typing import Callable

import yaml
from filelock import FileLock, Timeout


def _atomic_save_unlocked(path: Path, data: dict) -> None:
    """Write data to a YAML file atomically using write-then-rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, suffix=".tmp", prefix=f"{path.stem}_"
        )
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, path)
    except Exception as exc:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise RuntimeError(f"Failed to save YAML to {path}: {exc}") from exc


def atomic_save(path: Path, data: dict, timeout: float = 10.0) -> None:
    """Write data to a YAML file atomically with file locking."""
    path = Path(path)
    lock = FileLock(str(path) + ".lock", timeout=timeout)
    try:
        with lock:
            _atomic_save_unlocked(path, data)
    except Timeout:
        raise RuntimeError(
            f"Could not acquire lock on {path} within {timeout}s — "
            f"another process may be writing. Lock file: {path}.lock"
        )


def safe_load(path: Path, defaults: dict) -> dict:
    """Load a YAML file safely, returning defaults if missing."""
    path = Path(path)
    if not path.is_file():
        return copy.deepcopy(defaults)
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"{path.name} is corrupt and cannot be parsed: {exc}. "
            f"Run 'forge health repair' or inspect {path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Cannot read {path}: {exc}") from exc

    if data is None:
        return copy.deepcopy(defaults)

    if not isinstance(data, dict):
        raise RuntimeError(
            f"{path.name} has unexpected structure "
            f"(expected dict, got {type(data).__name__}). "
            f"Run 'forge health repair' or inspect {path}"
        )
    return data


def locked_update(
    path: Path,
    defaults: dict,
    updater: Callable[[dict], dict],
    timeout: float = 10.0,
) -> dict:
    """Atomically read, update, and write a YAML file under a single lock."""
    path = Path(path)
    lock = FileLock(str(path) + ".lock", timeout=timeout)
    try:
        with lock:
            data = safe_load(path, defaults)
            updated = updater(data)
            _atomic_save_unlocked(path, updated)
            return updated
    except Timeout:
        raise RuntimeError(
            f"Could not acquire lock on {path} within {timeout}s — "
            f"another process may be writing. Lock file: {path}.lock"
        )
