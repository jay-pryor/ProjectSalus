"""Adversarial path planning — 3D detection cost grid and Dijkstra's search.

Provides tools to autonomously discover the worst-case drone approach route:
the path that minimises detection exposure by exploiting terrain masking and
sensor coverage gaps.

Workflow:
    1. Build a 3D detection cost grid with ``build_detection_cost_grid``.
       Each cell holds the count of sensors that can detect a drone at that
       (row, col, altitude) position.
    2. Search for the minimum-cost path with ``find_adversarial_trajectory``.
       Dijkstra's algorithm finds the route that minimises cumulative detection
       exposure over the full approach to the protected asset.
    3. Pass the returned ``DroneTrajectory`` to ``analyse_trajectory`` for the
       full per-sensor detection timeline.
"""

from __future__ import annotations

import heapq
import logging
import math
import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from salus.engine.trajectory import sensor_can_detect_point
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel
from salus.models.threat import DroneTrajectory, TrajectoryWaypoint

_log = logging.getLogger(__name__)

# Default altitude bands (AGL, metres) used when none are specified.
_DEFAULT_ALTITUDE_BANDS_M: list[float] = [10.0, 30.0, 60.0, 100.0, 150.0]

# Weight applied per metre of altitude change in the Dijkstra edge cost.
_DEFAULT_ALTITUDE_TRANSITION_COST: float = 0.5

# Diagonal distance factor for horizontal 8-connectivity neighbours.
_SQRT2: float = math.sqrt(2.0)

# Minimum number of altitude bands allowed.
_MIN_ALTITUDE_BANDS: int = 1


@dataclass
class DetectionCostGrid:
    """3D raster of sensor detection counts across the site volume.

    Each cell ``grid[band_idx, row, col]`` holds the number of sensors that
    can detect a drone flying at altitude ``altitude_bands_m[band_idx]`` AGL
    at the cell centroid ``(col, row)``.  A value of 0 means the point is
    undetected by all sensors (a coverage gap).

    Attributes:
        grid: Integer array of shape ``(n_altitude_bands, rows, cols)``.
            Values are sensor detection counts >= 0.
        altitude_bands_m: Ordered list of AGL altitudes (metres) corresponding
            to the first axis of ``grid``.
        origin_x: CRS easting of the top-left corner of cell (0, 0) (metres).
        origin_y: CRS northing of the top-left corner of cell (0, 0) (metres).
        resolution: Metres per grid cell.
        rows: Number of rows in the grid.
        cols: Number of columns in the grid.
    """

    grid: npt.NDArray[np.int32]
    altitude_bands_m: list[float]
    origin_x: float
    origin_y: float
    resolution: float
    rows: int
    cols: int


def build_detection_cost_grid(
    site: SiteModel,
    sensor_placements: list[tuple[SensorDefinition, SensorPlacement]],
    altitude_bands_m: list[float] | None = None,
) -> DetectionCostGrid:
    """Build a 3D sensor detection count grid across the site volume.

    For each cell ``(row, col)`` at each altitude band, queries every sensor
    with ``sensor_can_detect_point`` and records the total number of sensors
    that detect a drone at that position.

    The grid is built once per sensor layout change and reused for all path
    queries.  Points outside the DEM or with NaN terrain values are treated as
    undetectable (detection count 0) for that cell.

    Args:
        site: Site terrain model.
        sensor_placements: All active sensors as ``(SensorDefinition,
            SensorPlacement)`` pairs.
        altitude_bands_m: Ordered list of AGL altitudes to evaluate (metres).
            All values must be finite and >= 0.  Defaults to
            ``[10, 30, 60, 100, 150]`` if not provided.

    Returns:
        A ``DetectionCostGrid`` covering the full site extent at each
        requested altitude band.

    Raises:
        ValueError: If ``altitude_bands_m`` is empty or contains non-finite
            or negative values.
    """
    effective_bands: list[float] = (
        list(altitude_bands_m) if altitude_bands_m is not None else _DEFAULT_ALTITUDE_BANDS_M
    )
    if len(effective_bands) == 0:
        raise ValueError("altitude_bands_m must not be empty")
    for band in effective_bands:
        if not math.isfinite(band) or band < 0.0:
            raise ValueError(f"altitude_bands_m values must be finite and >= 0, got {band}")

    rows = site.rows
    cols = site.cols
    n_bands = len(effective_bands)
    res = site.resolution
    ox = site.origin_x
    oy = site.origin_y

    grid: npt.NDArray[np.int32] = np.zeros((n_bands, rows, cols), dtype=np.int32)

    for band_idx, altitude_m in enumerate(effective_bands):
        for row in range(rows):
            # Cell centroid y-coordinate (northing decreases with row index)
            ty = oy - (row + 0.5) * res
            for col in range(cols):
                # Cell centroid x-coordinate (easting increases with col index)
                tx = ox + (col + 0.5) * res
                count = 0
                for sdef, spl in sensor_placements:
                    try:
                        if sensor_can_detect_point(site, sdef, spl, tx, ty, altitude_m):
                            count += 1
                    except IndexError:
                        # Unexpected numpy index error — treat cell as undetectable.
                        pass
                    # ValueError (sensor placement outside DEM) is not caught here:
                    # it indicates a misconfigured sensor and should propagate.
                grid[band_idx, row, col] = count

    return DetectionCostGrid(
        grid=grid,
        altitude_bands_m=effective_bands,
        origin_x=ox,
        origin_y=oy,
        resolution=res,
        rows=rows,
        cols=cols,
    )


