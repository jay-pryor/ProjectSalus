"""Report-module contract (I-12).

Defines the :class:`ReportModule` protocol and the value types that flow
between modules and the orchestrator.  Sections implement
:class:`ReportModule` and declare their placement via :class:`ModuleManifest`;
the orchestrator (:func:`salus.report.builder.build_report`) calls
:meth:`ReportModule.is_applicable` then :meth:`ReportModule.render` on each
module in order and stitches the resulting HTML fragments into a single PDF.

Sections are self-contained in v1: no module-to-module references and no
cross-section anchors.  That keeps the contract small enough to migrate the
existing 10 sections one at a time without coupling them prematurely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import jinja2

if TYPE_CHECKING:
    from salus.report.pdf import SimulationResults


@dataclass(frozen=True)
class ModuleManifest:
    """Static metadata describing a report section.

    Attributes:
        id: Stable identifier used in logs and curation profiles
            (e.g. ``"executive_summary"``).
        title: Human-readable section title.
        placement: ``"body"`` for narrative sections; ``"appendix"`` for
            reference material printed after the body.
        page_break_before: When True, the rendered HTML carries a CSS
            class that forces a page break before the section.
        landscape: When True, the section is rendered on landscape pages
            via the ``@page landscape`` CSS rule in ``base.html``.
        optional: When True, the orchestrator may omit the section from
            a curated report.  Non-optional sections (e.g. cover) are
            always rendered.
    """

    id: str
    title: str
    placement: Literal["body", "appendix"] = "body"
    page_break_before: bool = True
    landscape: bool = False
    optional: bool = True


@dataclass
class RenderedSection:
    """Output of :meth:`ReportModule.render`.

    The orchestrator concatenates :attr:`html` fragments from every applicable
    module in order, then injects the result into ``base.html`` for the final
    PDF render.  :attr:`warnings` are non-fatal issues surfaced for the
    gate-proof — they do not abort rendering.
    """

    module_id: str
    html: str
    landscape: bool = False
    page_break_before: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class RenderContext:
    """Shared per-render state passed to every module.

    Modules read this context to access the shared Jinja2 environment and
    common report-level metadata.  No module-to-module data flow exists in
    v1; if two modules need the same derived value, each computes it from
    :class:`~salus.report.pdf.SimulationResults` independently.
    """

    template_env: jinja2.Environment
    scenario_name: str
    generated_at: str


@runtime_checkable
class ReportModule(Protocol):
    """Contract every report section must satisfy.

    Implementations declare a :attr:`manifest` describing placement and a
    pair of methods: :meth:`is_applicable` guards rendering when the
    required inputs are missing, and :meth:`render` produces the section's
    HTML fragment.
    """

    manifest: ModuleManifest

    def is_applicable(self, sim: SimulationResults) -> bool:
        """Return True iff this module has the data it needs from ``sim``.

        The orchestrator calls this before :meth:`render` and skips modules
        that return False (with an info-level log line).  Implementations
        must not raise — return False for any missing prerequisite.
        """
        ...

    def render(self, sim: SimulationResults, ctx: RenderContext) -> RenderedSection:
        """Render the section to a :class:`RenderedSection`.

        Implementations should populate :attr:`RenderedSection.landscape`
        and :attr:`RenderedSection.page_break_before` from
        ``self.manifest`` so the orchestrator can respect per-section
        page rules without re-reading the manifest.
        """
        ...
