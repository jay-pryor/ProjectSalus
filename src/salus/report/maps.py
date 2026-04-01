"""Map rendering — coverage maps, gap maps, and site overview maps."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from shapely.geometry import MultiPolygon, Polygon

from salus.models.sensor import SensorType
from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType

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
