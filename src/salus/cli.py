"""Salus CLI entry point."""

from __future__ import annotations

import logging
import math
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import numpy as np
import yaml

from salus.engine.comparison import ConfigurationResult, compare_configs
from salus.engine.coverage import (
    boundary_mask,
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
)
from salus.engine.path_planner import build_detection_cost_grid, find_adversarial_trajectory
from salus.engine.placement import (
    PlacementWeights,
    generate_candidate_positions,
    greedy_place_sensors,
)
from salus.engine.saturation import (
    allocate_effectors,
    compute_reengagement_timeline,
    find_saturation_threshold,
)
from salus.engine.threat_corridor import find_worst_corridors
from salus.engine.trajectory import analyse_trajectory, find_worst_trajectories
from salus.engine.viewshed import clip_viewshed_to_sensor, compute_viewshed
from salus.ingest.boundaries import load_boundary
from salus.ingest.scenario import load_scenario
from salus.ingest.sensors import load_sensors, load_threats
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.report.charts import (
    render_comparison_statistics_table,
    render_coverage_comparison_chart,
    render_effector_utilisation_chart,
    render_saturation_threshold_chart,
)
from salus.report.maps import (
    render_adversarial_map,
    render_composite_coverage_map,
    render_corridor_overlay_map,
    render_corridor_polar_diagram,
    render_coverage_map,
    render_delta_map,
    render_gap_map,
    render_layer_coverage_maps,
    render_redundancy_map,
    render_side_by_side_coverage_maps,
    render_trajectory_map,
)

if TYPE_CHECKING:
    from salus.models.site import SiteModel

_log = logging.getLogger(__name__)

# Bundled sensor definitions shipped with the package.
_DEFAULT_SENSOR_DIR: Path = Path(__file__).parent / "data" / "sensors"

# Bundled threat profiles shipped with the package.
_DEFAULT_THREAT_DIR: Path = Path(__file__).parent / "data" / "threats"


_FALLBACK_SENSOR_FILENAME: str = "sensor"


def _safe_filename(name: str) -> str:
    """Convert a sensor name to a filesystem-safe filename component.

    Replaces runs of non-word characters with a single underscore and
    strips leading/trailing underscores. Returns 'sensor' if the result
    would be empty (e.g. the name consisted entirely of non-word characters).
    """
    result = re.sub(r"\W+", "_", name).strip("_")
    return result if result else _FALLBACK_SENSOR_FILENAME


@click.group()
@click.version_option()
def main() -> None:
    """Salus — cUAS site coverage simulation tool."""


