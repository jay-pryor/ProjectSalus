"""Map rendering — coverage maps, gap maps, and site overview maps."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from shapely.geometry import MultiPolygon, Polygon

from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType

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
