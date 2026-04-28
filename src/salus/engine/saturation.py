"""Multi-target effector allocation and saturation analysis (S8).

Implements a greedy priority-based effector allocation algorithm for
simultaneous drone threats and a saturation threshold sweep that answers
"how many simultaneous drones can this defence configuration handle?"

Workflow:
    1. Build a ``SaturationScenario`` with the simultaneous threats.
    2. Call ``allocate_effectors`` to assign effectors to targets.
    3. Use ``find_saturation_threshold`` to sweep over target counts and
       find the saturation point.
    4. Use ``compute_reengagement_timeline`` to model the temporal capacity
       of the effector network over a fixed engagement window.
"""

from __future__ import annotations

import logging
import math
from collections import Counter

from salus.engine.viewshed import line_of_sight_3d
from salus.models.saturation import (
    AllocationResult,
    ApproachVector,
    PriorityRule,
    ReengagementResult,
    SaturationResult,
    SaturationScenario,
    SaturationTarget,
)
from salus.models.scenario import EffectorPlacement
from salus.models.sensor import EffectorDefinition
from salus.models.site import SiteModel
from salus.models.threat import ThreatProfile

_log = logging.getLogger(__name__)

# Fraction of the maximum effector range used as the approach distance in the
# saturation threshold sweep.  0.75 keeps targets comfortably within range
# while leaving margin for arc and LOS restrictions.
_SWEEP_RANGE_FRACTION: float = 0.75

# Default engagement window for re-engagement timeline modelling (seconds).
_DEFAULT_WINDOW_S: float = 60.0

# Minimum engagement cycle time denominator guard (prevents division by zero).
_MIN_CYCLE_TIME_S: float = 1e-9

# Full circle in degrees — used for even angular spread of synthetic sweep targets.
_BEARING_MAX_DEG: float = 360.0


def _sample_dem_elevation(site: SiteModel, x: float, y: float) -> float:
    """Sample the DEM elevation nearest to (x, y), clamped to grid bounds.

    Returns 0.0 and logs a warning if the sampled cell contains NaN (nodata).
    Raises ValueError if site.resolution is not positive.
    """
    if site.resolution <= 0.0:
        raise ValueError(f"site.resolution must be > 0, got {site.resolution}")
    col = int((x - site.origin_x) / site.resolution)
    row = int((site.origin_y - y) / site.resolution)
    row = max(0, min(site.rows - 1, row))
    col = max(0, min(site.cols - 1, col))
    val = float(site.dem[row, col])
    if math.isnan(val):
        _log.warning(
            "DEM nodata (NaN) at (%.1f, %.1f) — clamped grid cell (%d, %d). "
            "Using 0.0 as ground elevation.",
            x,
            y,
            row,
            col,
        )
        return 0.0
    return val


def _target_crs_position(
    protected_point: tuple[float, float],
    approach_vector: ApproachVector,
) -> tuple[float, float]:
    """Return the CRS (x, y) position of a target given its approach vector.

    The drone is ``approach_vector.distance_m`` metres upstream of the
    protected asset along the approach bearing (i.e. it will fly towards the
    asset along that bearing).
    """
    bearing_rad = math.radians(approach_vector.bearing_deg)
    target_x = protected_point[0] - approach_vector.distance_m * math.sin(bearing_rad)
    target_y = protected_point[1] - approach_vector.distance_m * math.cos(bearing_rad)
    return target_x, target_y


def _effector_can_engage(
    effector: EffectorDefinition,
    placement: EffectorPlacement,
    target_x: float,
    target_y: float,
    target_z_abs: float,
    site: SiteModel,
) -> bool:
    """Return True if this effector placement can engage the target.

    Checks (in order): 2-D horizontal range, engagement arc, and line-of-sight
    when the effector requires it.
    """
    eff_x = placement.position_x
    eff_y = placement.position_y
    eff_height = placement.height_override_m if placement.height_override_m is not None else 0.0
    eff_ground_z = _sample_dem_elevation(site, eff_x, eff_y)
    eff_z_abs = eff_ground_z + eff_height

    dx = target_x - eff_x
    dy = target_y - eff_y
    range_2d = math.sqrt(dx * dx + dy * dy)

    # Range check (horizontal plane only — consistent with max_range_m spec).
    if range_2d < effector.min_range_m or range_2d > effector.max_range_m:
        return False

    # Engagement arc check.
    if effector.engagement_arc_deg < 360.0:
        bearing_to_target = math.degrees(math.atan2(dx, dy)) % 360.0
        half_arc = effector.engagement_arc_deg / 2.0
        diff = (bearing_to_target - placement.bearing_deg + 180.0) % 360.0 - 180.0
        if abs(diff) > half_arc:
            return False

    # Line-of-sight check.
    if effector.requires_los:
        try:
            if not line_of_sight_3d(
                site, eff_x, eff_y, eff_z_abs, target_x, target_y, target_z_abs
            ):
                return False
        except Exception as los_exc:  # noqa: BLE001
            # Any failure in LOS check — treat as no LOS and log with type for diagnosis.
            _log.warning(
                "LOS check raised %s for effector '%s' at (%.1f, %.1f) → target (%.1f, %.1f)."
                " Treating as no LOS.",
                type(los_exc).__name__,
                effector.name,
                eff_x,
                eff_y,
                target_x,
                target_y,
            )
            return False

    return True


