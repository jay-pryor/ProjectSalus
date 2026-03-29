"""Map rendering — coverage maps, gap maps, and site overview maps."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from salus.models.site import SiteModel


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
) -> Path:
    """Render a coverage map overlaid on terrain hillshade.

    Args:
        site: The site terrain model.
        coverage: Boolean 2D array — True = covered.
        output_path: Where to save the PNG.
        title: Map title.
        sensor_positions: Optional list of (x, y) positions to mark on the map.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    min_x, max_x, min_y, max_y = site.extent
    extent = (min_x, max_x, min_y, max_y)

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))

    # Hillshade background
    hs = _hillshade(site.dem)
    ax.imshow(hs, cmap="gray", extent=extent, origin="upper", alpha=0.7)

    # Coverage overlay — green where covered, transparent where not
    cov_display = np.ma.masked_where(~coverage, coverage.astype(float))
    cov_cmap = ListedColormap(["#2ecc71"])
    ax.imshow(cov_display, cmap=cov_cmap, extent=extent, origin="upper", alpha=0.5)

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
    try:
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path