def _nearest_node(
    cost_grid: DetectionCostGrid,
    x: float,
    y: float,
    z_agl: float,
) -> tuple[int, int, int]:
    """Return the (band_idx, row, col) node nearest to (x, y, z_agl).

    Clamps to valid grid bounds so that coordinates slightly outside the
    extent are snapped to the nearest edge cell.
    """
    res = cost_grid.resolution
    ox = cost_grid.origin_x
    oy = cost_grid.origin_y

    col = int((x - ox) / res)
    row = int((oy - y) / res)
    col = max(0, min(cost_grid.cols - 1, col))
    row = max(0, min(cost_grid.rows - 1, row))

    # Find nearest altitude band
    bands = cost_grid.altitude_bands_m
    if not bands:
        raise ValueError("cost_grid has no altitude bands — cannot map coordinate to node")
    band_idx = min(
        range(len(bands)),
        key=lambda i: abs(bands[i] - z_agl),
    )
    return band_idx, row, col


def _cell_centroid(
    cost_grid: DetectionCostGrid,
    row: int,
    col: int,
    band_idx: int,
) -> tuple[float, float, float]:
    """Return the (x, y, z_agl) centroid of a grid cell."""
    res = cost_grid.resolution
    x = cost_grid.origin_x + (col + 0.5) * res
    y = cost_grid.origin_y - (row + 0.5) * res
    z = cost_grid.altitude_bands_m[band_idx]
    return x, y, z


