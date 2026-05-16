"""Viewshed computation — determines visible cells from an observer position.

Uses GDAL's viewshed algorithm when available, falls back to a NumPy
ray-marching implementation for environments without GDAL.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import numpy.typing as npt

from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel

# Azimuth coverage at or above this value means no wedge masking is needed.
_FULL_ARC_DEG: float = 360.0

# Reference canopy height used in Bouguer-Lambert attenuation:
# transmission per step = penetration ** (canopy_height_m / _CANOPY_REFERENCE_HEIGHT_M).
# A value of 10 m represents a typical tree height; it controls the steepness of
# attenuation for cells shorter or taller than this reference.
_CANOPY_REFERENCE_HEIGHT_M: float = 10.0


def compute_viewshed(
    site: SiteModel,
    observer_x: float,
    observer_y: float,
    observer_height: float,
    max_range: float | None = None,
) -> npt.NDArray[np.bool_]:
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
    except ImportError:
        return _viewshed_numpy(site, observer_x, observer_y, observer_height, max_range)
    except OSError as exc:
        warnings.warn(
            f"GDAL raised OSError ({exc}); falling back to NumPy viewshed — "
            "results may differ from GDAL output.",
            stacklevel=2,
        )
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
        ValueError: If viewshed_array is not 2D.
    """
    if viewshed_array.ndim != 2:
        raise ValueError(f"viewshed_array must be 2D, got {viewshed_array.ndim}D")

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


