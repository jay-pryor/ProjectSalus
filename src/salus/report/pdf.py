"""PDF report generation for cUAS site coverage analysis (S13).

Provides data structures and functions for assembling and rendering a
professional PDF report from simulation results.  The pipeline is:

1. Run simulation to obtain :class:`SimulationResults`.
2. Call :func:`assemble_report_data` to render maps to base64, generate the
   executive summary, and build the structured assumptions section.
3. Call :func:`render_pdf` to render Jinja2 templates and produce a PDF via
   WeasyPrint.
"""

from __future__ import annotations

import base64
import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2
import numpy as np
import numpy.typing as npt
import weasyprint

from salus.engine.coverage import CoverageStats, compute_gaps
from salus.engine.threat_corridor import CorridorResult
from salus.models.saturation import SaturationResult
from salus.models.scenario import (
    KillChainConfig,
    KillChainResult,
    ScenarioConfig,
    SensorPlacement,
)
from salus.models.sensor import EffectorDefinition, SensorDefinition, SensorType
from salus.models.site import SiteModel

_log = logging.getLogger(__name__)

# Coverage quality thresholds (percentage)
_COVERAGE_THRESHOLD_GOOD: float = 80.0
_COVERAGE_THRESHOLD_ADEQUATE: float = 60.0

# Default templates directory (bundled with salus)
_DEFAULT_TEMPLATE_DIR: Path = Path(__file__).parent / "templates"

# Section criticality policy (I-16). REQUIRED sections must render successfully
# or render_pdf raises ReportRenderError. OPTIONAL sections may fail; the
# failure is recorded in ReportData.section_failures and the section is omitted
# from the PDF.  Required map assets (composite_map for site_overview, gap_map
# for gap_analysis) also raise on failure; per-layer maps and optional charts
# (kill_chain, saturation) are audit-logged and skipped.
_REQUIRED_SECTIONS: frozenset[str] = frozenset(
    {
        "cover",
        "executive_summary",
        "site_overview",
        "coverage_analysis",
        "gap_analysis",
        "assumptions",
        "appendix_sensors",
    }
)
_OPTIONAL_SECTIONS: frozenset[str] = frozenset(
    {
        "threat_analysis",
        "kill_chain",
        "saturation",
    }
)


class ReportRenderError(RuntimeError):
    """Raised when a required PDF section, template, or map asset fails to render.

    Optional-section failures do not raise — they are recorded in
    :attr:`ReportData.section_failures` and surfaced to the caller as a
    warning.  Only failures of REQUIRED sections / assets raise this error.
    """


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SimulationResults:
    """Results from running the full simulation pipeline.

    Used as input to :func:`assemble_report_data`.  The caller is responsible
    for running the simulation (viewshed, coverage, kill chain, saturation)
    and populating all fields before assembling the report.  Kill-chain and
    saturation fields default to empty/None when those analyses were not run.
    """

    site: SiteModel
    """Loaded terrain model."""

    scenario: ScenarioConfig
    """Scenario configuration that was simulated."""

    composite: npt.NDArray[np.bool_]
    """Composite boolean coverage array (True = covered by at least one sensor)."""

    layer_coverages: dict[SensorType, npt.NDArray[np.bool_]]
    """Per-sensor-type boolean coverage arrays."""

    stats: CoverageStats
    """Aggregate coverage statistics."""

    sensor_defs: list[SensorDefinition]
    """Sensor definitions used in the simulation."""

    effector_defs: list[EffectorDefinition] = field(default_factory=list)
    """Effector definitions used (empty if no effectors in scenario)."""

    corridor_results: list[CorridorResult] = field(default_factory=list)
    """Threat corridor analysis results (empty if analysis was not run)."""

    kill_chain_results: list[KillChainResult] = field(default_factory=list)
    """Kill-chain timeline results, one per corridor (empty if not run)."""

    saturation_result: SaturationResult | None = None
    """Saturation threshold sweep result (None if analysis was not run)."""

    saturation_threshold_data: dict[int, int] = field(default_factory=dict)
    """N → unengaged-count sweep data for the saturation bar chart.
    Keys are simultaneous target counts; values are unengaged targets at that N.
    Empty when saturation analysis was not run."""

    kill_chain_config: KillChainConfig | None = None
    """Kill-chain phase durations (None if analysis was not run)."""

    gaps: npt.NDArray[np.bool_] | None = None
    """Uncovered-cell boolean mask from :func:`~salus.engine.coverage.compute_gaps`.
    When None, a full-extent bitmask is used when rendering the gap map."""


