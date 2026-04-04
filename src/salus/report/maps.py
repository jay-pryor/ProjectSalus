"""Map rendering — coverage maps, gap maps, and site overview maps."""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.colors import ListedColormap, Normalize
from shapely.geometry import MultiPolygon, Polygon

from salus.engine.path_planner import DetectionCostGrid
from salus.engine.threat_corridor import CorridorResult
from salus.engine.trajectory import TrajectoryResult
from salus.models.sensor import SensorType
from salus.models.site import SiteModel
from salus.models.threat import DroneTrajectory
from salus.models.zone import Zone, ZoneType

if TYPE_CHECKING:
    from salus.engine.comparison import ComparisonResult

# Distinct colour per sensor type for per-layer and composite maps
_SENSOR_TYPE_COLOURS: dict[SensorType, str] = {
    SensorType.Radar: "#3498db",  # blue
    SensorType.EO_IR: "#9b59b6",  # purple
    SensorType.RF: "#e67e22",  # orange
    SensorType.Acoustic: "#2ecc71",  # green
}

# Rendering style per ZoneType: (edge_colour, fill_colour, hatch, label)
_ZONE_STYLE: dict[ZoneType, tuple[str, str, str, str]] = {
    ZoneType.perimeter: ("#1a73e8", "#1a73e8", "", "Perimeter"),
    ZoneType.inner: ("#f9a825", "#f9a825", "", "Inner"),
    ZoneType.critical_asset: ("#e53935", "#e53935", "", "Critical Asset"),
    ZoneType.exclusion: ("#6d4c41", "#6d4c41", "////", "Exclusion"),
}


def _hillshade(dem: np.ndarray, azimuth: float = 315, altitude: float = 45) -> np.ndarray:
    """Generate a hillshade array from a DEM for visual context.

    Raises:
        ValueError: If the DEM contains NaN values (nodata cells).
    """
    if np.any(np.isnan(dem)):
        raise ValueError(
            "DEM contains NaN values (nodata cells) — fill or mask nodata before rendering"
        )
    az_rad = np.radians(azimuth)
    alt_rad = np.radians(altitude)
    dy, dx = np.gradient(dem)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)
    shaded = np.sin(alt_rad) * np.cos(slope) + np.cos(alt_rad) * np.sin(slope) * np.cos(
        az_rad - aspect
    )
    return np.clip(shaded, 0, 1)


def render_coverage_map(
    site: SiteModel,
    coverage: np.ndarray,
    output_path: str | Path,
    title: str = "Coverage Map",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render a coverage map overlaid on terrain hillshade.

    Args:
        site: The site terrain model.
        coverage: Boolean 2D array — True = covered.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of (x, y) positions to mark on the map.
        boundary: Optional site boundary polygon to draw as an outline on the map.
        zones: Optional list of :class:`~salus.models.zone.Zone` objects to draw
            with distinct colours and labels. Critical asset zones are drawn in red,
            perimeter in blue, inner in amber, and exclusion zones with hatching.
            A legend entry is added for each zone type present.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)  # D-109
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        # Hillshade background
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7)

        # Coverage overlay — green where covered, transparent where not
        cov_display = np.ma.masked_where(~coverage, coverage.astype(float))
        cov_cmap = ListedColormap(["#2ecc71"])
        ax.imshow(cov_display, cmap=cov_cmap, extent=extent, origin="upper", alpha=0.5)

        # Boundary outline
        if boundary is not None:
            if isinstance(boundary, MultiPolygon):
                geoms: list[Polygon] = list(boundary.geoms)
            else:
                geoms = [boundary]
            for geom in geoms:
                if geom.is_empty:
                    continue
                bx, by = geom.exterior.xy
                ax.plot(bx, by, color="white", linewidth=2, zorder=5)

        # Zone overlays
        legend_handles: list[mpatches.Patch] = []
        seen_zone_types: set[ZoneType] = set()
        if zones:
            for zone in zones:
                style = _ZONE_STYLE.get(zone.zone_type)
                if style is None:
                    warnings.warn(
                        f"No render style defined for zone type '{zone.zone_type}' "
                        f"(zone '{zone.name}') — skipping.",
                        UserWarning,
                        stacklevel=2,
                    )
                    continue
                edge_colour, fill_colour, hatch, label = style
                if isinstance(zone.geometry, MultiPolygon):
                    geom_list: list[Polygon] = list(zone.geometry.geoms)
                elif isinstance(zone.geometry, Polygon):
                    geom_list = [zone.geometry]
                else:
                    warnings.warn(
                        f"Zone '{zone.name}' has unsupported geometry type "
                        f"{type(zone.geometry).__name__} — skipping.",
                        UserWarning,
                        stacklevel=2,
                    )
                    continue
                for geom in geom_list:
                    if geom.is_empty:
                        continue
                    if geom.exterior is None:
                        continue
                    zx, zy = geom.exterior.xy
                    ax.fill(
                        zx,
                        zy,
                        facecolor=fill_colour,
                        edgecolor=edge_colour,
                        alpha=0.25,
                        hatch=hatch,
                        zorder=4,
                    )
                    ax.plot(zx, zy, color=edge_colour, linewidth=1.5, zorder=4)
                # Label at centroid of first non-empty geometry
                first_geom = next((g for g in geom_list if not g.is_empty), None)
                if first_geom is not None:
                    cx, cy = first_geom.centroid.x, first_geom.centroid.y
                    if not (np.isnan(cx) or np.isnan(cy)):
                        ax.text(
                            cx,
                            cy,
                            zone.name,
                            fontsize=7,
                            ha="center",
                            va="center",
                            color=edge_colour,
                            fontweight="bold",
                            zorder=6,
                        )
                if zone.zone_type not in seen_zone_types:
                    seen_zone_types.add(zone.zone_type)
                    legend_handles.append(
                        mpatches.Patch(
                            facecolor=fill_colour,
                            edgecolor=edge_colour,
                            hatch=hatch,
                            alpha=0.5,
                            label=label,
                        )
                    )
            if legend_handles:
                try:
                    ax.legend(
                        handles=legend_handles,
                        loc="lower left",
                        fontsize=8,
                        framealpha=0.8,
                    )
                except Exception as exc:
                    warnings.warn(f"Zone legend could not be added: {exc}", stacklevel=2)

        # Sensor positions
        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(x, y, "r^", markersize=12, markeredgecolor="black", markeredgewidth=1)

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")

        # Scale bar — optional dependency
        try:
            from matplotlib_scalebar.scalebar import ScaleBar

            scalebar = ScaleBar(1, units="m", location="lower right")
            ax.add_artist(scalebar)
        except ImportError:
            pass  # matplotlib-scalebar not installed; scale bar omitted
        except Exception as exc:
            warnings.warn(f"ScaleBar could not be added: {exc}", stacklevel=2)

        # North arrow
        ax.annotate(
            "N",
            xy=(0.97, 0.97),
            xycoords="axes fraction",
            fontsize=14,
            fontweight="bold",
            ha="center",
            va="top",
        )
        ax.annotate(
            "",
            xy=(0.97, 0.97),
            xytext=(0.97, 0.92),
            xycoords="axes fraction",
            arrowprops=dict(arrowstyle="->", lw=2),
        )

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def _add_basemap(ax: plt.Axes, site: SiteModel) -> None:  # type: ignore[name-defined]
    """Try to add contextily basemap tiles to *ax*.

    Silently skips if contextily is not installed or the site has no CRS.
    Emits a UserWarning if tiles cannot be fetched (e.g. no network).
    """
    try:
        import contextily as ctx
    except ImportError:
        return

    if site.crs_epsg is None:
        warnings.warn(
            "site.crs_epsg is None — basemap tiles skipped. "
            "Set crs_epsg on SiteModel to enable geographic context.",
            UserWarning,
            stacklevel=3,
        )
        return

    try:
        ctx.add_basemap(
            ax,
            crs=f"EPSG:{site.crs_epsg}",
            source=ctx.providers.OpenStreetMap.Mapnik,
            zoom="auto",
            alpha=0.4,
            zorder=0,
        )
    except Exception as exc:
        warnings.warn(
            f"Basemap tiles could not be added ({exc}). "
            "Map will render without geographic context.",
            UserWarning,
            stacklevel=3,
        )