def compute_viewshed_through_canopy(
    site: SiteModel,
    observer_x: float,
    observer_y: float,
    observer_height: float,
    max_range: float | None = None,
    vegetation_penetration: float = 0.0,
) -> npt.NDArray[np.float32]:
    """Compute a viewshed with optional Bouguer–Lambert canopy attenuation.

    When ``site.canopy_height_m`` is present **and** ``vegetation_penetration``
    is greater than zero, each visible cell's transmission coefficient is
    calculated by ray-marching with a 3D line-of-sight check.  For every cell
    ``j`` along the discrete ray from the observer to a candidate target ``k``,
    the LOS elevation is linearly interpolated:

    .. code-block:: text

        los_z(j) = obs_z + (target_surface_z - obs_z) * (dist_j / dist_k)

    Attenuation is applied at cell ``j`` only when the LOS elevation falls
    below the canopy top (``dem[j] + canopy_height_m[j]``).  A ray skimming
    above the canopy receives no penalty; a ray dipping into the canopy
    column is attenuated:

    .. code-block:: text

        T_target_k *= penetration ** (canopy_height_m[j] / _CANOPY_REFERENCE_HEIGHT_M)

    The returned array contains float32 transmission values in [0.0, 1.0]:

    - 1.0 = fully visible, no canopy traversal on the LOS path
    - 0.0 = terrain-occluded (not visible in the binary viewshed)
    - intermediate = partial signal penetration through canopy

    **Initialisation:** Cells visible in the binary viewshed start at 1.0.
    Visible cells that no discrete ray happens to land on (perimeter cells
    missed by integer-rounded paths) retain the 1.0 default rather than
    silently appearing as fully blocked.

    **Occlusion handling:** When the ray walk encounters a cell that is not
    visible in the binary viewshed it stops; cells beyond the occluder on
    this ray are reached by other ray angles that don't pass through it.
    Per-target accumulators are not carried past terrain occluders.

    **Observer cell:** When the sensor is at or above the canopy top at its
    own cell, transmission is 1.0.  When the sensor is below the canopy
    height at its own cell the value reflects the canopy depth above the
    sensor:

    .. code-block:: text

        T_obs = penetration ** (
            (canopy_height_m[obs] - observer_height) / _CANOPY_REFERENCE_HEIGHT_M
        )

    **NaN canopy cells** (nodata from rasterio load) are treated as canopy-free
    (no attenuation applied to that cell).  This is the conservative-open policy:
    nodata means "no CHM measurement available" rather than "confirmed dense
    canopy", so the signal is not penalised.  NaN cells in the CHM do not affect
    the >= 0 guarantee on finite values.

    **NaN terrain cells:** A nodata observer-cell DEM elevation is rejected by
    :func:`compute_viewshed` (called first), which raises :class:`ValueError`.
    A nodata target-cell surface elevation falls back to conservative 2D
    accumulation for that target (every canopy cell on the path is penalised,
    no elevation gate) rather than silently leaving the cell unattenuated.

    When ``site.canopy_height_m`` is ``None`` **or** ``vegetation_penetration``
    is 0.0, falls back to the binary viewshed (same result as
    :func:`compute_viewshed`, cast to float32).

    Args:
        site: The site terrain model.
        observer_x: Observer easting in CRS units (metres).
        observer_y: Observer northing in CRS units (metres).
        observer_height: Observer height above ground in metres.
        max_range: Maximum analysis range in metres.  ``None`` = full extent.
        vegetation_penetration: Fraction of signal passing through a unit of
            canopy (0.0–1.0).  0.0 = fully opaque canopy; 1.0 = transparent.

    Returns:
        Float32 2D array matching ``site.dem`` shape.  Values in [0.0, 1.0].

    Raises:
        ValueError: If ``vegetation_penetration`` is not in [0.0, 1.0], if
            the observer position is outside the raster extent, or if the
            observer cell has a nodata (NaN) DEM elevation.
    """
    if not (0.0 <= vegetation_penetration <= 1.0):
        raise ValueError(f"vegetation_penetration must be in [0, 1], got {vegetation_penetration}")

    binary = compute_viewshed(site, observer_x, observer_y, observer_height, max_range)

    if site.canopy_height_m is None or vegetation_penetration == 0.0:
        return binary.astype(np.float32)

    canopy = site.canopy_height_m
    dem = site.dem
    surface = site.surface_array()
    obs_row, obs_col = _xy_to_rc(site, observer_x, observer_y)
    rows, cols = dem.shape
    # obs_z is finite here: compute_viewshed() above already raises ValueError
    # if the observer DEM cell is nodata (NaN), so the LOS slopes below are
    # never contaminated by a NaN observer elevation (D-586).
    obs_z = float(dem[obs_row, obs_col]) + observer_height

    # Visible cells start at 1.0 (no known canopy traversal); non-visible at 0.0.
    # Visible cells that no ray reaches due to integer rounding retain 1.0
    # rather than silently dropping to fully-blocked.
    transmission = binary.astype(np.float32)

    if max_range is not None and max_range <= 0.0:
        max_range = None

    max_cells: int
    if max_range is not None:
        max_cells = int(max_range / site.resolution) + 1
    else:
        max_cells = int(np.sqrt(rows**2 + cols**2)) + 1

    num_rays = max(360, 4 * max(rows, cols))
    angles = np.linspace(0, 2 * np.pi, num_rays, endpoint=False)

    ray_max_t = np.zeros((rows, cols), dtype=np.float32)
    ray_touched = np.zeros((rows, cols), dtype=bool)

    for angle in angles:
        dx = np.cos(angle)
        dy = np.sin(angle)

        # Collect cells along this ray up to (but not past) the first occluder.
        ray_path: list[tuple[int, int, int]] = []
        for step in range(1, max_cells + 1):
            c = obs_col + dx * step
            r = obs_row - dy * step
            ci = int(round(c))
            ri = int(round(r))
            if ri < 0 or ri >= rows or ci < 0 or ci >= cols:
                break
            dist = step * site.resolution
            if max_range is not None and dist > max_range:
                break
            if not binary[ri, ci]:
                # Terrain occluder — stop the ray.  Cells beyond are reached by
                # other rays whose 2D paths don't cross this blocking cell.
                break
            ray_path.append((step, ri, ci))

        # For each visible cell on this ray, compute the 3D LOS attenuation by
        # walking the cells in front of it and accumulating canopy penalties
        # only where the interpolated LOS elevation falls below the canopy top.
        for k_idx, (step_k, rk, ck) in enumerate(ray_path):
            target_z = float(surface[rk, ck])
            dist_k = step_k * site.resolution
            # A nodata (NaN) target surface leaves the 3D LOS geometry
            # undefined (D-587).  Fall back to conservative 2D accumulation —
            # penalise every canopy cell in front — rather than silently
            # leaving the cell unattenuated at 1.0.
            los_defined = not math.isnan(target_z)
            los_slope = (target_z - obs_z) / dist_k if los_defined else 0.0

            t = 1.0
            for step_j, rj, cj in ray_path[: k_idx + 1]:
                ch = float(canopy[rj, cj])
                # NaN → no CHM measurement available; negative finite values
                # are clamped to 0 even though the SiteModel validator rejects
                # them, so future relaxations don't bypass the guard here.
                if math.isnan(ch) or ch <= 0.0:
                    continue
                dem_j = float(dem[rj, cj])
                canopy_top_j = dem_j + ch
                los_z = obs_z + los_slope * (step_j * site.resolution)
                if not los_defined or los_z < canopy_top_j:
                    t *= vegetation_penetration ** (ch / _CANOPY_REFERENCE_HEIGHT_M)

            if not ray_touched[rk, ck] or t > ray_max_t[rk, ck]:
                ray_max_t[rk, ck] = t
                ray_touched[rk, ck] = True

    # Apply ray results.  Visible cells touched by at least one ray take the
    # max-over-rays transmission; visible cells missed by all rays keep the 1.0
    # baseline; non-visible cells stay at 0.0.
    transmission[ray_touched] = ray_max_t[ray_touched]

    # Observer cell: signal originates at the sensor, so the on-cell value
    # reflects the canopy depth above the sensor.  Above-canopy or no-canopy
    # observers see their own cell at 1.0.
    obs_ch = float(canopy[obs_row, obs_col])
    if math.isnan(obs_ch) or obs_ch <= 0.0 or observer_height >= obs_ch:
        transmission[obs_row, obs_col] = 1.0
    else:
        canopy_above_sensor = obs_ch - observer_height
        transmission[obs_row, obs_col] = vegetation_penetration ** (
            canopy_above_sensor / _CANOPY_REFERENCE_HEIGHT_M
        )

    return transmission


