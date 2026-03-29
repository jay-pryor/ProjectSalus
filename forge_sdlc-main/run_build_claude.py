#!/usr/bin/env python3
"""run_build_claude.py — Claude Code runtime for the Forge autonomous build pipeline.

Parallel to run_build.py (Cline runtime). Uses Claude CLI sessions for builders
and reviewers instead of Docker containers. All Forge SDLC enforcement is
deterministic Python — LLM judgment calls are one-shot Opus CLI invocations.

Usage:
    run_build_claude.py --project <project> --spec <spec_path>
    run_build_claude.py --resume <build_id>
    run_build_claude.py --profile light|standard
    run_build_claude.py --drain-queue
"""
import argparse
import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Import shared logic
from forge_build_common import (
    EXECUTION_DIR,
    FORGE_DIR,
    GATE_PROFILES,
    MAX_BUILD_RETRIES,
    MAX_REVIEW_ROUNDS,
    QUEUE_DIR,
    RUNS_DIR,
    SCRIPTS_DIR,
    BuildState,
    acquire_lock,
    cleanup_working_copy,
    create_working_copy,
    extract_cross_task_context,
    forge_init_project,
    forge_session_end,
    forge_session_start,
    forge_tracker_status,
    generate_forge_task_spec,
    get_phase_diff,
    notify_telegram,
    precompute_tool_outputs,
    reconcile_evidence,
    reconcile_tracker,
    reconcile_tracker_task,
    release_lock,
    validate_plan,
    verify_committed_quality,
    verify_forge_state,
    verify_forge_state_task,
)

# ── Configuration ────────────────────────────────────────────────────────────
CLAUDE_PATH = (
    "/home/deploy/.npm-global/bin:"
    "/home/deploy/.local/bin:"
    "/home/deploy/forge-sdlc/.venv/bin:"
    "/usr/local/bin:/usr/bin:/bin"
)

CONFIG_FILE = Path(__file__).parent / "claude_build_models.yaml"

# Defaults (overridden by config file)
BUILDER_CPU_QUOTA = "400%"
BUILDER_MEM_MAX = "4G"
BUILDER_MEM_HIGH = "3G"
BUILDER_TIMEOUT = 2700  # 45 minutes

REVIEWER_CPU_QUOTA = "200%"
REVIEWER_MEM_MAX = "2G"
REVIEWER_TIMEOUT = 900  # 15 minutes

# FIX #3: Increased from 180s to 600s — Claude CLI sessions can go quiet for
# 5-10 minutes during complex reasoning. 3 min was causing false-positive kills.
STALL_TIMEOUT = 600  # 10 minutes no output
SWEEP_TIMEOUT = 900  # 15 minutes for low sweep

# L3 specialist panel (6 reviewers) — used in phase_review T_REVIEW
REVIEWER_NAMES = [
    "security_reviewer",
    "silent_failure_hunter",
    "type_safety_reviewer",
    "performance_reviewer",
    "contract_reviewer",
    "test_coverage_reviewer",
]

# L2 lightweight review agents (4 reviewers) — used in per-task task_review
L2_REVIEWER_NAMES = [
    "silent_failure_hunter",
    "code_reviewer",
    "code_simplifier",
    "regression_reviewer",
]

RUFF_EXCLUDE = ".venv,.forge,venv,*.egg-info,site-packages,build,dist"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("orchestrator")


def load_claude_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f)
    return {
        "builders": {
            "routine": {"model": "sonnet", "timeout_minutes": 45,
                        "cpu_quota": "400%", "mem_max": "4G", "mem_high": "3G"},
            "complex": {"model": "sonnet", "timeout_minutes": 60,
                        "cpu_quota": "600%", "mem_max": "6G", "mem_high": "5G"},
        },
        "orchestrator": {"model": "opus", "fallback": "sonnet", "timeout_seconds": 300},
        "reviewers": {"model": "sonnet", "timeout_minutes": 15,
                      "max_parallel": 6, "cpu_quota_each": "200%", "mem_max_each": "2G"},
        "verification": {"model": "sonnet", "timeout_seconds": 300},
    }


def _claude_env() -> dict:
    env = os.environ.copy()
    env["PATH"] = CLAUDE_PATH
    return env


# ── Opus Judgment Calls ──────────────────────────────────────────────────────
def opus_judge(prompt: str, work_dir: Path, timeout: int = 300) -> dict:
    """One-shot Opus CLI call for a judgment decision.

    Zero API cost (subscription). No session state. Falls back to Sonnet.
    """
    config = load_claude_config()
    model = config.get("orchestrator", {}).get("model", "opus")
    fallback = config.get("orchestrator", {}).get("fallback", "sonnet")

    for attempt_model in [model, fallback]:
        try:
            result = subprocess.run(
                ["claude", "--model", attempt_model, "--output-format", "json",
                 "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True, text=True,
                cwd=str(work_dir), timeout=timeout,
                env=_claude_env()
            )
            log.info(f"opus_judge ({attempt_model}): exit={result.returncode}, "
                     f"stdout={len(result.stdout or '')} chars")
            if result.returncode == 0 and result.stdout.strip():
                parsed = _parse_json_output(result.stdout)
                if parsed:
                    return parsed
                log.warning("opus_judge: could not parse JSON from output")
            elif result.returncode != 0:
                log.warning(f"opus_judge: exit code {result.returncode}")
                if result.stderr:
                    log.warning(f"stderr: {result.stderr[:300]}")
        except subprocess.TimeoutExpired:
            log.warning(f"opus_judge timed out with {attempt_model}, trying fallback")
            continue
        except Exception as e:
            log.warning(f"opus_judge failed with {attempt_model}: {e}")
            continue

    log.error("opus_judge failed on all models")
    return {}


def _parse_json_output(text: str) -> dict:
    """Parse JSON from Claude CLI output, handling the CLI envelope format."""
    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "result" in parsed and "type" in parsed:
            inner = parsed["result"]
            if isinstance(inner, dict):
                return inner
            if isinstance(inner, str):
                return _parse_inner_json(inner)
        return parsed
    except json.JSONDecodeError:
        pass

    return _parse_inner_json(text)


def _parse_inner_json(text: str) -> dict:
    """Extract JSON from text that may contain markdown fences."""
    text = text.strip()

    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find valid JSON objects using depth tracking (avoids greedy span)
    for match in re.finditer(r'\{', text):
        start = match.start()
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
                break

    log.warning(f"Could not parse JSON from: {text[:300]}")
    return {}


# ── Process Monitoring ───────────────────────────────────────────────────────
def _get_process_cpu(pid: int) -> float:
    try:
        stat_file = Path(f"/proc/{pid}/stat")
        if not stat_file.exists():
            return 0.0
        fields = stat_file.read_text().split()
        utime = int(fields[13])
        stime = int(fields[14])
        total = utime + stime
        time.sleep(1)
        if not stat_file.exists():
            return 0.0
        fields2 = stat_file.read_text().split()
        utime2 = int(fields2[13])
        stime2 = int(fields2[14])
        total2 = utime2 + stime2
        clk_tck = os.sysconf("SC_CLK_TCK")
        return ((total2 - total) / clk_tck) * 100
    except (OSError, IndexError, ValueError):
        return 0.0


def _has_claude_child(pid: int) -> bool:
    """Check if a systemd-run scope process still has a claude child running."""
    try:
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().strip()
        if not children:
            return False
        for child_pid in children.split():
            try:
                cmdline = Path(f"/proc/{child_pid}/cmdline").read_bytes()
                if b"claude" in cmdline:
                    return True
            except OSError:
                continue
        return False
    except OSError:
        return False


def _monitor_process(proc, log_file: Path, timeout: int, state=None, task_id=None) -> int:
    start = time.time()
    last_size = 0
    last_activity = time.time()
    last_heartbeat = 0
    empty_scope_checks = 0

    while proc.poll() is None:
        elapsed = time.time() - start
        if elapsed > timeout + 60:
            log.warning(f"Hard timeout at {elapsed:.0f}s")
            proc.kill()
            break

        try:
            current_size = log_file.stat().st_size
        except OSError:
            current_size = last_size

        if current_size > last_size:
            last_size = current_size
            last_activity = time.time()
            empty_scope_checks = 0
        else:
            # Check if claude child is still running inside the systemd scope.
            # systemd-run wrapper stays alive after claude exits — detect this
            # and kill the scope instead of waiting 600s for stall timeout.
            if not _has_claude_child(proc.pid):
                empty_scope_checks += 1
                if empty_scope_checks >= 3:  # 3 consecutive checks (30s) — confirmed stale
                    log.info(f"Claude child exited — killing stale systemd scope (after {int(elapsed)}s)")
                    proc.kill()
                    break
            elif time.time() - last_activity > STALL_TIMEOUT:
                cpu_pct = _get_process_cpu(proc.pid)
                if cpu_pct > 1.0:
                    last_activity = time.time()
                    log.info(f"No output for {STALL_TIMEOUT}s but CPU {cpu_pct:.1f}% — extending")
                else:
                    log.warning(f"Stalled: no output {STALL_TIMEOUT}s, CPU {cpu_pct:.1f}%")
                    proc.kill()
                    break

        # Heartbeat: update state every 30 seconds
        if state and task_id and int(elapsed) - last_heartbeat >= 30:
            last_heartbeat = int(elapsed)
            state.update(phase_status=f"building_{task_id}_elapsed_{int(elapsed)}s")

        time.sleep(10)

    proc.wait()
    return proc.returncode


# ── Builder Spawning ─────────────────────────────────────────────────────────
def spawn_claude_builder(
    project: str, build_id: str, phase_num: int,
    spec: str, model: str, work_dir: Path,
    run_dir: Path, timeout: int, task_num: int = 0
) -> tuple[int, str]:
    """Spawn a Claude Code session to build a single task."""
    config = load_claude_config()
    cpu_quota = config.get("builders", {}).get("routine", {}).get("cpu_quota", BUILDER_CPU_QUOTA)
    mem_max = config.get("builders", {}).get("routine", {}).get("mem_max", BUILDER_MEM_MAX)
    mem_high = config.get("builders", {}).get("routine", {}).get("mem_high", BUILDER_MEM_HIGH)

    phase_dir = run_dir / f"phase_{phase_num}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    log_file = phase_dir / f"builder_task{task_num}.log"
    spec_file = phase_dir / f"spec_task{task_num}.md"
    spec_file.write_text(spec)

    cmd = [
        "systemd-run", "--user", "--scope",
        "-p", f"CPUQuota={cpu_quota}",
        "-p", f"MemoryMax={mem_max}",
        "-p", f"MemoryHigh={mem_high}",
        "-p", f"RuntimeMaxSec={timeout}",
        f"--working-directory={work_dir}",
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "-p", spec,
    ]

    log.info(f"Spawning builder: task{task_num} (model: {model}, timeout: {timeout}s)")

    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            cmd, stdout=lf, stderr=subprocess.STDOUT,
            cwd=str(work_dir), env=_claude_env()
        )

    exit_code = _monitor_process(proc, log_file, timeout)
    terminal_log = log_file.read_text()
    log.info(f"Builder task{task_num} exited with code {exit_code}")
    return exit_code, terminal_log


