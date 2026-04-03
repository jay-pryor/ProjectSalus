"""3D trajectory detection analysis.

Provides point-level sensor detection queries and full trajectory analysis
including binary-search-refined detection event timing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from salus.engine.viewshed import line_of_sight_3d
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel
from salus.models.threat import DroneTrajectory, TrajectoryWaypoint

# Azimuth arc at or above this value means no wedge masking is needed.
_FULL_ARC_DEG: float = 360.0

# Binary search tolerance divisor: crossing is found to segment_length_m / DIVISOR.
_BINARY_SEARCH_DIVISOR: float = 100.0


@dataclass(frozen=True)
class DetectionEvent:
    """A single sensor detection crossing on a drone trajectory.

    Captures the first moment a sensor transitions from non-detecting to
    detecting at a specific point along the trajectory.  All timing and
    position fields are at the refined (binary-search) crossing point.

    Attributes:
        sensor_name: Name of the sensor that detected the drone.
        time_s: Time along the trajectory (seconds from start) when detection
            first occurred.
        position_x: CRS easting at the detection crossing point (metres).
        position_y: CRS northing at the detection crossing point (metres).
        position_z_agl: AGL altitude at the detection crossing point (metres).
        distance_to_asset_m: Remaining piecewise-linear trajectory distance
            from the detection point to the final waypoint (metres).
        segment_index: Zero-based index of the trajectory segment (waypoint
            pair) in which the detection crossing occurred.
    """

    sensor_name: str
    time_s: float
    position_x: float
    position_y: float
    position_z_agl: float
    distance_to_asset_m: float
    segment_index: int


@dataclass(frozen=True)
class TrajectoryResult:
    """Aggregated detection analysis for one drone trajectory.

    Attributes:
        detection_events: All detection crossings (undetected → detected),
            sorted by ``time_s`` ascending.  One entry per sensor per crossing.
        first_detection: The earliest ``DetectionEvent`` across all sensors,
            or None if the asset is reached without any sensor detecting the
            drone.
        time_to_asset_s: Total traversal time for the trajectory
            (``total_length / speed_ms``).
        time_in_detection_s: Total time at least one sensor was detecting the
            drone.
        time_undetected_s: Total time no sensor was detecting
            (``time_to_asset_s - time_in_detection_s``).
        asset_reached_undetected: True if the drone reached the final waypoint
            without ever being detected.
        last_gap_before_asset_m: Length of the final contiguous undetected
            stretch immediately before the asset (metres).  0.0 if the drone
            was detected all the way to the asset.
    """

    detection_events: tuple[DetectionEvent, ...]
    first_detection: DetectionEvent | None
    time_to_asset_s: float
    time_in_detection_s: float
    time_undetected_s: float
    asset_reached_undetected: bool
    last_gap_before_asset_m: float


def analyse_trajectory(
    site: SiteModel,
    sensor_placements: list[tuple[SensorDefinition, SensorPlacement]],
    trajectory: DroneTrajectory,
    segment_length_m: float = 1.0,
) -> TrajectoryResult:
    """Walk a 3D trajectory and compute per-sensor detection events.

    Steps along each trajectory segment at ``segment_length_m`` intervals,
    checking all sensors at each sample point via ``sensor_can_detect_point``.
    When a per-sensor detection transition (undetected → detected) is found
    between consecutive samples, binary search within that interval finds the
    crossing to within ``segment_length_m / 100`` precision.

    The trajectory's final waypoint is treated as the protected asset.

    Args:
        site: Site terrain model.
        sensor_placements: All active sensors as ``(SensorDefinition,
            SensorPlacement)`` pairs.  An empty list produces a result with no
            detection events.
        trajectory: 3D piecewise-linear drone trajectory with constant speed.
        segment_length_m: Sampling interval in metres along each segment.
            Smaller values increase fidelity and computation time.  Must be > 0.

    Returns:
        TrajectoryResult with all detection events and aggregate timing.

    Raises:
        ValueError: If ``segment_length_m`` is not a finite value > 0.
    """
    if not math.isfinite(segment_length_m) or segment_length_m <= 0.0:
        raise ValueError(f"segment_length_m must be a finite value > 0, got {segment_length_m}")

    waypoints = trajectory.waypoints
    speed = trajectory.speed_ms
    n_sensors = len(sensor_placements)
    tolerance = segment_length_m / _BINARY_SEARCH_DIVISOR

    # ------------------------------------------------------------------
    # Pre-compute segment geometry
    # ------------------------------------------------------------------
    seg_lengths: list[float] = []
    total_length = 0.0
    for wa, wb in zip(waypoints[:-1], waypoints[1:]):
        length = math.sqrt((wb.x - wa.x) ** 2 + (wb.y - wa.y) ** 2 + (wb.z_agl - wa.z_agl) ** 2)
        seg_lengths.append(length)
        total_length += length

    if total_length == 0.0:
        # Degenerate: all waypoints coincide.
        return TrajectoryResult(
            detection_events=(),
            first_detection=None,
            time_to_asset_s=0.0,
            time_in_detection_s=0.0,
            time_undetected_s=0.0,
            asset_reached_undetected=True,
            last_gap_before_asset_m=0.0,
        )

    time_to_asset_s = total_length / speed

    # ------------------------------------------------------------------
    # Inner helpers (capture site / sensor_placements from outer scope)
    # ------------------------------------------------------------------

    def _interp(
        wa: TrajectoryWaypoint, wb: TrajectoryWaypoint, seg_len: float, d: float
    ) -> tuple[float, float, float]:
        """Linearly interpolate position at distance d along a segment."""
        t = max(0.0, min(1.0, d / seg_len)) if seg_len > 0.0 else 0.0
        return (
            wa.x + t * (wb.x - wa.x),
            wa.y + t * (wb.y - wa.y),
            wa.z_agl + t * (wb.z_agl - wa.z_agl),
        )

    def _detect_one(idx: int, x: float, y: float, z: float) -> bool:
        """Check a single sensor by index.

        Propagates ValueError from sensor_can_detect_point (e.g. sensor
        placement outside DEM) — these are configuration errors that must
        not be silently absorbed.  Returns False only for targets outside
        the DEM extent (not a configuration error).
        """
        sdef, spl = sensor_placements[idx]
        return sensor_can_detect_point(site, sdef, spl, x, y, z)

    def _detect_any(x: float, y: float, z: float) -> bool:
        """True if any sensor detects at (x, y, z)."""
        return any(_detect_one(j, x, y, z) for j in range(n_sensors))

    def _bisect_sensor(
        wa: TrajectoryWaypoint,
        wb: TrajectoryWaypoint,
        seg_len: float,
        d_lo: float,
        d_hi: float,
        initial_state: bool,
        sensor_idx: int,
    ) -> float:
        """Binary search for per-sensor detection crossing within [d_lo, d_hi]."""
        while d_hi - d_lo > tolerance:
            d_mid = (d_lo + d_hi) / 2.0
            x, y, z = _interp(wa, wb, seg_len, d_mid)
            if _detect_one(sensor_idx, x, y, z) == initial_state:
                d_lo = d_mid
            else:
                d_hi = d_mid
        return (d_lo + d_hi) / 2.0

    def _bisect_any(
        wa: TrajectoryWaypoint,
        wb: TrajectoryWaypoint,
        seg_len: float,
        d_lo: float,
        d_hi: float,
        initial_state: bool,
    ) -> float:
        """Binary search for 'any sensor' detection crossing within [d_lo, d_hi]."""
        while d_hi - d_lo > tolerance:
            d_mid = (d_lo + d_hi) / 2.0
            x, y, z = _interp(wa, wb, seg_len, d_mid)
            if _detect_any(x, y, z) == initial_state:
                d_lo = d_mid
            else:
                d_hi = d_mid
        return (d_lo + d_hi) / 2.0

    # ------------------------------------------------------------------
    # Initialise state at the start of the trajectory
    # ------------------------------------------------------------------
    start = waypoints[0]
    prev_det: list[bool] = [_detect_one(j, start.x, start.y, start.z_agl) for j in range(n_sensors)]
    prev_any: bool = any(prev_det)

    detection_events: list[DetectionEvent] = []

    # If the drone starts inside detection range, record initial events.
    if prev_any:
        for j, (sdef, _) in enumerate(sensor_placements):
            if prev_det[j]:
                detection_events.append(
                    DetectionEvent(
                        sensor_name=sdef.name,
                        time_s=0.0,
                        position_x=start.x,
                        position_y=start.y,
                        position_z_agl=start.z_agl,
                        distance_to_asset_m=total_length,
                        segment_index=0,
                    )
                )

    # Timing accumulators
    time_in_det: float = 0.0
    # det_start_d: cumulative distance where current "any detected" period began.
    # None means no detection period has started yet.
    det_start_d: float | None = 0.0 if prev_any else None
    last_exit_d: float = 0.0  # cumulative distance of last exit from detection

    # ------------------------------------------------------------------
    # Walk through segments
    # ------------------------------------------------------------------
    cum_d_seg_start: float = 0.0  # cumulative distance at start of current segment

    for seg_idx, (wa, wb, seg_len) in enumerate(zip(waypoints[:-1], waypoints[1:], seg_lengths)):
        if seg_len == 0.0:
            continue

        d_prev: float = 0.0

        while d_prev < seg_len:
            d_next = min(d_prev + segment_length_m, seg_len)
            x_next, y_next, z_next = _interp(wa, wb, seg_len, d_next)
            new_det: list[bool] = [_detect_one(j, x_next, y_next, z_next) for j in range(n_sensors)]
            new_any = any(new_det)

            # Per-sensor: undetected → detected transitions only.
            for j, (sdef, _) in enumerate(sensor_placements):
                if not prev_det[j] and new_det[j]:
                    d_cross = _bisect_sensor(wa, wb, seg_len, d_prev, d_next, False, j)
                    cum_d_cross = cum_d_seg_start + d_cross
                    cx, cy, cz = _interp(wa, wb, seg_len, d_cross)
                    detection_events.append(
                        DetectionEvent(
                            sensor_name=sdef.name,
                            time_s=cum_d_cross / speed,
                            position_x=cx,
                            position_y=cy,
                            position_z_agl=cz,
                            distance_to_asset_m=total_length - cum_d_cross,
                            segment_index=seg_idx,
                        )
                    )

            # "Any sensor" timing transitions.
            if not prev_any and new_any:
                d_cross_any = _bisect_any(wa, wb, seg_len, d_prev, d_next, False)
                det_start_d = cum_d_seg_start + d_cross_any
            elif prev_any and not new_any:
                d_cross_any = _bisect_any(wa, wb, seg_len, d_prev, d_next, True)
                exit_d = cum_d_seg_start + d_cross_any
                if det_start_d is not None:
                    # Clamp against floating-point rounding that can make the
                    # interval slightly negative when det_start_d was just set.
                    time_in_det += max(0.0, (exit_d - det_start_d) / speed)
                last_exit_d = exit_d

            prev_det = new_det
            prev_any = new_any
            d_prev = d_next

        cum_d_seg_start += seg_len

    # Close any open detection period at the trajectory end.
    if prev_any:
        if det_start_d is not None:
            time_in_det += max(0.0, (total_length - det_start_d) / speed)
        last_gap_before_asset_m: float = 0.0
    elif det_start_d is None:
        # Never entered detection.
        last_gap_before_asset_m = total_length
    else:
        last_gap_before_asset_m = total_length - last_exit_d

    # Clamp against floating-point accumulation overshoot.
    time_in_det = min(time_in_det, time_to_asset_s)
    time_undetected_s: float = max(0.0, time_to_asset_s - time_in_det)
    sorted_events: tuple[DetectionEvent, ...] = tuple(
        sorted(detection_events, key=lambda e: e.time_s)
    )
    first_det = sorted_events[0] if sorted_events else None
    # asset_reached_undetected is True only if the drone was NEVER detected at
    # any point along the trajectory (not just "not detected at arrival").
    asset_reached_undetected = first_det is None

    return TrajectoryResult(
        detection_events=sorted_events,
        first_detection=first_det,
        time_to_asset_s=time_to_asset_s,
        time_in_detection_s=time_in_det,
        time_undetected_s=time_undetected_s,
        asset_reached_undetected=asset_reached_undetected,
        last_gap_before_asset_m=last_gap_before_asset_m,
    )


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
