"""Salus CLI entry point."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click
import numpy as np

from salus.engine.coverage import (
    boundary_mask,
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
)
from salus.engine.threat_corridor import find_worst_corridors
from salus.engine.viewshed import clip_viewshed_to_sensor, compute_viewshed
from salus.ingest.boundaries import load_boundary
from salus.ingest.scenario import load_scenario
from salus.ingest.sensors import load_sensors, load_threats
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.report.maps import (
    render_composite_coverage_map,
    render_corridor_overlay_map,
    render_corridor_polar_diagram,
    render_coverage_map,
    render_gap_map,
    render_layer_coverage_maps,
    render_redundancy_map,
)

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
def simulate(
    scenario: str,
    sensor_dir: str | None,
    threat_dir: str | None,
    output_dir: str,
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

        for threat in matched_threats:
            click.echo(f"\n  Threat: {threat.name}")
            try:
                all_pairs = [pair for pairs in placements_by_type.values() for pair in pairs]
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
                click.echo(f"  {r.corridor.bearing_deg:>7.1f}°  {r.coverage_pct:>9.1f}%  {fd:>14}")
            if len(results) > 5:
                click.echo(f"  … {len(results) - 5} more corridors (worst shown first)")

            safe_threat = _safe_filename(threat.name)
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

    elif sc.threat_profiles and sc.protected_point is None:
        click.echo(
            "\nNote: threat_profiles specified in scenario but no protected_point defined "
            "— skipping corridor analysis.",
            err=True,
        )

    if failed or corridor_failed:
        msg_parts = []
        if failed:
            msg_parts.append(f"{failed} sensor error(s)")
        if corridor_failed:
            msg_parts.append("corridor analysis error(s)")
        click.echo(f"\nCompleted with {', '.join(msg_parts)}.", err=True)
        sys.exit(1)

    click.echo(f"\nDone. Output written to {output_path.resolve()}")
