"""3D trajectory detection analysis.

Provides point-level sensor detection queries and the foundation for
full trajectory analysis (implemented in Slices 6.3–6.5).
"""

from __future__ import annotations

import math

from salus.engine.viewshed import line_of_sight_3d
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel

# Azimuth arc at or above this value means no wedge masking is needed.
_FULL_ARC_DEG: float = 360.0


def sensor_can_detect_point(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
    tx: float,
    ty: float,
    tz_agl: float,
) -> bool:
    """Check whether a sensor can detect a target at a specific 3D position.

    Applies four checks in order, returning False as soon as any fails:

    1. **LOS** (if ``sensor.requires_los``): ``line_of_sight_3d`` from sensor
       to target.
    2. **3D slant range**: distance from sensor to target within
       ``[sensor.min_range_m, sensor.max_range_m]``.
    3. **Azimuth**: horizontal bearing to target within sensor's azimuth arc
       centred on ``placement.bearing_deg``.  Skipped for 360° sensors.
    4. **Elevation angle**: elevation angle from sensor to target within
       ``[sensor.elevation_boresight_deg ± sensor.elevation_coverage_deg / 2]``.

    Target and sensor absolute elevations are computed as
    ``DEM[cell] + height_above_ground``.  If the target falls outside the site
    DEM extent, or the DEM value at the target cell is NaN, the target is
    considered undetectable (returns False).

    Args:
        site: Site terrain model.
        sensor: Sensor capability definition.
        placement: Sensor deployment position, boresight, and optional height
            override.
        tx: Target CRS easting in metres.
        ty: Target CRS northing in metres.
        tz_agl: Target altitude above ground level in metres (>= 0).

    Returns:
        True if the sensor detects the target at ``(tx, ty, tz_agl)``.

    Raises:
        ValueError: If the sensor placement position is outside the site DEM.
        ValueError: If ``tz_agl`` is non-finite.
    """
    if not math.isfinite(tz_agl):
        raise ValueError(f"tz_agl must be finite, got {tz_agl}")

    # --- Sensor absolute elevation ---
    s_result = _row_col(site, placement.position_x, placement.position_y)
    if s_result is None:
        raise ValueError(
            f"Sensor position ({placement.position_x}, {placement.position_y}) "
            "is outside the site DEM extent"
        )
    s_row, s_col = s_result
    sensor_dem_val = float(site.dem[s_row, s_col])
    if math.isnan(sensor_dem_val):
        raise ValueError(
            f"DEM value at sensor position ({placement.position_x}, {placement.position_y}) "
            "is nodata (NaN) — cannot compute detection"
        )
    sensor_mount_h = (
        placement.height_override_m
        if placement.height_override_m is not None
        else sensor.mounting_height_m
    )
    sz_abs = sensor_dem_val + sensor_mount_h

    # --- Target absolute elevation ---
    t_result = _row_col(site, tx, ty)
    if t_result is None:
        return False  # Target outside site — cannot detect.
    t_row, t_col = t_result
    target_dem_val = float(site.dem[t_row, t_col])
    if math.isnan(target_dem_val):
        return False  # Nodata at target — cannot detect.
    tz_abs = target_dem_val + tz_agl

    sx, sy = placement.position_x, placement.position_y

    # --- Check 1: Line-of-sight ---
    if sensor.requires_los:
        if not line_of_sight_3d(site, sx, sy, sz_abs, tx, ty, tz_abs):
            return False

    # --- Check 2: 3D slant range ---
    slant_range = math.sqrt((tx - sx) ** 2 + (ty - sy) ** 2 + (tz_abs - sz_abs) ** 2)
    if not (sensor.min_range_m <= slant_range <= sensor.max_range_m):
        return False

    # --- Check 3: Azimuth arc ---
    dx = tx - sx
    dy = ty - sy
    if sensor.azimuth_coverage_deg < _FULL_ARC_DEG:
        bearing_to_target = math.degrees(math.atan2(dx, dy)) % _FULL_ARC_DEG
        half_az = sensor.azimuth_coverage_deg / 2.0
        boresight_az = placement.bearing_deg % _FULL_ARC_DEG
        az_diff = (bearing_to_target - boresight_az + 180.0) % _FULL_ARC_DEG - 180.0
        if abs(az_diff) > half_az:
            return False

    # --- Check 4: Elevation angle ---
    h_dist = math.sqrt(dx**2 + dy**2)
    if h_dist > 0.0:
        elevation_angle_deg = math.degrees(math.atan2(tz_abs - sz_abs, h_dist))
    else:
        # Target at same horizontal position as sensor (h_dist == 0).
        # Convention: treat as +90° (straight up) when at or above sensor,
        # -90° (straight down) when below. A sensor whose elevation arc does
        # not include ±90° will therefore report False for co-located targets.
        elevation_angle_deg = 90.0 if tz_abs >= sz_abs else -90.0
    half_elev = sensor.elevation_coverage_deg / 2.0
    if abs(elevation_angle_deg - sensor.elevation_boresight_deg) > half_elev:
        return False

    return True


def _row_col(site: SiteModel, x: float, y: float) -> tuple[int, int] | None:
    """Convert CRS coordinates to (row, col), or None if outside DEM bounds."""
    col = int((x - site.origin_x) / site.resolution)
    row = int((site.origin_y - y) / site.resolution)
    if 0 <= row < site.rows and 0 <= col < site.cols:
        return row, col
    return None
