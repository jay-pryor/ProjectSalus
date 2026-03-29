"""Forge CLI — Click-based command-line interface for the Forge SDLC framework.

Entry point for all forge operations: session management, task tracking,
evidence, standards checking, cross-cutting audits, health, and config sync.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from forge_core import __version__

# ── Output helpers ────────────────────────────────────────────────────


def _json_out(data: dict) -> None:
    """Print a dict as compact JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def _json_response(data: dict) -> None:
    """Print JSON and exit 1 if success is False."""
    _json_out(data)
    if not data.get("success", True):
        sys.exit(1)


def _get_project_dir() -> Path:
    """Resolve project directory from env or cwd."""
    env_dir = os.environ.get("FORGE_PROJECT_DIR")
    return Path(env_dir).resolve() if env_dir else Path.cwd().resolve()


# ── Root command ──────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="forge")
def cli() -> None:
    """Forge SDLC framework — engineering standards enforcement."""
    pass


# ── Session commands ──────────────────────────────────────────────────


@cli.group()
def session() -> None:
    """Session lifecycle management."""
    pass


@session.command("start")
@click.option("--agent", default="claude", help="Agent identifier")
def session_start(agent: str) -> None:
    """Start a new Forge session."""
    from forge_core.session import SessionManager
    project_dir = _get_project_dir()
    mgr = SessionManager(project_dir)
    result = mgr.start_session()
    _json_response(result)


@session.command("end")
def session_end() -> None:
    """End the current session."""
    from forge_core.session import SessionManager
    project_dir = _get_project_dir()
    mgr = SessionManager(project_dir)
    result = mgr.end_session()
    _json_response(result)


@session.command("status")
def session_status() -> None:
    """Show current session status."""
    from forge_core.session import SessionManager
    project_dir = _get_project_dir()
    mgr = SessionManager(project_dir)
    result = mgr.get_status()
    _json_response(result)


@session.command("resume")
def session_resume() -> None:
    """Show resume context from previous session."""
    from forge_core.session import SessionManager
    project_dir = _get_project_dir()
    mgr = SessionManager(project_dir)
    result = mgr.resume_session()
    _json_response(result)


# ── Tracker commands ──────────────────────────────────────────────────


@cli.group()
def tracker() -> None:
    """Task and phase tracking."""
    pass


@tracker.command("start")
@click.argument("task_id")
def tracker_start(task_id: str) -> None:
    """Mark a task as in-progress."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.start_task(task_id)
    _json_response(result)


@tracker.command("complete")
@click.argument("task_id")
@click.option("--validation", default="manual", help="Validation method used")
def tracker_complete(task_id: str, validation: str) -> None:
    """Mark a task as completed."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.complete_task(task_id, validation=validation)
    _json_response(result)


@tracker.command("block")
@click.argument("task_id")
@click.option("--reason", required=True, help="Reason for blocking")
def tracker_block(task_id: str, reason: str) -> None:
    """Mark a task as blocked."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.block_task(task_id, reason=reason)
    _json_response(result)


@tracker.command("skip")
@click.argument("task_id")
@click.option("--reason", required=True, help="Reason for skipping")
def tracker_skip(task_id: str, reason: str) -> None:
    """Mark a task as skipped."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.skip_task(task_id, reason=reason)
    _json_response(result)


@tracker.command("reopen")
@click.argument("task_id")
@click.option("--reason", required=True, help="Reason for reopening")
def tracker_reopen(task_id: str, reason: str) -> None:
    """Reopen a completed or skipped task."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.reopen_task(task_id, reason=reason)
    _json_response(result)


@tracker.command("status")
def tracker_status() -> None:
    """Show current tracker state summary."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.get_status()
    _json_response(result)