@main.command()
@click.option(
    "--dem",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to DEM GeoTIFF.",
)
@click.option(
    "--x",
    "observer_x",
    required=True,
    type=float,
    help="Observer easting in CRS units (m).",
)
@click.option(
    "--y",
    "observer_y",
    required=True,
    type=float,
    help="Observer northing in CRS units (m).",
)
@click.option(
    "--height",
    default=2.0,
    show_default=True,
    type=float,
    help="Observer height above ground (m).",
)
@click.option(
    "--range",
    "max_range",
    default=None,
    type=float,
    help="Maximum analysis range (m). Default: full extent.",
)
@click.option(
    "--output",
    default="coverage.png",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Output PNG path.",
)
@click.option(
    "--title",
    default="Coverage Map",
    show_default=True,
    help="Map title.",
)
def viewshed(
    dem: str,
    observer_x: float,
    observer_y: float,
    height: float,
    max_range: float | None,
    output: str,
    title: str,
) -> None:
    """Compute a viewshed from an observer position and render a coverage map.

    Example:

        salus viewshed --dem site.tif --x 500100 --y 6100150 --height 10 --output map.png
    """
    dem_path = Path(dem)
    output_path = Path(output)

    if output_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf"):
        click.echo(
            f"Warning: unrecognised output extension '{output_path.suffix}' — will attempt anyway.",
            err=True,
        )

    click.echo(f"Loading DEM: {dem_path}")
    try:
        site = load_dem(dem_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error loading DEM: {exc}", err=True)
        sys.exit(1)

    crs_info = f", EPSG:{site.crs_epsg}" if site.crs_epsg else ""
    click.echo(
        f"DEM loaded: {site.rows}×{site.cols} cells at {site.resolution:.1f} m resolution{crs_info}"
    )

    min_x, max_x, min_y, max_y = site.extent
    if not (min_x <= observer_x <= max_x and min_y <= observer_y <= max_y):
        click.echo(
            f"Error: observer ({observer_x}, {observer_y}) is outside DEM extent "
            f"({min_x:.0f}–{max_x:.0f} E, {min_y:.0f}–{max_y:.0f} N).",
            err=True,
        )
        sys.exit(1)

    range_info = f", range={max_range} m" if max_range else ""
    click.echo(
        f"Computing viewshed from ({observer_x}, {observer_y}), height={height} m{range_info}"
    )
    try:
        coverage = compute_viewshed(
            site, observer_x, observer_y, observer_height=height, max_range=max_range
        )
    except Exception as exc:
        click.echo(f"Error computing viewshed: {exc}", err=True)
        sys.exit(1)

    if coverage.size == 0:
        click.echo("Error: viewshed returned an empty array — DEM may be degenerate.", err=True)
        sys.exit(1)

    pct = coverage.sum() / coverage.size * 100
    click.echo(f"Viewshed complete: {pct:.1f}% of cells visible")

    click.echo(f"Rendering map → {output_path}")
    try:
        render_coverage_map(
            site,
            coverage,
            output_path,
            title=title,
            sensor_positions=[(observer_x, observer_y)],
        )
    except Exception as exc:
        click.echo(f"Error rendering map: {exc}", err=True)
        if output_path.exists():
            output_path.unlink()
        sys.exit(1)

    click.echo(f"Done. Output: {output_path.resolve()}")


@main.command()
@click.argument("scenario", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--sensors",
    "sensor_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help=(
        "Directory containing sensor YAML definition files. "
        "Defaults to the bundled sensor database."
    ),
)
@click.option(
    "--threats",
    "threat_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help=(
        "Directory containing threat profile YAML files. Defaults to the bundled threat database."
    ),
)
@click.option(
    "--output-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory for coverage PNG outputs. Created automatically if it does not exist.",
)
@click.option(
    "--segment-length",
    "segment_length",
    default=None,
    type=float,
    help=(
        "Sampling interval in metres for trajectory analysis. "
        "Overrides sweep_segment_length_m from the scenario file."
    ),
)
@click.option(
    "--adversarial",
    "adversarial",
    is_flag=True,
    default=False,
    help=(
        "Run adversarial path planning: discover the minimum-detection-exposure route "
        "from origin to the protected asset using Dijkstra's algorithm on a 3D cost grid."
    ),
)
@click.option(
    "--saturation",
    "saturation",
    is_flag=True,
    default=False,
    help=(
        "Run multi-target saturation analysis: determine the simultaneous-threat count "
        "at which the effector network becomes overwhelmed."
    ),
)
@click.option(
    "--origin",
    "origin",
    default=None,
    type=(float, float),
    metavar="X Y",
    help=(
        "Adversarial origin coordinates (easting northing). "
        "Required when --adversarial is set and no corridor results are available. "
        "If omitted, origin is inferred from the worst-approach corridor."
    ),
)
def simulate(
    scenario: str,
    sensor_dir: str | None,
    threat_dir: str | None,
    output_dir: str,
    segment_length: float | None,
    adversarial: bool,
    origin: tuple[float, float] | None,
    saturation: bool,
) -> None:
    """Compute sensor-clipped coverage maps from a scenario YAML file.

    Loads the scenario, loads the DEM, and for each LOS-requiring sensor
    placement computes a viewshed clipped to the sensor's range and azimuth,
    then renders a per-sensor coverage PNG.

    Non-LOS sensors (RF, acoustic) are skipped — they do not require terrain
    analysis.

    If the scenario defines threat_profiles and a protected_point, corridor
    analysis is run after the composite coverage is built.

    Example:

        salus simulate scenario.yaml --output-dir results/
    """
    scenario_path = Path(scenario)
    output_path = Path(output_dir)

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        click.echo(f"Error: cannot create output directory {output_path}: {exc}", err=True)
        sys.exit(1)
    if not output_path.is_dir():
        click.echo(f"Error: output path is not a directory: {output_path}", err=True)
        sys.exit(1)

    # Load scenario
    click.echo(f"Loading scenario: {scenario_path}")
    try:
        sc = load_scenario(scenario_path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error loading scenario: {exc}", err=True)
        sys.exit(1)

    # Resolve sensor definitions directory
    effective_sensor_dir: Path = Path(sensor_dir) if sensor_dir is not None else _DEFAULT_SENSOR_DIR

    click.echo(f"Loading sensor definitions: {effective_sensor_dir}")
    try:
        sensor_defs = load_sensors(effective_sensor_dir)
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        click.echo(f"Error loading sensor definitions: {exc}", err=True)
        sys.exit(1)

    if not sensor_defs:
        click.echo(f"Error: no sensor definitions found in {effective_sensor_dir}.", err=True)
        sys.exit(1)

    sensor_map: dict[str, SensorDefinition] = {s.name: s for s in sensor_defs}

    # Load DEM (and optional DSM)
    click.echo(f"Loading DEM: {sc.site_dem_path}")
    try:
        site = load_dem(sc.site_dem_path, dsm_path=sc.site_dsm_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error loading DEM: {exc}", err=True)
        sys.exit(1)

    crs_info = f", EPSG:{site.crs_epsg}" if site.crs_epsg else ""
    click.echo(
        f"DEM loaded: {site.rows}×{site.cols} cells at {site.resolution:.1f} m resolution{crs_info}"
    )

    if not sc.sensor_placements:
        click.echo("No sensor placements in scenario — nothing to simulate.")
        sys.exit(0)

    failed = 0
    rendered = 0

    for placement in sc.sensor_placements:
        sensor = sensor_map.get(placement.sensor_name)

        if sensor is None:
            click.echo(
                f"  Warning: sensor '{placement.sensor_name}' not found in definitions — skipping.",
                err=True,
            )
            failed += 1
            continue

        if not sensor.requires_los:
            click.echo(
                f"  [{placement.sensor_name}] Skipping — non-LOS sensor"
                " (no terrain analysis needed)."
            )
            continue

        observer_height = (
            placement.height_override_m
            if placement.height_override_m is not None
            else sensor.mounting_height_m
        )

        click.echo(
            f"  [{placement.sensor_name}] Computing viewshed from "
            f"({placement.position_x:.1f}, {placement.position_y:.1f}), "
            f"height={observer_height:.1f} m"
        )

        try:
            raw_viewshed = compute_viewshed(
                site,
                placement.position_x,
                placement.position_y,
                observer_height=observer_height,
                max_range=sensor.max_range_m,
            )
        except Exception as exc:
            click.echo(f"  [{placement.sensor_name}] Error computing viewshed: {exc}", err=True)
            failed += 1
            continue

        try:
            clipped = clip_viewshed_to_sensor(raw_viewshed, site, sensor, placement)
        except Exception as exc:
            click.echo(f"  [{placement.sensor_name}] Error clipping viewshed: {exc}", err=True)
            failed += 1
            continue

        if clipped.size == 0:
            click.echo(f"  [{placement.sensor_name}] Error: clipped viewshed is empty.", err=True)
            failed += 1
            continue

        pct = clipped.sum() / clipped.size * 100
        click.echo(f"  [{placement.sensor_name}] Coverage: {pct:.1f}%")

        safe_name = _safe_filename(placement.sensor_name)
        output_file = output_path / f"{safe_name}_coverage.png"

        try:
            render_coverage_map(
                site,
                clipped,
                output_file,
                title=f"{placement.sensor_name} — Coverage",
                sensor_positions=[(placement.position_x, placement.position_y)],
            )
        except Exception as exc:
            click.echo(f"  [{placement.sensor_name}] Error rendering map: {exc}", err=True)
            try:
                output_file.unlink(missing_ok=True)
            except OSError as unlink_exc:
                click.echo(
                    f"  [{placement.sensor_name}] Warning: could not remove partial output:"
                    f" {unlink_exc}",
                    err=True,
                )
            failed += 1
            continue

        click.echo(f"  → {output_file}")
        rendered += 1

    # -------------------------------------------------------------------------
    # Multi-sensor analysis pipeline (S5-6)
    # Build placements_by_type from all valid placements (LOS + non-LOS).
    # -------------------------------------------------------------------------
    placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]] = {}
    for placement in sc.sensor_placements:
        sensor = sensor_map.get(placement.sensor_name)
        if sensor is None:
            continue  # already warned in per-sensor loop above
        stype = sensor.type
        if stype not in placements_by_type:
            placements_by_type[stype] = []
        placements_by_type[stype].append((sensor, placement))

    if not placements_by_type:
        if rendered == 0 and failed == 0:
            click.echo("No sensor placements in scenario — nothing to simulate.")
        elif failed:
            click.echo(f"Completed with {failed} error(s).", err=True)
            sys.exit(1)
        else:
            click.echo(f"Done. {rendered} coverage map(s) written to {output_path.resolve()}")
        sys.exit(0)

    click.echo("\nRunning multi-sensor coverage analysis…")
    try:
        layer_coverages = compute_layer_coverage(site, placements_by_type)
    except Exception as exc:
        click.echo(f"Error computing layer coverages: {exc}", err=True)
        sys.exit(1)

    if not layer_coverages:  # D-117: explicit guard before composite
        click.echo(
            "Error: no coverage arrays were produced — check that sensor types are supported.",
            err=True,
        )
        sys.exit(1)

    try:
        composite = compute_composite_coverage(layer_coverages)
    except Exception as exc:
        click.echo(f"Error computing composite coverage: {exc}", err=True)
        sys.exit(1)

    # Boundary mask — use scenario boundary if present, otherwise full DEM.
    loaded_boundary = None
    if sc.boundary_path is not None:
        click.echo(f"  Loading boundary: {sc.boundary_path}")
        try:
            loaded_boundary = load_boundary(sc.boundary_path, site_epsg=site.crs_epsg)
            bitmask = boundary_mask(site, loaded_boundary)
        except Exception as exc:  # D-116: boundary failure is a hard error
            click.echo(f"Error loading boundary: {exc}", err=True)
            sys.exit(1)
    else:
        bitmask = np.ones((site.rows, site.cols), dtype=bool)

    try:
        gaps = compute_gaps(composite, bitmask)
    except Exception as exc:
        click.echo(f"Error computing gaps: {exc}", err=True)
        sys.exit(1)

    try:
        stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)
    except Exception as exc:
        click.echo(f"Error computing coverage statistics: {exc}", err=True)
        sys.exit(1)

    # Print summary statistics.
    click.echo("\nCoverage Summary")
    click.echo("─" * 40)
    click.echo(f"  Total coverage:          {stats.total_coverage_pct:.1f}%")
    click.echo(f"  Gap area:                {stats.gap_area_m2:,.0f} m²")
    click.echo(f"  Largest contiguous gap:  {stats.largest_contiguous_gap_m2:,.0f} m²")
    for stype, pct in stats.per_layer_coverage_pct.items():
        click.echo(f"  [{stype.value}] layer:      {pct:.1f}%")
    for zone_name, pct in stats.per_zone_coverage_pct.items():
        click.echo(f"  Zone '{zone_name}':       {pct:.1f}%")

    # Render multi-sensor maps.
    # D-118: validate array sizes before rendering to prevent silent multi-map degradation
    for stype, arr in layer_coverages.items():
        if arr.size == 0:
            click.echo(
                f"Error: coverage array for {stype.value} has zero elements — cannot render maps.",
                err=True,
            )
            sys.exit(1)

    click.echo("\nRendering coverage maps…")
    sensor_positions = [  # D-119: only positions of sensors that exist in sensor_map
        (p.position_x, p.position_y)
        for p in sc.sensor_placements
        if sensor_map.get(p.sensor_name) is not None
    ]

    try:
        layer_paths = render_layer_coverage_maps(
            site,
            layer_coverages,
            output_path / "layers",
            sensor_positions=sensor_positions,
            boundary=loaded_boundary,
            zones=site.zones or None,
        )
        for path in layer_paths.values():
            click.echo(f"  → {path}")
    except Exception as exc:
        click.echo(f"  Warning: could not render layer maps: {exc}", err=True)

    composite_out = output_path / "composite.png"
    try:
        render_composite_coverage_map(
            site,
            layer_coverages,
            composite_out,
            sensor_positions=sensor_positions,
            boundary=loaded_boundary,
            zones=site.zones or None,
        )
        click.echo(f"  → {composite_out}")
    except Exception as exc:
        click.echo(f"  Warning: could not render composite map: {exc}", err=True)

    gap_out = output_path / "gaps.png"
    try:
        render_gap_map(
            site,
            composite,
            gaps,
            gap_out,
            sensor_positions=sensor_positions,
            boundary=loaded_boundary,
            zones=site.zones or None,
        )
        click.echo(f"  → {gap_out}")
    except Exception as exc:
        click.echo(f"  Warning: could not render gap map: {exc}", err=True)

    redundancy_out = output_path / "redundancy.png"
    try:
        render_redundancy_map(
            site,
            stats.redundancy_map,
            redundancy_out,
            sensor_positions=sensor_positions,
            boundary=loaded_boundary,
            zones=site.zones or None,
        )
        click.echo(f"  → {redundancy_out}")
    except Exception as exc:
        click.echo(f"  Warning: could not render redundancy map: {exc}", err=True)

    # -------------------------------------------------------------------------
    # Threat corridor analysis (S6-5)
    # Run only when threat_profiles are listed in the scenario AND a
    # protected_point is defined.
    # -------------------------------------------------------------------------
    corridor_failed = False
    if sc.threat_profiles and sc.protected_point is not None:
        effective_threat_dir: Path = (
            Path(threat_dir) if threat_dir is not None else _DEFAULT_THREAT_DIR
        )
        click.echo("\nRunning threat corridor analysis…")
        click.echo(f"  Threat directory: {effective_threat_dir}")
        load_failed = False
        try:
            all_threats = load_threats(effective_threat_dir)
        except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
            click.echo(
                f"  Warning: could not load threat definitions from {effective_threat_dir}: {exc}",
                err=True,
            )
            all_threats = []
            load_failed = True

        threat_map = {t.name: t for t in all_threats}
        matched_threats = []
        for name in sc.threat_profiles:
            threat = threat_map.get(name)
            if threat is None:
                if not load_failed:
                    click.echo(
                        f"  Warning: threat '{name}' not found in "
                        f"{effective_threat_dir} — skipping.",
                        err=True,
                    )
            else:
                matched_threats.append(threat)

        if not matched_threats and not load_failed:
            click.echo(
                "  Warning: no matching threat profiles found — skipping corridor analysis.",
                err=True,
            )

        all_pairs = [pair for pairs in placements_by_type.values() for pair in pairs]
        # D-158: use a distinct name to avoid shadowing the coverage-map sensor_positions above.
        threat_sensor_positions = [(p.position_x, p.position_y) for _, p in all_pairs]

        for threat in matched_threats:
            click.echo(f"\n  Threat: {threat.name}")
            safe_threat = _safe_filename(threat.name)

            if sc.trajectory is not None:
                # ── Engagement calc mode ──────────────────────────────────────
                # A specific trajectory is provided: analyse it and render a
                # trajectory map.  Corridor overlay/polar are not produced.
                effective_seg_len = (
                    segment_length if segment_length is not None else sc.sweep_segment_length_m
                )
                try:
                    traj_result = analyse_trajectory(
                        site,
                        all_pairs,
                        sc.trajectory,
                        segment_length_m=effective_seg_len,
                    )
                except Exception as exc:
                    click.echo(
                        f"  Warning: trajectory analysis failed for '{threat.name}': {exc}",
                        err=True,
                    )
                    corridor_failed = True
                    continue

                # Print trajectory result summary
                click.echo(f"  Time to asset:        {traj_result.time_to_asset_s:.1f} s")
                click.echo(f"  Time in detection:    {traj_result.time_in_detection_s:.1f} s")
                click.echo(f"  Time undetected:      {traj_result.time_undetected_s:.1f} s")
                click.echo(f"  Asset reached undetected: {traj_result.asset_reached_undetected}")
                if traj_result.first_detection is not None:
                    first_ev = traj_result.first_detection
                    click.echo(
                        f"  First detection:      {first_ev.sensor_name} "
                        f"at {first_ev.time_s:.1f} s "
                        f"({first_ev.position_x:.0f}, {first_ev.position_y:.0f})"
                    )
                else:
                    click.echo("  First detection:      none")

                traj_map_out = output_path / f"trajectory_{safe_threat}_map.png"
                try:
                    render_trajectory_map(
                        site,
                        composite,
                        [(sc.trajectory, traj_result)],
                        sc.protected_point,
                        traj_map_out,
                        title=f"Trajectory Analysis — {threat.name}",
                        sensor_positions=threat_sensor_positions,
                    )
                    click.echo(f"  → {traj_map_out}")
                except Exception as exc:
                    click.echo(f"  Warning: could not render trajectory map: {exc}", err=True)

            else:
                # ── Planning sweep mode ───────────────────────────────────────
                # No specific trajectory: run corridor sweep (for backward-
                # compatible overlay/polar outputs) and additionally run the
                # worst-trajectory sweep using scenario sweep parameters.
                try:
                    results = find_worst_corridors(site, all_pairs, threat, sc.protected_point)
                except Exception as exc:
                    click.echo(
                        f"  Warning: corridor analysis failed for '{threat.name}': {exc}",
                        err=True,
                    )
                    corridor_failed = True
                    continue

                header = f"  {'Bearing':>8}  {'Coverage':>10}  {'First detect':>14}"
                click.echo(header)
                click.echo(f"  {'─' * 8}  {'─' * 10}  {'─' * 14}")
                for r in results[:5]:
                    fd = (
                        f"{r.first_detection_distance_m:.0f} m"
                        if r.first_detection_distance_m is not None
                        else "none"
                    )
                    click.echo(
                        f"  {r.corridor.bearing_deg:>7.1f}°  {r.coverage_pct:>9.1f}%  {fd:>14}"
                    )
                if len(results) > 5:
                    click.echo(f"  … {len(results) - 5} more corridors (worst shown first)")

                overlay_out = output_path / f"corridor_{safe_threat}_overlay.png"
                polar_out = output_path / f"corridor_{safe_threat}_polar.png"

                try:
                    render_corridor_overlay_map(
                        site,
                        composite,
                        results,
                        sc.protected_point,
                        overlay_out,
                        title=f"Corridor Analysis — {threat.name}",
                    )
                    click.echo(f"  → {overlay_out}")
                except Exception as exc:
                    click.echo(f"  Warning: could not render corridor overlay: {exc}", err=True)

                try:
                    render_corridor_polar_diagram(
                        results,
                        polar_out,
                        title=f"Coverage by Bearing — {threat.name}",
                    )
                    click.echo(f"  → {polar_out}")
                except Exception as exc:
                    click.echo(f"  Warning: could not render polar diagram: {exc}", err=True)

                # Worst-trajectory sweep using scenario sweep parameters.
                effective_seg_len = (
                    segment_length if segment_length is not None else sc.sweep_segment_length_m
                )
                try:
                    worst_traj_results = find_worst_trajectories(
                        site,
                        all_pairs,
                        threat,
                        sc.protected_point,
                        altitudes_m=sc.sweep_altitudes_m,
                        dive_angles_deg=sc.sweep_dive_angles_deg,
                        segment_length_m=effective_seg_len,
                    )
                    if worst_traj_results:
                        click.echo(
                            f"\n  Worst-trajectory sweep "
                            f"({len(worst_traj_results)} result(s), least covered first):"
                        )
                        sweep_header = (
                            f"  {'Time in detect':>15}  {'Time to asset':>14}  {'Undetected':>12}"
                        )
                        click.echo(sweep_header)
                        click.echo(f"  {'─' * 15}  {'─' * 14}  {'─' * 12}")
                        for wt in worst_traj_results[:5]:
                            click.echo(
                                f"  {wt.time_in_detection_s:>14.1f}s  "
                                f"{wt.time_to_asset_s:>13.1f}s  "
                                f"{wt.time_undetected_s:>11.1f}s"
                            )
                        if len(worst_traj_results) > 5:
                            click.echo(f"  … {len(worst_traj_results) - 5} more trajectories")
                except Exception as exc:
                    click.echo(
                        f"  Warning: worst-trajectory sweep failed for '{threat.name}': {exc}",
                        err=True,
                    )
                    corridor_failed = True  # D-156: propagate sweep failure to exit code

            # ── Adversarial path planning (optional, --adversarial flag) ─────
            if adversarial:
                click.echo(f"\n  Running adversarial path planner for '{threat.name}'…")
                try:
                    # Determine threat origin:
                    # (a) use --origin coordinates if provided, or
                    # (b) infer from worst corridor bearing at typical_altitude_m.
                    if origin is not None:
                        adv_ox, adv_oy = origin
                        adv_oz = threat.typical_altitude_m
                    else:
                        # Derive origin from worst corridor (lowest coverage_pct)
                        try:
                            worst_results = find_worst_corridors(
                                site, all_pairs, threat, sc.protected_point
                            )
                        except Exception as origin_exc:
                            click.echo(
                                f"  Warning: corridor sweep for origin inference failed:"
                                f" {origin_exc}. Using site-centre fallback.",
                                err=True,
                            )
                            worst_results = []
                        if worst_results:
                            worst_r = worst_results[0]
                            bearing_rad = math.radians(worst_r.corridor.bearing_deg)
                            dist = worst_r.corridor.start_distance_m
                            # Origin is start_distance_m from asset in reverse bearing direction
                            adv_ox = sc.protected_point[0] - math.sin(bearing_rad) * dist
                            adv_oy = sc.protected_point[1] - math.cos(bearing_rad) * dist
                            adv_oz = threat.typical_altitude_m
                        else:
                            # Fallback: place origin north of the site extent
                            _, _, min_y_ext, max_y_ext = site.extent
                            min_x_ext, max_x_ext, _, _ = site.extent
                            adv_ox = (min_x_ext + max_x_ext) / 2.0
                            adv_oy = max_y_ext - site.resolution
                            adv_oz = threat.typical_altitude_m

                    click.echo(f"  Origin: ({adv_ox:.0f}, {adv_oy:.0f}) at {adv_oz:.0f} m AGL")

                    adv_cost_grid = build_detection_cost_grid(site, all_pairs)
                    adv_traj = find_adversarial_trajectory(
                        site,
                        adv_cost_grid,
                        adv_ox,
                        adv_oy,
                        adv_oz,
                        sc.protected_point[0],
                        sc.protected_point[1],
                        speed_ms=threat.max_speed_ms,
                    )
                    effective_seg_len_adv: float = (
                        segment_length if segment_length is not None else sc.sweep_segment_length_m
                    )
                    adv_result = analyse_trajectory(
                        site,
                        all_pairs,
                        adv_traj,
                        segment_length_m=effective_seg_len_adv,
                    )

                    click.echo(
                        f"  Adversarial path: {len(adv_traj.waypoints)} waypoints, "
                        f"{adv_result.time_to_asset_s:.1f}s to asset"
                    )
                    click.echo(
                        f"  Time in detection:    {adv_result.time_in_detection_s:.1f}s / "
                        f"{adv_result.time_to_asset_s:.1f}s total"
                    )
                    click.echo(f"  Asset reached undetected: {adv_result.asset_reached_undetected}")

                    adv_map_out = output_path / f"adversarial_{safe_threat}_map.png"
                    render_adversarial_map(
                        site,
                        composite,
                        adv_cost_grid,
                        adv_traj,
                        adv_result,
                        sc.protected_point,
                        adv_map_out,
                        title=f"Adversarial Path — {threat.name}",
                        sensor_positions=threat_sensor_positions,
                    )
                    click.echo(f"  → {adv_map_out}")
                except Exception as exc:
                    click.echo(
                        f"  Warning: adversarial path planning failed for '{threat.name}': {exc}",
                        err=True,
                    )
                    corridor_failed = True

    elif sc.threat_profiles and sc.protected_point is None:
        click.echo(
            "\nNote: threat_profiles specified in scenario but no protected_point defined "
            "— skipping corridor analysis.",
            err=True,
        )
        if adversarial:
            click.echo(
                "Note: --adversarial requires a protected_point in the scenario — skipped.",
                err=True,
            )
    elif adversarial and (not sc.threat_profiles or sc.protected_point is None):
        click.echo(
            "Note: --adversarial requires threat_profiles and a protected_point "
            "in the scenario — skipped.",
            err=True,
        )

    # -------------------------------------------------------------------------
    # Saturation analysis (S8) — --saturation flag or scenario has scenarios.
    # -------------------------------------------------------------------------
    saturation_failed = False
    run_saturation = saturation or bool(sc.saturation_scenarios)

    if run_saturation and sc.protected_point is not None and sc.effector_placements:
        effective_threat_dir_sat: Path = (
            Path(threat_dir) if threat_dir is not None else _DEFAULT_THREAT_DIR
        )
        try:
            all_threats_sat = load_threats(effective_threat_dir_sat)
        except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
            click.echo(
                f"  Warning: could not load threat definitions for saturation analysis: {exc}",
                err=True,
            )
            all_threats_sat = []

        threat_map_sat = {t.name: t for t in all_threats_sat}

        # Load effector definitions — use the sensor dir as a peer directory.
        effector_dir_sat = effective_sensor_dir.parent / "effectors"
        try:
            from salus.ingest.sensors import load_effectors

            effector_defs = load_effectors(effector_dir_sat)
        except (FileNotFoundError, AttributeError, OSError):
            effector_defs = []

        effector_def_map = {e.name: e for e in effector_defs}

        # Resolve placed effector definitions.
        placed_effectors = [
            effector_def_map[p.effector_name]
            for p in sc.effector_placements
            if p.effector_name in effector_def_map
        ]

        if not placed_effectors:
            click.echo(
                "\nNote: --saturation requires effector definitions to be loaded — "
                "no matching effector definitions found, skipping saturation analysis.",
                err=True,
            )
        else:
            click.echo("\nRunning saturation analysis…")

            # Use the first matched threat profile for the threshold sweep.
            sweep_threat = None
            for name in sc.threat_profiles:
                sweep_threat = threat_map_sat.get(name)
                if sweep_threat is not None:
                    break

            if sweep_threat is not None:
                try:
                    sat_result = find_saturation_threshold(
                        placed_effectors,
                        sc.effector_placements,
                        site,
                        sc.protected_point,
                        sweep_threat,
                    )
                    cap = sat_result.simultaneous_engagement_capacity
                    click.echo(f"  Simultaneous engagement capacity: {cap}")
                    thresh = sat_result.saturation_threshold_n
                    click.echo(f"  Saturation threshold:             {thresh} targets")
                    unengaged = sat_result.unengaged_count_at_threshold
                    click.echo(f"  Unengaged at threshold:           {unengaged}")

                    # Build threshold_data for chart (N=1..threshold or max_targets).
                    # capacity is the max N that was fully engaged; threshold = capacity + 1.
                    capacity = sat_result.simultaneous_engagement_capacity
                    threshold_never_reached = (
                        sat_result.saturation_threshold_n > capacity
                        and sat_result.unengaged_count_at_threshold == 0
                    )
                    max_n = min(max(capacity, 1), 20)
                    threshold_data: dict[int, int] = {n: 0 for n in range(1, max_n + 1)}
                    if not threshold_never_reached and sat_result.saturation_threshold_n <= max_n:
                        threshold_data[sat_result.saturation_threshold_n] = (
                            sat_result.unengaged_count_at_threshold
                        )

                    if threshold_never_reached:
                        sat_chart_title = (
                            f"Saturation Threshold — {sweep_threat.name} "
                            f"(not reached within N={max_n})"
                        )
                        sat_threshold_line = max_n + 1  # push axvline off-chart
                    else:
                        sat_chart_title = f"Saturation Threshold — {sweep_threat.name}"
                        sat_threshold_line = sat_result.saturation_threshold_n

                    sat_chart_out = output_path / "saturation_threshold.png"
                    try:
                        render_saturation_threshold_chart(
                            threshold_data,
                            sat_threshold_line,
                            sat_chart_out,
                            title=sat_chart_title,
                        )
                        click.echo(f"  → {sat_chart_out}")
                    except Exception as exc:
                        click.echo(f"  Warning: could not render saturation chart: {exc}", err=True)

                    util_chart_out = output_path / "effector_utilisation.png"
                    if sat_result.per_effector_utilisation:
                        try:
                            render_effector_utilisation_chart(
                                sat_result,
                                util_chart_out,
                                title="Effector Utilisation at Saturation Threshold",
                            )
                            click.echo(f"  → {util_chart_out}")
                        except Exception as exc:
                            click.echo(
                                f"  Warning: could not render utilisation chart: {exc}", err=True
                            )

                except Exception as exc:
                    click.echo(f"  Warning: saturation threshold sweep failed: {exc}", err=True)
                    saturation_failed = True

            # Run explicit saturation scenarios from the scenario YAML.
            for s_idx, sat_scenario in enumerate(sc.saturation_scenarios):
                n_targets = len(sat_scenario.targets)
                click.echo(f"\n  Saturation scenario {s_idx + 1} ({n_targets} targets):")
                try:
                    assert sc.protected_point is not None, (
                        "protected_point is required for saturation scenarios"
                    )
                    alloc = allocate_effectors(
                        sat_scenario.targets,
                        placed_effectors,
                        sc.effector_placements,
                        sat_scenario.priority_rule,
                        site,
                        sc.protected_point,
                    )
                    click.echo(
                        f"    Engaged:   {len(alloc.engaged_indices)}/{len(sat_scenario.targets)}"
                    )
                    click.echo(f"    Unengaged: {len(alloc.unengaged_indices)}")
                    for tgt_idx, eff_name in alloc.assignments.items():
                        click.echo(f"    Target {tgt_idx} → {eff_name}")

                    if len(sat_scenario.targets) > 0:
                        try:
                            reen_result = compute_reengagement_timeline(
                                placed_effectors,
                                sc.effector_placements,
                                site,
                                sc.protected_point,
                                sat_scenario,
                            )
                            click.echo(
                                f"    Re-engagement: {reen_result.total_engagements_possible} "
                                f"engagements in {reen_result.window_s:.0f}s window"
                            )
                        except Exception as exc:
                            click.echo(
                                f"    Warning: re-engagement timeline failed: {exc}", err=True
                            )
                except Exception as exc:
                    click.echo(
                        f"  Warning: saturation scenario {s_idx + 1} failed: {exc}", err=True
                    )
                    saturation_failed = True

    elif run_saturation and (sc.protected_point is None or not sc.effector_placements):
        click.echo(
            "\nNote: --saturation requires a protected_point and effector_placements "
            "in the scenario — skipped.",
            err=True,
        )

    if failed or corridor_failed or saturation_failed:
        msg_parts = []
        if failed:
            msg_parts.append(f"{failed} sensor error(s)")
        if corridor_failed:
            msg_parts.append("corridor analysis error(s)")
        if saturation_failed:
            msg_parts.append("saturation analysis error(s)")
        click.echo(f"\nCompleted with {', '.join(msg_parts)}.", err=True)
        sys.exit(1)

    click.echo(f"\nDone. Output written to {output_path.resolve()}")