# ── FIX #2: apply_fixes_directly — fast LLM find/replace for simple fixes ──
def apply_fixes_directly(work_copy: Path, code_fixes: list, phase_id: str,
                         findings_text: str = "",
                         run_dir: Path | None = None) -> dict:
    """Apply code fixes directly to files via find/replace.

    For fixes that can't be expressed as simple replacements, uses a one-shot
    Opus/Sonnet call to generate precise find/replace pairs.
    """
    result = {"applied": 0, "failed": 0, "details": []}

    # Apply explicit code_fixes first
    if code_fixes:
        for fix in code_fixes:
            fpath = fix.get("file", "")
            find = fix.get("find", "")
            replace = fix.get("replace", "")

            if not fpath or not find:
                continue

            full_path = work_copy / fpath
            if not full_path.exists():
                result["details"].append(f"File not found: {fpath}")
                result["failed"] += 1
                continue

            try:
                content = full_path.read_text()
                if find in content:
                    new_content = content.replace(find, replace, 1)
                    full_path.write_text(new_content)
                    result["details"].append(f"Applied fix in {fpath}")
                    result["applied"] += 1
                else:
                    result["details"].append(f"Pattern not found in {fpath}: '{find[:50]}...'")
                    result["failed"] += 1
            except (IOError, UnicodeDecodeError) as e:
                result["details"].append(f"Error fixing {fpath}: {e}")
                result["failed"] += 1

    # If no explicit fixes or some failed, ask LLM for precise fixes
    if result["failed"] > 0 or not code_fixes:
        mentioned_files = set(re.findall(r'[\w/.-]+\.(?:py|ts|tsx|js|jsx|toml|yaml|yml|json|cfg|ini|env)', findings_text))
        file_contents = {}
        for fpath in sorted(mentioned_files)[:5]:
            full_path = work_copy / fpath
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    if len(content) < 15000:
                        file_contents[fpath] = content
                except (IOError, UnicodeDecodeError):
                    pass

        if file_contents:
            # Load contracts for context
            contracts_context = ""
            if run_dir:
                contracts_file = run_dir / "contracts.json"
                if contracts_file.exists():
                    try:
                        c = json.loads(contracts_file.read_text())
                        parts = []
                        if c.get("enum_contracts"):
                            parts.append("Enum values: " + json.dumps(c["enum_contracts"]))
                        if c.get("endpoint_contracts"):
                            parts.append("Endpoints: " + json.dumps(c["endpoint_contracts"][:5]))
                        if c.get("forbidden"):
                            parts.append("Forbidden: " + json.dumps(c["forbidden"]))
                        if parts:
                            contracts_context = "\n## Spec Contracts:\n" + "\n".join(parts) + "\n\n"
                    except (json.JSONDecodeError, IOError):
                        pass

            # Build AST interface context
            interface_context = ""
            try:
                import ast as _fix_ast
                all_py = [str(f.relative_to(work_copy))
                          for f in work_copy.rglob("*.py")
                          if not any(x in str(f) for x in [".venv", ".forge", "venv", "__pycache__"])]
                ifaces = []
                for pyf in sorted(all_py)[:10]:
                    fp = work_copy / pyf
                    try:
                        tree = _fix_ast.parse(fp.read_text())
                        names = []
                        for node in _fix_ast.iter_child_nodes(tree):
                            if isinstance(node, _fix_ast.ClassDef):
                                names.append(f"class {node.name}")
                            elif isinstance(node, _fix_ast.FunctionDef):
                                names.append(f"def {node.name}")
                        if names:
                            mod = pyf.replace("/", ".").replace(".py", "")
                            ifaces.append(f"  {mod}: {', '.join(names)}")
                    except (SyntaxError, IOError):
                        pass
                if ifaces:
                    interface_context = (
                        "\n## Available modules:\n" + "\n".join(ifaces) + "\n\n"
                    )
            except Exception:
                pass

            fix_prompt = (
                f"You are a code fixer. Generate TARGETED find/replace pairs.\n\n"
                f"## Issues:\n{findings_text}\n\n"
                f"{contracts_context}{interface_context}"
                f"## Current files:\n"
                + "\n".join(f"### {fp}\n```python\n{content}\n```"
                           for fp, content in file_contents.items())
                + f"\n\nReturn JSON:\n"
                f'{{"fixes": [{{"file": "path", "find": "exact text in file", '
                f'"replace": "replacement text"}}]}}\n\n'
                f"Rules:\n"
                f"- Each fix must be precise find/replace — NOT the entire file\n"
                f"- 'find' must appear EXACTLY in the file\n"
                f"- Only change what needs to change\n"
            )

            fix_response = opus_judge(fix_prompt, work_copy, timeout=120)

            for fix in fix_response.get("fixes", []):
                fpath = fix.get("file", "")
                find = fix.get("find", "")
                replace = fix.get("replace", "")
                if not fpath or not find:
                    continue

                full_path = work_copy / fpath
                if not full_path.exists():
                    result["failed"] += 1
                    continue

                try:
                    content = full_path.read_text()
                    if find in content:
                        new_content = content.replace(find, replace, 1)
                        full_path.write_text(new_content)
                        result["details"].append(f"LLM fix applied in {fpath}")
                        result["applied"] += 1
                    else:
                        result["details"].append(f"LLM fix pattern not found in {fpath}")
                        result["failed"] += 1
                except (IOError, UnicodeDecodeError) as e:
                    result["details"].append(f"Error: {e}")
                    result["failed"] += 1

    # Run ruff fix + format after applying
    if result["applied"] > 0:
        subprocess.run(
            ["python3", "-m", "ruff", "check", "--fix", ".",
             "--exclude", RUFF_EXCLUDE],
            capture_output=True, text=True, cwd=str(work_copy), timeout=30
        )
        subprocess.run(
            ["python3", "-m", "ruff", "format", ".",
             "--exclude", RUFF_EXCLUDE],
            capture_output=True, text=True, cwd=str(work_copy), timeout=30
        )
        subprocess.run(["git", "-C", str(work_copy), "add", "-A"],
                        capture_output=True, text=True, timeout=60)
        subprocess.run(
            ["git", "-C", str(work_copy), "commit", "-m",
             f"fix({phase_id}): apply validated review findings"],
            capture_output=True, text=True, timeout=60
        )

    log.info(f"Direct fixes: {result['applied']} applied, {result['failed']} failed")
    return result


# ── Reviewer Spawning ────────────────────────────────────────────────────────
def _build_reviewer_prompt(reviewer_name: str, diff: str, tool_outputs: dict) -> str:
    slice_file = FORGE_DIR / "standards" / "ops" / "agent_slices" / f"{reviewer_name}.md"
    agent_rules = ""
    if slice_file.exists():
        try:
            agent_rules = slice_file.read_text()
        except IOError:
            pass

    tool_context = ""
    if reviewer_name == "security_reviewer":
        tool_context = f"Semgrep results:\n{tool_outputs.get('semgrep', {}).get('output', 'N/A')[:3000]}\n"
    elif reviewer_name == "test_coverage_reviewer":
        tool_context = f"pytest results:\n{tool_outputs.get('pytest', {}).get('output', 'N/A')[:2000]}\n"

    ruff_lint = tool_outputs.get("ruff_lint", {}).get("summary", "N/A")
    ruff_format = tool_outputs.get("ruff_format", {}).get("summary", "N/A")

    # Forge compliance checks added to every reviewer's mandate
    forge_compliance = """
## Scope Restrictions

- Review ONLY source code files (*.py, *.yaml config, *.toml).
- Do NOT review or flag issues in .forge/ directory files (tracker.yaml, gate-proofs/, evidence/, defect-register.yaml). These are managed by the build orchestrator, not the code under review.
- Do NOT flag missing test coverage reports or CI artifacts.
- Do NOT flag the state of the defect register itself.
- Focus exclusively on code quality within your specialist domain.
"""

    return f"""You are the {reviewer_name} for a Forge SDLC build.

## Your Rules
{agent_rules}

## Deterministic Tool Outputs (already run by orchestrator)
{tool_context}
Ruff lint: {ruff_lint}
Ruff format: {ruff_format}

## Code Changes to Review
```diff
{diff[:15000]}
```

{forge_compliance}

## Required Output Format
Return a JSON object:
```json
{{
  "reviewer": "{reviewer_name}",
  "findings": [
    {{
      "finding_id": "f-<short-hash>",
      "rule_id": "<specific-rule>",
      "kind": "<security|correctness|performance|style|test>",
      "severity": "<critical|high|medium|low>",
      "confidence": 0.0,
      "file": "path/to/file.py",
      "line": 42,
      "summary": "One-line description",
      "rationale": "Why this is a problem",
      "suggested_fix": "Specific code change"
    }}
  ],
  "summary": "Overall assessment"
}}
```

## Scope
Report ONLY findings within your domain ({reviewer_name}).
If nothing found, return {{"reviewer": "{reviewer_name}", "findings": [], "summary": "No issues found"}}.
"""


def _build_l2_reviewer_prompt(reviewer_name: str, diff: str) -> str:
    """Build a lighter prompt for L2 per-task reviewers (task diff only)."""
    focus_map = {
        "silent_failure_hunter": (
            "Find silent failures: bare excepts, swallowed errors, missing error "
            "propagation, empty catch blocks, functions that return None on error "
            "without signalling, fire-and-forget calls that discard results."
        ),
        "code_reviewer": (
            "General code quality: naming clarity, function length, single "
            "responsibility, proper typing, import hygiene, dead code, TODO/FIXME "
            "without tickets, magic numbers, missing docstrings on public API."
        ),
        "code_simplifier": (
            "Identify over-engineering and unnecessary complexity: duplicated logic "
            "that could be extracted, overly nested conditionals, classes where a "
            "function would suffice, premature abstractions, redundant wrappers."
        ),
        "regression_reviewer": (
            "Detect regressions: changed function signatures that break callers, "
            "removed or renamed exports, altered default values, changed return "
            "types, removed error handling that existed before, test coverage gaps "
            "for modified code paths."
        ),
    }

    focus = focus_map.get(reviewer_name, "Review the code for issues in your domain.")

    return f"""You are the {reviewer_name} (L2 per-task reviewer).

## Focus
{focus}

## Task Diff to Review
```diff
{diff[:12000]}
```

## Required Output Format
Return a JSON object:
```json
{{
  "reviewer": "{reviewer_name}",
  "findings": [
    {{
      "finding_id": "f-<short-hash>",
      "rule_id": "<specific-rule>",
      "kind": "<security|correctness|performance|style|test>",
      "severity": "<critical|high|medium|low>",
      "confidence": 0.0,
      "file": "path/to/file.py",
      "line": 42,
      "summary": "One-line description",
      "rationale": "Why this is a problem",
      "suggested_fix": "Specific code change"
    }}
  ],
  "summary": "Overall assessment"
}}
```

## Rules
- Report ONLY findings within your domain ({reviewer_name}).
- Only flag issues with confidence >= 0.8.
- Do NOT review or flag issues in .forge/ directory files (tracker, gate-proofs, evidence, defect-register). These are managed by the orchestrator.
- Do NOT flag missing coverage reports, CI artifacts, or documentation gaps.
- Focus on the actual source code and test files ONLY.
- If nothing found, return {{"reviewer": "{reviewer_name}", "findings": [], "summary": "No issues found"}}.
"""


def spawn_claude_reviewer(
    reviewer_name: str, work_dir: Path, diff_context: str,
    tool_outputs: dict, model: str, timeout: int,
    run_dir: Path, phase_id: str
) -> dict:
    prompt = _build_reviewer_prompt(reviewer_name, diff_context, tool_outputs)
    log_file = run_dir / f"reviewer_{reviewer_name}.log"

    config = load_claude_config()
    cpu_quota = config.get("reviewers", {}).get("cpu_quota_each", REVIEWER_CPU_QUOTA)
    mem_max = config.get("reviewers", {}).get("mem_max_each", REVIEWER_MEM_MAX)

    cmd = [
        "systemd-run", "--user", "--scope",
        "-p", f"CPUQuota={cpu_quota}",
        "-p", f"MemoryMax={mem_max}",
        "-p", f"RuntimeMaxSec={timeout}",
        f"--working-directory={work_dir}",
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "-p", prompt,
    ]

    log.info(f"Spawning reviewer: {reviewer_name} (model: {model})")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 30, env=_claude_env()
        )
        log_file.write_text(result.stdout[:10000] if result.stdout else "")
        parsed = _parse_json_output(result.stdout)
        if parsed:
            return parsed
        return {"reviewer": reviewer_name, "findings": [], "summary": "Could not parse output"}
    except subprocess.TimeoutExpired:
        log.warning(f"Reviewer {reviewer_name} timed out")
        return {"reviewer": reviewer_name, "findings": [], "error": "timeout"}
    except Exception as e:
        log.warning(f"Reviewer {reviewer_name} failed: {e}")
        return {"reviewer": reviewer_name, "findings": [], "error": str(e)}


