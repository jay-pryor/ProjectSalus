"""Salus CLI entry point."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from salus.engine.viewshed import clip_viewshed_to_sensor, compute_viewshed
from salus.ingest.scenario import load_scenario
from salus.ingest.sensors import load_sensors
from salus.ingest.terrain import load_dem
from salus.models.sensor import SensorDefinition
from salus.report.maps import render_coverage_map

# Bundled sensor definitions shipped with the package.
_DEFAULT_SENSOR_DIR: Path = Path(__file__).parent / "data" / "sensors"


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
    "--output-dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory for per-sensor coverage PNG outputs. Must exist.",
)
def simulate(
    scenario: str,
    sensor_dir: str | None,
    output_dir: str,
) -> None:
    """Compute sensor-clipped coverage maps from a scenario YAML file.

    Loads the scenario, loads the DEM, and for each LOS-requiring sensor
    placement computes a viewshed clipped to the sensor's range and azimuth,
    then renders a per-sensor coverage PNG.

    Non-LOS sensors (RF, acoustic) are skipped — they do not require terrain
    analysis.

    Example:

        salus simulate scenario.yaml --output-dir results/
    """
    scenario_path = Path(scenario)
    output_path = Path(output_dir)

    if not output_path.exists():
        click.echo(f"Error: output directory does not exist: {output_path}", err=True)
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

    if rendered == 0 and failed == 0:
        click.echo("No LOS sensor placements processed.")
        sys.exit(0)

    if failed:
        click.echo(f"Completed with {failed} error(s).", err=True)
        sys.exit(1)

    click.echo(f"Done. {rendered} coverage map(s) written to {output_path.resolve()}")