@main.command()
@click.argument("scenario", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--sensor",
    "sensor_names",
    multiple=True,
    required=True,
    help=(
        "Name of a sensor to place (repeatable). Each occurrence represents one sensor "
        "to optimise. Use the option multiple times to place more than one sensor, "
        "e.g. --sensor EchoGuard --sensor EchoGuard --sensor RfOne."
    ),
)
@click.option(
    "--sensors",
    "sensor_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing sensor YAML definition files. Defaults to the bundled database.",
)
@click.option(
    "--step",
    default=50.0,
    show_default=True,
    type=float,
    help="Candidate grid spacing in metres. Smaller values improve result quality at higher cost.",
)
@click.option(
    "--coverage-threshold",
    default=100.0,
    show_default=True,
    type=float,
    help="Stop placing sensors once this weighted coverage percentage is reached.",
)
@click.option(
    "--output-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory to write the optimised placement coverage map. Created if absent.",
)
@click.option(
    "--write-scenario",
    default=None,
    type=click.Path(dir_okay=False),
    help=(
        "Path to write an updated scenario YAML with the recommended placements "
        "appended to sensor_placements. The original scenario is not modified."
    ),
)
def optimise(
    scenario: str,
    sensor_names: tuple[str, ...],
    sensor_dir: str | None,
    step: float,
    coverage_threshold: float,
    output_dir: str,
    write_scenario: str | None,
) -> None:
    """Suggest sensor placements that maximise zone-weighted coverage.

    Generates a candidate position grid across the site, then greedily places
    each named sensor at the position that covers the most previously-uncovered
    area (weighted by zone: critical_asset=3×, inner=2×, perimeter=1×).

    Example:

        salus optimise scenario.yaml --sensor EchoGuard --sensor RfOne --step 50
    """
    scenario_path = Path(scenario)
    output_path = Path(output_dir)

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        click.echo(f"Error: cannot create output directory {output_path}: {exc}", err=True)
        sys.exit(1)

    # Load scenario
    click.echo(f"Loading scenario: {scenario_path}")
    try:
        sc = load_scenario(scenario_path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error loading scenario: {exc}", err=True)
        sys.exit(1)

    # Load sensor definitions
    effective_sensor_dir: Path = Path(sensor_dir) if sensor_dir is not None else _DEFAULT_SENSOR_DIR
    click.echo(f"Loading sensor definitions: {effective_sensor_dir}")
    try:
        sensor_defs = load_sensors(effective_sensor_dir)
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        click.echo(f"Error loading sensor definitions: {exc}", err=True)
        sys.exit(1)

    sensor_map: dict[str, SensorDefinition] = {s.name: s for s in sensor_defs}

    # Resolve sensor names → SensorDefinition list (in order)
    sensors_to_place: list[SensorDefinition] = []
    for name in sensor_names:
        sensor = sensor_map.get(name)
        if sensor is None:
            click.echo(f"Error: sensor '{name}' not found in {effective_sensor_dir}.", err=True)
            sys.exit(1)
        sensors_to_place.append(sensor)

    # Load DEM
    click.echo(f"Loading DEM: {sc.site_dem_path}")
    try:
        site = load_dem(sc.site_dem_path, dsm_path=sc.site_dsm_path)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error loading DEM: {exc}", err=True)
        sys.exit(1)

    crs_info = f", EPSG:{site.crs_epsg}" if site.crs_epsg else ""
    click.echo(
        f"DEM loaded: {site.rows}×{site.cols} cells at {site.resolution:.1f} m resolution{crs_info}"
    )

    # Load optional boundary
    loaded_boundary = None
    if sc.boundary_path is not None:
        click.echo(f"Loading boundary: {sc.boundary_path}")
        try:
            loaded_boundary = load_boundary(sc.boundary_path, site_epsg=site.crs_epsg)
        except Exception as exc:
            click.echo(f"Error loading boundary: {exc}", err=True)
            sys.exit(1)

    # Collect exclusion zones from the site
    from salus.models.zone import ZoneType

    exclusion_zones = [z for z in site.zones if z.zone_type == ZoneType.exclusion]

    # Generate candidate positions
    click.echo(f"\nGenerating candidate positions (step={step:.1f} m)…")
    try:
        candidates = generate_candidate_positions(
            site=site,
            boundary=loaded_boundary,
            step_m=step,
            exclusion_zones=exclusion_zones,
        )
    except ValueError as exc:
        click.echo(f"Error generating candidates: {exc}", err=True)
        sys.exit(1)

    if not candidates:
        click.echo(
            "Error: no candidate positions generated. "
            "Try a smaller --step or check that the boundary overlaps the DEM.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"  {len(candidates)} candidate position(s) in search space.")

    # Run greedy placement
    click.echo(f"\nRunning greedy placement ({len(sensors_to_place)} sensor(s) to place)…")
    try:
        new_placements = greedy_place_sensors(
            site=site,
            sensors_to_place=sensors_to_place,
            candidates=candidates,
            coverage_threshold_pct=coverage_threshold,
            weights=PlacementWeights(),
        )
    except ValueError as exc:
        click.echo(f"Error during placement: {exc}", err=True)
        sys.exit(1)

    if not new_placements:
        click.echo("Warning: no placements were made.", err=True)
        sys.exit(1)

    # Print placement summary
    click.echo(f"\nOptimised placements ({len(new_placements)}):")
    click.echo("─" * 55)
    for i, p in enumerate(new_placements, start=1):
        click.echo(
            f"  {i:>2}. {p.sensor_name:<30} x={p.position_x:>10.1f}  y={p.position_y:>10.1f}"
        )

    # Render composite coverage map of the placed sensors
    placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]] = {}
    for p in new_placements:
        sensor = sensor_map.get(p.sensor_name)
        if sensor is None:
            continue
        if sensor.type not in placements_by_type:
            placements_by_type[sensor.type] = []
        placements_by_type[sensor.type].append((sensor, p))

    if placements_by_type:
        map_out = output_path / "optimised_coverage.png"
        try:
            layer_coverages = compute_layer_coverage(site, placements_by_type)
            sensor_positions = [(p.position_x, p.position_y) for p in new_placements]
            render_composite_coverage_map(
                site,
                layer_coverages,
                map_out,
                sensor_positions=sensor_positions,
                boundary=loaded_boundary,
                zones=site.zones or None,
            )
            click.echo(f"\n  → Coverage map: {map_out}")
        except Exception as exc:
            click.echo(f"  Warning: could not render coverage map: {exc}", err=True)

    # Optionally write updated scenario YAML
    if write_scenario is not None:
        write_path = Path(write_scenario)
        try:
            with scenario_path.open(encoding="utf-8") as fh:
                raw_scenario: Any = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            click.echo(f"Error reading scenario for rewrite: {exc}", err=True)
            sys.exit(1)

        if not isinstance(raw_scenario, dict):
            click.echo(
                "Error: scenario YAML is not a mapping — cannot write updated file.", err=True
            )
            sys.exit(1)

        serialised_placements = [
            {
                "sensor_name": p.sensor_name,
                "position_x": float(p.position_x),
                "position_y": float(p.position_y),
                "bearing_deg": float(p.bearing_deg),
                **(
                    {"height_override_m": float(p.height_override_m)}
                    if p.height_override_m is not None
                    else {}
                ),
            }
            for p in new_placements
        ]
        # D-182: guard against non-list values (e.g. null, string) in YAML
        _raw_placements = raw_scenario.get("sensor_placements")
        existing: list[Any] = _raw_placements if isinstance(_raw_placements, list) else []
        raw_scenario["sensor_placements"] = existing + serialised_placements

        try:
            write_path.parent.mkdir(parents=True, exist_ok=True)
            with write_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(raw_scenario, fh, default_flow_style=False, sort_keys=False)
            click.echo(f"  → Updated scenario: {write_path.resolve()}")
        except (OSError, yaml.YAMLError) as exc:  # D-183: numpy scalars raise YAMLError
            click.echo(f"Error writing updated scenario: {exc}", err=True)
            sys.exit(1)

    click.echo(f"\nDone. Output written to {output_path.resolve()}")


