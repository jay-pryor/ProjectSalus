"""Report-module contract and section implementations (I-12).

Each report section is a :class:`ReportModule` that can be developed, tested,
and curated independently.  The :func:`salus.report.builder.build_report`
orchestrator composes an ordered list of modules into a single PDF.
"""

from salus.report.modules._base import (
    ModuleManifest,
    RenderContext,
    RenderedSection,
    ReportModule,
)
from salus.report.modules.executive_summary import ExecutiveSummaryModule

__all__ = [
    "ExecutiveSummaryModule",
    "ModuleManifest",
    "RenderContext",
    "RenderedSection",
    "ReportModule",
]
