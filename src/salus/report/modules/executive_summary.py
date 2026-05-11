"""Executive Summary report module (I-12).

Thin adapter that wraps the legacy :func:`generate_executive_summary` prose
generator and the existing ``executive_summary.html`` Jinja2 template in the
:class:`~salus.report.modules._base.ReportModule` protocol.

The legacy template binds to a single ``report`` namespace with the fields
``executive_summary``, ``stats``, and ``kill_chain_results``.  This module
constructs an equivalent lightweight view object so the template renders
identically to the legacy pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from salus.report.modules._base import (
    ModuleManifest,
    RenderContext,
    RenderedSection,
)

if TYPE_CHECKING:
    from salus.engine.coverage import CoverageStats
    from salus.models.scenario import KillChainResult
    from salus.report.pdf import SimulationResults

_log = logging.getLogger(__name__)

_TEMPLATE_NAME = "executive_summary.html"


@dataclass(frozen=True)
class _ExecutiveSummaryView:
    """Minimal ``report``-shaped object consumed by the legacy template."""

    executive_summary: str
    stats: CoverageStats
    kill_chain_results: list[KillChainResult]


class ExecutiveSummaryModule:
    """Render the Executive Summary section.

    Reuses :func:`salus.report.pdf.generate_executive_summary` for the prose
    and the bundled ``executive_summary.html`` template for the metric-cards
    layout, so per-paragraph output matches the legacy pipeline exactly.
    """

    manifest: ModuleManifest = ModuleManifest(
        id="executive_summary",
        title="Executive Summary",
        placement="body",
        page_break_before=True,
        landscape=False,
        optional=True,
    )

    def is_applicable(self, sim: SimulationResults) -> bool:
        # `stats` is typed non-Optional on SimulationResults, but the legacy
        # contract also assumes `kill_chain_results` is at least an iterable
        # — the template iterates it with `selectattr`. Guard both so a
        # mutated SimulationResults cannot trigger a confusing TemplateError.
        return sim.stats is not None and sim.kill_chain_results is not None

    def render(self, sim: SimulationResults, ctx: RenderContext) -> RenderedSection:
        from salus.report.pdf import generate_executive_summary

        prose = generate_executive_summary(
            sim.stats,
            sim.kill_chain_results,
            sim.saturation_result,
        )
        view = _ExecutiveSummaryView(
            executive_summary=prose,
            stats=sim.stats,
            kill_chain_results=sim.kill_chain_results,
        )
        template = ctx.template_env.get_template(_TEMPLATE_NAME)
        html = template.render(report=view)
        return RenderedSection(
            module_id=self.manifest.id,
            html=html,
            landscape=self.manifest.landscape,
            page_break_before=self.manifest.page_break_before,
            warnings=[],
        )