def find_adversarial_trajectory(
    site: SiteModel,
    cost_grid: DetectionCostGrid,
    origin_x: float,
    origin_y: float,
    origin_z_agl: float,
    asset_x: float,
    asset_y: float,
    speed_ms: float,
    altitude_transition_cost: float = _DEFAULT_ALTITUDE_TRANSITION_COST,
) -> DroneTrajectory:
    """Find the minimum detection-exposure path from origin to asset.

    Treats the 3D cost grid as a weighted directed graph and runs Dijkstra's
    algorithm to find the path that minimises cumulative detection exposure:

    - **Horizontal edges**: 8-connected neighbours at the same altitude band.
      Edge weight = ``detection_count_at_destination × cell_area``.
    - **Vertical edges**: same cell at adjacent altitude bands.
      Edge weight = ``altitude_transition_cost × |altitude_step|``.

    The returned ``DroneTrajectory`` maps each node in the optimal path back
    to its cell centroid ``(x, y, z_agl)`` as a ``TrajectoryWaypoint``.

    Args:
        site: Site terrain model (used only for extent validation).
        cost_grid: Pre-built 3D detection cost grid from
            ``build_detection_cost_grid``.
        origin_x: Threat origin easting in CRS units (metres).
        origin_y: Threat origin northing in CRS units (metres).
        origin_z_agl: Threat origin altitude AGL (metres).
        asset_x: Protected asset easting in CRS units (metres).
        asset_y: Protected asset northing in CRS units (metres).
        speed_ms: Constant drone speed along the trajectory (m/s, > 0).
        altitude_transition_cost: Cost multiplier per metre of altitude
            change.  Higher values discourage altitude changes.

    Returns:
        A ``DroneTrajectory`` representing the minimum-detection-exposure
        path from origin to asset.

    Raises:
        ValueError: If ``speed_ms`` is not finite or <= 0.
        ValueError: If the cost grid has no altitude bands.
    """
    if not math.isfinite(speed_ms) or speed_ms <= 0.0:
        raise ValueError(f"speed_ms must be a finite value > 0, got {speed_ms}")
    if not cost_grid.altitude_bands_m:
        raise ValueError("cost_grid must have at least one altitude band")

    rows = cost_grid.rows
    cols = cost_grid.cols
    n_bands = len(cost_grid.altitude_bands_m)
    res = cost_grid.resolution
    cell_area: float = res * res

    # Node encoding: node_id = band_idx * (rows * cols) + row * cols + col
    n_nodes = n_bands * rows * cols

    def node_id(band: int, row: int, col: int) -> int:
        return band * (rows * cols) + row * cols + col

    def node_coords(nid: int) -> tuple[int, int, int]:
        band = nid // (rows * cols)
        rem = nid % (rows * cols)
        row = rem // cols
        col = rem % cols
        return band, row, col

    start_band, start_row, start_col = _nearest_node(cost_grid, origin_x, origin_y, origin_z_agl)
    # Goal: nearest cell in horizontal position; any altitude band (pick lowest cost)
    goal_band, goal_row, goal_col = _nearest_node(cost_grid, asset_x, asset_y, 0.0)

    start = node_id(start_band, start_row, start_col)
    goal_rc = (goal_row, goal_col)  # horizontal goal ignoring altitude band

    # Dijkstra's: (cost, node_id)
    dist: list[float] = [math.inf] * n_nodes
    prev: list[int] = [-1] * n_nodes
    dist[start] = 0.0
    heap: list[tuple[float, int]] = [(0.0, start)]

    # Track whether any goal-cell node has been settled, and at which cost.
    goal_node: int = -1
    goal_cost: float = math.inf

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue

        u_band, u_row, u_col = node_coords(u)

        # Check if this is a goal cell (any altitude band at goal position).
        # Track the cheapest altitude band at the goal; continue processing
        # to allow all goal-band nodes to be properly settled.
        if (u_row, u_col) == goal_rc:
            if d < goal_cost:
                goal_cost = d
                goal_node = u
            continue

        # Horizontal 8-connected neighbours at same altitude band
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = u_row + dr, u_col + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                nb = u_band
                v = node_id(nb, nr, nc)
                detect_count = int(cost_grid.grid[nb, nr, nc])
                # Diagonal neighbours have √2 × cell traversal distance
                h_factor = _SQRT2 if (dr != 0 and dc != 0) else 1.0
                edge_w = detect_count * cell_area * h_factor
                nd = d + edge_w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))

        # Vertical neighbours: same (row, col) at adjacent altitude bands
        for delta_band in (-1, 1):
            nb = u_band + delta_band
            if not (0 <= nb < n_bands):
                continue
            v = node_id(nb, u_row, u_col)
            altitude_step = abs(cost_grid.altitude_bands_m[nb] - cost_grid.altitude_bands_m[u_band])
            edge_w = altitude_transition_cost * altitude_step
            nd = d + edge_w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    # Reconstruct path from goal back to start
    if goal_node == -1:
        # No path found (shouldn't happen on a connected grid). Emit a warning
        # so operators can investigate, then fall back to a direct two-waypoint
        # trajectory rather than raising.
        warnings.warn(
            "find_adversarial_trajectory: Dijkstra's search did not reach the goal cell. "
            "Falling back to a direct two-waypoint trajectory. "
            "Check that origin and asset coordinates lie within the site extent.",
            RuntimeWarning,
            stacklevel=2,
        )
        _log.warning(
            "Dijkstra goal unreachable (start=%s, goal_rc=%s). Using direct fallback.",
            (start_band, start_row, start_col),
            goal_rc,
        )
        ox, oy_c, oz = _cell_centroid(cost_grid, start_row, start_col, start_band)
        gx, gy, gz = _cell_centroid(cost_grid, goal_row, goal_col, goal_band)
        return DroneTrajectory(
            waypoints=[
                TrajectoryWaypoint(x=ox, y=oy_c, z_agl=oz),
                TrajectoryWaypoint(x=gx, y=gy, z_agl=gz),
            ],
            speed_ms=speed_ms,
        )

    path: list[int] = []
    cur = goal_node
    while cur != -1:
        path.append(cur)
        cur = prev[cur]
    path.reverse()

    # Convert node path to waypoints — simplify by keeping only waypoints at
    # direction changes or altitude changes to keep DroneTrajectory concise.
    waypoints: list[TrajectoryWaypoint] = []
    # prev_dr/prev_dc/prev_band start as None; the first interior node (i==1)
    # records the baseline direction without adding a waypoint, so subsequent
    # nodes are compared against a valid int, not None.
    prev_dr: int | None = None
    prev_dc: int | None = None
    prev_band: int | None = None

    for i, nid in enumerate(path):
        b, r, c = node_coords(nid)
        x, y, z = _cell_centroid(cost_grid, r, c, b)

        if i == 0 or i == len(path) - 1:
            waypoints.append(TrajectoryWaypoint(x=x, y=y, z_agl=z))
            continue

        pb, pr, pc = node_coords(path[i - 1])
        dr = r - pr
        dc = c - pc

        if prev_dr is None:
            # First interior node — record baseline direction; no waypoint needed.
            prev_dr = dr
            prev_dc = dc
            prev_band = b
            continue

        # Add waypoint if direction or altitude band changed
        if dr != prev_dr or dc != prev_dc or b != prev_band:
            waypoints.append(TrajectoryWaypoint(x=x, y=y, z_agl=z))

        prev_dr = dr
        prev_dc = dc
        prev_band = b

    # Ensure minimum of 2 waypoints
    if len(waypoints) < 2:
        b0, r0, c0 = node_coords(path[0])
        x0, y0, z0 = _cell_centroid(cost_grid, r0, c0, b0)
        bg, rg, cg = node_coords(goal_node)
        xg, yg, zg = _cell_centroid(cost_grid, rg, cg, bg)
        waypoints = [
            TrajectoryWaypoint(x=x0, y=y0, z_agl=z0),
            TrajectoryWaypoint(x=xg, y=yg, z_agl=zg),
        ]

    return DroneTrajectory(waypoints=waypoints, speed_ms=speed_ms)