def _sorted_target_indices(
    targets: list[SaturationTarget],
    priority_rule: PriorityRule,
) -> list[int]:
    """Return target indices sorted by the given priority rule."""
    if priority_rule == PriorityRule.CLOSEST_TO_ASSET:
        return sorted(range(len(targets)), key=lambda i: targets[i].approach_vector.distance_m)
    if priority_rule == PriorityRule.HIGHEST_THREAT:
        return sorted(range(len(targets)), key=lambda i: targets[i].speed_ms, reverse=True)
    # USER_DEFINED: preserve insertion order.
    return list(range(len(targets)))


def allocate_effectors(
    targets: list[SaturationTarget],
    effectors: list[EffectorDefinition],
    placements: list[EffectorPlacement],
    priority_rule: PriorityRule,
    site: SiteModel,
    protected_point: tuple[float, float],
) -> AllocationResult:
    """Greedily allocate effectors to simultaneous targets by priority.

    Sorts targets according to ``priority_rule``, then for each target (in
    priority order) assigns the first available effector placement that has
    remaining simultaneous-engagement capacity and can physically engage the
    target (range, arc, and LOS checks).

    Args:
        targets: List of simultaneous threat targets to allocate.
        effectors: Available effector definitions.
        placements: Deployed effector placements (positions on the site).
        priority_rule: Ordering rule for target engagement priority.
        site: Site terrain model (used for LOS checks and elevation sampling).
        protected_point: CRS coordinates (x, y) of the protected asset.

    Returns:
        ``AllocationResult`` with engaged/unengaged indices and assignments.

    Raises:
        ValueError: If ``targets`` or ``effectors`` or ``placements`` is empty.
    """
    if not targets:
        raise ValueError("targets must not be empty")
    if not effectors:
        raise ValueError("effectors must not be empty")
    if not placements:
        raise ValueError("placements must not be empty")

    effector_map: dict[str, EffectorDefinition] = {e.name: e for e in effectors}

    # Per-placement remaining simultaneous engagement capacity.
    capacity: dict[int, int] = {}
    for p_idx, p in enumerate(placements):
        eff = effector_map.get(p.effector_name)
        if eff is not None:
            capacity[p_idx] = eff.simultaneous_engagements

    assignments: dict[int, str] = {}
    priority_indices = _sorted_target_indices(targets, priority_rule)

    for tgt_idx in priority_indices:
        tgt = targets[tgt_idx]
        tgt_x, tgt_y = _target_crs_position(protected_point, tgt.approach_vector)
        tgt_ground_z = _sample_dem_elevation(site, tgt_x, tgt_y)
        tgt_z_abs = tgt_ground_z + tgt.altitude_m

        for p_idx, p in enumerate(placements):
            if capacity.get(p_idx, 0) <= 0:
                continue
            eff = effector_map.get(p.effector_name)
            if eff is None:
                continue
            if _effector_can_engage(eff, p, tgt_x, tgt_y, tgt_z_abs, site):
                assignments[tgt_idx] = p.effector_name
                capacity[p_idx] -= 1
                _log.debug(
                    "Target %d (bearing=%.1f°, dist=%.0fm) assigned to '%s'",
                    tgt_idx,
                    tgt.approach_vector.bearing_deg,
                    tgt.approach_vector.distance_m,
                    p.effector_name,
                )
                break

    engaged_indices = sorted(assignments.keys())
    unengaged_indices = sorted(i for i in range(len(targets)) if i not in assignments)

    _log.debug(
        "Allocation: %d/%d targets engaged, %d unengaged",
        len(engaged_indices),
        len(targets),
        len(unengaged_indices),
    )
    return AllocationResult(
        engaged_indices=engaged_indices,
        unengaged_indices=unengaged_indices,
        assignments=assignments,
    )


