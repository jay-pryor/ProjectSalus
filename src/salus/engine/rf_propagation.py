"""RF propagation models — Free-Space Path Loss (FSPL) and knife-edge diffraction."""

from __future__ import annotations

import math
import warnings

import numpy as np
import numpy.typing as npt

from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel

# Speed of light in vacuum (m/s) — ITU-R P.525
_C_M_S: float = 299_792_458.0

# Precomputed constant term: 20 * log10(4π / c)
_FSPL_CONSTANT_DB: float = 20.0 * math.log10(4.0 * math.pi / _C_M_S)

# Minimum nu below which diffraction loss is negligible (ITU-R P.526-15)
_NU_NO_LOSS_THRESHOLD: float = -0.78


def compute_fspl(distance_m: float, frequency_hz: float) -> float:
    """Compute Free-Space Path Loss (FSPL) in dB.

    Uses the standard FSPL formula (ITU-R P.525):

        FSPL (dB) = 20·log10(d) + 20·log10(f) + 20·log10(4π/c)

    where d is distance in metres, f is frequency in Hz, and c is the speed
    of light in vacuum (299 792 458 m/s).

    Args:
        distance_m: Distance between transmitter and receiver in metres. Must be > 0.
        frequency_hz: Signal frequency in Hz. Must be > 0.

    Returns:
        Path loss in dB. Subtract from transmitted power (dBm) to obtain received
        signal level. May be negative at sub-metre distances — the formula is a
        far-field approximation only.

    Raises:
        ValueError: If distance_m or frequency_hz is non-positive, NaN, or infinite.
    """
    if not math.isfinite(distance_m) or distance_m <= 0.0:
        raise ValueError(f"distance_m must be a finite positive number, got {distance_m}")
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be a finite positive number, got {frequency_hz}")

    return 20.0 * math.log10(distance_m) + 20.0 * math.log10(frequency_hz) + _FSPL_CONSTANT_DB


def _knife_edge_loss_db(nu: float) -> float:
    """ITU-R P.526-15 eq.(13) approximation for knife-edge diffraction loss in dB.

    Args:
        nu: Fresnel-Kirchhoff diffraction parameter.

    Returns:
        Diffraction loss in dB (>= 0).

    Raises:
        ValueError: If nu is NaN or infinite.
    """
    if not math.isfinite(nu):
        raise ValueError(f"nu must be finite, got {nu}")
    if nu <= _NU_NO_LOSS_THRESHOLD:
        return 0.0
    inner = math.sqrt((nu - 0.1) ** 2 + 1.0) + nu - 0.1
    if inner <= 0.0:
        return 0.0
    return 6.9 + 20.0 * math.log10(inner)