@tracker.command("list")
@click.option("--status", "filter_status", default=None, help="Filter by status")
def tracker_list(filter_status: str | None) -> None:
    """List tasks, optionally filtered by status."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.list_tasks(status_filter=filter_status)
    _json_response(result)


# ── Evidence commands ─────────────────────────────────────────────────


@cli.group()
def evidence() -> None:
    """Evidence management."""
    pass


@evidence.command("create")
@click.argument("task_id")
@click.argument("name")
def evidence_create(task_id: str, name: str) -> None:
    """Create an evidence artifact shell."""
    from forge_core.evidence import EvidenceManager
    project_dir = _get_project_dir()
    mgr = EvidenceManager(project_dir)
    result = mgr.create(task_id, name)
    _json_response(result)


@evidence.command("verify")
@click.option("--phase", required=True, help="Phase ID to verify")
def evidence_verify(phase: str) -> None:
    """Verify evidence completeness for a phase."""
    from forge_core.evidence import EvidenceManager
    project_dir = _get_project_dir()
    mgr = EvidenceManager(project_dir)
    result = mgr.verify_phase(phase)
    _json_response(result)


@evidence.command("summarise")
@click.argument("task_id")
def evidence_summarise(task_id: str) -> None:
    """Summarise evidence for a task."""
    from forge_core.evidence import EvidenceManager
    project_dir = _get_project_dir()
    mgr = EvidenceManager(project_dir)
    result = mgr.summarise(task_id)
    _json_response(result)


# ── Phase commands ────────────────────────────────────────────────────


@cli.group()
def phase() -> None:
    """Phase management."""
    pass


@phase.command("plan-gate")
@click.argument("phase_id")
def phase_plan_gate(phase_id: str) -> None:
    """Validate a phase specification."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.validate_phase_spec(phase_id)
    _json_response(result)


@phase.command("complete")
@click.argument("phase_id")
def phase_complete(phase_id: str) -> None:
    """Mark a phase as complete."""
    from forge_core.tracker import TaskTracker
    project_dir = _get_project_dir()
    t = TaskTracker(project_dir)
    result = t.complete_phase(phase_id)
    _json_response(result)


# ── Standards commands ────────────────────────────────────────────────


@cli.group("check")
def check() -> None:
    """Run automated checks (standards, cross-cutting, config-sync)."""
    pass


@check.command("standards")
@click.option("--file", "files", multiple=True, help="Files to check")
@click.option("--standard", "standards", multiple=True, help="Specific standards to check")
@click.option("--task-id", default="adhoc", help="Task ID for tracking")
def check_standards(files: tuple[str, ...], standards: tuple[str, ...], task_id: str) -> None:
    """Run standards checks on files."""
    from forge_core.standards_checker import StandardsChecker
    project_dir = _get_project_dir()
    checker = StandardsChecker(project_dir)
    file_list = list(files) if files else None
    standard_list = list(standards) if standards else None

    if file_list is None:
        # Discover files from git
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-files"], capture_output=True, text=True,
                timeout=10, cwd=str(project_dir),
            )
            if result.returncode == 0:
                file_list = [f for f in result.stdout.strip().splitlines() if f]
            else:
                file_list = []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            file_list = []

    result = checker.check(task_id, file_list, active_standards=standard_list)
    _json_response(result)


@check.command("cross-cutting")
@click.option("--category", "categories", multiple=True, help="Specific categories to check")
def check_cross_cutting(categories: tuple[str, ...]) -> None:
    """Run cross-cutting consistency checks."""
    from forge_core.cross_cutting import CrossCuttingAuditor
    project_dir = _get_project_dir()
    auditor = CrossCuttingAuditor(project_dir)
    category_list = list(categories) if categories else None
    result = auditor.audit(checks=category_list)
    _json_response(result)


@check.command("config-sync")
def check_config_sync() -> None:
    """Validate config consistency."""
    from forge_core.config_sync import ConfigSyncValidator
    # Config sync works from forge-sdlc root, not project dir
    forge_root = Path(__file__).resolve().parent.parent
    validator = ConfigSyncValidator(forge_root)
    result = validator.validate_all()
    _json_response(result)


# ── Sync commands ────────────────────────────────────────────────────


@cli.group()
def sync() -> None:
    """Sync external findings into Forge."""
    pass


@sync.command("coderabbit")
def sync_coderabbit() -> None:
    """Pull CodeRabbit PR comments into defect register."""
    from forge_core.coderabbit_sync import sync_coderabbit_findings
    project_dir = _get_project_dir()
    result = sync_coderabbit_findings(project_dir)
    _json_response(result)


# ── Standards loader commands ─────────────────────────────────────────