# ---------------------------------------------------------------------------
# S10 helper — run a single config's coverage pipeline
# ---------------------------------------------------------------------------


def _run_config_simulation(
    scenario_path: Path,
    sensor_dir: Path,
    label: str,
    cost_estimate: float | None,
) -> ConfigurationResult:
    """Load a scenario and run the coverage pipeline, returning a ConfigurationResult.

    Raises:
        SystemExit: On any fatal error (sensor load failure, DEM failure, etc.)
    """
    try:
        sc = load_scenario(scenario_path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error loading scenario '{label}': {exc}", err=True)
        raise SystemExit(1) from exc

    try:
        sensor_defs = load_sensors(sensor_dir)
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        click.echo(f"Error loading sensor definitions for '{label}': {exc}", err=True)
        raise SystemExit(1) from exc

    sensor_map: dict[str, SensorDefinition] = {s.name: s for s in sensor_defs}

    try:
        site = load_dem(sc.site_dem_path, dsm_path=sc.site_dsm_path)
    except Exception as exc:
        click.echo(f"Error loading DEM for '{label}': {exc}", err=True)
        raise SystemExit(1) from exc

    placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]] = {}
    for placement in sc.sensor_placements:
        sensor = sensor_map.get(placement.sensor_name)
        if sensor is None:
            click.echo(
                f"  [{label}] Warning: sensor '{placement.sensor_name}' not found — skipping.",
                err=True,
            )
            continue
        placements_by_type.setdefault(sensor.type, []).append((sensor, placement))

    if not placements_by_type:
        click.echo(f"  [{label}] No valid sensor placements — coverage will be 0%.", err=True)
        from salus.engine.coverage import CoverageStats

        empty = np.zeros((site.rows, site.cols), dtype=bool)
        gap_m2 = float(site.rows * site.cols) * site.resolution**2
        empty_stats = CoverageStats(
            total_coverage_pct=0.0,
            per_layer_coverage_pct={},
            per_zone_coverage_pct={},
            gap_area_m2=gap_m2,
            redundancy_map=np.zeros((site.rows, site.cols), dtype=np.intp),
            largest_contiguous_gap_m2=gap_m2,
        )
        return ConfigurationResult(
            label=label, composite=empty, stats=empty_stats, cost_estimate=cost_estimate
        )

    try:
        layer_coverages = compute_layer_coverage(site, placements_by_type)
        composite = compute_composite_coverage(layer_coverages)
        bitmask = np.ones((site.rows, site.cols), dtype=bool)
        if sc.boundary_path is not None:
            try:
                loaded_boundary = load_boundary(sc.boundary_path, site_epsg=site.crs_epsg)
                bitmask = boundary_mask(site, loaded_boundary)
            except Exception as exc:
                click.echo(
                    f"  [{label}] Warning: boundary load failed ({exc}), using full DEM.",
                    err=True,
                )
                # D-219: also log so non-interactive pipelines capture the event.
                _log.warning(
                    "[%s] Boundary load failed — reverting to full DEM mask: %s",
                    label,
                    exc,
                )
        gaps = compute_gaps(composite, bitmask)
        stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)
    except Exception as exc:
        click.echo(f"Error running coverage pipeline for '{label}': {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(
        f"  [{label}] Coverage: {stats.total_coverage_pct:.1f}% "
        f"({len(sc.sensor_placements)} sensor(s))"
    )
    return ConfigurationResult(
        label=label,
        composite=composite,
        layer_coverages=layer_coverages,
        stats=stats,
        cost_estimate=cost_estimate,
    )


