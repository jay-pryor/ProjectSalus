"""Salus CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from salus.engine.viewshed import compute_viewshed
from salus.ingest.terrain import load_dem
from salus.report.maps import render_coverage_map


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