def line_of_sight_3d(
    site: SiteModel,
    x1: float,
    y1: float,
    z1_abs: float,
    x2: float,
    y2: float,
    z2_abs: float,
) -> bool:
    """Check line-of-sight between two absolute 3D positions against site terrain.

    Ray-marches from (x1, y1, z1_abs) to (x2, y2, z2_abs) at intervals of
    ``site.resolution``, sampling the surface (DSM when available, else DEM) at
    each horizontal position and checking whether terrain rises above the ray.

    Out-of-bounds sample positions are skipped — terrain outside the site
    extent does not occlude the ray.  A NaN surface value is treated as a
    solid obstruction (returns False).

    Args:
        site: Site terrain model providing the surface array and grid geometry.
        x1: CRS easting of the first point (metres).
        y1: CRS northing of the first point (metres).
        z1_abs: Absolute elevation of the first point (metres ASL).
        x2: CRS easting of the second point (metres).
        y2: CRS northing of the second point (metres).
        z2_abs: Absolute elevation of the second point (metres ASL).

    Returns:
        True if terrain does not occlude the ray between the two points.
        False if terrain rises above the ray at any sampled position.

    Raises:
        ValueError: If any coordinate is non-finite.
    """
    if not all(math.isfinite(v) for v in (x1, y1, z1_abs, x2, y2, z2_abs)):
        raise ValueError(
            f"All coordinates must be finite, got ({x1}, {y1}, {z1_abs}) → ({x2}, {y2}, {z2_abs})"
        )

    h_dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if h_dist == 0.0:
        # Same horizontal position — no terrain path to march along.
        return True

    surface = site.surface_array()
    # Sample at every resolution step; add 2 to include both endpoints.
    num_steps = max(2, int(h_dist / site.resolution) + 2)

    for i in range(num_steps):
        t = i / (num_steps - 1)
        sx = x1 + t * (x2 - x1)
        sy = y1 + t * (y2 - y1)
        ray_elev = z1_abs + t * (z2_abs - z1_abs)

        col = int((sx - site.origin_x) / site.resolution)
        row = int((site.origin_y - sy) / site.resolution)

        if not (0 <= row < site.rows and 0 <= col < site.cols):
            continue  # Outside DEM extent — skip.

        terrain_elev = float(surface[row, col])
        if math.isnan(terrain_elev):
            return False  # Nodata treated as solid obstruction.
        if terrain_elev > ray_elev:
            return False  # Terrain rises above the ray.

    return True


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