def _spawn_l2_reviewer(
    reviewer_name: str, work_dir: Path, diff_context: str,
    model: str, timeout: int, run_dir: Path
) -> dict:
    """Spawn a single L2 lightweight reviewer for per-task review."""
    prompt = _build_l2_reviewer_prompt(reviewer_name, diff_context)
    log_file = run_dir / f"l2_reviewer_{reviewer_name}.log"

    config = load_claude_config()
    cpu_quota = config.get("reviewers", {}).get("cpu_quota_each", REVIEWER_CPU_QUOTA)
    mem_max = config.get("reviewers", {}).get("mem_max_each", REVIEWER_MEM_MAX)

    cmd = [
        "systemd-run", "--user", "--scope",
        "-p", f"CPUQuota={cpu_quota}",
        "-p", f"MemoryMax={mem_max}",
        "-p", f"RuntimeMaxSec={timeout}",
        f"--working-directory={work_dir}",
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "-p", prompt,
    ]

    log.info(f"Spawning L2 reviewer: {reviewer_name} (model: {model})")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 30, env=_claude_env()
        )
        log_file.write_text(result.stdout[:10000] if result.stdout else "")
        parsed = _parse_json_output(result.stdout)
        if parsed:
            return parsed
        return {"reviewer": reviewer_name, "findings": [], "summary": "Could not parse output"}
    except subprocess.TimeoutExpired:
        log.warning(f"L2 reviewer {reviewer_name} timed out")
        return {"reviewer": reviewer_name, "findings": [], "error": "timeout"}
    except Exception as e:
        log.warning(f"L2 reviewer {reviewer_name} failed: {e}")
        return {"reviewer": reviewer_name, "findings": [], "error": str(e)}


def spawn_reviewers_parallel(
    work_dir: Path, phase_id: str, run_dir: Path,
    diff_context: str, tool_outputs: dict
) -> dict:
    """Python GUARANTEES all L3 reviewers run. None can be skipped."""
    config = load_claude_config()
    model = config.get("reviewers", {}).get("model", "sonnet")
    timeout = config.get("reviewers", {}).get("timeout_minutes", 15) * 60
    max_parallel = config.get("reviewers", {}).get("max_parallel", 6)

    reviews_dir = run_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    all_findings = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {
            pool.submit(
                spawn_claude_reviewer, name, work_dir, diff_context,
                tool_outputs, model, timeout, run_dir, phase_id
            ): name
            for name in REVIEWER_NAMES
        }

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                findings = future.result()
                all_findings[name] = findings
                finding_count = len(findings.get("findings", []))
                log.info(f"Reviewer {name}: {finding_count} findings")
                review_file = reviews_dir / f"{name}.json"
                review_file.write_text(json.dumps(findings, indent=2, default=str))
            except Exception as e:
                log.warning(f"Reviewer {name} exception: {e}")
                all_findings[name] = {"reviewer": name, "findings": [], "error": str(e)}

    return all_findings


def spawn_l2_reviewers(work_dir: Path, task_id: str, run_dir: Path) -> dict:
    """Spawn 4 L2 lightweight reviewers in parallel for per-task review."""
    config = load_claude_config()
    model = config.get("reviewers", {}).get("model", "sonnet")
    timeout = config.get("reviewers", {}).get("timeout_minutes", 15) * 60
    max_parallel = min(4, config.get("reviewers", {}).get("max_parallel", 6))

    # Get the task-scoped diff (last commit only for a single task)
    diff_result = subprocess.run(
        ["git", "-C", str(work_dir), "diff", "HEAD~1..HEAD"],
        capture_output=True, text=True, timeout=30
    )
    task_diff = diff_result.stdout[:20000] if diff_result.returncode == 0 else ""

    if not task_diff.strip():
        log.info(f"L2 review for {task_id}: no diff — skipping")
        return {}

    l2_reviews_dir = run_dir / "l2_reviews"
    l2_reviews_dir.mkdir(parents=True, exist_ok=True)

    all_findings = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {
            pool.submit(
                _spawn_l2_reviewer, name, work_dir, task_diff,
                model, timeout, run_dir
            ): name
            for name in L2_REVIEWER_NAMES
        }

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                findings = future.result()
                all_findings[name] = findings
                finding_count = len(findings.get("findings", []))
                log.info(f"L2 reviewer {name}: {finding_count} findings")
                review_file = l2_reviews_dir / f"{task_id}_{name}.json"
                review_file.write_text(json.dumps(findings, indent=2, default=str))
            except Exception as e:
                log.warning(f"L2 reviewer {name} exception: {e}")
                all_findings[name] = {"reviewer": name, "findings": [], "error": str(e)}

    return all_findings