@dataclass
class ReportData:
    """All data needed to render the full PDF report.

    Produced by :func:`assemble_report_data`; consumed by :func:`render_pdf`.
    All map images are pre-rendered to base64-encoded PNG strings so that the
    rendering step has no dependency on the original simulation arrays.
    """

    scenario_name: str
    """Human-readable scenario name (derived from the DEM file stem)."""

    generated_at: str
    """ISO-8601 UTC timestamp at which the report was assembled."""

    stats: CoverageStats
    """Aggregate coverage statistics."""

    executive_summary: str
    """Auto-generated narrative summary (3–5 paragraphs)."""

    assumptions: dict[str, list[str]]
    """Structured assumptions mapping section title → list of assumption strings."""

    sensor_defs: list[SensorDefinition]
    """Sensor definitions used in the simulation."""

    effector_defs: list[EffectorDefinition]
    """Effector definitions used in the simulation."""

    sensor_placements: list[SensorPlacement]
    """Sensor placements from the scenario configuration."""

    scenario: ScenarioConfig
    """Source scenario configuration."""

    composite_map_b64: str | None
    """Base64-encoded composite coverage map PNG, or None if rendering failed."""

    gap_map_b64: str | None
    """Base64-encoded gap analysis map PNG, or None if rendering failed."""

    layer_maps_b64: dict[str, str]
    """Base64-encoded per-layer coverage map PNGs keyed by SensorType.value."""

    kill_chain_chart_b64: str | None
    """Base64-encoded kill-chain Gantt chart PNG, or None if not available."""

    saturation_chart_b64: str | None
    """Base64-encoded saturation threshold chart PNG, or None if not available."""

    corridor_results: list[CorridorResult]
    """Threat corridor analysis results (empty if not run)."""

    kill_chain_results: list[KillChainResult]
    """Kill-chain timeline results (empty if not run)."""

    saturation_result: SaturationResult | None
    """Saturation analysis result (None if not run)."""

    kill_chain_config: KillChainConfig | None
    """Kill-chain configuration used during analysis (None if not run)."""

    map_screenshot: str | None = None
    """Optional base64-encoded PNG map capture from the interface."""

    section_failures: list[str] = field(default_factory=list)
    """Audit log of optional sections / assets that failed to render and were
    omitted from the PDF (I-16 section-criticality policy).  Each entry is a
    `"<section_or_layer>: <reason>"` string.  Empty when the PDF rendered
    cleanly.  Required-section failures never appear here — they raise
    :class:`ReportRenderError` instead.  Callers should surface a non-empty
    list to the operator as an audit-visible warning."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assemble_report_data(
    scenario: ScenarioConfig,
    sim_results: SimulationResults,
) -> ReportData:
    """Assemble all data needed to render the PDF report.

    Renders coverage maps and charts to in-memory base64-encoded PNGs,
    generates the executive summary narrative, and builds the structured
    assumptions section.

    Failure policy (I-16 section-criticality):

    * The composite coverage map and the gap map are required assets — a
      rendering failure raises :class:`ReportRenderError`.
    * Per-layer coverage maps and optional charts (kill-chain Gantt,
      saturation threshold) are audit-logged: a rendering failure appends an
      entry to :attr:`ReportData.section_failures` and the corresponding
      field is left as ``None`` / omitted.  The PDF still renders.

    Args:
        scenario: Scenario configuration that was simulated.
        sim_results: Results from running the simulation pipeline.

    Returns:
        :class:`ReportData` ready to pass to :func:`render_pdf`.

    Raises:
        ReportRenderError: If the composite map or gap map fails to render.
    """
    from salus.report.maps import render_composite_coverage_map, render_gap_map

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scenario_name = Path(scenario.site_dem_path).stem

    sensor_positions = [(p.position_x, p.position_y) for p in scenario.sensor_placements]
    section_failures: list[str] = []

    # Composite coverage map — REQUIRED (site_overview section).
    composite_map_b64 = _render_to_b64(
        render_composite_coverage_map,
        sim_results.site,
        sim_results.layer_coverages,
        _asset_label="site_overview.composite_map",
        title="Composite Coverage",
        sensor_positions=sensor_positions,
    )

    # Gap map — REQUIRED (gap_analysis section).
    if sim_results.gaps is not None:
        gaps_arr = sim_results.gaps
    else:
        full_bitmask = np.ones((sim_results.site.rows, sim_results.site.cols), dtype=bool)
        gaps_arr = compute_gaps(sim_results.composite, full_bitmask)

    gap_map_b64 = _render_gap_map_to_b64(
        render_gap_map,
        sim_results.site,
        sim_results.composite,
        gaps_arr,
        title="Coverage Gap Analysis",
        sensor_positions=sensor_positions,
    )

    # Per-layer coverage maps — OPTIONAL assets within the required
    # coverage_analysis section.  Individual layer failures are audit-logged
    # and skipped; the surrounding section still renders.
    layer_maps_b64: dict[str, str] = {}
    for sensor_type, layer_arr in sim_results.layer_coverages.items():
        try:
            layer_b64 = _render_to_b64(
                render_composite_coverage_map,
                sim_results.site,
                {sensor_type: layer_arr},
                _asset_label=f"coverage_analysis.{sensor_type.value}",
                title=f"{sensor_type.value} Layer Coverage",
                sensor_positions=sensor_positions,
            )
        except ReportRenderError as exc:
            section_failures.append(str(exc))
            _log.warning(
                "Per-layer map render failed for %s — section_failures recorded; "
                "skipping this layer.",
                sensor_type.value,
            )
            continue
        layer_maps_b64[sensor_type.value] = layer_b64

    # Kill-chain Gantt chart — OPTIONAL (data-gated).
    kill_chain_chart_b64 = _render_kill_chain_chart_to_b64(sim_results, section_failures)

    # Saturation threshold chart — OPTIONAL (data-gated).
    saturation_chart_b64 = _render_saturation_chart_to_b64(sim_results, section_failures)

    executive_summary = generate_executive_summary(
        sim_results.stats,
        sim_results.kill_chain_results,
        sim_results.saturation_result,
    )

    assumptions = _build_assumptions(sim_results)

    return ReportData(
        scenario_name=scenario_name,
        generated_at=generated_at,
        stats=sim_results.stats,
        executive_summary=executive_summary,
        assumptions=assumptions,
        sensor_defs=sim_results.sensor_defs,
        effector_defs=sim_results.effector_defs,
        sensor_placements=scenario.sensor_placements,
        scenario=scenario,
        composite_map_b64=composite_map_b64,
        gap_map_b64=gap_map_b64,
        layer_maps_b64=layer_maps_b64,
        kill_chain_chart_b64=kill_chain_chart_b64,
        saturation_chart_b64=saturation_chart_b64,
        corridor_results=sim_results.corridor_results,
        kill_chain_results=sim_results.kill_chain_results,
        saturation_result=sim_results.saturation_result,
        kill_chain_config=sim_results.kill_chain_config,
        section_failures=section_failures,
    )


def render_pdf(
    report_data: ReportData,
    output_path: str | Path,
    template_dir: str | Path | None = None,
) -> Path:
    """Render a PDF report from assembled report data.

    Renders each template section with Jinja2, concatenates the HTML
    fragments inside ``base.html``, and converts the complete document to
    PDF using WeasyPrint.  Landscape page orientation is applied for map
    sections via CSS ``@page`` rules.  Images are embedded at sufficient
    resolution for print quality (>= 150 DPI at A4 width).

    Sections are conditionally included: threat_analysis and kill_chain are
    only included when corridor or kill-chain results are present; saturation
    is only included when a saturation result exists.  Optional sections
    whose chart asset already failed in :func:`assemble_report_data` (and
    therefore have an entry in ``report_data.section_failures``) are dropped.

    Failure policy (I-16 section-criticality):

    * Required sections (``cover``, ``executive_summary``, ``site_overview``,
      ``coverage_analysis``, ``gap_analysis``, ``assumptions``,
      ``appendix_sensors``) raise :class:`ReportRenderError` on any Jinja
      ``TemplateError`` or ``TemplateNotFound``.
    * Optional sections (``threat_analysis``, ``kill_chain``, ``saturation``)
      append a ``"<section>: <reason>"`` entry to
      ``report_data.section_failures`` and are omitted from the PDF.

    Args:
        report_data: Assembled report data from :func:`assemble_report_data`.
        output_path: Destination path for the output PDF file.  Parent
            directories are created automatically.
        template_dir: Directory containing Jinja2 HTML templates.  If None,
            uses the default template directory bundled with salus.

    Returns:
        Resolved :class:`~pathlib.Path` to the written PDF file.

    Raises:
        FileNotFoundError: If the template directory does not exist.
        OSError: If the output file cannot be written.
        ReportRenderError: If a required section fails to render.
    """
    output_path = Path(output_path)
    tmpl_dir = Path(template_dir) if template_dir is not None else _DEFAULT_TEMPLATE_DIR

    if not tmpl_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {tmpl_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        autoescape=jinja2.select_autoescape(["html"]),
    )

    # Build list of sections to render — optional sections only when data
    # is present AND the section has not already been marked failed in
    # assemble_report_data (e.g. kill_chain dropped when its chart failed).
    already_failed = {entry.split(":", 1)[0] for entry in report_data.section_failures}
    section_names = [
        "cover",
        "executive_summary",
        "site_overview",
        "coverage_analysis",
        "gap_analysis",
    ]
    if report_data.corridor_results and "threat_analysis" not in already_failed:
        section_names.append("threat_analysis")
    if (
        report_data.kill_chain_results
        and report_data.kill_chain_chart_b64 is not None
        and "kill_chain" not in already_failed
    ):
        section_names.append("kill_chain")
    if (
        report_data.saturation_result is not None
        and report_data.saturation_chart_b64 is not None
        and "saturation" not in already_failed
    ):
        section_names.append("saturation")
    section_names.extend(["assumptions", "appendix_sensors"])

    content_parts: list[str] = []
    for section in section_names:
        try:
            tmpl = env.get_template(f"{section}.html")
            content_parts.append(tmpl.render(report=report_data))
        except (jinja2.TemplateNotFound, jinja2.TemplateError) as exc:
            if section in _REQUIRED_SECTIONS:
                raise ReportRenderError(
                    f"Required section '{section}' failed to render: {exc}"
                ) from exc
            reason = (
                "template not found"
                if isinstance(exc, jinja2.TemplateNotFound)
                else f"template error: {exc}"
            )
            report_data.section_failures.append(f"{section}: {reason}")
            _log.warning(
                "Optional section '%s' omitted from PDF (%s) — recorded in section_failures.",
                section,
                reason,
            )

    base_tmpl = env.get_template("base.html")
    full_html = base_tmpl.render(
        content="\n".join(content_parts),
        report=report_data,
    )

    _log.info("Rendering PDF → %s", output_path)
    try:
        weasyprint.HTML(string=full_html, base_url=str(tmpl_dir)).write_pdf(str(output_path))
    except Exception as exc:
        raise OSError(f"WeasyPrint failed to render PDF to {output_path}: {exc}") from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OSError(f"WeasyPrint produced an empty or missing PDF at {output_path}")

    size_kb = output_path.stat().st_size // 1024
    _log.info("PDF written: %s (%d KB)", output_path, size_kb)

    return output_path.resolve()


def generate_executive_summary(
    stats: CoverageStats,
    kill_chain_results: list[KillChainResult],
    saturation_result: SaturationResult | None,
) -> str:
    """Generate a 3–5 paragraph executive summary narrative.

    Uses conditional logic to classify coverage as good (≥ 80%), adequate
    (60–80%), or poor (< 60%), and produces corresponding natural-language
    paragraphs for coverage overview, per-layer breakdown (when available),
    zone coverage (when available), kill-chain feasibility (when kill-chain
    results are provided), and saturation capacity (when saturation analysis
    was run).

    Args:
        stats: Aggregate coverage statistics from the simulation.
        kill_chain_results: Kill-chain results per corridor (empty if not run).
        saturation_result: Saturation analysis result (None if not run).

    Returns:
        Multi-paragraph string separated by double newlines, suitable for
        embedding in the executive summary section of the report.
    """
    paras: list[str] = []

    # Para 1: Coverage overview with profile-specific recommendation
    pct = stats.total_coverage_pct
    gap_km2 = stats.gap_area_m2 / 1_000_000.0
    largest_gap_ha = stats.largest_contiguous_gap_m2 / 10_000.0

    if pct >= _COVERAGE_THRESHOLD_GOOD:
        qual = "comprehensive"
        recommendation = (
            "This coverage level meets the recommended threshold for high-value asset protection."
        )
    elif pct >= _COVERAGE_THRESHOLD_ADEQUATE:
        qual = "partial"
        recommendation = (
            "Additional sensor placements or coverage optimisation should be considered "
            "to address residual gaps."
        )
    else:
        qual = "limited"
        recommendation = (
            "Significant coverage gaps exist. Additional sensors or a revised placement "
            "strategy are strongly recommended before operational deployment."
        )

    paras.append(
        f"The assessed sensor configuration provides {pct:.1f}% composite coverage across the "
        f"site, representing a {qual} detection capability. "
        f"The total uncovered area is {gap_km2:.3f}\u00a0km\u00b2, with the largest contiguous "
        f"gap measuring {largest_gap_ha:.2f}\u00a0ha. {recommendation}"
    )

    # Para 2: Per-layer coverage breakdown (always present — fallback when no per-layer data)
    if stats.per_layer_coverage_pct:
        sorted_layers = sorted(
            stats.per_layer_coverage_pct.items(), key=lambda x: x[1], reverse=True
        )
        layer_lines = ", ".join(f"{st.value}: {layer_pct:.1f}%" for st, layer_pct in sorted_layers)
        paras.append(
            f"Coverage by sensor modality is as follows: {layer_lines}. "
            "Combining multiple sensor modalities improves overall detection probability "
            "and reduces the risk of a single-modality gap being exploited by an adversary."
        )
    else:
        paras.append(
            "No per-modality coverage breakdown is available for this configuration. "
            "Deploying multiple complementary sensor modalities (RF, radar, EO/IR, acoustic) "
            "improves detection probability and reduces the risk of exploitation through "
            "single-modality gaps."
        )

    # Para 3: Zone coverage (only when named zones are defined)
    if stats.per_zone_coverage_pct:
        zone_lines = "; ".join(
            f"{name}: {z_pct:.1f}%" for name, z_pct in stats.per_zone_coverage_pct.items()
        )
        critical_zones = [
            name
            for name, z_pct in stats.per_zone_coverage_pct.items()
            if z_pct < _COVERAGE_THRESHOLD_GOOD
        ]
        zone_para = f"Named zone coverage: {zone_lines}."
        if critical_zones:
            zone_para += (
                f" The following zones have coverage below {_COVERAGE_THRESHOLD_GOOD:.0f}% "
                f"and warrant targeted improvement: {', '.join(critical_zones)}."
            )
        paras.append(zone_para)
    else:
        # Para 3 fallback — always produce at least 3 paragraphs
        paras.append(
            "No named zone analysis was performed for this configuration. "
            "Defining named zones for critical assets (runways, buildings, perimeter boundary) "
            "enables per-asset coverage metrics and more targeted gap prioritisation. "
            "Zone analysis can be added by providing a GeoJSON zones file in the scenario."
        )

    # Para 4: Kill-chain feasibility
    if kill_chain_results:
        n_feasible = sum(1 for r in kill_chain_results if r.engagement_feasible)
        n_total = len(kill_chain_results)
        n_second = sum(1 for r in kill_chain_results if r.second_engagement_possible)

        if n_feasible == n_total:
            kc_body = (
                f"all {n_total} assessed approach corridor(s) provide sufficient "
                "detection-to-engagement time"
            )
            kc_detail = (
                f"A second engagement opportunity is available on {n_second} of "
                f"{n_total} corridor(s). The kill chain is assessed as viable across "
                "the full threat envelope."
            )
        elif n_feasible > 0:
            kc_body = (
                f"{n_feasible} of {n_total} approach corridors provide sufficient "
                "detection-to-engagement time"
            )
            kc_detail = (
                "Additional sensor or effector coverage should be considered for "
                "corridors where engagement time is insufficient."
            )
        else:
            kc_body = (
                "no assessed approach corridors provide sufficient detection-to-engagement time"
            )
            kc_detail = (
                "The kill chain cannot be completed before threat arrival on any assessed "
                "corridor. Significant capability improvements are required."
            )

        paras.append(
            f"Kill-chain analysis indicates that {kc_body} for the configured effector "
            f"network. {kc_detail}"
        )

    # Para 5: Saturation capacity
    if saturation_result is not None:
        cap = saturation_result.simultaneous_engagement_capacity
        thresh = saturation_result.saturation_threshold_n
        threshold_never_reached = (
            thresh > cap and saturation_result.unengaged_count_at_threshold == 0
        )

        if threshold_never_reached:
            sat_text = (
                f"The effector network can engage up to {cap} simultaneous targets without "
                "saturation within the analysed threat count range. The saturation threshold "
                "was not reached, indicating adequate capacity for the scenarios assessed."
            )
        elif thresh <= 2:
            sat_text = (
                f"The effector network becomes saturated at {thresh} simultaneous target(s) "
                f"(engagement capacity: {cap}). This represents a critical vulnerability — "
                "small coordinated swarms are likely to overwhelm defences."
            )
        else:
            sat_text = (
                f"The effector network becomes saturated at {thresh} simultaneous targets "
                f"(simultaneous engagement capacity: {cap}). A coordinated threat of "
                f"{thresh} or more drones would result in at least one target reaching "
                "the protected asset unengaged."
            )

        paras.append(sat_text)

    return "\n\n".join(paras)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_assumptions(sim_results: SimulationResults) -> dict[str, list[str]]:
    """Build the structured assumptions and limitations dictionary for the report.

    Returns a mapping from section title to list of assumption strings covering
    terrain model provenance, sensor modelling limitations, propagation model
    constraints, and threat model simplifications.
    """
    site = sim_results.site
    res = site.resolution
    epsg_str = f" (EPSG:{site.crs_epsg})" if site.crs_epsg else ""

    terrain_items: list[str] = [
        f"Terrain model: Digital Elevation Model (DEM) at {res:.1f} m/pixel resolution{epsg_str}",
    ]
    if site.dsm is not None:
        terrain_items.append(
            "Digital Surface Model (DSM) loaded — buildings and structures occlude "
            "sensor lines of sight"
        )
    if site.canopy_height_m is not None:
        terrain_items.append(
            "Canopy Height Model (CHM) loaded — vegetation attenuation applied using "
            "sensor-specific Bouguer–Lambert penetration factors"
        )
    else:
        terrain_items.append(
            "No vegetation layer — canopy attenuation not modelled; "
            "results may be optimistic in forested areas"
        )

    sensor_items: list[str] = [
        "Sensor specifications sourced from manufacturer data sheets unless noted otherwise",
        "Detection model: binary (detected / not-detected) — no probability-of-detection "
        "(Pd) curves applied; detection is either certain or impossible at range boundaries",
        "All sensors modelled as stationary at their configured mounting height above ground",
        "Azimuth coverage is a hard arc boundary — beam-shape, side-lobe, and antenna "
        "pattern effects are not modelled",
        "Sensor elevation arc is a hard cone boundary — target elevation angle must fall "
        "within the configured arc; no tapering at arc edges",
    ]

    propagation_items: list[str] = [
        "Free-space propagation model — multipath, diffraction, and atmospheric refraction "
        "are not modelled",
        "No atmospheric attenuation applied — rain, fog, temperature gradients, and humidity "
        "effects on RF and acoustic propagation are excluded",
        "RF propagation uses line-of-sight assessment only — ground-wave and ionospheric "
        "propagation paths are not considered",
        "Radar cross-section (RCS) assumed constant across all aspect angles — target "
        "attitude, material, and orientation are not modelled",
        "Acoustic propagation uses free-field spherical spreading — wind noise, turbulence, "
        "and ground-reflection effects are excluded",
    ]

    threat_items: list[str] = [
        "Threat approach modelled as constant-altitude, constant-speed, straight-line flight",
        "No evasive manoeuvres, terrain-following, or nap-of-the-earth flight modelled",
        "Threat altitude taken from profile typical_altitude_m — actual operational "
        "altitude may differ",
        "Threat radar cross-section and RF emission profile sourced from published "
        "threat data; actual values may vary by operator modification",
        "Kill-chain timings are deterministic — operator reaction-time variability and "
        "comms latency are not modelled",
    ]

    return {
        "Terrain Model": terrain_items,
        "Sensor Modelling": sensor_items,
        "Propagation Model": propagation_items,
        "Threat Model": threat_items,
    }


def _render_to_b64(
    render_func: Callable[..., Path],
    *args: Any,
    _asset_label: str = "map",
    **kwargs: Any,
) -> str:
    """Call a render function with a temp file path; return base64-encoded PNG.

    The temporary file is always deleted regardless of success or failure.

    Raises:
        ReportRenderError: If the render function raises.  The original
            exception is chained via ``from``.  Callers that want to treat
            individual failures as non-fatal (e.g. per-layer maps) must catch
            this explicitly.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        render_func(*args, output_path=tmp_path, **kwargs)
        data = tmp_path.read_bytes()
        return base64.b64encode(data).decode()
    except Exception as exc:
        raise ReportRenderError(
            f"{_asset_label}: render failed ({getattr(render_func, '__name__', '?')}): {exc}"
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_gap_map_to_b64(
    render_func: Callable[..., Path],
    site: SiteModel,
    composite: npt.NDArray[np.bool_],
    gaps: npt.NDArray[np.bool_],
    **kwargs: Any,
) -> str:
    """Render the gap map to a base64-encoded PNG string.

    The gap map is required by the gap_analysis section.

    Raises:
        ReportRenderError: If gap map rendering fails.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        render_func(site, composite, gaps, output_path=tmp_path, **kwargs)
        data = tmp_path.read_bytes()
        return base64.b64encode(data).decode()
    except Exception as exc:
        raise ReportRenderError(f"gap_analysis.gap_map: render failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_kill_chain_chart_to_b64(
    sim_results: SimulationResults,
    section_failures: list[str],
) -> str | None:
    """Render the kill-chain Gantt chart to a base64-encoded PNG string.

    Returns None when kill-chain results, config, or effectors are unavailable
    (the legitimate "no chart applicable" case).  When inputs ARE available
    but rendering fails, appends a ``"kill_chain: <reason>"`` entry to
    ``section_failures`` and returns None — the section is then dropped from
    the PDF by :func:`render_pdf`.
    """
    from salus.report.charts import render_kill_chain_chart

    if (
        not sim_results.kill_chain_results
        or not sim_results.corridor_results
        or sim_results.kill_chain_config is None
        or not sim_results.effector_defs
    ):
        return None

    # Select the most capable effector for the kill chain chart
    effector_for_chart = max(sim_results.effector_defs, key=lambda e: e.defeat_probability)
    if len(sim_results.effector_defs) > 1:
        _log.warning(
            "Kill-chain chart: %d effectors available; selecting %r "
            "(highest defeat_probability=%.2f).",
            len(sim_results.effector_defs),
            effector_for_chart.name,
            effector_for_chart.defeat_probability,
        )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        render_kill_chain_chart(
            sim_results.corridor_results,
            sim_results.kill_chain_results,
            sim_results.kill_chain_config,
            effector_for_chart,
            tmp_path,
        )
        data = tmp_path.read_bytes()
        return base64.b64encode(data).decode()
    except Exception as exc:
        section_failures.append(f"kill_chain: chart render failed: {exc}")
        _log.warning(
            "Kill-chain chart render failed (%s) — section omitted; recorded in section_failures.",
            exc,
        )
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_saturation_chart_to_b64(
    sim_results: SimulationResults,
    section_failures: list[str],
) -> str | None:
    """Render the saturation threshold chart to a base64-encoded PNG string.

    Returns None when saturation data is unavailable (the legitimate "no
    chart applicable" case).  When data IS available but rendering fails,
    appends a ``"saturation: <reason>"`` entry to ``section_failures`` and
    returns None — the section is dropped from the PDF.
    """
    from salus.report.charts import render_saturation_threshold_chart

    sat = sim_results.saturation_result
    if sat is None or not sim_results.saturation_threshold_data:
        return None

    threshold_never_reached = (
        sat.saturation_threshold_n > sat.simultaneous_engagement_capacity
        and sat.unengaged_count_at_threshold == 0
    )
    if threshold_never_reached:
        # Push the threshold line off the right edge of the chart
        sat_threshold_line = max(sim_results.saturation_threshold_data) + 1
    else:
        sat_threshold_line = sat.saturation_threshold_n

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        render_saturation_threshold_chart(
            sim_results.saturation_threshold_data,
            sat_threshold_line,
            tmp_path,
        )
        data = tmp_path.read_bytes()
        return base64.b64encode(data).decode()
    except Exception as exc:
        section_failures.append(f"saturation: chart render failed: {exc}")
        _log.warning(
            "Saturation chart render failed (%s) — section omitted; recorded in section_failures.",
            exc,
        )
        return None
    finally:
        tmp_path.unlink(missing_ok=True)
