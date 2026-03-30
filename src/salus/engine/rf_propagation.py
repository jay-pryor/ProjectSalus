"""RF propagation models — Free-Space Path Loss (FSPL) and knife-edge diffraction."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

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
