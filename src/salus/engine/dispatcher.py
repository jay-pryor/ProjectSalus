"""Sensor-type coverage dispatcher — single entry point for coverage computation."""

from __future__ import annotations

import math
from typing import assert_never

import numpy as np
import numpy.typing as npt

from salus.engine.acoustic import compute_acoustic_coverage
from salus.engine.rf_propagation import compute_rf_coverage
from salus.engine.viewshed import clip_viewshed_to_sensor, compute_viewshed
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel

# Default RF sensitivity used by the dispatcher when not explicitly provided.
# Representative value for passive spectrum-analyser sensors (e.g. DroneShield RfOne).
_DEFAULT_SENSITIVITY_DBM: float = -70.0

# Default ambient noise for acoustic sensors when not explicitly provided.
# Corresponds to the sensor's quiet-reference condition (no penalty applied).
_DEFAULT_AMBIENT_NOISE_DB: float = 0.0


def compute_sensor_coverage(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
    *,
    sensitivity_dbm: float = _DEFAULT_SENSITIVITY_DBM,
    ambient_noise_db: float = _DEFAULT_AMBIENT_NOISE_DB,
) -> npt.NDArray[np.bool_]:
    """Compute detection coverage for a sensor placement.

    Routes to the appropriate propagation model based on ``sensor.type``:

    - **Radar**, **EO_IR** → :func:`~salus.engine.viewshed.compute_viewshed`
      followed by :func:`~salus.engine.viewshed.clip_viewshed_to_sensor`
      (terrain line-of-sight with range and azimuth arc clipping).
    - **RF** → :func:`~salus.engine.rf_propagation.compute_rf_coverage`
      (FSPL + knife-edge diffraction, no LOS requirement).
    - **Acoustic** → :func:`~salus.engine.acoustic.compute_acoustic_coverage`
      (range circle with ambient noise penalty, no terrain occlusion).

    Args:
        site: Site terrain model.
        sensor: Sensor capability definition. ``sensor.type`` determines routing.
        placement: Deployed sensor position and boresight bearing.
        sensitivity_dbm: Minimum detectable received signal level (dBm). Used
            only for ``SensorType.RF``. Default: ``_DEFAULT_SENSITIVITY_DBM``.
        ambient_noise_db: Ambient noise penalty (dB) relative to quiet baseline.
            Used only for ``SensorType.Acoustic``. Default: ``_DEFAULT_AMBIENT_NOISE_DB``.

    Returns:
        Boolean ``NDArray`` of shape ``site.dem.shape``. ``True`` = sensor can
        detect a target at that cell.

    Raises:
        ValueError: If ``sensor.type`` is not a recognised ``SensorType``.
    """
    match sensor.type:
        case SensorType.Radar | SensorType.EO_IR:
            return _viewshed_coverage(site, sensor, placement)
        case SensorType.RF:
            return compute_rf_coverage(site, sensor, placement, sensitivity_dbm)
        case SensorType.Acoustic:
            return compute_acoustic_coverage(site, sensor, placement, ambient_noise_db)
        case _ as unreachable:
            assert_never(unreachable)


def _viewshed_coverage(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
) -> npt.NDArray[np.bool_]:
    """Compute viewshed-based coverage for a Radar or EO/IR sensor."""
    sensor_agl = (
        placement.height_override_m
        if placement.height_override_m is not None
        else sensor.mounting_height_m
    )
    if not math.isfinite(sensor_agl):
        raise ValueError(
            f"sensor height AGL is non-finite ({sensor_agl}); "
            "check placement.height_override_m and sensor.mounting_height_m"
        )
    raw_viewshed = compute_viewshed(
        site,
        placement.position_x,
        placement.position_y,
        sensor_agl,
    )
    return clip_viewshed_to_sensor(raw_viewshed, site, sensor, placement)
