"""Modular PDF report orchestrator (I-12).

Composes an ordered list of :class:`~salus.report.modules.ReportModule`
instances into a single PDF.  Runs alongside the legacy
:func:`salus.report.pdf.render_pdf` entry point — neither path is modified
by this module.

Pipeline:

1. Build a shared :class:`~salus.report.modules.RenderContext` (Jinja2 env,
   scenario name, timestamp).
2. For each module: call :meth:`is_applicable`; if False, skip with an info
   log; otherwise call :meth:`render` and collect the
   :class:`~salus.report.modules.RenderedSection`.
3. Concatenate the section HTML fragments and inject into ``base.html``.
4. Convert to PDF via WeasyPrint.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import weasyprint

from salus.report.modules import ModuleManifest, RenderContext, ReportModule

if TYPE_CHECKING:
    from salus.report.pdf import SimulationResults

_log = logging.getLogger(__name__)

_DEFAULT_TEMPLATE_DIR: Path = Path(__file__).parent / "templates"


def build_report(
    sim: SimulationResults,
    modules: Sequence[ReportModule],
    output_path: str | Path,
    template_dir: str | Path | None = None,
) -> Path:
    """Render a PDF from an ordered list of report modules.

    Args:
        sim: Simulation results used by every module.
        modules: Ordered sequence of :class:`ReportModule` instances.  The
            order determines the order of sections in the output PDF.
        output_path: Destination path for the PDF.  Parent directories
            are created automatically.
        template_dir: Directory containing the bundled Jinja2 templates
            (``base.html`` and per-section templates).  When ``None``,
            uses the package default.

    Returns:
        Resolved :class:`~pathlib.Path` to the written PDF.

    Raises:
        FileNotFoundError: If ``template_dir`` does not exist, or no
            ``base.html`` is present inside it.
        ValueError: If ``sim.scenario`` is missing or its
            ``site_dem_path`` is empty, or if no modules are applicable
            to the simulation (an empty PDF would otherwise be written).
        RuntimeError: If a module's ``render()`` raises — wrapped so the
            failing module id is captured in the message.
        OSError: If WeasyPrint fails to write the PDF or produces an
            empty file.
    """
    if sim.scenario is None or not getattr(sim.scenario, "site_dem_path", ""):
        raise ValueError("build_report requires sim.scenario with a non-empty site_dem_path")

    output_path = Path(output_path)
    tmpl_dir = Path(template_dir) if template_dir is not None else _DEFAULT_TEMPLATE_DIR

    if not tmpl_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {tmpl_dir}")
    if not (tmpl_dir / "base.html").exists():
        raise FileNotFoundError(f"base.html missing in template directory: {tmpl_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        autoescape=jinja2.select_autoescape(["html"]),
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scenario_name = Path(sim.scenario.site_dem_path).stem or "unnamed_scenario"

    ctx = RenderContext(
        template_env=env,
        scenario_name=scenario_name,
        generated_at=generated_at,
    )

    fragments: list[str] = []
    rendered_ids: list[str] = []
    for module in modules:
        if not isinstance(module.manifest, ModuleManifest):
            raise TypeError(
                f"Module {type(module).__name__} has manifest of type "
                f"{type(module.manifest).__name__}; expected ModuleManifest"
            )
        mid = module.manifest.id
        if not module.is_applicable(sim):
            _log.info("Skipping module %s: is_applicable=False", mid)
            continue
        try:
            section = module.render(sim, ctx)
        except Exception as exc:
            raise RuntimeError(f"Module {mid} render() raised {type(exc).__name__}: {exc}") from exc
        rendered_ids.append(section.module_id)
        fragments.append(section.html)

    if not fragments:
        raise ValueError(
            f"No modules applicable to this simulation (modules={len(modules)}); "
            f"refusing to write an empty PDF to {output_path}"
        )

    base_tmpl = env.get_template("base.html")
    full_html = base_tmpl.render(content="\n".join(fragments))

    _log.info("Rendering PDF → %s (sections=%s)", output_path, rendered_ids)
    try:
        weasyprint.HTML(string=full_html, base_url=str(tmpl_dir)).write_pdf(str(output_path))
    except Exception as exc:
        raise OSError(f"WeasyPrint failed to render PDF to {output_path}: {exc}") from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OSError(f"WeasyPrint produced an empty or missing PDF at {output_path}")

    size_kb = output_path.stat().st_size // 1024
    _log.info("PDF written: %s (%d KB)", output_path, size_kb)

    return output_path.resolve()
