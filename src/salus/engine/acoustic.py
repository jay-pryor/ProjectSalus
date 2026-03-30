"""Acoustic detection coverage model."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel

# Acoustic pressure decays as 1/r (inverse distance); in dB this is 20·log10(r).
# Effective range scales as 10^(-noise_db / 20): +6 dB ambient noise halves range,
# +20 dB reduces range to one tenth.
_ACOUSTIC_NOISE_EXPONENT: float = 20.0


def compute_acoustic_coverage(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
    ambient_noise_db: float,
) -> npt.NDArray[np.bool_]:
    """Compute acoustic detection coverage as a range circle with noise penalty.

    Models acoustic sensor detection as a simple range circle with no terrain
    occlusion — sound diffracts around obstacles at the frequencies relevant to
    drone detection, so line-of-sight is not required.

    Ambient noise reduces the effective detection range according to:

        effective_range = sensor.max_range_m * 10 ** (-ambient_noise_db / 20)

    At ``ambient_noise_db = 0`` the effective range equals ``sensor.max_range_m``
    (the sensor's quiet-condition specification). Positive values represent noise
    above the quiet baseline and reduce the detectable range; the result is capped
    at ``sensor.max_range_m`` so negative values (quieter than baseline) do not
    inflate range beyond the sensor's rated maximum.

    ``sensor.min_range_m`` is applied as a dead-zone exclusion. No azimuth
    restriction is applied (acoustic sensors detect in all directions).

    Args:
        site: Site terrain model (provides grid geometry only; DEM values are
            not used because acoustic coverage is terrain-independent).
        sensor: Sensor capability definition (``max_range_m``, ``min_range_m``).
        placement: Deployed sensor position.
        ambient_noise_db: Ambient acoustic noise level relative to the sensor's
            quiet-condition reference (dB). Zero = quiet baseline; positive values
            reduce effective range.

    Returns:
        Boolean ``NDArray`` of shape ``site.dem.shape``. ``True`` = acoustic
        coverage.

    Raises:
        ValueError: If any input is non-finite or out of range: ``ambient_noise_db``
            non-finite; ``site.resolution`` non-positive; ``site.origin_x`` or
            ``site.origin_y`` non-finite; ``sensor.max_range_m`` or
            ``sensor.min_range_m`` non-finite; ``placement.position_x`` or
            ``placement.position_y`` non-finite.
    """
    if not math.isfinite(ambient_noise_db):
        raise ValueError(f"ambient_noise_db must be finite, got {ambient_noise_db}")
    if not math.isfinite(site.resolution) or site.resolution <= 0.0:
        raise ValueError(f"site.resolution must be a finite positive number, got {site.resolution}")
    for _name, _val in (("site.origin_x", site.origin_x), ("site.origin_y", site.origin_y)):
        if not math.isfinite(_val):
            raise ValueError(f"{_name} must be finite, got {_val}")
    if not math.isfinite(sensor.max_range_m):
        raise ValueError(f"sensor.max_range_m must be finite, got {sensor.max_range_m}")
    if not math.isfinite(sensor.min_range_m):
        raise ValueError(f"sensor.min_range_m must be finite, got {sensor.min_range_m}")
    for _name, _val in (
        ("placement.position_x", placement.position_x),
        ("placement.position_y", placement.position_y),
    ):
        if not math.isfinite(_val):
            raise ValueError(f"{_name} must be finite, got {_val}")

    # Effective range after ambient noise penalty.
    # numpy float64 arithmetic with overflow silenced: extreme negative
    # ambient_noise_db values produce inf (not OverflowError), then the subsequent
    # min() caps the result at sensor.max_range_m.
    with np.errstate(over="ignore"):
        effective_range = float(
            sensor.max_range_m * np.float64(10.0) ** (-ambient_noise_db / _ACOUSTIC_NOISE_EXPONENT)
        )
    effective_range = min(effective_range, sensor.max_range_m)

    rows, cols = site.dem.shape
    col_coords = site.origin_x + np.arange(cols, dtype=np.float64) * site.resolution
    row_coords = site.origin_y - np.arange(rows, dtype=np.float64) * site.resolution
    cell_x, cell_y = np.meshgrid(col_coords, row_coords)

    dx = cell_x - placement.position_x
    dy = cell_y - placement.position_y
    dist: npt.NDArray[np.float64] = np.sqrt(dx**2 + dy**2)

    return (dist >= sensor.min_range_m) & (dist <= effective_range)