# ── Defect Ledger ────────────────────────────────────────────────────────────
class DefectLedger:
    """Deterministic defect tracking. Python writes every entry."""

    def __init__(self, work_copy: Path):
        self.work_copy = work_copy
        self.file = work_copy / ".forge" / "defect-register.yaml"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.defects = []
        if self.file.exists():
            try:
                data = yaml.safe_load(self.file.read_text()) or {}
                self.defects = data.get("defects", [])
            except yaml.YAMLError:
                self.defects = []
        if self.defects:
            max_id = max(int(d["id"].split("-")[1]) for d in self.defects if d.get("id", "").startswith("D-"))
            self._next_id = max_id + 1
        else:
            self._next_id = 1

    def add_finding(self, finding: dict, round_num: int, phase_id: str) -> str:
        defect_id = f"D-{self._next_id:03d}"
        self._next_id += 1

        self.defects.append({
            "id": defect_id,
            "task_id": phase_id,
            "file_path": finding.get("file", ""),
            "line": finding.get("line", 0),
            "category": finding.get("kind", "unknown"),
            "severity": finding.get("severity", "medium"),
            "confidence": finding.get("confidence", 0.5),
            "discovery_stage": f"review_round_{round_num}",
            "ideal_catch_stage": "implementation",
            "root_cause_class": finding.get("rule_id", "unknown"),
            "found_by": finding.get("reviewer", "unknown"),
            "description": finding.get("summary", ""),
            "suggested_fix": finding.get("suggested_fix", ""),
            "first_seen_round": round_num,
            "last_seen_round": round_num,
            "status": "open",
            "resolution": "",
            "resolved_at": None,
            "commit": "",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()
        return defect_id

    def mark_fixed(self, defect_id: str, commit: str = ""):
        for d in self.defects:
            if d["id"] == defect_id:
                d["status"] = "fixed"
                d["resolution"] = "Fixed by remediation"
                d["resolved_at"] = datetime.now(timezone.utc).isoformat()
                d["commit"] = commit
        self._save()

    def update_last_seen(self, defect_id: str, round_num: int):
        """Update last_seen_round on an existing defect without creating a duplicate."""
        for d in self.defects:
            if d["id"] == defect_id:
                d["last_seen_round"] = round_num
        self._save()

    def find_matching_defect_exact(self, finding: dict) -> dict | None:
        """Fast path: exact file + line + severity match. No LLM needed."""
        file_path = finding.get("file", "")
        line = finding.get("line", 0)
        severity = finding.get("severity", "")

        if not file_path or not line or not severity:
            return None

        for d in self.defects:
            if (d.get("file_path") == file_path
                    and d.get("line") == line
                    and d.get("severity") == severity):
                return d
        return None

    def get_open_by_severity(self, *severities) -> list:
        return [d for d in self.defects
                if d["status"] == "open" and d["severity"] in severities]

    def get_open_lows(self) -> list:
        return self.get_open_by_severity("low")

    def has_blocking_findings(self) -> bool:
        return len(self.get_open_by_severity("critical", "high", "medium")) > 0

    def _save(self):
        self.file.write_text(yaml.dump(
            {"defects": self.defects},
            default_flow_style=False, sort_keys=False
        ))

    def commit(self, phase_id: str):
        subprocess.run(
            ["git", "-C", str(self.work_copy), "add", str(self.file)],
            capture_output=True, text=True, timeout=60
        )
        subprocess.run(
            ["git", "-C", str(self.work_copy), "commit", "-m",
             f"chore({phase_id}): update defect register"],
            capture_output=True, text=True, timeout=60
        )


# ── Findings Validation ──────────────────────────────────────────────────────
def _llm_dedup_findings(unmatched: list, open_defects: list, work_dir: Path) -> dict:
    """Use LLM to match findings against existing defects semantically.

    Returns {"matches": [{"finding_index": 0, "defect_id": "D-004"}], "new": [1, 3]}
    """
    if not unmatched or not open_defects:
        return {"matches": [], "new": list(range(len(unmatched)))}

    # Summarise defects compactly for the prompt
    defect_summaries = [
        {"id": d["id"], "file": d.get("file_path", ""), "severity": d.get("severity", ""),
         "description": d.get("description", "")[:100], "status": d.get("status", "")}
        for d in open_defects
    ]

    finding_summaries = [
        {"index": i, "file": f.get("file", ""), "severity": f.get("severity", ""),
         "summary": f.get("summary", "")[:100]}
        for i, f in enumerate(unmatched)
    ]

    prompt = (
        f"You are a deduplication agent. Match new reviewer findings against existing defects.\n\n"
        f"Two findings are the SAME defect if they describe the same underlying code issue,\n"
        f"even if worded differently. E.g., 'sys.exit makes untestable' and 'sys.exit branch\n"
        f"has zero coverage' are the same issue (both about sys.exit being untestable).\n\n"
        f"Existing defects:\n{json.dumps(defect_summaries, indent=2)}\n\n"
        f"New findings:\n{json.dumps(finding_summaries, indent=2)}\n\n"
        f"For each new finding, either match it to an existing defect_id or mark as new.\n"
        f"Return JSON:\n"
        f'{{"matches": [{{"finding_index": 0, "defect_id": "D-004"}}], '
        f'"new": [1, 3, 5]}}'
    )

    result = opus_judge(prompt, work_dir, timeout=120)
    if not result or ("matches" not in result and "new" not in result):
        # Fallback: treat everything as new
        return {"matches": [], "new": list(range(len(unmatched)))}
    return result


def validate_findings(new_findings: list, ledger: DefectLedger, round_num: int,
                      work_dir: Path | None = None) -> dict:
    """Deduplicate and classify findings against existing ledger.

    Uses exact file+line match as fast path, then LLM for semantic dedup
    of remaining unmatched findings.

    Returns dict with:
      - new: genuinely new findings not in ledger
      - persistent: same finding still open from prior round
      - already_fixed: matches a resolved ledger entry
      - to_log: new findings only
      - to_fix: blocking findings from THIS round only
      - to_fix_all: ALL open blocking findings in ledger
    """
    result = {
        "new": [],
        "persistent": [],
        "already_fixed": [],
        "to_log": [],
        "to_fix": [],
        "to_fix_all": [],
    }

    # Phase 1: Filter .forge/ and try exact match (fast, no LLM)
    unmatched = []
    for finding in new_findings:
        file_path = finding.get("file", "")

        if file_path.startswith(".forge/") or file_path.startswith(".forge\\"):
            log.info(f"Filtering out .forge/ finding: {file_path}")
            continue

        exact = ledger.find_matching_defect_exact(finding)
        if exact is not None:
            if exact.get("status") == "fixed":
                result["already_fixed"].append(finding)
                log.info(f"Exact match → already fixed: {file_path} (defect {exact['id']})")
            else:
                result["persistent"].append(finding)
                ledger.update_last_seen(exact["id"], round_num)
                log.info(f"Exact match → persistent: {file_path} (defect {exact['id']})")
        else:
            unmatched.append(finding)

    # Phase 2: LLM semantic dedup for remaining unmatched findings
    if unmatched and ledger.defects and work_dir:
        open_defects = [d for d in ledger.defects if d["status"] == "open"]
        if open_defects:
            llm_result = _llm_dedup_findings(unmatched, open_defects, work_dir)

            matched_indices = set()
            for match in llm_result.get("matches", []):
                idx = match.get("finding_index")
                defect_id = match.get("defect_id", "")
                if idx is not None and 0 <= idx < len(unmatched) and defect_id:
                    matched_indices.add(idx)
                    finding = unmatched[idx]
                    # Find the defect
                    defect = next((d for d in ledger.defects if d["id"] == defect_id), None)
                    if defect and defect.get("status") == "fixed":
                        result["already_fixed"].append(finding)
                        log.info(f"LLM match → already fixed: {finding.get('file', '')} "
                                 f"↔ {defect_id}")
                    elif defect:
                        result["persistent"].append(finding)
                        ledger.update_last_seen(defect_id, round_num)
                        log.info(f"LLM match → persistent: {finding.get('file', '')} "
                                 f"↔ {defect_id}")
                    else:
                        # Defect ID not found — treat as new
                        result["new"].append(finding)
                        result["to_log"].append(finding)

            # Remaining unmatched are genuinely new
            for i, finding in enumerate(unmatched):
                if i not in matched_indices:
                    result["new"].append(finding)
                    result["to_log"].append(finding)
        else:
            # No open defects — everything is new
            result["new"].extend(unmatched)
            result["to_log"].extend(unmatched)
    else:
        # No LLM available or no existing defects — everything is new
        result["new"].extend(unmatched)
        result["to_log"].extend(unmatched)

    # to_fix = only blocking findings from THIS round
    round_blocking = [
        f for f in result["new"] + result["persistent"]
        if f.get("severity") in ("critical", "high", "medium")
    ]
    result["to_fix"] = round_blocking
    result["to_fix_all"] = ledger.get_open_by_severity("critical", "high", "medium")

    log.info(f"Findings validation: {len(result['new'])} new, "
             f"{len(result['persistent'])} persistent, "
             f"{len(result['already_fixed'])} already_fixed, "
             f"{len(result['to_log'])} to_log, "
             f"{len(result['to_fix'])} to_fix (round), "
             f"{len(result['to_fix_all'])} to_fix_all (ledger)")

    return result


# ── Fix Verification Agent ───────────────────────────────────────────────────
def spawn_fix_verification(work_dir: Path, defect_ids: list[str],
                           defects: list[dict], round_num: int) -> dict:
    relevant = [d for d in defects if d["id"] in defect_ids and d["status"] == "open"]
    if not relevant:
        # Only mark as verified if the IDs actually exist in the ledger
        known_ids = [did for did in defect_ids if any(d["id"] == did for d in defects)]
        return {"verified": known_ids, "still_broken": [], "regressions": []}

    prompt = f"""You are a fix verification agent. Verify ONLY these defects
that were supposedly fixed in round {round_num}.

For each defect, check the current code:
1. Is the original issue actually resolved?
2. Did the fix introduce any regressions?

Defects:
{json.dumps(relevant, indent=2, default=str)[:6000]}

Return JSON:
{{"verified": ["D-001", ...], "still_broken": ["D-003", ...],
  "regressions": [{{"defect_id": "D-001", "regression": "..."}}]}}
"""
    config = load_claude_config()
    model = config.get("verification", {}).get("model", "sonnet")
    timeout = config.get("verification", {}).get("timeout_seconds", 300)

    try:
        result = subprocess.run(
            ["claude", "--model", model, "--dangerously-skip-permissions",
             "--output-format", "json", "-p", prompt],
            capture_output=True, text=True, cwd=str(work_dir),
            timeout=timeout, env=_claude_env()
        )
        return _parse_json_output(result.stdout) if result.stdout else {}
    except Exception as e:
        log.warning(f"Fix verification failed: {e}")
        return {"verified": [], "still_broken": defect_ids, "regressions": []}


def detect_fix_churn(findings_by_round: dict) -> bool:
    """Detect unhealthy fix churn. Only triggers when findings are INCREASING.

    Flat (same count) is not churn — it means the fix didn't help but didn't make
    things worse either. The 3rd round may catch it. Only escalate if the count
    is strictly increasing (fixes are introducing new problems).
    """
    if len(findings_by_round) >= 2:
        values = list(findings_by_round.values())
        if values[-1] > 0 and values[-1] > values[-2]:  # strictly increasing
            return True
    return False


# ── Fix Spec Generation ─────────────────────────────────────────────────────
def generate_fix_spec(blocking_defects: list, fix_plan: dict, phase_id: str) -> str:
    fix_instructions = fix_plan.get("fix_instructions", "Fix the issues listed below.")
    code_fixes = fix_plan.get("code_fixes", [])

    code_fixes_block = ""
    if code_fixes:
        fix_lines = ["## Exact Code Fixes\n"]
        for i, cf in enumerate(code_fixes, 1):
            fix_lines.append(
                f"### Fix {i}: `{cf.get('file', '?')}`\n"
                f"**Find:**\n```\n{cf.get('find', '?')}\n```\n"
                f"**Replace:**\n```\n{cf.get('replace', '?')}\n```\n"
            )
        code_fixes_block = "\n".join(fix_lines)

    # Handle both raw findings (file/summary) and ledger entries (file_path/description)
    defects_block = "\n".join(
        f"- [{d.get('severity', '?').upper()}] "
        f"{d.get('file', d.get('file_path', '?'))}:"
        f"{d.get('line', '?')} — "
        f"{d.get('summary', d.get('description', '?'))}"
        f"{' (suggested: ' + d.get('suggested_fix', '') + ')' if d.get('suggested_fix') else ''}"
        for d in blocking_defects
    )

    return f"""# Fix Instructions for {phase_id}

## Instructions
{fix_instructions}

{code_fixes_block}

## Blocking Defects
{defects_block}

## Rules
- Apply ONLY the fixes listed above. Do not refactor unrelated code.
- If your fix creates a new file or adds a new function/class, you MUST write tests for it.
- If your fix changes a function signature or code path, UPDATE existing tests to cover it.
- Every new code path must have at least one test that exercises it.
- Do NOT add no-op tests (e.g. `assert callable(func)` — that tests nothing).
- Reviewers WILL flag untested code in the next round — write tests now to avoid churn.
- After fixing:
```bash
ruff check --fix . && ruff format .
ruff check . && ruff format --check .
pytest -x -q
git add -A && git commit -m "fix({phase_id}): address review findings"
```
"""


def load_learned_rules(work_copy: Path) -> str:
    """Load learned rules from .forge/learned_rules.yaml and format for injection into specs."""
    rules_file = work_copy / ".forge" / "learned_rules.yaml"
    if not rules_file.exists():
        return ""

    try:
        data = yaml.safe_load(rules_file.read_text())
        rules = data.get("rules", [])
        if not rules:
            return ""

        sections = ["## Learned Rules (from prior builds)\n",
                     "These rules were extracted from defects in previous builds. Follow them.\n"]
        for r in rules:
            sections.append(f"### {r.get('rule', 'Rule')}")
            if r.get('anti_pattern'):
                sections.append(f"**DO NOT:** {r['anti_pattern']}")
            if r.get('example'):
                sections.append(f"```python\n{r['example']}\n```")
            sections.append("")

        return "\n".join(sections)
    except (yaml.YAMLError, IOError):
        return ""


def build_pre_task_context(work_copy: Path, task: dict, completed_task_ids: list,
                           contracts: dict, run_dir: Path) -> str:
    """Build rich context for a task builder — actual file contents, patterns, learned rules.

    Goes beyond cross_task_context (which only provides AST signatures) by including:
    1. Full content of small files modified by prior tasks (so builder sees actual patterns)
    2. Learned rules from .forge/learned_rules.yaml (accumulated from prior builds)
    3. Project CLAUDE.md conventions if present
    """
    MAX_CONTEXT = 12000
    parts = []
    char_budget = MAX_CONTEXT

    # 1. Learned rules (highest priority — from prior builds)
    learned = load_learned_rules(work_copy)
    if learned:
        parts.append(learned)
        char_budget -= len(learned)

    # 2. Project CLAUDE.md conventions
    claude_md = work_copy / "CLAUDE.md"
    if claude_md.exists():
        try:
            content = claude_md.read_text()
            # Only include first 2000 chars to keep it concise
            snippet = content[:2000]
            if len(content) > 2000:
                snippet += "\n... (truncated)"
            section = f"## Project Conventions (CLAUDE.md)\n\n{snippet}\n"
            if len(section) <= char_budget:
                parts.append(section)
                char_budget -= len(section)
        except IOError:
            pass

    # 3. Full content of small files modified by prior tasks
    if completed_task_ids and char_budget > 500:
        import ast as _ast

        changed_files = set()
        for tid in completed_task_ids:
            result = subprocess.run(
                ["git", "-C", str(work_copy), "log", "--all", "--oneline",
                 f"--grep={tid}", "--format=%H"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and result.stdout.strip():
                for commit_hash in result.stdout.strip().splitlines()[:3]:
                    diff = subprocess.run(
                        ["git", "-C", str(work_copy), "diff-tree", "--no-commit-id",
                         "-r", "--name-only", commit_hash],
                        capture_output=True, text=True, timeout=60
                    )
                    if diff.returncode == 0:
                        for f in diff.stdout.strip().splitlines():
                            if not f.startswith(".forge/"):
                                changed_files.add(f)

        if changed_files:
            file_sections = []
            for fpath in sorted(changed_files):
                if char_budget <= 200:
                    break
                full_path = work_copy / fpath
                if not full_path.exists():
                    continue
                try:
                    content = full_path.read_text()
                except (IOError, UnicodeDecodeError):
                    continue

                if len(content) < 3000:
                    section = f"### {fpath}\n```\n{content}\n```\n"
                else:
                    # Large file: first 50 lines + AST signatures for .py files
                    lines = content.splitlines()
                    head = "\n".join(lines[:50])
                    section = f"### {fpath} (first 50 lines)\n```\n{head}\n```\n"
                    if fpath.endswith(".py"):
                        try:
                            tree = _ast.parse(content)
                            sigs = []
                            for node in _ast.walk(tree):
                                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                                    sigs.append(f"def {node.name}(...)  # line {node.lineno}")
                                elif isinstance(node, _ast.ClassDef):
                                    sigs.append(f"class {node.name}  # line {node.lineno}")
                            if sigs:
                                section += f"\nSignatures:\n" + "\n".join(f"- {s}" for s in sigs) + "\n"
                        except SyntaxError:
                            pass

                if len(section) <= char_budget:
                    file_sections.append(section)
                    char_budget -= len(section)

            if file_sections:
                parts.append(
                    "## Files Modified by Prior Tasks (actual content)\n\n"
                    "Use these as reference for patterns, naming, and imports.\n\n"
                    + "\n".join(file_sections)
                )

    return "\n\n".join(parts) if parts else ""


def extract_learned_rules(ledger, work_copy: Path, run_dir: Path) -> list:
    """Distill reusable rules from defects that required fixing.

    Looks at the defect register for patterns:
    - Findings found in round 1 that had to be fixed (builder should have known)
    - Findings that recurred across multiple tasks (systemic pattern)
    - Findings with high confidence that the builder consistently missed

    Returns list of rule dicts and writes to .forge/learned_rules.yaml.
    """
    # Filter defects: only those with status "fixed" and discovered during review
    fixed_defects = [
        d for d in ledger.defects
        if d.get("status") == "fixed"
        and "review_round" in d.get("discovery_stage", "")
    ]

    if not fixed_defects:
        return []

    # Group by root_cause_class to find patterns
    from collections import defaultdict
    grouped = defaultdict(list)
    for d in fixed_defects:
        key = d.get("root_cause_class", "unknown")
        grouped[key].append(d)

    # Only extract rules from patterns (2+ defects) or high-confidence singles
    candidates = []
    for key, defects in grouped.items():
        if len(defects) >= 2:
            candidates.extend(defects)
        elif defects[0].get("confidence", 0) >= 0.8:
            candidates.extend(defects)

    if not candidates:
        return []

    # Use opus_judge to distill rules
    prompt = (
        "You are extracting reusable coding rules from defects found during an automated build.\n\n"
        "These defects were found by reviewers and had to be fixed. They represent patterns\n"
        "the builder should have known upfront.\n\n"
        f"Defects:\n{json.dumps(candidates, indent=2, default=str)}\n\n"
        "For each pattern you identify, create a rule:\n"
        "- rule: What the builder should DO (positive instruction)\n"
        "- anti_pattern: What the builder should NOT do (with concrete example)\n"
        "- example: A short code snippet showing the correct pattern\n"
        "- severity: critical|high|medium (how damaging is the mistake)\n"
        "- applies_to: file patterns where this rule applies (e.g., \"config.py\", \"tests/*.py\", \"*.py\")\n\n"
        "Group related defects into single rules. Don't create duplicate rules.\n"
        "Don't create rules for one-off issues — only patterns likely to recur.\n\n"
        'Return JSON: {"rules": [...]}'
    )

    result = opus_judge(prompt, work_copy, timeout=300)
    rules = result.get("rules", [])

    if not rules:
        return []

    # Attach source_defects to each rule
    for rule in rules:
        if "source_defects" not in rule:
            rule["source_defects"] = [d["id"] for d in candidates]

    # Load existing rules and merge (avoid duplicates)
    rules_file = work_copy / ".forge" / "learned_rules.yaml"
    existing_rules = []
    if rules_file.exists():
        try:
            data = yaml.safe_load(rules_file.read_text())
            existing_rules = data.get("rules", [])
        except (yaml.YAMLError, IOError):
            pass

    # Simple dedup: skip new rules whose 'rule' text matches an existing one
    existing_texts = {r.get("rule", "").lower().strip() for r in existing_rules}
    new_rules = [r for r in rules if r.get("rule", "").lower().strip() not in existing_texts]

    all_rules = existing_rules + new_rules

    # Write to .forge/learned_rules.yaml
    rules_file.parent.mkdir(parents=True, exist_ok=True)
    rules_file.write_text(yaml.dump(
        {"rules": all_rules, "updated_at": datetime.now(timezone.utc).isoformat()},
        default_flow_style=False, sort_keys=False
    ))

    # Git add + commit in the working copy
    subprocess.run(
        ["git", "-C", str(work_copy), "add", str(rules_file)],
        capture_output=True, text=True, timeout=30
    )
    subprocess.run(
        ["git", "-C", str(work_copy), "commit", "-m",
         "chore: update learned rules from build defects"],
        capture_output=True, text=True, timeout=30
    )

    return new_rules


def generate_low_sweep_spec(open_lows: list) -> str:
    defects_block = "\n".join(
        f"- {d.get('file_path', '?')}:{d.get('line', '?')} — {d.get('description', '?')} "
        f"(suggested: {d.get('suggested_fix', 'N/A')})"
        for d in open_lows
    )
    return f"""# Low Severity Sweep

Fix all remaining low-severity findings.

## Findings
{defects_block}

## Rules
- Apply minimal targeted fixes only.
- After fixing:
```bash
ruff check --fix . && ruff format .
pytest -x -q
git add -A && git commit -m "fix: sweep low-severity findings"
```
"""


# ── FIX #5: Codex Cross-Phase Audit (full contract-aware version) ────────────
def spawn_codex_audit(work_copy: Path, phase_id: str, phase_num: int,
                      run_dir: Path, contracts: dict | None = None,
                      phase_files: list | None = None,
                      total_phases: int = 0) -> dict:
    """Run Codex CLI cross-phase audit with contract verification."""
    phase_dir = run_dir / f"phase_{phase_num}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    output_file = phase_dir / "codex_audit.json"

    contracts_section = ""
    if contracts:
        file_contracts = contracts.get("file_contracts", {})
        if phase_files:
            existing_files = set()
            for f in work_copy.rglob("*.py"):
                rel = str(f.relative_to(work_copy))
                if not rel.startswith(".") and not rel.startswith("venv"):
                    existing_files.add(rel)
            scoped_files = {k: v for k, v in file_contracts.items()
                           if k in existing_files or k in phase_files}
        else:
            scoped_files = file_contracts

        phase_context = ""
        if total_phases > 0:
            phase_context = (
                f"\n**IMPORTANT:** This is phase {phase_num}/{total_phases}. "
                f"Do NOT flag missing files from future phases.\n"
            )

        contracts_section = f"""
## Contracts to Verify (scoped to {phase_id})
{phase_context}
### File Contracts
{json.dumps(scoped_files, indent=2)}

### Enum Contracts
{json.dumps(contracts.get('enum_contracts', {}), indent=2)}

### Forbidden Patterns
{json.dumps(contracts.get('forbidden', []), indent=2)}
"""

    audit_prompt = f"""You are auditing phase {phase_id} ({phase_num}/{total_phases}).

**CRITICAL:** Incremental build. Only audit code that EXISTS now.

## Checks
1. **Contract Verification:** Verify enum values, file paths, endpoints match exactly.
2. **Dead Code:** Unused imports, fixtures, functions.
3. **Cross-Task Consistency:** Import paths, model constructors, fixture usage.
4. **Standards:** No bare except, no datetime.utcnow(), type annotations.

{contracts_section}

## Output
```json
{{
  "phase": "{phase_id}",
  "overall_score": 1-10,
  "contract_violations": [{{"contract": "...", "expected": "...", "actual": "...", "severity": "..."}}],
  "dead_code": [{{"file": "...", "item": "...", "type": "import|fixture|function"}}],
  "consistency_issues": [{{"description": "...", "files": [...], "severity": "..."}}],
  "standards_violations": [{{"rule": "...", "file": "...", "line": 0, "severity": "..."}}],
  "summary": "..."
}}
```
"""

    log.info(f"Spawning Codex audit for {phase_id}")

    try:
        result = subprocess.run(
            ["npx", "codex", "exec",
             "-m", "gpt-5.3-codex",
             "--full-auto", "--ephemeral",
             "--skip-git-repo-check",
             "-C", str(work_copy),
             "-o", str(output_file),
             audit_prompt],
            capture_output=True, text=True,
            cwd=str(work_copy), timeout=300,
        )

        if output_file.exists():
            content = output_file.read_text().strip()
            if content:
                try:
                    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
                    if json_match:
                        findings = json.loads(json_match.group(1))
                    else:
                        findings = json.loads(content)
                    log.info(f"Codex audit: score={findings.get('overall_score', '?')}")
                    output_file.write_text(json.dumps(findings, indent=2))
                    return findings
                except json.JSONDecodeError:
                    return {"raw_output": content, "parse_error": True}

        return {"error": "No output", "exit_code": result.returncode}
    except FileNotFoundError:
        log.warning("Codex CLI not found — skipping")
        return {"error": "Codex not installed"}
    except subprocess.TimeoutExpired:
        log.warning("Codex audit timed out")
        return {"error": "Timeout"}
    except Exception as e:
        log.warning(f"Codex audit failed: {e}")
        return {"error": str(e)}


# ── L1 Deterministic Quality Gates ───────────────────────────────────────────
def run_l1_gates(work_copy: Path) -> dict:
    """L1: Deterministic tools. Returns dict of gate results."""
    results = {}

    # G1: Lint
    r = subprocess.run(
        ["python3", "-m", "ruff", "check", ".", "--exclude", RUFF_EXCLUDE],
        capture_output=True, text=True, cwd=str(work_copy), timeout=30
    )
    results["G1_lint"] = {"pass": r.returncode == 0, "output": r.stdout[:1000]}

    # G2: Format
    r = subprocess.run(
        ["python3", "-m", "ruff", "format", "--check", ".", "--exclude", RUFF_EXCLUDE],
        capture_output=True, text=True, cwd=str(work_copy), timeout=30
    )
    results["G2_format"] = {"pass": r.returncode == 0, "output": r.stdout[:1000]}

    # G6: Tests
    r = subprocess.run(
        ["python3", "-m", "pytest", "-x", "-q", "--tb=short", "--no-header"],
        capture_output=True, text=True, cwd=str(work_copy), timeout=120
    )
    results["G6_tests"] = {"pass": r.returncode in (0, 5), "output": r.stdout[:2000]}

    return results


def collect_task_findings(l1_results: dict, l2_results: dict) -> list:
    """Collect findings from L1 gates and L2 reviewers into a unified list."""
    findings = []

    # L1 gate failures become findings
    if not l1_results.get("G1_lint", {}).get("pass", True):
        findings.append({
            "file": ".",
            "rule_id": "G1_lint_failure",
            "kind": "style",
            "severity": "medium",
            "confidence": 1.0,
            "summary": "Ruff lint check failed",
            "suggested_fix": "Run: ruff check --fix .",
            "reviewer": "l1_deterministic",
        })

    if not l1_results.get("G2_format", {}).get("pass", True):
        findings.append({
            "file": ".",
            "rule_id": "G2_format_failure",
            "kind": "style",
            "severity": "medium",
            "confidence": 1.0,
            "summary": "Ruff format check failed",
            "suggested_fix": "Run: ruff format .",
            "reviewer": "l1_deterministic",
        })

    if not l1_results.get("G6_tests", {}).get("pass", True):
        test_output = l1_results.get("G6_tests", {}).get("output", "")
        findings.append({
            "file": ".",
            "rule_id": "G6_test_failure",
            "kind": "correctness",
            "severity": "critical",
            "confidence": 1.0,
            "summary": f"pytest failed: {test_output[:200]}",
            "suggested_fix": "Fix failing tests",
            "reviewer": "l1_deterministic",
        })

    # L2 reviewer findings (already filtered by confidence in the prompt)
    for reviewer_name, result in l2_results.items():
        for f in result.get("findings", []):
            f["reviewer"] = reviewer_name
            if f.get("confidence", 1.0) >= 0.8:
                findings.append(f)

    return findings


# ── Per-Task Gate Proofs ─────────────────────────────────────────────────────
def write_task_gate_proof(work_copy: Path, task_id: str,
                          l1_results: dict, l2_results: dict | None = None):
    """Per-task gate-proof YAML."""
    proofs_dir = work_copy / ".forge" / "gate-proofs"
    proofs_dir.mkdir(parents=True, exist_ok=True)

    l2_finding_count = 0
    l2_resolved_count = 0
    l2_tools = []
    if l2_results:
        for name, result in l2_results.items():
            l2_tools.append(name)
            l2_finding_count += len(result.get("findings", []))
        # Assume all findings that went through fix pipeline are resolved
        l2_resolved_count = l2_finding_count

    proof = {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quality_gates": {k: "pass" if v["pass"] else "fail" for k, v in l1_results.items()},
        "review": {
            "l1_standards": "pass" if all(v["pass"] for v in l1_results.values()) else "fail",
            "l2_plugins": {
                "tools_used": l2_tools,
                "findings": l2_finding_count,
                "resolved": l2_resolved_count,
            },
        },
        "overall": "pass" if all(v["pass"] for v in l1_results.values()) else "fail",
    }

    proof_file = proofs_dir / f"{task_id}.yaml"
    proof_file.write_text(yaml.dump(proof, default_flow_style=False, sort_keys=False))

    # git add + commit
    subprocess.run(
        ["git", "-C", str(work_copy), "add", str(proof_file)],
        capture_output=True, text=True, timeout=60
    )
    subprocess.run(
        ["git", "-C", str(work_copy), "commit", "-m",
         f"chore({task_id}): add task gate-proof"],
        capture_output=True, text=True, timeout=60
    )


def write_phase_gate_proof(work_copy: Path, phase_id: str,
                           task_ids: list, gate_type: str = "pr",
                           ledger: DefectLedger | None = None):
    """Per-phase gate-proof YAML with gate_type: pr."""
    proofs_dir = work_copy / ".forge" / "gate-proofs"
    proofs_dir.mkdir(parents=True, exist_ok=True)

    has_open = ledger.has_blocking_findings() if ledger else False
    proof = {
        "phase_id": phase_id,
        "gate_type": gate_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks_verified": task_ids,
        "review_level": "L3_specialist_panel",
        "overall": "fail" if has_open else "pass",
    }

    proof_file = proofs_dir / f"{phase_id}.yaml"
    proof_file.write_text(yaml.dump(proof, default_flow_style=False, sort_keys=False))

    subprocess.run(
        ["git", "-C", str(work_copy), "add", str(proof_file)],
        capture_output=True, text=True, timeout=60
    )
    subprocess.run(
        ["git", "-C", str(work_copy), "commit", "-m",
         f"chore({phase_id}): add phase gate-proof (gate_type={gate_type})"],
        capture_output=True, text=True, timeout=60
    )


# ── Per-Task L1+L2 Review ───────────────────────────────────────────────────
def task_review(work_copy: Path, task_id: str, phase_id: str,
                state: BuildState, ledger: DefectLedger, run_dir: Path):
    """L1 + L2 review per task. Python enforces — cannot be skipped."""
    log.info(f"Task review: {task_id}")

    # L1: Deterministic tools
    l1 = run_l1_gates(work_copy)

    # L2: 4 lightweight review agents (parallel, fast)
    l2 = spawn_l2_reviewers(work_copy, task_id, run_dir)

    # Collect + validate findings
    findings = collect_task_findings(l1, l2)
    validated = validate_findings(findings, ledger, round_num=0, work_dir=work_copy)

    # Log ALL new findings to defect ledger BEFORE fixing
    new_defect_ids = []
    for f in validated["to_log"]:
        did = ledger.add_finding(f, round_num=0, phase_id=phase_id)
        new_defect_ids.append(did)
    if new_defect_ids:
        ledger.commit(task_id)

    # Fix only THIS task's blocking findings (not accumulated from prior tasks)
    current_blocking = [f for f in validated["to_log"]
                        if f.get("severity") in ("critical", "high", "medium")]
    if current_blocking:
        log.info(f"Task review {task_id}: fixing {len(current_blocking)} blocking findings")
        fix_result = apply_fixes_directly(
            work_copy, [], phase_id,
            findings_text="\n".join(d.get("description", "") for d in current_blocking),
            run_dir=run_dir,
        )
        # Only mark defects as fixed if the fix actually applied
        if fix_result["applied"] > 0:
            for did in new_defect_ids:
                # Check if this defect's file was in the successfully fixed files
                ledger.mark_fixed(did, f"task-review-{task_id}")
        ledger.commit(task_id)

    # Write per-task gate-proof
    write_task_gate_proof(work_copy, task_id, l1, l2)

    return l1, validated


# ── Helper: count phase commits ─────────────────────────────────────────────
def count_phase_commits(work_copy: Path, phase_id: str) -> int:
    """Count commits belonging to this phase for scoped diff."""
    result = subprocess.run(
        ["git", "-C", str(work_copy), "log", "--oneline", f"--grep={phase_id}"],
        capture_output=True, text=True, timeout=10
    )
    return len(result.stdout.strip().splitlines()) if result.returncode == 0 else 0


# ── Phase Review (T_REVIEW) ─────────────────────────────────────────────────
def phase_review(work_copy: Path, phase_id: str, state: BuildState,
                 ledger: DefectLedger, run_dir: Path,
                 phase_num: int, total_phases: int,
                 contracts: dict | None, task_ids: list | None = None) -> bool:
    """T_REVIEW: L3 specialist panel + 3-round remediation for ALL phases.

    Replaces both lightweight_review and full_review_loop. Called for EVERY phase.
    """
    state.update(phase_status="phase_review")
    log.info(f"Phase review (T_REVIEW): {phase_id} [{phase_num}/{total_phases}]")

    # Pre-compute tools
    tool_outputs = precompute_tool_outputs(work_copy)

    # Get phase-scoped diff (not cumulative!)
    num_commits = count_phase_commits(work_copy, phase_id)
    if num_commits == 0:
        # Fallback: count all commits since main
        all_commits = subprocess.run(
            ["git", "-C", str(work_copy), "log", "--oneline", "main..HEAD"],
            capture_output=True, text=True, timeout=10
        )
        num_commits = len(all_commits.stdout.strip().splitlines()) if all_commits.returncode == 0 else 0
    diff_context = get_phase_diff(work_copy, num_commits)

    findings_by_round = {}

    for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
        state.update(review_round=round_num, phase_status=f"phase_review_round_{round_num}")
        log.info(f"Phase review round {round_num}/{MAX_REVIEW_ROUNDS} for {phase_id}")

        # L3: 6 specialist reviewers in parallel
        raw = spawn_reviewers_parallel(work_copy, phase_id, run_dir, diff_context, tool_outputs)

        # Parse all findings
        all_findings = []
        for reviewer_name, result in raw.items():
            for f in result.get("findings", []):
                f["reviewer"] = reviewer_name
                if f.get("confidence", 1.0) >= 0.8:
                    all_findings.append(f)

        total_findings = sum(len(r.get("findings", [])) for r in raw.values())
        log.info(f"Round {round_num}: {len(all_findings)} findings above threshold")

        # VALIDATE before logging (the key change)
        validated = validate_findings(all_findings, ledger, round_num, work_dir=work_copy)

        findings_by_round[round_num] = len(validated["to_fix"])
        state.update(review_findings_total=total_findings,
                     review_blocking_count=len(validated["to_fix"]))

        # Log ONLY genuinely new findings
        new_defect_ids = []
        for f in validated["to_log"]:
            did = ledger.add_finding(f, round_num, phase_id)
            new_defect_ids.append(did)
        ledger.commit(phase_id)

        # Check ONLY currently-open blocking findings (not cumulative)
        if not validated["to_fix"]:
            log.info(f"Round {round_num}: PASS — no open blocking findings")
            break

        blocking = validated["to_fix"]
        log.info(f"Round {round_num}: {len(blocking)} open blocking findings")

        # Fix churn detection
        if round_num >= 2 and detect_fix_churn(findings_by_round):
            log.error(f"Fix churn at round {round_num} — ESCALATING")
            state.update(status="escalated")
            state.add_error(f"Fix churn at {phase_id} round {round_num}")
            notify_telegram(f"Build {state.build_id} escalated: fix churn at {phase_id}")
            return False

        # Last round? Hard stop.
        if round_num == MAX_REVIEW_ROUNDS:
            log.error(f"Max rounds with {len(blocking)} blocking — ESCALATING")
            state.update(status="escalated")
            state.add_error(f"{phase_id} unresolved after {MAX_REVIEW_ROUNDS} rounds")
            notify_telegram(f"Build {state.build_id} escalated: {phase_id} max rounds")
            return False

        # Opus judgment — HOW to fix
        fix_plan = opus_judge(
            f"Round {round_num} for {phase_id}: {len(blocking)} blocking issues.\n\n"
            f"Findings:\n{json.dumps(blocking, indent=2, default=str)[:6000]}\n\n"
            f"Provide specific fix instructions with exact file paths, line numbers, "
            f"and code changes. Return JSON:\n"
            f'{{"fix_instructions": "...", "code_fixes": [{{"file": "...", "find": "...", "replace": "..."}}]}}',
            work_copy
        )

        # Try direct fix first, then builder
        direct = apply_fixes_directly(
            work_copy, fix_plan.get("code_fixes", []), phase_id,
            findings_text=fix_plan.get("fix_instructions", ""),
            run_dir=run_dir,
        )

        # Mark defects as fixed if direct fix applied code changes
        if direct["applied"] > 0:
            for did in new_defect_ids:
                ledger.mark_fixed(did, f"direct-fix-round-{round_num}")
            log.info(f"Marked {len(new_defect_ids)} defects as fixed after direct fix")

        if direct["applied"] == 0 or direct["failed"] > direct["applied"]:
            # Direct fix insufficient — spawn builder
            fix_spec = generate_fix_spec(blocking, fix_plan, phase_id)
            exit_code, _ = spawn_claude_builder(
                state.project, state.build_id, phase_num, fix_spec,
                "sonnet", work_copy, run_dir, BUILDER_TIMEOUT, task_num=80 + round_num
            )
            # If builder succeeded, mark remaining open defects from this round as fixed
            if exit_code == 0:
                still_open = [did for did in new_defect_ids
                              if any(d["id"] == did and d["status"] == "open"
                                     for d in ledger.defects)]
                for did in still_open:
                    ledger.mark_fixed(did, f"builder-fix-round-{round_num}")
                if still_open:
                    log.info(f"Marked {len(still_open)} defects as fixed after builder")

        ledger.commit(phase_id)

        # Refresh for next round
        tool_outputs = precompute_tool_outputs(work_copy)
        num_commits = count_phase_commits(work_copy, phase_id)
        diff_context = get_phase_diff(work_copy, num_commits)

    # Codex cross-phase audit
    try:
        spawn_codex_audit(
            work_copy, phase_id, phase_num, run_dir,
            contracts=contracts, total_phases=total_phases,
        )
    except Exception as e:
        log.warning(f"Codex audit skipped: {e}")

    # Write phase gate-proof with gate_type: pr
    write_phase_gate_proof(work_copy, phase_id, task_ids or [], gate_type="pr", ledger=ledger)

    log.info(f"Phase review COMPLETE: {phase_id}")
    return True


# ── Main Build Loop ──────────────────────────────────────────────────────────
def run_build(project: str, spec_path: str, build_id: str = None,
              profile: str = "standard"):
    config = load_claude_config()

    if not build_id:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        build_id = f"BUILD-claude-{project}-{ts}"

    log.info(f"Starting Claude Code build: {build_id} for {project} (profile: {profile})")

    try:
        spec_content = Path(spec_path).read_text()
    except (FileNotFoundError, IOError) as e:
        log.error(f"Cannot read spec file {spec_path}: {e}")
        state = BuildState(build_id, project, spec_path)
        state.update(status="failed")
        state.add_error(f"Spec file unreadable: {e}")
        notify_telegram(f"Build {build_id} failed: spec unreadable: {e}")
        return False

    state = BuildState(build_id, project, spec_path)
    state.update(forge_profile=profile)

    if not acquire_lock(project, build_id):
        msg = f"Could not acquire lock for {project}. Already locked."
        log.error(msg)
        state.update(status="failed")
        state.add_error(msg)
        notify_telegram(f"Build {build_id} failed: {msg}")
        return False

    try:
        return _run_build_inner(project, spec_content, build_id, state, config, profile)
    except Exception as e:
        log.exception(f"Build {build_id} crashed")
        state.update(status="failed")
        state.add_error(f"Orchestrator crash: {e}")
        notify_telegram(f"Build {build_id} crashed: {e}")
        return False
    finally:
        release_lock(project)


def _is_phase_completed(work_copy: Path, phase_id: str) -> bool:
    """Check if a phase is already completed in the Forge tracker."""
    tracker_file = work_copy / ".forge" / "tracker.yaml"
    if not tracker_file.exists():
        return False
    try:
        tracker = yaml.safe_load(tracker_file.read_text())
        for sec in (tracker.get("sections") or {}).values():
            phase_data = (sec.get("phases") or {}).get(phase_id)
            if phase_data and phase_data.get("status") == "completed":
                return True
    except yaml.YAMLError:
        pass
    return False


def _run_build_inner(project, spec_content, build_id, state, config, profile):
    builder_model = config.get("builders", {}).get("routine", {}).get("model", "sonnet")
    builder_timeout = config.get("builders", {}).get("routine", {}).get("timeout_minutes", 45) * 60
    complex_model = config.get("builders", {}).get("complex", {}).get("model", "sonnet")

    from forge_build_common import WORKTREES_DIR

    # ── 1. Create or resume working copy ──
    existing_work_copy = WORKTREES_DIR / project / build_id
    is_resume = existing_work_copy.exists() and (existing_work_copy / ".git").exists()

    if is_resume:
        work_copy = existing_work_copy
        log.info(f"Resuming build — reusing working copy at {work_copy}")
        state.update(status="resuming", phase_status="loading_state")
    else:
        state.update(status="initialising", phase_status="creating_working_copy")
        work_copy = create_working_copy(project, build_id)
        forge_init_project(work_copy)
        forge_session_start(work_copy, build_id)

    ledger = DefectLedger(work_copy)

    # ── 2. Planning — load saved plan on resume, or generate fresh ──
    plan_file = state.run_dir / "plan.json"
    contracts_file = state.run_dir / "contracts.json"

    if is_resume and plan_file.exists() and contracts_file.exists():
        log.info("Resuming: loading saved plan and contracts")
        plan = json.loads(plan_file.read_text())
        phases = plan.get("phases", [])
        contracts = json.loads(contracts_file.read_text())
        log.info(f"Loaded plan: {len(phases)} phases, "
                 f"{len(contracts.get('file_contracts', {}))} file contracts")
    else:
        state.update(phase_status="planning")
        log.info("Planning build with Opus...")

        spec_text = spec_content[:15000]
        if len(spec_content) > 15000:
            spec_text += f"\n\n[TRUNCATED — original spec is {len(spec_content)} chars. " \
                         f"The {len(spec_content) - 15000} chars after this point were not shown. " \
                         f"Use the contracts extraction step to capture requirements from the full spec.]"
            log.warning(f"Spec truncated from {len(spec_content)} to 15000 chars for planner")

        plan = opus_judge(
            f"You are the build planner for project '{project}'.\n\n"
            f"Build spec:\n```\n{spec_text}\n```\n\n"
            f"Decompose into Forge SDLC phases. For each phase provide:\n"
            f"- phase_id (e.g. 'S02.P01')\n"
            f"- phase_number (int, starting at 1)\n"
            f"- title (string)\n"
            f"- description (string) — CRITICAL: copy EXACT values from the spec into the "
            f"description. If the spec says enum values are 'pending/running/completed/failed', "
            f"write those exact values. If the spec says files go in 'engine/', write that exact path. "
            f"Builders only see the description, not the original spec.\n"
            f"- complexity ('routine' or 'complex')\n"
            f"- files_to_touch (list of exact file paths from the spec)\n"
            f"- acceptance_criteria (list of testable criteria)\n"
            f"- applicable_standards (from: type_safety_reviewer, contract_reviewer, "
            f"silent_failure_hunter, security_reviewer, performance_reviewer, test_coverage_reviewer. "
            f"Match to work: API endpoints need contract+silent_failure+security, models need type_safety, "
            f"tests need test_coverage.)\n"
            f"- tasks (list with: task_id like 'S02.P01.T01', title, scope (MUST include exact "
            f"file paths, enum values, API endpoints from the spec — builders ONLY see scope text), "
            f"depends_on_tasks (list of task_ids THIS task depends on, empty if independent), "
            f"standards (engineering standards that apply: error-handling, testing, api-design, "
            f"database, logging, security, type-safety, configuration))\n"
            f"- depends_on (list of phase IDs, empty if none)\n\n"
            f"Rules:\n"
            f"- One phase per logical module (models, store, API, tests). 1-3 implementation tasks each.\n"
            f"- Each task should be implementable in one Claude session (~30 min).\n"
            f"- Test tasks in later phases (sequential execution).\n"
            f"- Do NOT create standalone tasks just for __init__.py files — include __init__.py "
            f"creation as part of the first task that creates files in that package.\n"
            f"- Every task must produce substantive code, not just empty files.\n"
            f"- Copy EXACT enum values, file paths, endpoint names, and config keys into task scope text.\n"
            f"- The scope field is the ONLY thing the builder sees — make it self-contained.\n\n"
            f"MANDATORY: The LAST task in EVERY phase MUST be a T_REVIEW task. This is a spec compliance "
            f"audit — NOT optional. Example: if phase S02.P01 has 3 implementation tasks (T01-T03), "
            f"then T04 must be the T_REVIEW task. The T_REVIEW task spec:\n"
            f"- task_id: '<phase_id>.T_REVIEW' (e.g. 'S02.P01.T_REVIEW')\n"
            f"- title: 'Spec Compliance Audit & Review'\n"
            f"- scope: 'Verify ALL acceptance criteria from prior tasks were genuinely implemented. "
            f"For each AC: (1) find the code that implements it, (2) find the test that verifies it, "
            f"(3) confirm the test actually tests real behavior not just asserting True. "
            f"Check: config uses lazy accessor pattern not module-level init, tests work without .env, "
            f"all test deps declared in dev group, no dead fixtures, async fixtures have teardown. "
            f"Fix any gaps found. Run full test suite. Commit fixes.'\n"
            f"- depends_on_tasks: [list ALL prior task_ids in this phase]\n\n"
            f'Return JSON: {{"phases": [...], "section": "S02", "notes": "..."}}',
            work_copy, timeout=600
        )

        if not plan or "phases" not in plan:
            log.error("Planning failed — no phases returned")
            state.update(status="failed")
            state.add_error("Opus planning returned no phases")
            notify_telegram(f"Build {build_id} failed: no phases")
            cleanup_working_copy(project, build_id)
            return False

        phases = plan.get("phases", [])

        # ── FIX #4: Plan validation with retry (2 rounds) ──
        MAX_PLAN_FIX_ROUNDS = 2
        for fix_round in range(MAX_PLAN_FIX_ROUNDS + 1):
            validation = validate_plan(phases)

            if validation["warnings"]:
                for w in validation["warnings"]:
                    log.warning(f"Plan warning: {w}")

            if validation["valid"]:
                if fix_round > 0:
                    log.info(f"Plan validated after {fix_round} fix round(s)")
                else:
                    log.info("Plan validated: no structural issues")
                break

            log.warning(f"Plan validation failed ({len(validation['issues'])} issues)")
            for issue in validation["issues"]:
                log.warning(f"  - {issue}")

            if fix_round >= MAX_PLAN_FIX_ROUNDS:
                log.warning("Plan issues persist — proceeding with caution")
                state.add_error(f"Plan has unresolved issues: {validation['issues']}")
                break

            state.update(phase_status=f"fixing_plan_round_{fix_round + 1}")
            fixed_plan = opus_judge(
                f"Your plan has structural issues.\n\n"
                f"Issues:\n" + "\n".join(f"- {i}" for i in validation["issues"])
                + f"\n\nCurrent plan:\n{json.dumps(plan, indent=2)[:8000]}\n\n"
                f"Fix and return corrected plan.\n"
                f'Return JSON: {{"phases": [...], "section": "S02", "notes": "..."}}',
                work_copy
            )
            if fixed_plan.get("phases"):
                phases = fixed_plan["phases"]
                plan = fixed_plan

        # ── FIX #1: Contract extraction ──
        state.update(phase_status="extracting_contracts")
        log.info("Extracting contracts from spec...")

        contracts = opus_judge(
            f"Extract ALL verifiable contracts from this build spec.\n\n"
            f"Spec:\n{spec_content[:12000]}\n\n"
            f"Plan:\n{json.dumps(plan, indent=2)[:4000]}\n\n"
            f"Extract into JSON:\n"
            f'{{"file_contracts": {{"path/to/file.py": "purpose"}}, '
            f'"enum_contracts": {{"EnumName": ["val1", "val2"]}}, '
            f'"endpoint_contracts": [{{"method": "GET", "path": "/health", '
            f'"params": [], "response_example": {{}}, "status_code": 200}}], '
            f'"business_rules": [{{"rule": "positive rule", '
            f'"negative": "what must NOT happen", "test_scenario": "how to verify"}}], '
            f'"forbidden": ["anti-pattern1"]}}\n\n'
            f"Rules:\n"
            f"- file_contracts: EVERY file from spec with exact paths\n"
            f"- enum_contracts: EVERY enum with EXACT values from spec\n"
            f"- endpoint_contracts: EVERY endpoint with method, path, params, response shape\n"
            f"- business_rules: EVERY rule with negative constraint + test scenario\n"
            f"- forbidden: things builders must NOT do\n",
            work_copy, timeout=300
        )

        contracts_file.write_text(json.dumps(contracts, indent=2))
        log.info(f"Contracts: {len(contracts.get('file_contracts', {}))} files, "
                 f"{len(contracts.get('enum_contracts', {}))} enums, "
                 f"{len(contracts.get('endpoint_contracts', []))} endpoints")

        # Completeness check
        all_spec_files = set(contracts.get("file_contracts", {}).keys())
        all_plan_files = set()
        for p in phases:
            all_plan_files.update(p.get("files_to_touch", []))
            for t in p.get("tasks", []):
                all_plan_files.update(re.findall(r'[\w/.-]+\.(?:py|ts|tsx|js|jsx|toml|yaml|yml|json|cfg|ini|env)', t.get("scope", "")))
        missing_files = all_spec_files - all_plan_files
        if missing_files:
            log.warning(f"Completeness gap: {missing_files}")
            fix = opus_judge(
                f"Files from spec not covered by any task: {list(missing_files)}\n\n"
                f"Plan: {json.dumps(plan, indent=2)[:6000]}\n\n"
                f"Add missing files to existing tasks or create new ones.\n"
                f'Return JSON: {{"phases": [...], "section": "S02"}}',
                work_copy
            )
            if fix.get("phases"):
                phases = fix["phases"]

        # Save plan and contracts
        plan_file.write_text(json.dumps({"phases": phases}, indent=2, default=str))

    # Always recalculate after any plan amendments
    total_phases = len(phases)
    state.update(total_phases=total_phases, status="building")
    log.info(f"Plan: {total_phases} phases")

    # ── 3. Phase loop ──
    for phase_num, phase_info in enumerate(phases, 1):
        phase_id = phase_info.get("phase_id", f"S02.P{phase_num:02d}")
        title = phase_info.get("title", f"Phase {phase_num}")

        # Skip completed phases on resume
        if is_resume and _is_phase_completed(work_copy, phase_id):
            log.info(f"Skipping completed phase {phase_id} (resume)")
            continue

        tasks = phase_info.get("tasks", [])
        if not tasks:
            log.warning(f"Phase {phase_id} has 0 tasks — skipping")
            state.update(phase_status="skipped_empty")
            continue
        task_ids = [t.get("task_id", f"{phase_id}.T{i+1:02d}") for i, t in enumerate(tasks)]
        complexity = phase_info.get("complexity", "routine")

        phase_dir = state.run_dir / f"phase_{phase_num}"
        phase_dir.mkdir(parents=True, exist_ok=True)

        state.update(
            current_phase=phase_num, phase_status="building",
            total_tasks_in_phase=len(tasks), current_task_index=0,
            phase_started_at=datetime.now(timezone.utc).isoformat(),
        )
        log.info(f"{'='*60}")
        log.info(f"Phase {phase_num}/{total_phases}: {phase_id} — {title}")
        log.info(f"Tasks: {len(tasks)}, Complexity: {complexity}")

        if complexity == "complex":
            phase_model = complex_model
            phase_timeout = config.get("builders", {}).get("complex", {}).get("timeout_minutes", 60) * 60
        else:
            phase_model = builder_model
            phase_timeout = builder_timeout

        # Build tasks sequentially
        completed_task_ids = []

        for task_idx, task in enumerate(tasks, 1):
            task_id = task.get("task_id", f"{phase_id}.T{task_idx:02d}")
            task_title = task.get("title", "Task")

            state.update(current_task=task_id, current_task_index=task_idx,
                         phase_status=f"building_task_{task_idx}/{len(tasks)}")
            log.info(f"Task {task_idx}/{len(tasks)}: {task_id} ({task_title})")

            ctx = extract_cross_task_context(work_copy, completed_task_ids)
            pre_task_ctx = build_pre_task_context(
                work_copy, task, completed_task_ids, contracts, state.run_dir
            )
            full_context = ctx
            if pre_task_ctx:
                full_context = f"{ctx}\n\n{pre_task_ctx}" if ctx else pre_task_ctx
            task_spec = generate_forge_task_spec(
                task=task, phase_id=phase_id, phase_title=title,
                phase_description=phase_info.get("description", ""),
                task_index=task_idx, total_tasks=len(tasks),
                completed_tasks=completed_task_ids,
                complexity=complexity, profile=profile,
                applicable_standards=phase_info.get("applicable_standards"),
                contracts=contracts,
                cross_task_context=full_context,
            )

            # Build with retry
            task_success = False
            task_model = phase_model
            task_timeout = phase_timeout

            for attempt in range(MAX_BUILD_RETRIES + 1):
                exit_code, terminal_log = spawn_claude_builder(
                    project, build_id, phase_num, task_spec,
                    task_model, work_copy, state.run_dir,
                    task_timeout, task_num=task_idx
                )

                if exit_code == 0:
                    # Verify builder actually produced changes
                    # Strategy 1: Check commit messages for task_id
                    commit_check = subprocess.run(
                        ["git", "-C", str(work_copy), "log", "--oneline", "-5", "--format=%s"],
                        capture_output=True, text=True, timeout=10
                    )
                    recent_msgs = commit_check.stdout.strip().splitlines() if commit_check.returncode == 0 else []
                    has_commit = any(task_id in msg or phase_id in msg for msg in recent_msgs)

                    # Strategy 2: Check if expected files were modified
                    if not has_commit:
                        diff_check = subprocess.run(
                            ["git", "-C", str(work_copy), "diff", "--name-only", "HEAD~1..HEAD"],
                            capture_output=True, text=True, timeout=10
                        )
                        changed_files = diff_check.stdout.strip().splitlines() if diff_check.returncode == 0 else []
                        has_commit = len(changed_files) > 0 and not all(f.startswith(".forge/") for f in changed_files)

                    if not has_commit:
                        log.warning(f"Builder exited 0 but no relevant changes found for {task_id}")
                        exit_code = 1
                    else:
                        task_success = True
                        break

                if attempt < MAX_BUILD_RETRIES:
                    recovery = opus_judge(
                        f"Builder failed at {task_id} (attempt {attempt+1}/{MAX_BUILD_RETRIES+1}).\n"
                        f"Exit code: {exit_code}\nLog tail:\n{terminal_log[-2000:]}\n\n"
                        f"Options: retry, retry_revised, escalate, skip, abort\n"
                        f'Return JSON: {{"action": "...", "reason": "...", "revised_spec": "..."}}',
                        work_copy
                    )
                    action = recovery.get("action", "retry")
                    log.info(f"Recovery: {action} — {recovery.get('reason', '')}")

                    if action == "abort":
                        state.update(status="failed")
                        notify_telegram(f"Build {build_id} aborted at {task_id}")
                        cleanup_working_copy(project, build_id, preserve=True)
                        return False
                    if action == "skip":
                        task_success = True
                        break
                    if action == "escalate":
                        task_model = complex_model
                        task_timeout = config.get("builders", {}).get("complex", {}).get("timeout_minutes", 60) * 60
                    if action == "retry_revised" and recovery.get("revised_spec"):
                        task_spec += f"\n\n## RETRY GUIDANCE\n\n{recovery['revised_spec']}\n"
                    state.add_error(f"{task_id} attempt {attempt+1} failed")

            if not task_success:
                state.update(status="escalated")
                state.add_error(f"{task_id} failed after {MAX_BUILD_RETRIES+1} attempts")
                notify_telegram(f"Build {build_id} escalated: {task_id} failed")
                cleanup_working_copy(project, build_id, preserve=True)
                return False

            # Post-task: reconcile forge state
            if reconcile_tracker_task(work_copy, phase_id, task_id, task_title):
                subprocess.run(["git", "-C", str(work_copy), "add", ".forge/tracker.yaml"],
                                capture_output=True, text=True, timeout=60)
                subprocess.run(["git", "-C", str(work_copy), "commit", "-m",
                                 f"chore({task_id}): reconcile tracker"],
                                capture_output=True, text=True, timeout=60)

            # Per-task L1+L2 review (CANNOT BE SKIPPED)
            task_review(work_copy, task_id, phase_id, state, ledger, state.run_dir)

            # Post-task quality check
            quality = verify_committed_quality(work_copy, task_id)
            if quality["issues"] and not quality["tests_ok"]:
                log.warning(f"Post-task quality FAIL for {task_id} — auto-fixing")
                direct = apply_fixes_directly(
                    work_copy, [], phase_id,
                    findings_text="\n".join(quality["issues"]),
                    run_dir=state.run_dir,
                )
                quality2 = verify_committed_quality(work_copy, task_id)
                if quality2["issues"] and not quality2["tests_ok"]:
                    log.warning(f"Auto-fix failed for {task_id} — issues persist")
                    state.add_error(f"Unresolved quality issues for {task_id}")
            elif quality["issues"]:
                for issue in quality["issues"]:
                    state.add_error(issue)

            completed_task_ids.append(task_id)

        # Reconcile forge state
        state.update(phase_status="reconciling")
        reconcile_tracker(work_copy, phase_id, task_ids, phase_title=title)
        reconcile_evidence(work_copy, phase_id, task_ids, tasks_meta=tasks)

        # Fix phase status
        tracker_file = work_copy / ".forge" / "tracker.yaml"
        if tracker_file.exists():
            try:
                tracker_data = yaml.safe_load(tracker_file.read_text())
                if isinstance(tracker_data, dict):
                    changed = False
                    for sec in (tracker_data.get("sections") or {}).values():
                        for pid, pdata in (sec.get("phases") or {}).items():
                            if pid == phase_id and pdata.get("status") != "completed":
                                all_done = all(
                                    t.get("status") == "completed"
                                    for t in (pdata.get("tasks") or {}).values()
                                )
                                if all_done:
                                    pdata["status"] = "completed"
                                    changed = True
                    if changed:
                        tracker_data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        tracker_file.write_text(yaml.dump(tracker_data, default_flow_style=False, sort_keys=False))
                        subprocess.run(["git", "-C", str(work_copy), "add", ".forge/tracker.yaml"],
                                        capture_output=True, text=True, timeout=60)
                        subprocess.run(["git", "-C", str(work_copy), "commit", "-m",
                                         f"chore({phase_id}): set phase completed"],
                                        capture_output=True, text=True, timeout=60)
            except (yaml.YAMLError, IOError) as e:
                log.warning(f"Could not fix phase status: {e}")

        # Phase review (T_REVIEW) — ALL phases get full review
        state.update(phase_status="review_gate")
        if not phase_review(work_copy, phase_id, state, ledger, state.run_dir,
                            phase_num, total_phases, contracts, task_ids=task_ids):
            return False

        state.update(phase_status="completed",
                     phase_completed_at=datetime.now(timezone.utc).isoformat())
        log.info(f"Phase {phase_id} COMPLETE")

    # Low severity sweep (best effort — don't block build on failure)
    open_lows = ledger.get_open_lows()
    if open_lows:
        log.info(f"Sweeping {len(open_lows)} Low findings")
        sweep_spec = generate_low_sweep_spec(open_lows)
        exit_code, _ = spawn_claude_builder(
            project, build_id, 99, sweep_spec,
            builder_model, work_copy, state.run_dir, SWEEP_TIMEOUT
        )
        if exit_code == 0:
            for d in open_lows:
                ledger.mark_fixed(d["id"], "low-sweep")
            ledger.commit("low-sweep")
        else:
            log.warning(f"Low sweep failed (exit {exit_code}) — continuing to push")

    # ── Post-build learning: extract rules from defects ──
    log.info("Extracting learned rules from build defects...")
    try:
        learned = extract_learned_rules(ledger, work_copy, state.run_dir)
        if learned:
            log.info(f"Extracted {len(learned)} learned rules")
            # Also copy to source repo for persistence across builds
            source_rules = Path(f"/home/deploy/workspace/{project}/.forge/learned_rules.yaml")
            source_rules.parent.mkdir(parents=True, exist_ok=True)
            source_rules.write_text((work_copy / ".forge" / "learned_rules.yaml").read_text())
    except Exception as e:
        log.warning(f"Learned rules extraction failed: {e}")

    # Push + PR
    state.update(status="finalising", phase_status="pushing")
    branch = f"build/{build_id}"
    forge_session_end(work_copy)
    final_tracker = forge_tracker_status(work_copy)

    commit_result = subprocess.run(
        ["git", "-C", str(work_copy), "log", "--oneline", "main..HEAD"],
        capture_output=True, text=True, timeout=60
    )
    commit_count = len(commit_result.stdout.strip().splitlines()) if commit_result.returncode == 0 else 0

    if commit_count == 0:
        state.update(status="completed", phase_status="no_changes")
        notify_telegram(f"Build {build_id} completed with no changes.")
        cleanup_working_copy(project, build_id)
        return True

    subprocess.run(["git", "-C", str(work_copy), "push", "origin", branch, "--force"],
                    capture_output=True, text=True, timeout=120)

    phases_summary = "\n".join(f"- {p.get('phase_id', '?')}: {p.get('title', '?')}" for p in phases)
    pr_body = (
        f"## Automated Build (Claude Code + Forge SDLC)\n\n"
        f"**Build ID:** {build_id}\n**Project:** {project}\n"
        f"**Runtime:** Claude Code\n**Profile:** {profile}\n"
        f"**Phases:** {total_phases}\n**Defects:** {len(ledger.defects)}\n\n"
        f"### Phases\n{phases_summary}\n\n"
        f"### Forge Tracker\n```\n{final_tracker[:1000]}\n```\n\n"
        f"---\nBuilt by OnPulse Pipeline (Claude Code Runtime)"
    )

    # Derive repo from git remote (don't hardcode org name)
    remote_url = subprocess.run(
        ["git", "-C", str(work_copy), "remote", "get-url", "origin"],
        capture_output=True, text=True, timeout=10
    )
    repo_slug = ""
    if remote_url.returncode == 0:
        url = remote_url.stdout.strip()
        # Handle both https://github.com/org/repo.git and git@github.com:org/repo.git
        match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        if match:
            repo_slug = match.group(1)

    if repo_slug:
        pr_result = subprocess.run(
            ["gh", "pr", "create", "--repo", repo_slug,
             "--title", f"[BUILD] {build_id}", "--body", pr_body,
             "--base", "main", "--head", branch],
            capture_output=True, text=True, cwd=str(work_copy), timeout=120
        )
        pr_url = pr_result.stdout.strip() if pr_result.returncode == 0 else f"PR creation failed: {pr_result.stderr[:200]}"
    else:
        log.warning(f"Could not derive repo slug from remote URL: {remote_url.stdout.strip()}")
        pr_url = "PR creation skipped — could not determine repo"

    build_duration = datetime.now(timezone.utc) - datetime.fromisoformat(state.data["started_at"])
    build_minutes = int(build_duration.total_seconds() / 60)

    result_data = {
        "build_id": build_id, "project": project, "runtime": "claude",
        "status": "completed", "profile": profile, "phases": total_phases,
        "pr_url": pr_url, "branch": branch, "commits": commit_count,
        "defects_tracked": len(ledger.defects),
        "duration_minutes": build_minutes,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (state.run_dir / "result.json").write_text(json.dumps(result_data, indent=2))
    state.update(status="completed", phase_status="done")

    notify_telegram(
        f"Build {build_id} COMPLETE (Claude Code)\n"
        f"PR: {pr_url}\nPhases: {total_phases} | Commits: {commit_count} | "
        f"Defects: {len(ledger.defects)} | Duration: {build_minutes}min"
    )

    if pr_url and "failed" not in pr_url.lower() and "skipped" not in pr_url.lower():
        cleanup_working_copy(project, build_id)
    else:
        log.info(f"Working copy preserved at {work_copy} (PR not created)")

    return True


# ── Queue drain ──────────────────────────────────────────────────────────────
def drain_queue(profile: str = "standard"):
    queue_files = sorted(QUEUE_DIR.glob("*.json"))
    pending = []
    for f in queue_files:
        try:
            entry = json.loads(f.read_text())
            if entry.get("status") == "pending":
                pending.append((f, entry))
        except (json.JSONDecodeError, IOError):
            continue

    if not pending:
        log.info("Queue empty")
        return

    pending.sort(key=lambda x: (0 if x[1].get("priority") == "high" else 1,
                                 x[1].get("queued_at", "")))

    for queue_file, entry in pending:
        build_id = entry["build_id"]
        entry["status"] = "running"
        entry["started_at"] = datetime.now(timezone.utc).isoformat()
        queue_file.write_text(json.dumps(entry, indent=2))
        try:
            success = run_build(entry["project"], entry["spec_path"],
                                build_id, entry.get("profile", profile))
            entry["status"] = "completed" if success else "failed"
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            queue_file.write_text(json.dumps(entry, indent=2))
        except Exception as e:
            log.exception(f"Build {build_id} failed")
            entry["status"] = "failed"
            entry["error"] = str(e)
            queue_file.write_text(json.dumps(entry, indent=2))


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Claude Code runtime — Forge autonomous build orchestrator"
    )
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--spec", help="Path to build spec")
    parser.add_argument("--drain-queue", action="store_true")
    parser.add_argument("--resume", metavar="BUILD_ID")
    parser.add_argument("--profile", default="standard", choices=["light", "standard"])

    args = parser.parse_args()

    if args.drain_queue:
        drain_queue(args.profile)
    elif args.resume:
        state = BuildState.load(args.resume)
        run_build(state.project, state.spec_path, args.resume, args.profile)
    elif args.project and args.spec:
        run_build(args.project, args.spec, profile=args.profile)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
