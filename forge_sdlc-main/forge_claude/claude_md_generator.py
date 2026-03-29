"""Forge CLAUDE.md generator — generates project-specific Forge section.

Appends a Forge-specific section to a project's CLAUDE.md file with
skill references, active standards, and review gate requirements.
"""

from pathlib import Path

from forge_core.standards_loader import StandardsLoader

__all__ = ["generate_forge_section", "append_to_claude_md"]

START_MARKER = "<!-- FORGE:START -->"
END_MARKER = "<!-- FORGE:END -->"


def generate_forge_section(
    project_name: str,
    project_type: str,
    governance_profile: str = "standard",
) -> str:
    """Generate the Forge section content for CLAUDE.md."""
    loader = StandardsLoader()

    # Determine applicable standards
    all_standards = loader.list_standards().get("standards", [])
    python_standards = [
        "error-handling", "testing", "logging", "type-safety", "api-design",
        "database", "security", "dependency-management", "configuration", "documentation",
    ]
    frontend_standards = [
        "typescript-safety", "component-testing", "api-client-contracts",
        "error-boundaries", "frontend-design-system",
    ]

    if project_type == "python":
        applicable = [s for s in python_standards if s in all_standards]
    elif project_type == "frontend":
        applicable = [s for s in frontend_standards if s in all_standards]
    else:  # fullstack
        applicable = [s for s in python_standards + frontend_standards if s in all_standards]

    # Build section
    lines = [
        START_MARKER,
        "",
        f"## Forge SDLC — {project_name}",
        "",
        f"**Project type:** {project_type}",
        f"**Governance:** {governance_profile}",
        "",
        "### Forge Commands",
        "",
        "| Command | Purpose |",
        "|---------|---------|",
        "| `forge session start` | Start a work session |",
        "| `forge tracker status` | View current task states |",
        "| `forge check standards` | Run standards checks |",
        "| `forge check cross-cutting` | Run cross-cutting audit |",
        "| `forge health check` | Framework integrity check |",
        "",
        "### Active Standards",
        "",
    ]

    for s in applicable:
        lines.append(f"- `{s}`")

    lines.extend([
        "",
        "### Review Gate Requirements",
        "",
        "**Required agents:** forge_spec_compliance, forge_silent_failure_hunter, forge_code_simplifier, forge_regression_reviewer",
        "",
    ])

    if project_type in ("fullstack", "frontend"):
        lines.append("**Conditional:** forge_frontend_design_reviewer (on .tsx/.css changes)")
        lines.append("")

    lines.extend([
        "Gate-proofs written to `.forge/gate-proofs/{task_id}.yaml`",
        "",
        END_MARKER,
    ])

    return "\n".join(lines)


def append_to_claude_md(
    project_dir: Path,
    project_name: str,
    project_type: str,
    governance_profile: str = "standard",
) -> dict:
    """Append or replace the Forge section in a project's CLAUDE.md."""
    claude_md = project_dir / "CLAUDE.md"
    forge_section = generate_forge_section(project_name, project_type, governance_profile)

    if claude_md.is_file():
        content = claude_md.read_text(encoding="utf-8")
        # Replace existing forge section if present
        if START_MARKER in content and END_MARKER in content:
            start_idx = content.index(START_MARKER)
            end_idx = content.index(END_MARKER) + len(END_MARKER)
            content = content[:start_idx] + forge_section + content[end_idx:]
        else:
            content = content.rstrip() + "\n\n" + forge_section + "\n"
    else:
        content = f"# {project_name}\n\n{forge_section}\n"

    claude_md.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "action": "claude_md.generate",
        "project_name": project_name,
        "project_type": project_type,
        "file": str(claude_md),
        "standards_count": len(forge_section.split("- `")) - 1,
    }