def render_layer_coverage_maps(
    site: SiteModel,
    layer_coverages: dict[SensorType, np.ndarray],
    output_dir: str | Path,
    title_prefix: str = "Coverage",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> dict[SensorType, Path]:
    """Render one coverage map per sensor-type layer.

    Each map shows the layer's coverage in a distinct type-specific colour
    overlaid on the terrain hillshade, with optional basemap tiles for
    geographic context.

    Args:
        site: The site terrain model.
        layer_coverages: Per-sensor-type boolean coverage arrays (output of
            :func:`~salus.engine.coverage.compute_layer_coverage`).
        output_dir: Directory where PNG files will be saved.
        title_prefix: Prefix for each map title; sensor type is appended.
        sensor_positions: Optional list of ``(x, y)`` sensor positions to mark.
        boundary: Optional boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Mapping from :class:`~salus.models.sensor.SensorType` to saved PNG path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[SensorType, Path] = {}
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    for sensor_type, coverage in layer_coverages.items():
        if coverage.size == 0:  # D-107: guard zero-size array before division
            raise ValueError(
                f"Coverage array for {sensor_type.value} has zero elements — cannot render map."
            )
        colour = _SENSOR_TYPE_COLOURS.get(sensor_type, "#95a5a6")
        safe_name = sensor_type.value.lower().replace(" ", "_").replace("/", "_")
        out_path = output_dir / f"layer_{safe_name}.png"

        fig, ax = plt.subplots(1, 1, figsize=(12, 10))
        try:
            hs = _hillshade(site.dem)
            ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

            _add_basemap(ax, site)

            cov_display = np.ma.masked_where(~coverage.astype(bool), coverage.astype(float))
            cov_cmap = ListedColormap([colour])
            ax.imshow(
                cov_display, cmap=cov_cmap, extent=extent, origin="upper", alpha=0.55, zorder=2
            )

            _render_boundary(ax, boundary)
            _render_zones(ax, zones)

            if sensor_positions:
                for x, y in sensor_positions:
                    ax.plot(
                        x,
                        y,
                        "r^",
                        markersize=12,
                        markeredgecolor="black",
                        markeredgewidth=1,
                        zorder=7,
                    )

            covered_pct = coverage.astype(bool).sum() / coverage.size * 100.0
            ax.set_title(
                f"{title_prefix} — {sensor_type.value} ({covered_pct:.1f}% covered)",
                fontsize=14,
                fontweight="bold",
            )
            ax.set_xlabel("Easting (m)")
            ax.set_ylabel("Northing (m)")
            _add_cartographic_elements(ax)

            legend_patch = mpatches.Patch(
                facecolor=colour, alpha=0.6, label=f"{sensor_type.value} coverage"
            )
            ax.legend(handles=[legend_patch], loc="lower left", fontsize=9, framealpha=0.8)

            fig.tight_layout()
            fig.savefig(out_path, dpi=200, bbox_inches="tight")
            paths[sensor_type] = (
                out_path  # D-110: inside try so failures don't silently drop entries
            )
        finally:
            plt.close(fig)

    return paths


def render_composite_coverage_map(
    site: SiteModel,
    layer_coverages: dict[SensorType, np.ndarray],
    output_path: str | Path,
    title: str = "Composite Coverage Map",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render all sensor-type layers overlaid on a single composite map.

    Each sensor type is shown in its distinct colour.  Cells covered by
    multiple layers show overlapping transparent patches.  A basemap is
    added for geographic context when the site CRS is known.

    Args:
        site: The site terrain model.
        layer_coverages: Per-sensor-type boolean coverage arrays.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of ``(x, y)`` sensor positions to mark.
        boundary: Optional boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)  # D-105
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        legend_handles: list[mpatches.Patch] = []
        for sensor_type, coverage in layer_coverages.items():
            colour = _SENSOR_TYPE_COLOURS.get(sensor_type, "#95a5a6")
            cov_display = np.ma.masked_where(~coverage.astype(bool), coverage.astype(float))
            cov_cmap = ListedColormap([colour])
            ax.imshow(
                cov_display,
                cmap=cov_cmap,
                extent=extent,
                origin="upper",
                alpha=0.45,
                zorder=2,
            )
            legend_handles.append(
                mpatches.Patch(facecolor=colour, alpha=0.6, label=sensor_type.value)
            )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        if legend_handles:
            ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def render_gap_map(
    site: SiteModel,
    composite: np.ndarray,
    gaps: np.ndarray,
    output_path: str | Path,
    title: str = "Coverage Gap Map",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render a gap map with gaps highlighted in red against greyed-out coverage.

    Covered cells are shown in muted grey-green.  Gap cells (inside boundary
    but uncovered) are shown in red.  A basemap is added for geographic context
    when the site CRS is known.

    Args:
        site: The site terrain model.
        composite: Any-sensor composite coverage boolean array.
        gaps: Uncovered cell mask (output of
            :func:`~salus.engine.coverage.compute_gaps`).
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of ``(x, y)`` sensor positions to mark.
        boundary: Optional boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)  # D-106
    if composite.shape != gaps.shape:  # D-108
        raise ValueError(
            f"composite shape {composite.shape} != gaps shape {gaps.shape} — arrays must match."
        )
    if gaps.size == 0:  # D-107
        raise ValueError("gaps array has zero elements — cannot render gap map.")
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        # Covered cells in muted grey-green
        covered = composite.astype(bool) & ~gaps.astype(bool)
        cov_display = np.ma.masked_where(~covered, covered.astype(float))
        ax.imshow(
            cov_display,
            cmap=ListedColormap(["#7fb3a0"]),
            extent=extent,
            origin="upper",
            alpha=0.5,
            zorder=2,
        )

        # Gap cells in red
        gap_display = np.ma.masked_where(~gaps.astype(bool), gaps.astype(float))
        ax.imshow(
            gap_display,
            cmap=ListedColormap(["#e74c3c"]),
            extent=extent,
            origin="upper",
            alpha=0.65,
            zorder=3,
        )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        gap_pct = gaps.astype(bool).sum() / gaps.size * 100.0
        ax.set_title(f"{title} ({gap_pct:.1f}% gap)", fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        legend_handles = [
            mpatches.Patch(facecolor="#7fb3a0", alpha=0.6, label="Covered"),
            mpatches.Patch(facecolor="#e74c3c", alpha=0.7, label="Gap (uncovered)"),
        ]
        ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def _render_boundary(
    ax: plt.Axes,  # type: ignore[name-defined]
    boundary: Polygon | MultiPolygon | None,
) -> None:
    """Draw a boundary polygon outline on *ax*."""
    if boundary is None:
        return
    geoms: list[Polygon] = (
        list(boundary.geoms) if isinstance(boundary, MultiPolygon) else [boundary]
    )
    for geom in geoms:
        if geom.is_empty:
            continue
        bx, by = geom.exterior.xy
        ax.plot(bx, by, color="white", linewidth=2, zorder=5)


def _render_zones(
    ax: plt.Axes,  # type: ignore[name-defined]
    zones: list[Zone] | None,
) -> None:
    """Draw zone overlays on *ax* using per-type styles."""
    if not zones:
        return
    for zone in zones:
        style = _ZONE_STYLE.get(zone.zone_type)
        if style is None:
            warnings.warn(
                f"No render style defined for zone type '{zone.zone_type}' "
                f"(zone '{zone.name}') — skipping.",  # D-111: match render_coverage_map wording
                UserWarning,
                stacklevel=3,
            )
            continue
        edge_colour, fill_colour, hatch, _ = style
        geom_list: list[Polygon] = (
            list(zone.geometry.geoms)
            if isinstance(zone.geometry, MultiPolygon)
            else [zone.geometry]
            if isinstance(zone.geometry, Polygon)
            else []
        )
        for geom in geom_list:
            if geom.is_empty or geom.exterior is None:
                continue
            zx, zy = geom.exterior.xy
            ax.fill(
                zx,
                zy,
                facecolor=fill_colour,
                edgecolor=edge_colour,
                alpha=0.25,
                hatch=hatch,
                zorder=4,
            )
            ax.plot(zx, zy, color=edge_colour, linewidth=1.5, zorder=4)


def _add_cartographic_elements(ax: plt.Axes) -> None:  # type: ignore[name-defined]
    """Add scale bar and north arrow to *ax* where available."""
    try:
        from matplotlib_scalebar.scalebar import ScaleBar

        ax.add_artist(ScaleBar(1, units="m", location="lower right"))
    except ImportError:
        pass
    except Exception as exc:
        warnings.warn(f"ScaleBar could not be added: {exc}", stacklevel=3)

    ax.annotate(
        "N",
        xy=(0.97, 0.97),
        xycoords="axes fraction",
        fontsize=14,
        fontweight="bold",
        ha="center",
        va="top",
    )
    ax.annotate(
        "",
        xy=(0.97, 0.97),
        xytext=(0.97, 0.92),
        xycoords="axes fraction",
        arrowprops=dict(arrowstyle="->", lw=2),
    )


# Colour per redundancy level: 0=uncovered, 1=single, 2=double, 3+=triple+
_REDUNDANCY_COLOURS: list[str] = [
    "#e74c3c",  # 0 sensors — red
    "#f1c40f",  # 1 sensor  — yellow
    "#2ecc71",  # 2 sensors — green
    "#27ae60",  # 3+ sensors — dark green
]


def render_redundancy_map(
    site: SiteModel,
    redundancy_map: np.ndarray,
    output_path: str | Path,
    title: str = "Sensor Redundancy Map",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render a redundancy heat map coloured by sensor count per cell.

    Colour scale:
    - Red    (0 sensors) — uncovered cell
    - Yellow (1 sensor)  — single coverage; no redundancy
    - Green  (2 sensors) — double coverage
    - Dark green (3+)    — triple or higher coverage

    Args:
        site: The site terrain model.
        redundancy_map: Integer array (dtype intp) giving the number of sensor
            layers covering each cell — output of
            :func:`~salus.engine.coverage.compute_coverage_stats`.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of ``(x, y)`` sensor positions to mark.
        boundary: Optional boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Path to the saved PNG.

    Raises:
        ValueError: If *redundancy_map* is not a 2-D array or has zero elements.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if redundancy_map.ndim != 2:
        raise ValueError(f"redundancy_map must be 2-D, got ndim={redundancy_map.ndim}.")
    if redundancy_map.size == 0:
        raise ValueError("redundancy_map has zero elements — cannot render map.")
    if not np.issubdtype(redundancy_map.dtype, np.integer):  # D-114
        raise ValueError(f"redundancy_map must have an integer dtype, got {redundancy_map.dtype}.")
    if np.any(redundancy_map < 0):  # D-112
        raise ValueError(
            f"redundancy_map contains negative values (min={redundancy_map.min()}) — "
            "fill nodata before rendering."
        )
    if redundancy_map.shape != site.dem.shape:  # D-113
        raise ValueError(
            f"redundancy_map shape {redundancy_map.shape} does not match "
            f"DEM shape {site.dem.shape}."
        )

    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    # Clamp counts to 0–3 bucket (3 = "3 or more")
    bucketed = np.clip(redundancy_map.astype(np.intp), 0, 3)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        cmap = ListedColormap(_REDUNDANCY_COLOURS)
        ax.imshow(
            bucketed,
            cmap=cmap,
            vmin=0,
            vmax=3,
            extent=extent,
            origin="upper",
            alpha=0.65,
            zorder=2,
        )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        legend_handles = [
            mpatches.Patch(
                facecolor=_REDUNDANCY_COLOURS[0], alpha=0.75, label="0 sensors (uncovered)"
            ),
            mpatches.Patch(facecolor=_REDUNDANCY_COLOURS[1], alpha=0.75, label="1 sensor"),
            mpatches.Patch(facecolor=_REDUNDANCY_COLOURS[2], alpha=0.75, label="2 sensors"),
            mpatches.Patch(facecolor=_REDUNDANCY_COLOURS[3], alpha=0.75, label="3+ sensors"),
        ]
        try:  # D-115: guard against Matplotlib legend failures
            ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)
        except Exception as exc:
            warnings.warn(f"Redundancy legend could not be added: {exc}", stacklevel=2)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


# Colormap for corridor lines: red (poor coverage) → green (good coverage)
_CORRIDOR_CMAP: str = "RdYlGn"
# Linewidth for corridor paths drawn on the overlay map
_CORRIDOR_LINEWIDTH: float = 2.5
# Marker size for first-detection points on the corridor overlay map
_DETECTION_MARKER_SIZE: int = 8


def render_corridor_overlay_map(
    site: SiteModel,
    composite_coverage: npt.NDArray[np.bool_],
    corridor_results: list[CorridorResult],
    protected_point: tuple[float, float],
    output_path: str | Path,
    title: str = "Threat Corridor Analysis",
    sensor_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render corridor approach paths overlaid on the composite coverage map.

    Each corridor is drawn as a line from its start point to the protected
    asset, colour-coded by coverage percentage (red = poorly covered,
    green = well covered).  Where a first detection distance is available, a
    circle marker is placed at that point along the corridor.

    Args:
        site: The site terrain model.
        composite_coverage: Boolean 2D coverage array matching ``site.dem``.
        corridor_results: List of analysed corridors (output of
            :func:`~salus.engine.threat_corridor.find_worst_corridors` or
            a manual list of
            :func:`~salus.engine.threat_corridor.analyse_corridor` results).
        protected_point: ``(x, y)`` CRS coordinates of the protected asset
            (the near end of every corridor).
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional sensor positions to mark on the map.
        boundary: Optional boundary polygon outline.
        zones: Optional zone overlays.

    Returns:
        Path to the saved PNG.

    Raises:
        ValueError: If ``composite_coverage`` is not 2D, is empty, has a
            shape mismatch with ``site.dem``, or if ``protected_point``
            contains non-finite coordinates.
    """
    if composite_coverage.ndim != 2:
        raise ValueError(f"composite_coverage must be 2D, got {composite_coverage.ndim}D")
    if composite_coverage.size == 0:
        raise ValueError("composite_coverage must not be empty")
    if composite_coverage.shape != site.dem.shape:
        raise ValueError(
            f"composite_coverage shape {composite_coverage.shape} does not match "
            f"site.dem shape {site.dem.shape}"
        )
    px, py = protected_point
    if not (math.isfinite(px) and math.isfinite(py)):
        raise ValueError(f"protected_point coordinates must be finite, got ({px}, {py})")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    cmap = plt.get_cmap(_CORRIDOR_CMAP)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        # Composite coverage background (muted grey-green)
        cov_display = np.ma.masked_where(~composite_coverage, composite_coverage.astype(float))
        ax.imshow(
            cov_display,
            cmap=ListedColormap(["#7fb3a0"]),
            extent=extent,
            origin="upper",
            alpha=0.4,
            zorder=2,
        )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        # Draw each corridor path and first-detection markers
        for result in corridor_results:
            bearing_rad = math.radians(result.corridor.bearing_deg)
            sin_b = math.sin(bearing_rad)
            cos_b = math.cos(bearing_rad)
            start_d = result.corridor.start_distance_m
            far_x = px - start_d * sin_b
            far_y = py - start_d * cos_b
            colour = cmap(result.coverage_pct / 100.0)

            ax.plot(
                [far_x, px],
                [far_y, py],
                color=colour,
                linewidth=_CORRIDOR_LINEWIDTH,
                alpha=0.8,
                zorder=5,
            )

            if result.first_detection_distance_m is not None:
                det_x = px - result.first_detection_distance_m * sin_b
                det_y = py - result.first_detection_distance_m * cos_b
                ax.plot(
                    det_x,
                    det_y,
                    "o",
                    color=colour,
                    markersize=_DETECTION_MARKER_SIZE,
                    markeredgecolor="black",
                    markeredgewidth=0.5,
                    zorder=6,
                )

        # Protected asset marker
        ax.plot(
            px,
            py,
            "k*",
            markersize=15,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=8,
        )

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        # Colorbar for corridor coverage percentage
        if corridor_results:
            sm = plt.cm.ScalarMappable(cmap=_CORRIDOR_CMAP, norm=Normalize(vmin=0, vmax=100))
            sm.set_array([])
            try:
                cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.04)
                cbar.set_label("Corridor coverage (%)", fontsize=10)
            except Exception as exc:
                warnings.warn(f"Corridor colorbar could not be added: {exc}", stacklevel=2)

        # D-126: include legend entries for all map symbols
        all_legend: list = [
            mpatches.Patch(facecolor="#7fb3a0", alpha=0.5, label="Covered"),
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gray",
                markeredgecolor="black",
                markersize=_DETECTION_MARKER_SIZE,
                label="First detection",
            ),
            plt.Line2D(
                [0],
                [0],
                marker="*",
                color="w",
                markerfacecolor="black",
                markeredgecolor="white",
                markersize=12,
                label="Protected asset",
            ),
        ]
        try:
            ax.legend(handles=all_legend, loc="lower left", fontsize=8, framealpha=0.8)
        except Exception as exc:
            warnings.warn(f"Legend could not be added: {exc}", stacklevel=2)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def render_corridor_polar_diagram(
    corridor_results: list[CorridorResult],
    output_path: str | Path,
    title: str = "Coverage by Approach Bearing",
    trajectory_results_and_bearings: list[tuple[float, TrajectoryResult]] | None = None,
) -> Path:
    """Render a polar (radar) chart of coverage percentage by approach bearing.

    Each bearing segment is drawn as a bar coloured by coverage percentage
    (red = poor, green = good) using the RdYlGn colormap.  The radial axis
    shows coverage percentage 0–100%.  Bearings follow compass convention:
    North (0°) at the top, clockwise.

    When ``trajectory_results_and_bearings`` is provided, trajectory results
    are overlaid as additional bars coloured by ``time_in_detection_s`` as a
    fraction of ``time_to_asset_s`` (0 = no detection = red, 1 = full
    detection = green).  ``corridor_results`` may then be an empty list.

    Args:
        corridor_results: List of analysed corridors.  Must be non-empty unless
            ``trajectory_results_and_bearings`` is provided.
        output_path: Where to save the PNG.
        title: Diagram title.
        trajectory_results_and_bearings: Optional list of ``(bearing_deg,
            TrajectoryResult)`` pairs to overlay as trajectory bars.

    Returns:
        Path to the saved PNG.

    Raises:
        ValueError: If both ``corridor_results`` and
            ``trajectory_results_and_bearings`` are empty/None.
    """
    if not corridor_results and not trajectory_results_and_bearings:
        raise ValueError(
            "corridor_results must not be empty unless trajectory_results_and_bearings is provided"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort by bearing so bars are drawn in order
    sorted_results = sorted(corridor_results, key=lambda r: r.corridor.bearing_deg)

    # Collect all bearings (corridor + trajectory) to compute a consistent bar width.
    # Duplicates are detected first to preserve the existing error contract.
    all_thetas_rad: list[float] = [math.radians(r.corridor.bearing_deg) for r in sorted_results]
    if trajectory_results_and_bearings:
        all_thetas_rad += [math.radians(b) for b, _ in trajectory_results_and_bearings]
    if len(all_thetas_rad) != len(set(all_thetas_rad)):
        raise ValueError("duplicate bearings in input — bar_width would be zero")
    all_thetas_sorted = sorted(all_thetas_rad)
    total = len(all_thetas_sorted)

    if total == 1:
        bar_width = 2.0 * math.pi
    else:
        gaps = [
            (all_thetas_sorted[(i + 1) % total] - all_thetas_sorted[i]) % (2.0 * math.pi)
            for i in range(total)
        ]
        bar_width = min(gaps)

    # Convert compass bearings to matplotlib polar radians for corridor data.
    thetas = [math.radians(r.corridor.bearing_deg) for r in sorted_results]
    coverages = [r.coverage_pct for r in sorted_results]

    cmap = plt.get_cmap(_CORRIDOR_CMAP)

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, polar=True)
    try:
        ax.set_theta_zero_location("N")  # type: ignore[attr-defined]
        ax.set_theta_direction(-1)  # type: ignore[attr-defined]  # clockwise

        for theta, coverage in zip(thetas, coverages):
            colour = cmap(coverage / 100.0)
            ax.bar(
                theta,
                coverage,
                width=bar_width,
                color=colour,
                alpha=0.75,
                edgecolor="white",
                linewidth=0.5,
                zorder=2,
            )

        # Trajectory overlay bars: coloured by detection fraction (0=red, 1=green).
        if trajectory_results_and_bearings:
            for bearing_deg, traj_result in trajectory_results_and_bearings:
                theta_t = math.radians(bearing_deg)
                if traj_result.time_to_asset_s > 0.0:
                    detection_pct = min(
                        traj_result.time_in_detection_s / traj_result.time_to_asset_s * 100.0,
                        100.0,
                    )
                else:
                    detection_pct = 0.0
                colour_t = cmap(detection_pct / 100.0)
                ax.bar(
                    theta_t,
                    detection_pct,
                    width=bar_width,
                    color=colour_t,
                    alpha=0.55,
                    edgecolor="black",
                    linewidth=0.8,
                    linestyle="--",
                    zorder=3,
                )

        ax.set_ylim(0, 100)
        ax.set_yticks([25, 50, 75, 100])
        ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=9)
        ax.grid(True, alpha=0.3, zorder=1)

        # Compass labels (N/E/S/W)
        ax.set_xticks([math.radians(a) for a in range(0, 360, 45)])
        ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"], fontsize=10)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)

        # Colorbar
        sm = plt.cm.ScalarMappable(cmap=_CORRIDOR_CMAP, norm=Normalize(vmin=0, vmax=100))
        sm.set_array([])
        try:
            cbar = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.08, shrink=0.6)
            cbar.set_label("Coverage (%)", fontsize=10)
        except Exception as exc:
            warnings.warn(f"Polar colorbar could not be added: {exc}", stacklevel=2)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