# ---------------------------------------------------------------------------
# S10 — compare command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--config-a",
    "config_a",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Scenario YAML for configuration A.",
)
@click.option(
    "--config-b",
    "config_b",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Scenario YAML for configuration B.",
)
@click.option(
    "--label-a",
    default="Config A",
    show_default=True,
    help="Human-readable label for configuration A.",
)
@click.option(
    "--label-b",
    default="Config B",
    show_default=True,
    help="Human-readable label for configuration B.",
)
@click.option(
    "--sensors",
    "sensor_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Directory of sensor YAML definitions (shared by both configs). Defaults to bundled DB.",
)
@click.option(
    "--output-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory for comparison outputs. Created automatically if absent.",
)
@click.option(
    "--cost-a",
    "cost_a",
    default=None,
    type=float,
    help="Estimated cost of configuration A (any currency unit). Optional.",
)
@click.option(
    "--cost-b",
    "cost_b",
    default=None,
    type=float,
    help="Estimated cost of configuration B (any currency unit). Optional.",
)
def compare(
    config_a: str,
    config_b: str,
    label_a: str,
    label_b: str,
    sensor_dir: str | None,
    output_dir: str,
    cost_a: float | None,
    cost_b: float | None,
) -> None:
    """Compare two sensor configurations against the same site.

    Runs the coverage pipeline for both configurations, then generates:

    \b
    - delta.png           — delta map (green=B gain, red=A loss, grey=both)
    - comparison.png      — grouped bar chart of per-zone coverage A vs B
    - comparison stats    — printed to stdout

    Both scenario files must reference a DEM with the same grid dimensions.

    Example:

        salus compare --config-a base.yaml --config-b enhanced.yaml \\
            --label-a "Baseline" --label-b "Enhanced" --output-dir comparison/
    """
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        click.echo(f"Error: cannot create output directory {output_path}: {exc}", err=True)
        sys.exit(1)

    effective_sensor_dir = Path(sensor_dir) if sensor_dir is not None else _DEFAULT_SENSOR_DIR

    click.echo("Comparing configurations:")
    click.echo(f"  A: {config_a}  ({label_a})")
    click.echo(f"  B: {config_b}  ({label_b})")
    click.echo(f"  Sensor DB: {effective_sensor_dir}")
    click.echo("")

    result_a = _run_config_simulation(Path(config_a), effective_sensor_dir, label_a, cost_a)
    result_b = _run_config_simulation(Path(config_b), effective_sensor_dir, label_b, cost_b)

    # Validate same grid shape.
    if result_a.composite.shape != result_b.composite.shape:
        click.echo(
            f"Error: configuration grids have different shapes: "
            f"{result_a.composite.shape} vs {result_b.composite.shape}. "
            "Both scenarios must reference a DEM with the same dimensions.",
            err=True,
        )
        sys.exit(1)

    try:
        comparison = compare_configs(result_a, result_b)
    except ValueError as exc:
        click.echo(f"Error computing comparison: {exc}", err=True)
        sys.exit(1)

    # Print key metrics.
    sign = "+" if comparison.coverage_delta_pct >= 0 else ""
    click.echo("\nComparison Summary")
    click.echo("─" * 50)
    click.echo(f"  {label_a} coverage:  {comparison.coverage_pct_a:.1f}%")
    click.echo(
        f"  {label_b} coverage:  {comparison.coverage_pct_b:.1f}%  "
        f"({sign}{comparison.coverage_delta_pct:.1f}%)"
    )
    if comparison.cost_delta is not None:
        cost_sign = "+" if comparison.cost_delta >= 0 else ""
        click.echo(f"  Cost delta (B − A): {cost_sign}{comparison.cost_delta:,.0f}")
    if comparison.per_zone_delta_pct:
        click.echo("  Per-zone delta (B − A):")
        for zone, delta in comparison.per_zone_delta_pct.items():
            zs = "+" if delta >= 0 else ""
            click.echo(f"    {zone}: {zs}{delta:.1f}%")

    # Count delta cells.
    from salus.engine.comparison import DELTA_A_ONLY, DELTA_B_ONLY, DELTA_BOTH, DELTA_NEITHER

    n_cells = comparison.delta_grid.size
    n_both = int((comparison.delta_grid == DELTA_BOTH).sum())
    n_a_only = int((comparison.delta_grid == DELTA_A_ONLY).sum())
    n_b_only = int((comparison.delta_grid == DELTA_B_ONLY).sum())
    n_neither = int((comparison.delta_grid == DELTA_NEITHER).sum())
    click.echo(f"\n  Cell breakdown ({n_cells} total):")
    click.echo(f"    Both cover:    {n_both:>7}  ({n_both / n_cells * 100:.1f}%)")
    click.echo(f"    {label_a} only: {n_a_only:>7}  ({n_a_only / n_cells * 100:.1f}%)")
    click.echo(f"    {label_b} only: {n_b_only:>7}  ({n_b_only / n_cells * 100:.1f}%)")
    click.echo(f"    Neither:       {n_neither:>7}  ({n_neither / n_cells * 100:.1f}%)")

    # Render outputs.
    click.echo("\nRendering comparison outputs…")

    # Load site once for all map renders (D-221: avoid double-loading).
    try:
        site = _load_site_for_comparison(Path(config_a))
    except Exception as exc:
        _log.warning("Could not load DEM for map rendering: %s", exc, exc_info=True)
        site = None

    # D-227: guard against DEM/composite shape mismatch before passing to renderers.
    if site is not None and site.dem.shape != comparison.delta_grid.shape:
        _log.warning(
            "DEM shape %s does not match delta grid shape %s — skipping map renders.",
            site.dem.shape,
            comparison.delta_grid.shape,
        )
        site = None

    if site is not None:
        delta_out = output_path / "delta.png"
        try:
            render_delta_map(
                site,
                comparison,
                delta_out,
                title=f"Coverage Delta — {label_a} vs {label_b}",
            )
            click.echo(f"  → {delta_out}")
        except Exception as exc:
            # D-220: log with traceback so non-interactive pipelines capture it.
            _log.warning("Delta map rendering failed: %s", exc, exc_info=True)
            click.echo(f"  Warning: delta map failed: {exc}", err=True)

        side_by_side_out = output_path / "side_by_side.png"
        try:
            render_side_by_side_coverage_maps(
                site,
                comparison,
                side_by_side_out,
                title=f"Coverage Comparison — {label_a} vs {label_b}",
            )
            click.echo(f"  → {side_by_side_out}")
        except Exception as exc:
            _log.warning("Side-by-side map rendering failed: %s", exc, exc_info=True)
            click.echo(f"  Warning: side-by-side map failed: {exc}", err=True)

    comparison_out = output_path / "comparison.png"
    try:
        render_coverage_comparison_chart(
            comparison,
            comparison_out,
            title=f"Coverage Comparison — {label_a} vs {label_b}",
        )
        click.echo(f"  → {comparison_out}")
    except Exception as exc:
        _log.warning("Comparison chart rendering failed: %s", exc, exc_info=True)
        click.echo(f"  Warning: comparison chart failed: {exc}", err=True)

    stats_out = output_path / "statistics.png"
    try:
        render_comparison_statistics_table(
            comparison,
            stats_out,
            title=f"Statistics — {label_a} vs {label_b}",
        )
        click.echo(f"  → {stats_out}")
    except Exception as exc:
        _log.warning("Statistics table rendering failed: %s", exc, exc_info=True)
        click.echo(f"  Warning: statistics table failed: {exc}", err=True)

    click.echo(f"\nDone. Output written to {output_path.resolve()}")


def _load_site_for_comparison(scenario_path: Path) -> "SiteModel":
    """Load the DEM from a scenario file for map rendering.

    Raises:
        FileNotFoundError: If the scenario file or DEM path does not exist.
        ValueError: If the scenario file cannot be parsed.
        OSError: If the DEM file cannot be opened.
    """
    try:
        sc = load_scenario(scenario_path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise type(exc)(
            f"Failed to load scenario '{scenario_path}' for delta map rendering: {exc}"
        ) from exc
    try:
        return load_dem(sc.site_dem_path, dsm_path=sc.site_dsm_path)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        # D-221: include ValueError/RuntimeError for rasterio decode failures.
        raise type(exc)(
            f"Failed to load DEM '{sc.site_dem_path}' for delta map rendering: {exc}"
        ) from exc
