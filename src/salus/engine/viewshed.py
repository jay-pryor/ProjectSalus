"""Viewshed computation — determines visible cells from an observer position.

Uses GDAL's viewshed algorithm when available, falls back to a NumPy
ray-marching implementation for environments without GDAL.
"""

from __future__ import annotations

import numpy as np

from salus.models.site import SiteModel


def compute_viewshed(
    site: SiteModel,
    observer_x: float,
    observer_y: float,
    observer_height: float,
    max_range: float | None = None,
) -> np.ndarray:
    """Compute a binary viewshed from an observer position.

    Args:
        site: The site terrain model.
        observer_x: Observer easting in CRS units (metres).
        observer_y: Observer northing in CRS units (metres).
        observer_height: Observer height above ground in metres.
        max_range: Maximum analysis range in metres. None = full extent.

    Returns:
        Boolean 2D array matching site.dem shape. True = visible from observer.
    """
    # Normalise: treat 0.0 as unlimited (same as None) so both paths agree
    if max_range is not None and max_range <= 0.0:
        max_range = None

    try:
        return _viewshed_gdal(site, observer_x, observer_y, observer_height, max_range)
    except ImportError:
        return _viewshed_numpy(site, observer_x, observer_y, observer_height, max_range)


def _xy_to_rc(site: SiteModel, x: float, y: float) -> tuple[int, int]:
    """Convert CRS coordinates to row, col indices."""
    col = int((x - site.origin_x) / site.resolution)
    row = int((site.origin_y - y) / site.resolution)
    return row, col


def _viewshed_gdal(
    site: SiteModel,
    observer_x: float,
    observer_y: float,
    observer_height: float,
    max_range: float | None,
) -> np.ndarray:
    """Viewshed using GDAL — preferred path."""
    from osgeo import gdal, osr

    gdal.UseExceptions()

    surface = site.surface_array()
    rows, cols = surface.shape

    # Create in-memory raster
    driver = gdal.GetDriverByName("MEM")
    ds = driver.Create("", cols, rows, 1, gdal.GDT_Float64)
    if ds is None:
        raise RuntimeError(f"GDAL MEM driver failed to create in-memory raster ({rows}×{cols})")
    ds.SetGeoTransform(
        (
            site.origin_x,
            site.resolution,
            0,
            site.origin_y,
            0,
            -site.resolution,
        )
    )
    if site.crs_epsg:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(site.crs_epsg)
        ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(surface)

    max_dist = max_range if max_range is not None else 0.0  # 0.0 = unlimited in GDAL

    vs_ds = gdal.ViewshedGenerate(
        ds.GetRasterBand(1),
        "MEM",
        "",
        creationOptions=[],
        observerX=observer_x,
        observerY=observer_y,
        observerHeight=observer_height,
        targetHeight=0.0,
        visibleVal=1,
        invisibleVal=0,
        outOfRangeVal=0,
        noDataVal=-1,
        dfCurvCoeff=0.85714,
        mode=2,  # whole raster
        maxDistance=max_dist,
    )
    if vs_ds is None:
        ds = None
        raise RuntimeError(
            "gdal.ViewshedGenerate returned None — check observer coordinates and DEM validity"
        )

    try:
        result = vs_ds.GetRasterBand(1).ReadAsArray().astype(bool)
    finally:
        vs_ds = None
        ds = None
    return result


def _viewshed_numpy(
    site: SiteModel,
    observer_x: float,
    observer_y: float,
    observer_height: float,
    max_range: float | None,
) -> np.ndarray:
    """Pure-NumPy ray-marching viewshed — fallback when GDAL is unavailable.

    Casts rays at regular angular intervals and marches along each ray,
    tracking the maximum elevation angle seen. A cell is visible if its
    elevation angle exceeds all previous cells along the ray.
    """
    surface = site.surface_array()
    rows, cols = surface.shape
    obs_row, obs_col = _xy_to_rc(site, observer_x, observer_y)

    # Observer absolute elevation
    obs_elev = surface[obs_row, obs_col] + observer_height

    visible = np.zeros((rows, cols), dtype=bool)
    visible[obs_row, obs_col] = True

    # Max range in cells
    if max_range is not None:
        max_cells = int(max_range / site.resolution) + 1
    else:
        max_cells = int(np.sqrt(rows**2 + cols**2)) + 1

    # Cast rays at angular intervals — finer at short range via adaptive step
    num_rays = max(360, 4 * max(rows, cols))
    angles = np.linspace(0, 2 * np.pi, num_rays, endpoint=False)

    for angle in angles:
        dx = np.cos(angle)
        dy = np.sin(angle)
        max_slope = -np.inf

        for step in range(1, max_cells + 1):
            c = obs_col + dx * step
            r = obs_row - dy * step  # y-axis inverted in raster

            ci, ri = int(round(c)), int(round(r))
            if ri < 0 or ri >= rows or ci < 0 or ci >= cols:
                break

            dist = step * site.resolution
            if max_range is not None and dist > max_range:
                break

            elev = surface[ri, ci]
            slope = (elev - obs_elev) / dist

            if slope > max_slope:
                max_slope = slope
                visible[ri, ci] = True

    return visible