def find_saturation_threshold(
    effectors: list[EffectorDefinition],
    placements: list[EffectorPlacement],
    site: SiteModel,
    protected_point: tuple[float, float],
    threat_profile: ThreatProfile,
    max_targets: int = 20,
    priority_rule: PriorityRule = PriorityRule.CLOSEST_TO_ASSET,
) -> SaturationResult:
    """Sweep over simultaneous target counts to find the saturation threshold.

    Distributes N targets evenly around the compass (bearings 0°, 360°/N,
    720°/N, …) at a fixed approach distance equal to
    ``_SWEEP_RANGE_FRACTION × max(effector.max_range_m)``.  For each N from
    1 to ``max_targets``, runs ``allocate_effectors`` with the specified
    ``priority_rule``.  The saturation threshold is the first N at which at
    least one target is unengaged.

    Args:
        effectors: Available effector definitions.  At least one required.
        placements: Deployed effector placements.  At least one required.
        site: Site terrain model.
        protected_point: CRS coordinates (x, y) of the protected asset.
        threat_profile: Threat template providing altitude and speed values
            used when constructing sweep targets.
        max_targets: Maximum number of simultaneous targets to test.
            Must be >= 1.
        priority_rule: Engagement priority rule passed to ``allocate_effectors``
            for each sweep step.  Defaults to ``CLOSEST_TO_ASSET``.

    Returns:
        ``SaturationResult`` with threshold, capacity, and per-effector
        utilisation metrics.

    Raises:
        ValueError: If ``effectors`` or ``placements`` is empty, or if
            ``max_targets`` < 1.
    """
    if not effectors:
        raise ValueError("effectors must not be empty")
    if not placements:
        raise ValueError("placements must not be empty")
    if max_targets < 1:
        raise ValueError(f"max_targets must be >= 1, got {max_targets}")

    effector_map: dict[str, EffectorDefinition] = {e.name: e for e in effectors}

    # Total simultaneous engagement capacity across all deployments.
    simultaneous_capacity = sum(
        effector_map[p.effector_name].simultaneous_engagements
        for p in placements
        if p.effector_name in effector_map
    )

    max_range = max(e.max_range_m for e in effectors)
    approach_distance = max_range * _SWEEP_RANGE_FRACTION
    if not math.isfinite(approach_distance) or approach_distance <= 0.0:
        raise ValueError(
            f"Computed approach_distance {approach_distance} is not usable — "
            f"max effector max_range_m ({max_range}) may be too small or non-finite."
        )

    saturation_threshold_n = max_targets + 1  # sentinel: threshold never reached
    unengaged_at_threshold = 0
    last_allocation: AllocationResult | None = None

    for n in range(1, max_targets + 1):
        targets = [
            SaturationTarget(
                approach_vector=ApproachVector(
                    bearing_deg=(i * _BEARING_MAX_DEG / n) % _BEARING_MAX_DEG,
                    distance_m=approach_distance,
                ),
                altitude_m=threat_profile.typical_altitude_m,
                speed_ms=threat_profile.max_speed_ms,
                threat_profile_ref=threat_profile.name,
            )
            for i in range(n)
        ]

        result = allocate_effectors(
            targets,
            effectors,
            placements,
            priority_rule,
            site,
            protected_point,
        )

        if result.unengaged_indices:
            saturation_threshold_n = n
            unengaged_at_threshold = len(result.unengaged_indices)
            _log.info(
                "Saturation threshold reached at N=%d: %d target(s) unengaged",
                n,
                unengaged_at_threshold,
            )
            # Use the allocation just before saturation for utilisation, if available.
            break

        last_allocation = result

    # Compute per-effector utilisation from the last fully-handled allocation.
    per_effector_utilisation: dict[str, float] = {}
    if last_allocation is not None:
        usage: Counter[str] = Counter(last_allocation.assignments.values())
        for eff in effectors:
            matching = [p for p in placements if p.effector_name == eff.name]
            total_cap = eff.simultaneous_engagements * len(matching)
            if total_cap > 0:
                per_effector_utilisation[eff.name] = min(1.0, usage.get(eff.name, 0) / total_cap)
    else:
        # Saturated immediately at N=1 — no fully-handled scenario.
        for eff in effectors:
            matching = [p for p in placements if p.effector_name == eff.name]
            if matching:
                per_effector_utilisation[eff.name] = 0.0

    _log.info(
        "Saturation sweep complete: capacity=%d, threshold=%d",
        simultaneous_capacity,
        saturation_threshold_n,
    )
    return SaturationResult(
        simultaneous_engagement_capacity=simultaneous_capacity,
        saturation_threshold_n=saturation_threshold_n,
        unengaged_count_at_threshold=unengaged_at_threshold,
        per_effector_utilisation=per_effector_utilisation,
    )


