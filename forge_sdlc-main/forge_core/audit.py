"""Immutable append-only audit log with log rotation.

v1.0.0 improvements:
- Configurable log rotation (max_size_mb + archive_count)
- Structured JSON entries alongside human-readable
- Archive files: audit.jsonl.1, audit.jsonl.2, etc.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from filelock import FileLock, Timeout as FileLockTimeout

from forge_core.jsonl_io import read_jsonl
from forge_core.log import safe_log


class AuditLog:
    def __init__(
        self,
        project_dir: Path,
        max_size_mb: float = 10.0,
        archive_count: int = 5,
    ):
        self._path = project_dir / ".forge" / "audit.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._archive_count = archive_count

    def emit(
        self,
        category: str,
        action: str,
        data: dict,
        provenance: dict | None = None,
    ) -> dict:
        """Append an audit event. Returns the event dict."""
        lock = FileLock(str(self._path) + ".lock", timeout=5)
        try:
            with lock:
                self._maybe_rotate()
                seq, prev_hash = self._read_last_event()

                event = {
                    "seq": seq + 1,
                    "ts": time.time(),
                    "category": category,
                    "action": action,
                    "data": data,
                    "prev_hash": prev_hash,
                }
                if provenance:
                    event["provenance"] = provenance

                event_json = json.dumps(event, sort_keys=True)
                event["hash"] = hashlib.sha256(event_json.encode()).hexdigest()

                with open(self._path, "a") as f:
                    f.write(json.dumps(event, sort_keys=True) + "\n")
                    f.flush()
                    os.fsync(f.fileno())

                safe_log(
                    "audit_event_emitted",
                    level="debug",
                    seq=event["seq"],
                    category=category,
                    action=action,
                )
        except FileLockTimeout:
            raise RuntimeError(
                f"Could not acquire lock on {self._path}.lock within 5s."
            )
        return event

    def verify_chain(self) -> dict:
        """Verify the integrity of the audit chain."""
        if not self._path.is_file():
            return {"valid": True, "events": 0, "issues": []}

        issues: list[str] = []
        events = 0
        prev_hash = ""
        skip_after_corrupt = False

        try:
            with open(self._path) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        issues.append(f"Line {line_num}: invalid JSON")
                        skip_after_corrupt = True
                        continue

                    events += 1

                    if skip_after_corrupt:
                        if event.get("seq") is not None:
                            events = event["seq"]
                    elif event.get("seq") != events:
                        issues.append(
                            f"Line {line_num}: expected seq {events}, got {event.get('seq')}"
                        )

                    if skip_after_corrupt:
                        skip_after_corrupt = False
                    elif event.get("prev_hash") != prev_hash:
                        issues.append(f"Line {line_num}: prev_hash mismatch")

                    stored_hash = event.get("hash", "")
                    hashless = {k: v for k, v in event.items() if k != "hash"}
                    event_json = json.dumps(hashless, sort_keys=True)
                    computed_hash = hashlib.sha256(event_json.encode()).hexdigest()

                    if stored_hash != computed_hash:
                        issues.append(f"Line {line_num}: hash mismatch (tampered)")

                    prev_hash = stored_hash

        except OSError as exc:
            issues.append(f"Cannot read audit log: {exc}")

        return {"valid": len(issues) == 0, "events": events, "issues": issues}

    def tail(self, count: int = 10) -> list[dict]:
        """Return the last N events."""
        if not self._path.is_file():
            return []
        from collections import deque
        recent: deque[dict] = deque(maxlen=count)
        try:
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        recent.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return []
        return list(recent)

    def read_all(self) -> list[dict]:
        """Return all audit events."""
        return read_jsonl(self._path)

    def _maybe_rotate(self) -> None:
        """Rotate the audit log if it exceeds max size."""
        if not self._path.is_file():
            return
        try:
            size = self._path.stat().st_size
        except OSError:
            return
        if size < self._max_size_bytes:
            return

        # Rotate: audit.jsonl.2 -> audit.jsonl.3, audit.jsonl.1 -> audit.jsonl.2, etc.
        for i in range(self._archive_count, 1, -1):
            src = self._path.parent / f"audit.jsonl.{i - 1}"
            dst = self._path.parent / f"audit.jsonl.{i}"
            if src.is_file():
                shutil.move(str(src), str(dst))

        # Current -> .1
        archive_1 = self._path.parent / "audit.jsonl.1"
        shutil.move(str(self._path), str(archive_1))

        # Delete oldest if over limit
        oldest = self._path.parent / f"audit.jsonl.{self._archive_count + 1}"
        if oldest.is_file():
            oldest.unlink()

        safe_log("audit_log_rotated", level="info", archived_to=str(archive_1))

    def _read_last_event(self) -> tuple[int, str]:
        """Read sequence number and hash from the last event."""
        if not self._path.is_file():
            return (0, "")
        last_line = ""
        try:
            with open(self._path) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
        except OSError as exc:
            raise RuntimeError(
                f"Audit log exists but cannot be read: {exc}."
            ) from exc
        if not last_line:
            return (0, "")
        try:
            event = json.loads(last_line)
            return (event.get("seq", 0), event.get("hash", ""))
        except json.JSONDecodeError:
            raise RuntimeError(
                "Audit log last line is corrupt JSON. Chain integrity at risk."
            )
