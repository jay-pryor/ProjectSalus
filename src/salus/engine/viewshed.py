"""Viewshed computation — determines visible cells from an observer position.

Uses GDAL's viewshed algorithm when available, falls back to a NumPy
ray-marching implementation for environments without GDAL.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel

# Azimuth coverage at or above this value means no wedge masking is needed.
_FULL_ARC_DEG: float = 360.0


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

    # Validate observer position and elevation before dispatch
    obs_row, obs_col = _xy_to_rc(site, observer_x, observer_y)
    dem_rows, dem_cols = site.dem.shape
    if not (0 <= obs_row < dem_rows and 0 <= obs_col < dem_cols):
        raise ValueError(
            f"Observer position ({observer_x}, {observer_y}) is outside the raster extent"
        )
    surface = site.surface_array()
    dem_at_obs = float(site.dem[obs_row, obs_col])
    surface_at_obs = float(surface[obs_row, obs_col])
    if np.isnan(dem_at_obs):
        raise ValueError(
            f"DEM value at observer position ({observer_x}, {observer_y}) is nodata (NaN) — "
            "cannot compute viewshed"
        )
    abs_observer_elev = dem_at_obs + observer_height
    if abs_observer_elev < surface_at_obs:
        raise ValueError(
            f"Observer height ({observer_height}m above DEM) places sensor below the surface "
            f"at observer position (DEM={dem_at_obs:.1f}m, surface={surface_at_obs:.1f}m)"
        )

    try:
        return _viewshed_gdal(site, observer_x, observer_y, observer_height, max_range)
    except (ImportError, OSError):
        return _viewshed_numpy(site, observer_x, observer_y, observer_height, max_range)


def clip_viewshed_to_sensor(
    viewshed_array: npt.NDArray[np.bool_],
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
) -> npt.NDArray[np.bool_]:
    """Clip a raw viewshed to the sensor's range and azimuth arc constraints.

    Applies two masks to the input viewshed:
    - **Range mask**: retains cells whose distance from the sensor is within
      [sensor.min_range_m, sensor.max_range_m].
    - **Azimuth mask**: retains cells that fall within the sensor's horizontal
      field of regard (azimuth_coverage_deg) centred on placement.bearing_deg.
      Skipped when azimuth_coverage_deg >= 360°.

    Note on the sensor's own position cell (dist == 0): np.arctan2(0, 0) returns
    0.0, so the cell at the exact sensor position is assigned bearing north (0°).
    Whether it is included depends on the azimuth arc and boresight. Use
    min_range_m > 0 to explicitly exclude the sensor's dead zone.

    Args:
        viewshed_array: Boolean 2D array from compute_viewshed. Not modified.
        site: Site terrain model (provides origin and resolution for cell coords).
        sensor: Sensor capability definition (range limits, azimuth arc width).
        placement: Sensor deployment position and boresight compass bearing.

    Returns:
        Boolean 2D array with cells outside sensor coverage set to False.

    Raises:
        ValueError: If viewshed_array is not 2D, or site.resolution is <= 0.
    """
    if viewshed_array.ndim != 2:
        raise ValueError(f"viewshed_array must be 2D, got {viewshed_array.ndim}D")
    if site.resolution <= 0.0:
        raise ValueError(f"site.resolution must be > 0, got {site.resolution}")

    # Normalise dtype — guards against callers passing integer or float arrays.
    viewshed_bool: npt.NDArray[np.bool_] = viewshed_array.astype(bool)

    rows, cols = viewshed_bool.shape

    # Build per-cell coordinate grids aligned with site CRS (metres).
    col_coords = site.origin_x + np.arange(cols, dtype=float) * site.resolution
    row_coords = site.origin_y - np.arange(rows, dtype=float) * site.resolution
    cell_x, cell_y = np.meshgrid(col_coords, row_coords)

    dx = cell_x - placement.position_x
    dy = cell_y - placement.position_y

    # --- Range mask ---
    dist = np.sqrt(dx**2 + dy**2)
    range_mask: npt.NDArray[np.bool_] = (dist >= sensor.min_range_m) & (dist <= sensor.max_range_m)

    # --- Azimuth mask ---
    if sensor.azimuth_coverage_deg >= _FULL_ARC_DEG:
        azimuth_mask: npt.NDArray[np.bool_] = np.ones((rows, cols), dtype=bool)
    else:
        # Compass bearing from placement to each cell: 0=north, 90=east, clockwise.
        bearing_to_cell = np.degrees(np.arctan2(dx, dy)) % _FULL_ARC_DEG
        half_arc = sensor.azimuth_coverage_deg / 2.0
        boresight = placement.bearing_deg % _FULL_ARC_DEG
        # Signed angular difference, wrapped to [-180, +180].
        diff = (bearing_to_cell - boresight + 180.0) % _FULL_ARC_DEG - 180.0
        azimuth_mask = np.abs(diff) <= half_arc

    return viewshed_bool & range_mask & azimuth_mask


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

    # Sensor height is given relative to DEM (ground level).
    # GDAL observerHeight is relative to the raster surface (DSM when available).
    # Convert: effective_h = (DEM + sensor_height) - surface_at_observer
    obs_row, obs_col = _xy_to_rc(site, observer_x, observer_y)
    effective_observer_height = (
        site.dem[obs_row, obs_col] + observer_height - surface[obs_row, obs_col]
    )

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
    err = ds.GetRasterBand(1).WriteArray(surface)
    if err != 0:
        ds = None
        raise RuntimeError(f"GDAL WriteArray failed with error code {err}")

    max_dist = max_range if max_range is not None else 0.0  # 0.0 = unlimited in GDAL

    vs_ds = gdal.ViewshedGenerate(
        ds.GetRasterBand(1),
        "MEM",
        "",
        creationOptions=[],
        observerX=observer_x,
        observerY=observer_y,
        observerHeight=effective_observer_height,
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

    # Observer absolute elevation — height above DEM (ground level), not above surface
    obs_elev = site.dem[obs_row, obs_col] + observer_height

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
            if np.isnan(elev):
                # Treat nodata cells as fully opaque — stop the ray
                break

            slope = (elev - obs_elev) / dist

            if slope > max_slope:
                max_slope = slope
                visible[ri, ci] = True

    return visible