def _engagements_in_window(reaction_time_s: float, reload_time_s: float, window_s: float) -> int:
    """Return the number of engagements one effector slot can complete in window_s.

    First shot fires at ``reaction_time_s``; subsequent shots fire after an
    additional ``reload_time_s + reaction_time_s``.

    Formula: floor((window_s + reload_time_s) / (reaction_time_s + reload_time_s))
    If window_s < reaction_time_s, returns 0.
    """
    cycle = reaction_time_s + reload_time_s
    if cycle < _MIN_CYCLE_TIME_S or window_s < reaction_time_s:
        return 0
    return int((window_s + reload_time_s) / cycle)


def compute_reengagement_timeline(
    effectors: list[EffectorDefinition],
    placements: list[EffectorPlacement],
    site: SiteModel,
    protected_point: tuple[float, float],
    scenario: SaturationScenario,
    window_s: float = _DEFAULT_WINDOW_S,
) -> ReengagementResult:
    """Model the temporal engagement capacity over a fixed window.

    For each effector placement, computes how many times it can fire within
    ``window_s`` given its ``reaction_time_s`` and ``reload_time_s``.  Each
    slot is multiplied by ``simultaneous_engagements`` to give total engagement
    capacity.

    Args:
        effectors: Available effector definitions.
        placements: Deployed effector placements.
        site: Site terrain model (used for the initial allocation pass).
        protected_point: CRS coordinates (x, y) of the protected asset.
        scenario: Saturation scenario providing the initial target set.
        window_s: Engagement window duration in seconds (> 0).

    Returns:
        ``ReengagementResult`` with total engagements, cycle time, and
        per-effector counts.

    Raises:
        ValueError: If ``effectors`` or ``placements`` is empty, or if
            ``window_s`` <= 0.
    """
    if not effectors:
        raise ValueError("effectors must not be empty")
    if not placements:
        raise ValueError("placements must not be empty")
    if not math.isfinite(window_s) or window_s <= 0.0:
        raise ValueError(f"window_s must be a finite value > 0, got {window_s}")

    effector_map: dict[str, EffectorDefinition] = {e.name: e for e in effectors}

    # Determine which effector names are active in the initial allocation.
    initial_allocation = allocate_effectors(
        scenario.targets,
        effectors,
        placements,
        scenario.priority_rule,
        site,
        protected_point,
    )
    active_names: set[str] = set(initial_allocation.assignments.values())

    per_effector_engagements: dict[str, int] = {}
    min_cycle_time = math.inf

    for p in placements:
        eff = effector_map.get(p.effector_name)
        if eff is None:
            continue
        if eff.name not in active_names:
            continue

        shots = _engagements_in_window(eff.reaction_time_s, eff.reload_time_s, window_s)
        engagement_count = shots * eff.simultaneous_engagements

        cycle_time = eff.reaction_time_s + eff.reload_time_s
        if cycle_time < min_cycle_time:
            min_cycle_time = cycle_time

        per_effector_engagements[eff.name] = (
            per_effector_engagements.get(eff.name, 0) + engagement_count
        )

    total_engagements = sum(per_effector_engagements.values())

    if not math.isfinite(min_cycle_time):
        # No active effectors participated in the initial allocation.
        _log.warning(
            "compute_reengagement_timeline: no active effectors found in initial allocation "
            "— reengagement_cycle_time_s set to 0.0 to signal missing data."
        )
        min_cycle_time = 0.0

    _log.info(
        "Re-engagement timeline: window=%.0fs, total_engagements=%d, min_cycle=%.1fs",
        window_s,
        total_engagements,
        min_cycle_time,
    )
    return ReengagementResult(
        window_s=window_s,
        total_engagements_possible=total_engagements,
        reengagement_cycle_time_s=min_cycle_time,
        per_effector_engagements=per_effector_engagements,
    )