@cli.group("standards")
def standards() -> None:
    """Standards listing and loading."""
    pass


@standards.command("list")
def standards_list() -> None:
    """List all available standards."""
    from forge_core.standards_loader import StandardsLoader
    loader = StandardsLoader()
    result = loader.list_standards()
    _json_response(result)


@standards.command("show")
@click.argument("name")
def standards_show(name: str) -> None:
    """Show a specific standard's content."""
    from forge_core.standards_loader import StandardsLoader
    loader = StandardsLoader()
    result = loader.load(name)
    _json_response(result)


# ── Health commands ───────────────────────────────────────────────────


@cli.group()
def health() -> None:
    """Framework integrity checks."""
    pass


@health.command("check")
def health_check() -> None:
    """Run full integrity validation."""
    from forge_core.health import HealthChecker
    project_dir = _get_project_dir()
    checker = HealthChecker(project_dir)
    result = checker.check()
    _json_response(result)


@health.command("repair")
def health_repair() -> None:
    """Fix recoverable issues."""
    from forge_core.health import HealthChecker
    project_dir = _get_project_dir()
    checker = HealthChecker(project_dir)
    result = checker.repair()
    _json_response(result)


# ── Preflight commands ────────────────────────────────────────────────


@cli.command()
def preflight() -> None:
    """Pre-flight environment diagnostics."""
    from forge_core.preflight import PreflightDiagnostic
    diag = PreflightDiagnostic()
    result = diag.run()
    _json_response(result)


# ── Validate command ──────────────────────────────────────────────────


@cli.command()
@click.option("--file", "config_file", default=None, help="Config file to validate")
@click.option("--schema", "schema_name", default="config", help="Schema name")
@click.option("--strict/--no-strict", default=True, help="Strict mode (reject unknown keys)")
def validate(config_file: str | None, schema_name: str, strict: bool) -> None:
    """Validate a Forge config file against its schema."""
    from forge_core.validators import validate_config
    project_dir = _get_project_dir()

    if config_file is None:
        config_file = str(project_dir / ".forge" / "config.json")

    result = validate_config(Path(config_file), schema_name, strict=strict)
    _json_response(result)


# ── Init command ──────────────────────────────────────────────────────


@cli.command()
@click.argument("project_name")
@click.option("--dir", "project_dir", default=".", help="Project directory")
@click.option("--profile", default="standard", help="Governance profile: standard or light")
def init(project_name: str, project_dir: str, profile: str) -> None:
    """Bootstrap a project with Forge scaffolding."""
    target = Path(project_dir).resolve()
    forge_dir = target / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)

    # Detect project type
    from forge_core.standards_loader import StandardsLoader
    loader = StandardsLoader()
    project_type = loader.detect_project_type(target)

    # Create config.json
    config = {
        "version": "1.0.0",
        "project_name": project_name,
        "project_type": project_type,
        "governance_profile": profile,
        "hooks_enabled": True,
    }
    config_path = forge_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    # Create tracker.yaml
    import yaml
    tracker_data = {
        "version": "1.0.0",
        "project": project_name,
        "phases": [],
    }
    tracker_path = forge_dir / "tracker.yaml"
    tracker_path.write_text(yaml.dump(tracker_data, default_flow_style=False))

    # Create state.yaml
    state_data = {
        "version": "1.0.0",
        "current_session": None,
        "history": [],
    }
    state_path = forge_dir / "state.yaml"
    state_path.write_text(yaml.dump(state_data, default_flow_style=False))

    # Create log.md
    log_path = forge_dir / "log.md"
    log_path.write_text(f"# Forge Implementation Log — {project_name}\n\n")

    # Create evidence dir
    evidence_dir = target / "evidence"
    evidence_dir.mkdir(exist_ok=True)

    # Create gate-proofs dir
    gate_proofs_dir = forge_dir / "gate-proofs"
    gate_proofs_dir.mkdir(exist_ok=True)

    _json_response({
        "success": True,
        "action": "init",
        "project_name": project_name,
        "project_type": project_type,
        "governance_profile": profile,
        "created": [
            str(config_path),
            str(tracker_path),
            str(state_path),
            str(log_path),
            str(evidence_dir),
            str(gate_proofs_dir),
        ],
    })


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