def _bilinear_interp(
    dem: npt.NDArray[np.float64],
    rows: npt.NDArray[np.float64],
    cols: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Bilinear interpolation of DEM values at fractional (row, col) positions.

    Clamps to array bounds; propagates NaN where either surrounding cell is NaN.
    """
    nrows, ncols = dem.shape
    r0 = np.floor(rows).astype(int)
    c0 = np.floor(cols).astype(int)
    r1 = r0 + 1
    c1 = c0 + 1
    r0 = np.clip(r0, 0, nrows - 1)
    r1 = np.clip(r1, 0, nrows - 1)
    c0 = np.clip(c0, 0, ncols - 1)
    c1 = np.clip(c1, 0, ncols - 1)
    dr = rows - np.floor(rows)
    dc = cols - np.floor(cols)
    return (
        dem[r0, c0] * (1.0 - dr) * (1.0 - dc)
        + dem[r0, c1] * (1.0 - dr) * dc
        + dem[r1, c0] * dr * (1.0 - dc)
        + dem[r1, c1] * dr * dc
    )


def extract_terrain_profile(
    site: SiteModel,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    num_samples: int | None = None,
) -> npt.NDArray[np.float64]:
    """Extract a terrain height profile from the DEM using bilinear interpolation.

    Samples the DEM at ``num_samples`` evenly-spaced points along the straight
    line from (x1, y1) to (x2, y2).

    Args:
        site: Site terrain model containing the DEM.
        x1, y1: Easting/northing of the start point (TX) in CRS units (m).
        x2, y2: Easting/northing of the end point (RX) in CRS units (m).
        num_samples: Number of sample points including endpoints. Defaults to
            ``max(3, ceil(path_length / resolution) + 1)`` so there is at least
            one sample per DEM cell.

    Returns:
        NDArray of shape ``(num_samples, 2)`` where column 0 is distance from
        the start point (m) and column 1 is interpolated terrain height (m).

    Raises:
        ValueError: If any coordinate is non-finite, num_samples < 2, if start
            and end points are identical, or if any sample falls outside the DEM
            extent.
    """
    for name, val in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
        if not math.isfinite(val):
            raise ValueError(f"{name} must be finite, got {val}")

    dx = x2 - x1
    dy = y2 - y1
    path_length = math.sqrt(dx * dx + dy * dy)

    if path_length == 0.0:
        raise ValueError("Start and end points are identical — path length is zero.")

    if num_samples is None:
        num_samples = max(3, math.ceil(path_length / site.resolution) + 1)

    if num_samples < 2:
        raise ValueError(f"num_samples must be >= 2, got {num_samples}")

    t = np.linspace(0.0, 1.0, num_samples)
    xs = x1 + t * dx
    ys = y1 + t * dy

    # Convert world coordinates to fractional DEM pixel indices
    cols = (xs - site.origin_x) / site.resolution
    rows = (site.origin_y - ys) / site.resolution

    nrows, ncols = site.dem.shape
    out_of_bounds = (
        (cols < 0.0).any()
        or (cols > ncols - 1).any()
        or (rows < 0.0).any()
        or (rows > nrows - 1).any()
    )
    if out_of_bounds:
        raise ValueError(
            "One or more sample points fall outside the DEM extent. "
            "Ensure TX/RX coordinates lie within the loaded terrain raster."
        )

    heights = _bilinear_interp(site.dem, rows, cols)
    distances = t * path_length

    return np.column_stack([distances, heights])


def compute_knife_edge_loss(
    terrain_profile: npt.NDArray[np.float64],
    tx_height: float,
    rx_height: float,
    frequency_hz: float,
) -> float:
    """Compute additional diffraction loss for a single knife-edge obstacle (ITU-R P.526).

    Finds the dominant terrain obstruction along the path (the point with maximum
    clearance above the direct line-of-sight), computes the Fresnel-Kirchhoff
    diffraction parameter nu, and returns the ITU-R P.526-15 diffraction loss.

    Args:
        terrain_profile: NDArray of shape ``(N, 2)`` where column 0 is cumulative
            distance from the TX (m) and column 1 is terrain height (m). Typically
            produced by :func:`extract_terrain_profile`. Must have N >= 2.
        tx_height: Absolute elevation of the transmitter (terrain + antenna height) in m.
        rx_height: Absolute elevation of the receiver (terrain + antenna height) in m.
        frequency_hz: Signal frequency in Hz. Must be finite and > 0.

    Returns:
        Additional diffraction loss in dB (>= 0). Zero when line-of-sight has
        adequate Fresnel clearance (nu <= -0.78).

    Raises:
        ValueError: If terrain_profile shape is wrong, has fewer than 2 points,
            total path length is non-positive, or frequency_hz is invalid.
    """
    if not math.isfinite(tx_height):
        raise ValueError(f"tx_height must be finite, got {tx_height}")
    if not math.isfinite(rx_height):
        raise ValueError(f"rx_height must be finite, got {rx_height}")
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be a finite positive number, got {frequency_hz}")
    if terrain_profile.ndim != 2 or terrain_profile.shape[1] != 2:
        raise ValueError(f"terrain_profile must have shape (N, 2), got {terrain_profile.shape}")
    n = terrain_profile.shape[0]
    if n < 2:
        raise ValueError(f"terrain_profile must have at least 2 points, got {n}")

    distances: npt.NDArray[np.float64] = terrain_profile[:, 0]
    heights: npt.NDArray[np.float64] = terrain_profile[:, 1]
    total_dist = float(distances[-1])

    if total_dist <= 0.0:
        raise ValueError(f"Total path length must be > 0, got {total_dist}")

    if float(distances[0]) != 0.0:
        raise ValueError(f"terrain_profile distances must start at 0.0, got {distances[0]}")

    if not np.isfinite(heights).all():
        raise ValueError(
            "terrain_profile contains non-finite height values (NaN or Inf). "
            "Check the DEM for nodata or masked cells along the profile path."
        )

    # Line-of-sight height at each sample point (linear interpolation TX → RX)
    los = tx_height + (rx_height - tx_height) * distances / total_dist

    # Clearance above LOS (positive = obstacle protrudes above LOS)
    clearance = heights - los

    # Only interior points (not TX or RX themselves) can be obstructions
    if n <= 2:
        return 0.0

    interior_clearance = clearance[1:-1]
    interior_distances = distances[1:-1]

    peak_idx = int(np.argmax(interior_clearance))
    h = float(interior_clearance[peak_idx])
    d1 = float(interior_distances[peak_idx])
    d2 = total_dist - d1

    # Guard: obstacle at an endpoint would cause division by zero
    if d1 <= 0.0 or d2 <= 0.0:
        return 0.0

    wavelength = _C_M_S / frequency_hz
    denominator = wavelength * d1 * d2
    if denominator <= 0.0:
        # Underflow to zero (subnormal float) — treat as effectively no clearance
        return 0.0

    nu = h * math.sqrt(2.0 * total_dist / denominator)

    return _knife_edge_loss_db(nu)


# ---------------------------------------------------------------------------
# S4-3: RF Coverage Grid
# ---------------------------------------------------------------------------

# Assumed consumer drone control-link transmit power (dBm). Representative
# value for 2.4/5.8 GHz ISM-band remote controllers (ITU-R M.2171 reference).
_DRONE_TX_POWER_DBM: float = 20.0

# Assumed drone AGL for RF path-loss computation (m). Conservative ground-level
# estimate — if coverage exists at terrain level, it holds at any height above.
_TARGET_HEIGHT_AGL_M: float = 0.0

# Full azimuth circle constant used for arc bypass logic.
_FULL_ARC_DEG: float = 360.0


def _parse_frequency_band_hz(band: str) -> float:
    """Parse a frequency band descriptor string to Hz.

    Recognises suffix formats GHz, MHz, kHz, Hz (case-insensitive).
    Example: ``'2.4 GHz'`` → ``2.4e9``, ``'900 MHz'`` → ``9e8``.

    Args:
        band: Frequency band string, e.g. ``'2.4 GHz'``.

    Returns:
        Frequency in Hz as a float.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    if not isinstance(band, str):
        raise ValueError(
            f"Expected a string for frequency band, got {type(band).__name__}: {band!r}"
        )
    s = band.strip().upper()
    for suffix, multiplier in (("GHZ", 1e9), ("MHZ", 1e6), ("KHZ", 1e3), ("HZ", 1.0)):
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)].strip()) * multiplier
            except ValueError:
                raise ValueError(
                    f"Cannot parse frequency value from band string: {band!r}"
                ) from None
    raise ValueError(
        f"Cannot parse frequency band string {band!r}: "
        "expected suffix GHz, MHz, kHz, or Hz (case-insensitive)"
    )


