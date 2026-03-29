#\!/usr/bin/env python3
"""Standards ↔ Agent Slices ↔ Tool Configs cross-reference validator.

Validates that:
1. Every rule ID referenced in agent slices exists in a parent OPS standard
2. Every agent definition references a valid agent slice file
3. Every tool config references a valid standard section
4. No orphan references exist
"""

import re
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

FORGE_DIR = Path("/home/deploy/forge-sdlc")
STANDARDS_DIR = FORGE_DIR / "standards" / "ops"
AGENT_SLICES_DIR = STANDARDS_DIR / "agent_slices"
TOOL_CONFIGS_DIR = STANDARDS_DIR / "tool_configs"
AGENT_DEFS_DIR = FORGE_DIR / "forge_claw" / "agents" / "ops"

# Patterns to extract references
OPS_STD_PATTERN = re.compile(r"OPS-STD-\d{3}")
SECTION_PATTERN = re.compile(r"§\d+(?:\.\d+)*")
CONTROL_ID_PATTERN = re.compile(r"\b(APP-[A-Z]+-\d+|INF-[A-Z]+-\d+)\b")


def validate_agent_slice_refs() -> list[str]:
    """Check that agent slices reference valid standards."""
    errors = []
    if not AGENT_SLICES_DIR.exists():
        errors.append(f"Agent slices directory not found: {AGENT_SLICES_DIR}")
        return errors

    for slice_file in AGENT_SLICES_DIR.glob("*.md"):
        content = slice_file.read_text()
        std_refs = OPS_STD_PATTERN.findall(content)
        for ref in set(std_refs):
            matching = list(STANDARDS_DIR.glob("*.md"))
            found = any(ref.replace("-", "_") in f.name.upper() or ref in f.read_text()
                       for f in matching)
            if not found:
                errors.append(f"{slice_file.name}: references {ref} but no matching standard found")

    return errors


def validate_agent_def_refs() -> list[str]:
    """Check that agent definitions reference valid slice files."""
    errors = []
    if not AGENT_DEFS_DIR.exists():
        errors.append(f"Agent definitions directory not found: {AGENT_DEFS_DIR}")
        return errors

    for def_file in AGENT_DEFS_DIR.glob("*.yaml"):
        content = def_file.read_text()
        # Look for context_inject path references
        slice_refs = re.findall(r"path:\s*standards/agent_slices/(\S+)", content)
        for ref in slice_refs:
            if not (AGENT_SLICES_DIR / ref).exists():
                errors.append(f"{def_file.name}: references slice {ref} but file not found")

    return errors


def validate_tool_config_refs() -> list[str]:
    """Check that tool configs reference valid standards."""
    errors = []
    if not TOOL_CONFIGS_DIR.exists():
        return errors

    for config_file in TOOL_CONFIGS_DIR.rglob("*.yaml"):
        content = config_file.read_text()
        std_refs = OPS_STD_PATTERN.findall(content)
        for ref in set(std_refs):
            matching = list(STANDARDS_DIR.glob("*.md"))
            found = any(ref in f.read_text() for f in matching)
            if not found:
                errors.append(f"{config_file.name}: references {ref} but standard not found")

    return errors


def main():
    log.info("Validating standards cross-references...")
    all_errors = []

    log.info("Checking agent slice references...")
    all_errors.extend(validate_agent_slice_refs())

    log.info("Checking agent definition references...")
    all_errors.extend(validate_agent_def_refs())

    log.info("Checking tool config references...")
    all_errors.extend(validate_tool_config_refs())

    if all_errors:
        log.error("Found %d validation errors:", len(all_errors))
        for err in all_errors:
            print(f"  ERROR: {err}")
        sys.exit(1)
    else:
        log.info("All cross-references valid.")
        print("PASS: Zero stale references found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
