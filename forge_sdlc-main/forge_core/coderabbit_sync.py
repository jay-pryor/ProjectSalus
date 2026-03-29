"""Forge CodeRabbit sync — pull PR comments into the defect register."""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from forge_core.yaml_io import atomic_save, safe_load


def _run(cmd: list[str], cwd: str | None = None) -> str:
    """Run a subprocess with timeout, returning stripped stdout."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out: {' '.join(cmd)}") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _classify_severity(body: str) -> str:
    """Classify comment severity from keywords in the body."""
    lower = body.lower()
    if any(kw in lower for kw in ("critical", "security", "vulnerability")):
        return "critical"
    if any(kw in lower for kw in ("bug", "error", "incorrect", "missing")):
        return "high"
    return "medium"


def _fingerprint(path: str, body: str) -> str:
    """Create a dedup fingerprint from file path + first 50 chars of body."""
    return f"{path}:{body[:50]}"


def _max_defect_id(defects: list[dict]) -> int:
    """Find the highest D-NNN numeric id among existing defects."""
    max_id = 0
    pattern = re.compile(r"^D-(\d+)$")
    for d in defects:
        m = pattern.match(str(d.get("id", "")))
        if m:
            max_id = max(max_id, int(m.group(1)))
    return max_id


def sync_coderabbit_findings(project_dir: Path) -> dict:
    """Pull CodeRabbit PR comments into the defect register.

    Returns a dict with: success, action, pr_number, comments_found,
    findings_added, open_by_severity.
    """
    project_dir = Path(project_dir).resolve()
    cwd = str(project_dir)

    # 1. Get current git branch
    try:
        branch = _run(["git", "branch", "--show-current"], cwd=cwd)
    except RuntimeError as exc:
        return {"success": False, "action": "sync-coderabbit", "error": str(exc)}

    if not branch:
        return {
            "success": False,
            "action": "sync-coderabbit",
            "error": "Could not determine current branch (detached HEAD?).",
        }

    # 2. Find open PR for this branch
    try:
        pr_json = _run(
            ["gh", "pr", "list", "--head", branch, "--json", "number,url",
             "--jq", ".[0]"],
            cwd=cwd,
        )
    except RuntimeError as exc:
        return {"success": False, "action": "sync-coderabbit", "error": str(exc)}

    if not pr_json:
        return {
            "success": False,
            "action": "sync-coderabbit",
            "error": f"No open PR found for branch '{branch}'.",
        }

    pr_data = json.loads(pr_json)
    pr_number = pr_data["number"]

    # 3. Get repo name
    try:
        repo = _run(
            ["gh", "repo", "view", "--json", "nameWithOwner",
             "--jq", ".nameWithOwner"],
            cwd=cwd,
        )
    except RuntimeError as exc:
        return {"success": False, "action": "sync-coderabbit", "error": str(exc)}

    # 4. Fetch CodeRabbit comments
    jq_filter = (
        '[.[] | select(.user.login == "coderabbitai[bot]") '
        '| {path, line: .original_line, body, created_at}]'
    )
    try:
        comments_json = _run(
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/comments",
             "--jq", jq_filter],
            cwd=cwd,
        )
    except RuntimeError as exc:
        return {"success": False, "action": "sync-coderabbit", "error": str(exc)}

    comments = json.loads(comments_json) if comments_json else []

    # 5. Load defect register (handles both list and dict formats)
    defect_path = project_dir / ".forge" / "defect-register.yaml"
    raw = safe_load(defect_path, {"defects": []})

    if isinstance(raw, dict):
        defects = raw.get("defects", [])
        if not isinstance(defects, list):
            defects = []
    else:
        defects = []

    # 6. Find max defect ID
    next_id = _max_defect_id(defects) + 1

    # 7. Build existing fingerprints for coderabbit entries
    existing_fps: set[str] = set()
    for d in defects:
        if d.get("found_by") == "coderabbit-pr-sync":
            fp = _fingerprint(
                str(d.get("file", "")),
                str(d.get("description", "")),
            )
            existing_fps.add(fp)

    # 8-9. Classify and append new defects
    added = 0
    now = datetime.now(timezone.utc).isoformat()
    for c in comments:
        fp = _fingerprint(str(c.get("path", "")), str(c.get("body", "")))
        if fp in existing_fps:
            continue
        existing_fps.add(fp)

        severity = _classify_severity(str(c.get("body", "")))
        defects.append({
            "id": f"D-{next_id:03d}",
            "file": c.get("path", ""),
            "line": c.get("line"),
            "severity": severity,
            "status": "open",
            "description": c.get("body", ""),
            "found_by": "coderabbit-pr-sync",
            "pr": pr_number,
            "created_at": c.get("created_at", now),
            "synced_at": now,
        })
        next_id += 1
        added += 1

    # 10. Save updated defect register
    raw["defects"] = defects
    atomic_save(defect_path, raw)

    # 11. Compute open_by_severity
    severity_counts: dict[str, int] = {}
    for d in defects:
        if d.get("status") == "open":
            sev = d.get("severity", "medium")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "success": True,
        "action": "sync-coderabbit",
        "pr_number": pr_number,
        "comments_found": len(comments),
        "findings_added": added,
        "open_by_severity": severity_counts,
    }