def compute_rf_coverage(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
    sensitivity_dbm: float,
    *,
    frequency_hz: float | None = None,
) -> npt.NDArray[np.bool_]:
    """Compute RF detection coverage for a sensor placement over the terrain grid.

    For each grid cell, models the drone-to-sensor RF path as:

        RSL = _DRONE_TX_POWER_DBM - (FSPL + knife_edge_loss)

    A cell is marked covered (True) when ``RSL >= sensitivity_dbm``.

    FSPL is computed vectorially for all candidates at once. Knife-edge loss is
    computed per cell only for cells where FSPL alone already gives sufficient
    signal (``RSL_fspl >= sensitivity_dbm``); cells blocked by free-space loss
    alone are definitively uncovered and skip the expensive terrain profile step.
    Azimuth arc and range constraints are applied before any propagation math.

    Args:
        site: Site terrain model.
        sensor: Sensor capability definition (range, azimuth arc).
        placement: Deployed sensor position and boresight bearing.
        sensitivity_dbm: Minimum detectable received signal level in dBm.
        frequency_hz: Operating frequency in Hz. If ``None``, the first entry of
            ``sensor.frequency_bands`` is parsed. Raises ``ValueError`` if no
            frequency can be determined.

    Returns:
        Boolean ``NDArray`` of shape ``site.dem.shape``. ``True`` = RF coverage.

    Raises:
        ValueError: If ``sensitivity_dbm`` is non-finite; if ``site.resolution``
            is not a finite positive number; if ``frequency_hz`` cannot be
            determined or is not a finite positive number; if the sensor position
            is outside the DEM extent; or if the DEM has NaN/inf at the sensor
            position.
    """
    if not math.isfinite(sensitivity_dbm):
        raise ValueError(f"sensitivity_dbm must be finite, got {sensitivity_dbm}")

    # --- Validate site resolution (used as divisor throughout) ---
    if not math.isfinite(site.resolution) or site.resolution <= 0.0:
        raise ValueError(f"site.resolution must be a finite positive number, got {site.resolution}")

    # --- Resolve operating frequency ---
    if frequency_hz is None:
        if not sensor.frequency_bands:
            raise ValueError(
                "frequency_hz not provided and sensor.frequency_bands is empty; "
                "cannot determine operating frequency"
            )
        frequency_hz = _parse_frequency_band_hz(sensor.frequency_bands[0])
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be a finite positive number, got {frequency_hz}")

    rows, cols = site.dem.shape

    # --- Validate sensor position is within DEM ---
    sensor_col_f = (placement.position_x - site.origin_x) / site.resolution
    sensor_row_f = (site.origin_y - placement.position_y) / site.resolution
    if not (0.0 <= sensor_col_f <= cols - 1 and 0.0 <= sensor_row_f <= rows - 1):
        raise ValueError(
            f"Sensor position ({placement.position_x}, {placement.position_y}) "
            "is outside the DEM extent."
        )

    # --- Build coordinate grids ---
    col_coords = site.origin_x + np.arange(cols, dtype=np.float64) * site.resolution
    row_coords = site.origin_y - np.arange(rows, dtype=np.float64) * site.resolution
    cell_x, cell_y = np.meshgrid(col_coords, row_coords)

    dx = cell_x - placement.position_x
    dy = cell_y - placement.position_y

    # --- Range mask ---
    dist: npt.NDArray[np.float64] = np.sqrt(dx**2 + dy**2)
    range_mask: npt.NDArray[np.bool_] = (dist >= sensor.min_range_m) & (dist <= sensor.max_range_m)

    # --- Azimuth mask ---
    if sensor.azimuth_coverage_deg >= _FULL_ARC_DEG:
        azimuth_mask: npt.NDArray[np.bool_] = np.ones((rows, cols), dtype=bool)
    else:
        bearing_to_cell = np.degrees(np.arctan2(dx, dy)) % _FULL_ARC_DEG
        half_arc = sensor.azimuth_coverage_deg / 2.0
        boresight = placement.bearing_deg % _FULL_ARC_DEG
        diff = (bearing_to_cell - boresight + 180.0) % _FULL_ARC_DEG - 180.0
        azimuth_mask = np.abs(diff) <= half_arc

    candidate_mask: npt.NDArray[np.bool_] = range_mask & azimuth_mask

    # --- Sensor absolute elevation ---
    sensor_terrain_h = float(
        _bilinear_interp(
            site.dem,
            np.array([sensor_row_f]),
            np.array([sensor_col_f]),
        )[0]
    )
    if not math.isfinite(sensor_terrain_h):
        raise ValueError(
            f"DEM has NaN/inf at sensor position ({placement.position_x}, "
            f"{placement.position_y}); cannot compute sensor absolute elevation."
        )
    sensor_agl = (
        placement.height_override_m
        if placement.height_override_m is not None
        else sensor.mounting_height_m
    )
    sensor_abs_h = sensor_terrain_h + sensor_agl

    # --- Vectorised FSPL for all candidate cells ---
    # Explicitly exclude the sensor cell (dist == 0) from candidates: FSPL is
    # undefined at zero distance and the cell is typically inside min_range_m.
    candidate_mask &= dist > 0.0
    safe_dist: npt.NDArray[np.float64] = np.where(dist > 0.0, dist, np.nan)
    fspl_grid: npt.NDArray[np.float64] = (
        20.0 * np.log10(safe_dist) + 20.0 * math.log10(frequency_hz) + _FSPL_CONSTANT_DB
    )
    rsl_fspl: npt.NDArray[np.float64] = _DRONE_TX_POWER_DBM - fspl_grid

    # Cells covered by FSPL alone — these are candidates for knife-edge refinement.
    # Cells where FSPL already blocks (rsl_fspl < sensitivity_dbm) are definitively
    # uncovered: knife-edge adds loss, never reduces it.
    fspl_covered: npt.NDArray[np.bool_] = candidate_mask & (rsl_fspl >= sensitivity_dbm)

    # --- Knife-edge refinement ---
    coverage: npt.NDArray[np.bool_] = fspl_covered.copy()

    cand_rows_arr, cand_cols_arr = np.nonzero(fspl_covered)
    for r_idx, c_idx in zip(cand_rows_arr.tolist(), cand_cols_arr.tolist()):
        cell_x_val = site.origin_x + c_idx * site.resolution
        cell_y_val = site.origin_y - r_idx * site.resolution
        target_terrain_h = float(site.dem[r_idx, c_idx])

        # Guard: DEM nodata (NaN/inf) at target cell — warn and skip.
        if not math.isfinite(target_terrain_h):
            warnings.warn(
                f"NaN/inf DEM value at cell ({r_idx}, {c_idx}); "
                "marking cell uncovered (check DEM for nodata gaps).",
                stacklevel=2,
            )
            coverage[r_idx, c_idx] = False
            continue

        target_abs_h = target_terrain_h + _TARGET_HEIGHT_AGL_M

        # extract_terrain_profile may raise ValueError for edge cells that fall
        # just outside the DEM after floating-point coordinate rounding. Catch
        # only that step; let compute_knife_edge_loss errors propagate — they
        # indicate a programming error (bad profile shape, non-zero start, etc).
        try:
            profile = extract_terrain_profile(
                site,
                placement.position_x,
                placement.position_y,
                cell_x_val,
                cell_y_val,
            )
        except ValueError as exc:
            warnings.warn(
                f"Terrain profile extraction failed for cell ({r_idx}, {c_idx}): {exc}",
                stacklevel=2,
            )
            coverage[r_idx, c_idx] = False
            continue

        ke_loss = compute_knife_edge_loss(
            profile,
            tx_height=sensor_abs_h,
            rx_height=target_abs_h,
            frequency_hz=frequency_hz,
        )

        rsl_total = _DRONE_TX_POWER_DBM - (float(fspl_grid[r_idx, c_idx]) + ke_loss)
        coverage[r_idx, c_idx] = rsl_total >= sensitivity_dbm

    return coverage