# Colormap for trajectory detection exposure (red = low detection = dangerous).
_TRAJECTORY_CMAP: str = "RdYlGn"

# Line width for trajectory path segments.
_TRAJECTORY_LINEWIDTH: float = 2.0


def render_trajectory_map(
    site: SiteModel,
    composite_coverage: npt.NDArray[np.bool_],
    trajectory_results: list[tuple[DroneTrajectory, TrajectoryResult]],
    protected_point: tuple[float, float],
    output_path: str | Path,
    title: str = "Trajectory Analysis",
    sensor_positions: list[tuple[float, float]] | None = None,
) -> Path:
    """Render a top-down trajectory analysis map.

    Draws the composite sensor coverage as a background, then overlays each
    trajectory path as a colour-coded line (red = low detection exposure =
    dangerous, green = high detection exposure = well-covered).  Detection
    crossing events are marked as labelled circle markers.

    Args:
        site: Site terrain model used to establish spatial extent.
        composite_coverage: Boolean array (rows × cols) of composite coverage.
        trajectory_results: List of ``(DroneTrajectory, TrajectoryResult)``
            pairs.  Must not be empty.
        protected_point: ``(x, y)`` easting/northing of the protected asset in
            CRS units.  Drawn as a black star.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of ``(x, y)`` sensor positions drawn as
            red triangles.

    Returns:
        Path to the saved PNG.

    Raises:
        ValueError: If ``trajectory_results`` is empty.
    """
    if not trajectory_results:
        raise ValueError("trajectory_results must not be empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    px, py = protected_point
    min_x, max_x, min_y, max_y = site.extent

    cmap = plt.get_cmap(_TRAJECTORY_CMAP)

    # Normalise time_in_detection_s across all trajectories for consistent colouring.
    # D-155: guard against vmin==vmax (e.g. all trajectories fully undetected at 0 s)
    # so the colorbar Normalize has a meaningful span.
    all_detection_times = [tr.time_in_detection_s for _, tr in trajectory_results]
    det_min = min(all_detection_times)
    det_max = max(all_detection_times)
    if det_max <= det_min:
        det_max = det_min + 1.0
    det_range = det_max - det_min

    fig, ax = plt.subplots(figsize=(12, 10))
    try:
        # Hillshade background for terrain context (consistent with other render functions).
        hs = _hillshade(site.dem)
        ax.imshow(
            hs,
            cmap="gray",
            origin="upper",
            extent=(min_x, max_x, min_y, max_y),
            vmin=0,
            vmax=1,
            zorder=1,
        )
        _add_basemap(ax, site)

        # Coverage overlay (semi-transparent teal)
        coverage_rgba = np.zeros((*composite_coverage.shape, 4))
        coverage_rgba[composite_coverage] = [0.498, 0.702, 0.627, 0.45]
        ax.imshow(
            coverage_rgba,
            origin="upper",
            extent=(min_x, max_x, min_y, max_y),
            zorder=3,
        )

        # Draw trajectory paths and detection event markers.
        for traj, result in trajectory_results:
            norm_val = (result.time_in_detection_s - det_min) / det_range
            line_colour = cmap(norm_val)

            xs = [wp.x for wp in traj.waypoints]
            ys = [wp.y for wp in traj.waypoints]
            ax.plot(
                xs,
                ys,
                color=line_colour,
                linewidth=_TRAJECTORY_LINEWIDTH,
                solid_capstyle="round",
                zorder=5,
            )
            # Start of trajectory (approach origin)
            ax.plot(xs[0], ys[0], "o", color=line_colour, markersize=6, zorder=6)

            # Detection event markers
            for event in result.detection_events:
                # D-157: skip non-finite positions to avoid silent invisible annotations
                if not (math.isfinite(event.position_x) and math.isfinite(event.position_y)):
                    warnings.warn(
                        f"DetectionEvent for sensor '{event.sensor_name}' has non-finite "
                        f"position ({event.position_x}, {event.position_y}) — skipping marker",
                        stacklevel=2,
                    )
                    continue
                ax.plot(
                    event.position_x,
                    event.position_y,
                    "o",
                    color="white",
                    markersize=_DETECTION_MARKER_SIZE,
                    markeredgecolor="black",
                    markeredgewidth=0.8,
                    zorder=7,
                )
                label = f"{event.sensor_name}\n{event.time_s:.1f}s"
                ax.annotate(
                    label,
                    xy=(event.position_x, event.position_y),
                    xytext=(4, 4),
                    textcoords="offset points",
                    fontsize=6,
                    zorder=8,
                    clip_on=True,
                )

        # Protected asset marker
        ax.plot(
            px,
            py,
            "k*",
            markersize=15,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=9,
        )

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=8,
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        # Colorbar for trajectory detection exposure
        sm = plt.cm.ScalarMappable(
            cmap=_TRAJECTORY_CMAP,
            norm=Normalize(vmin=det_min, vmax=det_max),
        )
        sm.set_array([])
        try:
            cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.04)
            cbar.set_label("Time in detection (s)", fontsize=10)
        except Exception as exc:
            warnings.warn(f"Trajectory colorbar could not be added: {exc}", stacklevel=2)

        # Legend
        legend_entries: list = [
            mpatches.Patch(facecolor="#7fb3a0", alpha=0.5, label="Covered"),
            plt.Line2D(
                [0],
                [0],
                color="gray",
                linewidth=_TRAJECTORY_LINEWIDTH,
                label="Trajectory path",
            ),
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="white",
                markeredgecolor="black",
                markersize=_DETECTION_MARKER_SIZE,
                label="Detection event",
            ),
            plt.Line2D(
                [0],
                [0],
                marker="*",
                color="w",
                markerfacecolor="black",
                markeredgecolor="white",
                markersize=12,
                label="Protected asset",
            ),
        ]
        try:
            ax.legend(handles=legend_entries, loc="lower left", fontsize=8, framealpha=0.8)
        except Exception as exc:
            warnings.warn(f"Legend could not be added: {exc}", stacklevel=2)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def render_adversarial_map(
    site: SiteModel,
    composite_coverage: npt.NDArray[np.bool_],
    cost_grid: DetectionCostGrid,
    trajectory: DroneTrajectory,
    trajectory_result: TrajectoryResult,
    protected_point: tuple[float, float],
    output_path: str | Path,
    title: str = "Adversarial Path Analysis",
    sensor_positions: list[tuple[float, float]] | None = None,
) -> Path:
    """Render the adversarial path discovery result as a top-down map.

    Overlays the minimum-cost adversarial trajectory on a coverage heatmap,
    with the detection cost grid shown as a semi-transparent red heatmap
    (brighter = more sensors can detect).  Detection events along the path are
    marked as circle markers labelled with sensor name and detection time.

    Args:
        site: Site terrain model.
        composite_coverage: Boolean coverage array (rows x cols).
        cost_grid: Pre-built detection cost grid (collapsed to max across
            altitude bands for 2D display).
        trajectory: The adversarial DroneTrajectory discovered by
            find_adversarial_trajectory.
        trajectory_result: Detection analysis of the adversarial trajectory
            from analyse_trajectory.
        protected_point: (x, y) of the protected asset.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional sensor positions drawn as triangles.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    px, py = protected_point
    min_x, max_x, min_y, max_y = site.extent

    # Collapse cost grid to 2D by taking the max detection count across altitude bands.
    cost_2d = cost_grid.grid.max(axis=0).astype(np.float32)

    fig, ax = plt.subplots(figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(
            hs,
            cmap="gray",
            origin="upper",
            extent=(min_x, max_x, min_y, max_y),
            vmin=0,
            vmax=1,
            zorder=1,
        )
        _add_basemap(ax, site)

        # Coverage overlay (semi-transparent teal)
        coverage_rgba = np.zeros((*composite_coverage.shape, 4))
        coverage_rgba[composite_coverage] = [0.498, 0.702, 0.627, 0.35]
        ax.imshow(
            coverage_rgba,
            origin="upper",
            extent=(min_x, max_x, min_y, max_y),
            zorder=3,
        )

        # Detection cost grid heatmap (red = high detection density)
        if cost_2d.max() > 0:
            cost_norm = cost_2d / cost_2d.max()
        else:
            cost_norm = cost_2d
        cost_rgba = np.zeros((*cost_norm.shape, 4))
        cost_rgba[..., 0] = cost_norm  # red channel
        cost_rgba[..., 3] = cost_norm * 0.4  # alpha proportional to detection count
        ax.imshow(
            cost_rgba,
            origin="upper",
            extent=(min_x, max_x, min_y, max_y),
            zorder=4,
        )

        # Adversarial trajectory path
        xs = [wp.x for wp in trajectory.waypoints]
        ys = [wp.y for wp in trajectory.waypoints]
        ax.plot(
            xs,
            ys,
            color="navy",
            linewidth=_TRAJECTORY_LINEWIDTH + 0.5,
            linestyle="--",
            solid_capstyle="round",
            zorder=5,
        )
        ax.plot(xs[0], ys[0], "o", color="navy", markersize=8, zorder=6)

        # Detection event markers along the adversarial path
        for event in trajectory_result.detection_events:
            if not (math.isfinite(event.position_x) and math.isfinite(event.position_y)):
                continue
            ax.plot(
                event.position_x,
                event.position_y,
                "o",
                color="white",
                markersize=_DETECTION_MARKER_SIZE,
                markeredgecolor="black",
                markeredgewidth=0.8,
                zorder=7,
            )
            ax.annotate(
                f"{event.sensor_name}\n{event.time_s:.1f}s",
                xy=(event.position_x, event.position_y),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=6,
                zorder=8,
                clip_on=True,
            )

        # Protected asset marker
        ax.plot(px, py, "k*", markersize=15, markeredgecolor="white", markeredgewidth=0.5, zorder=9)

        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x, y, "r^", markersize=12, markeredgecolor="black", markeredgewidth=1, zorder=8
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        # Colorbar for detection density
        sm = plt.cm.ScalarMappable(
            cmap="Reds",
            norm=Normalize(vmin=0, vmax=max(int(cost_2d.max()), 1)),
        )
        sm.set_array([])
        try:
            cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.04)
            cbar.set_label("Detection count (sensors)", fontsize=10)
        except Exception as exc:
            warnings.warn(f"Adversarial colorbar could not be added: {exc}", stacklevel=2)

        legend_entries: list = [
            mpatches.Patch(facecolor="#7fb3a0", alpha=0.5, label="Covered"),
            mpatches.Patch(facecolor="red", alpha=0.4, label="Detection density"),
            plt.Line2D(
                [0],
                [0],
                color="navy",
                linewidth=_TRAJECTORY_LINEWIDTH,
                linestyle="--",
                label="Adversarial path",
            ),
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="white",
                markeredgecolor="black",
                markersize=_DETECTION_MARKER_SIZE,
                label="Detection event",
            ),
            plt.Line2D(
                [0],
                [0],
                marker="*",
                color="w",
                markerfacecolor="black",
                markeredgecolor="white",
                markersize=12,
                label="Protected asset",
            ),
        ]
        try:
            ax.legend(handles=legend_entries, loc="lower left", fontsize=8, framealpha=0.8)
        except Exception as exc:
            warnings.warn(f"Legend could not be added: {exc}", stacklevel=2)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


# ---------------------------------------------------------------------------
# Configuration comparison map (S10)
# ---------------------------------------------------------------------------

# Colours for the four delta categories.
_DELTA_COLOUR_A_ONLY: str = "#e74c3c"  # red   — A covers, B does not
_DELTA_COLOUR_B_ONLY: str = "#2ecc71"  # green — B covers, A does not
_DELTA_COLOUR_BOTH: str = "#95a5a6"  # grey  — both cover
# Neither = transparent (not drawn)


def render_delta_map(
    site: SiteModel,
    comparison: "ComparisonResult",
    output_path: str | Path,
    title: str = "Coverage Delta Map (A vs B)",
    sensor_positions_a: list[tuple[float, float]] | None = None,
    sensor_positions_b: list[tuple[float, float]] | None = None,
) -> Path:
    """Render a coverage delta map comparing two sensor configurations.

    Cells are coloured by category:

    - **Grey** — both A and B cover this cell.
    - **Red** — only A covers this cell (B loses coverage here).
    - **Green** — only B covers this cell (B gains coverage here).
    - **Transparent** — neither configuration covers this cell.

    A hillshade background provides topographic context.

    Args:
        site: Site terrain model (used for hillshade and coordinate extent).
        comparison: Output of :func:`~salus.engine.comparison.compare_configs`.
        output_path: Where to write the PNG file.  Parent directories are
            created if absent.
        title: Map title.
        sensor_positions_a: Optional ``(x, y)`` positions for configuration A
            sensors (rendered as red triangles).
        sensor_positions_b: Optional ``(x, y)`` positions for configuration B
            sensors (rendered as green squares).

    Returns:
        Resolved :class:`~pathlib.Path` to the written PNG file.

    Raises:
        TypeError: If ``comparison`` is not a :class:`ComparisonResult`.
    """
    from salus.engine.comparison import (
        DELTA_A_ONLY,
        DELTA_B_ONLY,
        DELTA_BOTH,
        ComparisonResult,
    )

    if not isinstance(comparison, ComparisonResult):
        raise TypeError(f"comparison must be a ComparisonResult, got {type(comparison).__name__}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)
    delta = comparison.delta_grid

    fig, ax = plt.subplots(figsize=(12, 10))
    try:
        # D-197: catch hillshade failure and enrich the error with DEM diagnostics.
        try:
            hs = _hillshade(site.dem)
        except ValueError as exc:
            is_float = np.issubdtype(site.dem.dtype, np.floating)
            nan_count = int(np.isnan(site.dem).sum()) if is_float else 0
            raise ValueError(
                f"render_delta_map: hillshade failed ({nan_count} NaN cell(s) in DEM): {exc}"
            ) from exc
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.6, zorder=1)
        _add_basemap(ax, site)

        for mask_val, colour in (
            (DELTA_BOTH, _DELTA_COLOUR_BOTH),
            (DELTA_A_ONLY, _DELTA_COLOUR_A_ONLY),
            (DELTA_B_ONLY, _DELTA_COLOUR_B_ONLY),
        ):
            mask = delta == mask_val
            if not mask.any():
                continue
            overlay = np.ma.masked_where(~mask, np.ones_like(delta, dtype=float))
            ax.imshow(
                overlay,
                cmap=ListedColormap([colour]),
                extent=extent,
                origin="upper",
                alpha=0.50,
                zorder=2,
                vmin=0,
                vmax=1,
            )

        if sensor_positions_a:
            for x, y in sensor_positions_a:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=10,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )
        if sensor_positions_b:
            for x, y in sensor_positions_b:
                ax.plot(
                    x,
                    y,
                    "gs",
                    markersize=10,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        sign = "+" if comparison.coverage_delta_pct >= 0 else ""
        subtitle = (
            f"{comparison.label_a}: {comparison.coverage_pct_a:.1f}%  \u2192  "
            f"{comparison.label_b}: {comparison.coverage_pct_b:.1f}%  "
            f"({sign}{comparison.coverage_delta_pct:.1f}%)"
        )
        ax.set_title(f"{title}\n{subtitle}", fontsize=13, fontweight="bold")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        legend_handles: list[mpatches.Patch] = [
            mpatches.Patch(facecolor=_DELTA_COLOUR_BOTH, alpha=0.6, label="Both cover"),
            mpatches.Patch(
                facecolor=_DELTA_COLOUR_A_ONLY,
                alpha=0.6,
                label=f"{comparison.label_a} only",
            ),
            mpatches.Patch(
                facecolor=_DELTA_COLOUR_B_ONLY,
                alpha=0.6,
                label=f"{comparison.label_b} only",
            ),
        ]
        ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path.resolve()


# ---------------------------------------------------------------------------
# Effector coverage maps (S11-2)
# ---------------------------------------------------------------------------

# Teal overlay colour for effector engagement zones.
# Intentionally distinct from _SENSOR_TYPE_COLOURS[SensorType.Radar] (#3498db) so
# effector zones and radar detection layers are visually distinguishable on composite maps.
_EFFECTOR_COVERAGE_COLOUR: str = "#1abc9c"

# Amber overlay colour for "detected but cannot engage" cells.
_DETECTION_NO_ENGAGEMENT_COLOUR: str = "#f39c12"


def render_effector_coverage_map(
    site: SiteModel,
    effector_coverage: npt.NDArray[np.bool_],
    output_path: str | Path,
    title: str = "Effector Coverage Map",
    effector_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render the effector engagement zone as a distinct blue overlay on terrain.

    Cells where at least one effector can engage a target are shown in blue
    against a hillshade background.  This layer is intentionally distinct from
    sensor detection coverage (green) so operators can visually compare the two.

    Args:
        site: Site terrain model.
        effector_coverage: Boolean 2D array — ``True`` where at least one
            effector can engage a target.  Typically the output of
            :func:`~salus.engine.effector_coverage.compute_effector_layer_coverage`.
        output_path: Where to save the PNG.  Parent directories are created if
            absent.
        title: Map title.
        effector_positions: Optional list of ``(x, y)`` CRS positions to mark
            as blue triangles (▲) on the map.
        boundary: Optional site boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Resolved :class:`~pathlib.Path` to the saved PNG file.

    Raises:
        ValueError: If *effector_coverage* is not a 2-D array or has zero
            elements.
    """
    if effector_coverage.ndim != 2:
        raise ValueError(f"effector_coverage must be 2-D, got ndim={effector_coverage.ndim}")
    if effector_coverage.size == 0:
        raise ValueError("effector_coverage has zero elements — cannot render map")
    # D-210: guard against shape mismatch producing silently mis-registered overlay
    if effector_coverage.shape != site.dem.shape:
        raise ValueError(
            f"effector_coverage shape {effector_coverage.shape} != "
            f"site.dem shape {site.dem.shape} — arrays must match"
        )
    # D-206/D-208: cast to float before isnan — integer-dtype DEMs raise TypeError
    if np.issubdtype(site.dem.dtype, np.floating) and np.any(np.isnan(site.dem)):
        raise ValueError(
            f"site.dem contains NaN values — fill nodata before rendering {output_path}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        # Blue overlay for effector engagement zone
        eff_display = np.ma.masked_where(
            ~effector_coverage.astype(bool), effector_coverage.astype(float)
        )
        ax.imshow(
            eff_display,
            cmap=ListedColormap([_EFFECTOR_COVERAGE_COLOUR]),
            extent=extent,
            origin="upper",
            alpha=0.55,
            zorder=2,
        )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        if effector_positions:
            for x, y in effector_positions:
                ax.plot(
                    x,
                    y,
                    marker="^",
                    color=_EFFECTOR_COVERAGE_COLOUR,
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        cov_pct = effector_coverage.astype(bool).sum() / effector_coverage.size * 100.0
        ax.set_title(
            f"{title} ({cov_pct:.1f}% engagement coverage)",
            fontsize=14,
            fontweight="bold",
        )
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        legend_handles = [
            mpatches.Patch(
                facecolor=_EFFECTOR_COVERAGE_COLOUR,
                alpha=0.6,
                label="Effector engagement zone",
            )
        ]
        ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path.resolve()


def render_detection_without_engagement_map(
    site: SiteModel,
    sensor_composite: npt.NDArray[np.bool_],
    effector_coverage: npt.NDArray[np.bool_],
    output_path: str | Path,
    title: str = "Detection-Without-Engagement Gap Map",
    sensor_positions: list[tuple[float, float]] | None = None,
    effector_positions: list[tuple[float, float]] | None = None,
    boundary: Polygon | MultiPolygon | None = None,
    zones: list[Zone] | None = None,
) -> Path:
    """Render a map highlighting "detection-without-engagement" gaps.

    Cells are coloured by three categories:

    - **Grey-green** — detected by sensors *and* covered by an effector: the
      threat can be seen and defeated.
    - **Amber** — detected by sensors but *not* covered by any effector: an
      operator can observe the drone but cannot stop it.  These are the
      critical "detection-without-engagement" gaps.
    - **Transparent** — not detected by any sensor: outside the surveillance
      perimeter entirely.

    Args:
        site: Site terrain model.
        sensor_composite: Any-sensor composite boolean coverage array — output
            of :func:`~salus.engine.coverage.compute_composite_coverage`.
        effector_coverage: Effector engagement zone boolean array — output of
            :func:`~salus.engine.effector_coverage.compute_effector_layer_coverage`.
        output_path: Where to save the PNG.  Parent directories are created if
            absent.
        title: Map title.
        sensor_positions: Optional list of ``(x, y)`` sensor positions to mark
            as red triangles (▲).
        effector_positions: Optional list of ``(x, y)`` effector positions to
            mark as blue squares (■).
        boundary: Optional site boundary polygon to draw as an outline.
        zones: Optional zone overlays.

    Returns:
        Resolved :class:`~pathlib.Path` to the saved PNG file.

    Raises:
        ValueError: If *sensor_composite* and *effector_coverage* have
            different shapes, or if either has zero elements.
    """
    if sensor_composite.shape != effector_coverage.shape:
        raise ValueError(
            f"sensor_composite shape {sensor_composite.shape} != "
            f"effector_coverage shape {effector_coverage.shape} — arrays must match"
        )
    if sensor_composite.size == 0:
        raise ValueError("arrays have zero elements — cannot render map")
    # D-211: guard against shape mismatch vs DEM producing silently mis-registered overlays
    if sensor_composite.shape != site.dem.shape:
        raise ValueError(
            f"sensor_composite shape {sensor_composite.shape} != "
            f"site.dem shape {site.dem.shape} — arrays must match"
        )
    # D-206/D-209: cast check — integer-dtype DEMs raise TypeError with np.isnan
    if np.issubdtype(site.dem.dtype, np.floating) and np.any(np.isnan(site.dem)):
        raise ValueError(
            f"site.dem contains NaN values — fill nodata before rendering {output_path}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    sensor_bool: npt.NDArray[np.bool_] = sensor_composite.astype(bool)
    effector_bool: npt.NDArray[np.bool_] = effector_coverage.astype(bool)

    # D-207: warn when sensor coverage is empty — gap map will be blank
    if not sensor_bool.any():
        warnings.warn(
            "sensor_composite has no True cells — detection-without-engagement map "
            "will be blank. Check that sensor coverage was computed correctly.",
            UserWarning,
            stacklevel=2,
        )

    # Cells with both sensor detection and effector coverage (good)
    both_covered: npt.NDArray[np.bool_] = sensor_bool & effector_bool
    # Cells detected but NOT engageable (the critical gap)
    det_no_engage: npt.NDArray[np.bool_] = sensor_bool & ~effector_bool

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    try:
        hs = _hillshade(site.dem)
        ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7, zorder=1)

        _add_basemap(ax, site)

        # Grey-green: detected AND engageable
        both_display = np.ma.masked_where(~both_covered, both_covered.astype(float))
        ax.imshow(
            both_display,
            cmap=ListedColormap(["#7fb3a0"]),
            extent=extent,
            origin="upper",
            alpha=0.5,
            zorder=2,
        )

        # Amber: detected but NOT engageable — the gap
        gap_display = np.ma.masked_where(~det_no_engage, det_no_engage.astype(float))
        ax.imshow(
            gap_display,
            cmap=ListedColormap([_DETECTION_NO_ENGAGEMENT_COLOUR]),
            extent=extent,
            origin="upper",
            alpha=0.65,
            zorder=3,
        )

        _render_boundary(ax, boundary)
        _render_zones(ax, zones)

        # Sensor positions (red triangles)
        if sensor_positions:
            for x, y in sensor_positions:
                ax.plot(
                    x,
                    y,
                    "r^",
                    markersize=12,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        # Effector positions (blue squares)
        if effector_positions:
            for x, y in effector_positions:
                ax.plot(
                    x,
                    y,
                    marker="s",
                    color=_EFFECTOR_COVERAGE_COLOUR,
                    markersize=10,
                    markeredgecolor="black",
                    markeredgewidth=1,
                    zorder=7,
                )

        gap_pct = det_no_engage.sum() / max(sensor_bool.sum(), 1) * 100.0
        ax.set_title(
            f"{title} ({gap_pct:.1f}% of detected area unengageable)",
            fontsize=14,
            fontweight="bold",
        )
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        _add_cartographic_elements(ax)

        legend_handles = [
            mpatches.Patch(facecolor="#7fb3a0", alpha=0.6, label="Detected + engageable"),
            mpatches.Patch(
                facecolor=_DETECTION_NO_ENGAGEMENT_COLOUR,
                alpha=0.7,
                label="Detected — NO effector coverage (gap)",
            ),
        ]
        ax.legend(handles=legend_handles, loc="lower left", fontsize=9, framealpha=0.8)

        fig.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path.resolve()
