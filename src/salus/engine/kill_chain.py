"""Kill-chain timeline computation (S7).

Implements the D-T-I-D-E-A (Detect–Track–Identify–Decide–Engage–Assess)
timeline model for cUAS engagements.  Given the first-detection range from a
corridor analysis and the configured phase durations, determines whether the
kill chain can complete before the drone reaches the protected asset, and
whether a second engagement is possible if the first attempt fails.

Workflow:
    1. Build corridor results with ``find_worst_corridors`` (threat_corridor.py).
    2. Call ``compute_all_kill_chains`` with the corridor results, a
       ``KillChainConfig``, and the available effectors.
    3. Inspect results: ``engagement_feasible`` and ``second_engagement_possible``
       flags identify which corridors are operationally satisfactory.
"""

from __future__ import annotations

import logging
import math

from salus.engine.threat_corridor import CorridorResult
from salus.models.scenario import KillChainConfig, KillChainResult
from salus.models.sensor import EffectorDefinition

_log = logging.getLogger(__name__)

# Sentinel for "no detection" — available time collapses to zero.
_NO_DETECTION_TIME_S: float = 0.0


def compute_kill_chain(
    corridor_result: CorridorResult,
    kill_chain_config: KillChainConfig,
    effector: EffectorDefinition,
    threat_speed_ms: float,
) -> KillChainResult:
    """Compute the kill-chain timeline for a single approach corridor.

    Available time is the window between first detection and drone impact:
    ``available_time_s = first_detection_range_m / threat_speed_ms``.

    Required time is the sum of all D-T-I-D-E-A phase durations:
    ``required_time_s = track + identify + decide + reaction + assess``.

    Margin is the slack remaining: ``margin_s = available_time_s - required_time_s``.

    A second engagement is possible when margin_s exceeds
    ``effector.reload_time_s + effector.reaction_time_s + kill_chain_config.assess_time_s``.

    Args:
        corridor_result: Analysis result for the corridor being evaluated.
        kill_chain_config: Operator/C2 phase durations (track, identify,
            decide, assess).
        effector: Effector used in the engagement (provides reaction_time_s
            and reload_time_s).
        threat_speed_ms: Drone approach speed in m/s.

    Returns:
        KillChainResult with timeline metrics and feasibility flags.

    Raises:
        ValueError: If ``threat_speed_ms`` is not a finite positive value.
    """
    if not (math.isfinite(threat_speed_ms) and threat_speed_ms > 0.0):
        raise ValueError(f"threat_speed_ms must be a finite positive value, got {threat_speed_ms}")

    required_time_s = _required_time(kill_chain_config, effector)
    first_det_range = corridor_result.first_detection_distance_m

    if first_det_range is None or first_det_range <= 0.0:
        # Drone was never detected — kill chain cannot execute.
        _log.debug(
            "No detection on corridor bearing=%.1f° for '%s' — kill chain infeasible.",
            corridor_result.corridor.bearing_deg,
            corridor_result.threat_name,
        )
        return KillChainResult(
            available_time_s=_NO_DETECTION_TIME_S,
            required_time_s=required_time_s,
            margin_s=_NO_DETECTION_TIME_S - required_time_s,
            first_detection_range_m=first_det_range,
            engagement_feasible=False,
            second_engagement_possible=False,
        )

    available_time_s = first_det_range / threat_speed_ms
    margin_s = available_time_s - required_time_s
    engagement_feasible = margin_s >= 0.0

    # Second engagement requires reload + re-acquire + assess within remaining margin.
    second_threshold = (
        effector.reload_time_s + effector.reaction_time_s + kill_chain_config.assess_time_s
    )
    second_engagement_possible = engagement_feasible and margin_s > second_threshold

    _log.debug(
        "Kill chain corridor=%.1f° available=%.1fs required=%.1fs margin=%.1fs feasible=%s",
        corridor_result.corridor.bearing_deg,
        available_time_s,
        required_time_s,
        margin_s,
        engagement_feasible,
    )

    return KillChainResult(
        available_time_s=available_time_s,
        required_time_s=required_time_s,
        margin_s=margin_s,
        first_detection_range_m=first_det_range,
        engagement_feasible=engagement_feasible,
        second_engagement_possible=second_engagement_possible,
    )


def compute_all_kill_chains(
    corridor_results: list[CorridorResult],
    kill_chain_config: KillChainConfig,
    effectors: list[EffectorDefinition],
    threat_speed_ms: float,
) -> list[KillChainResult]:
    """Compute kill-chain results for every corridor, selecting the best effector.

    For each corridor, all provided effectors are evaluated and the one that
    produces the largest margin is selected — representing the defender's
    optimal weapon choice per approach direction.

    Results are returned in the same order as ``corridor_results``.

    Identifies:
    - **Failure corridors**: ``margin_s < 0`` — drone reaches asset before
      the kill chain completes.
    - **Single-engagement corridors**: ``engagement_feasible`` but not
      ``second_engagement_possible`` — one chance to defeat the threat.

    Args:
        corridor_results: List of corridor analysis results to evaluate.
        kill_chain_config: Operator/C2 phase durations.
        effectors: Available effector definitions.  At least one required.
        threat_speed_ms: Drone approach speed in m/s.

    Returns:
        List of ``KillChainResult`` in the same order as ``corridor_results``.

    Raises:
        ValueError: If ``effectors`` is empty or ``threat_speed_ms`` is invalid.
    """
    if not effectors:
        raise ValueError("effectors must not be empty — at least one effector is required")
    if not corridor_results:
        raise ValueError("corridor_results must not be empty — at least one corridor is required")

    results: list[KillChainResult] = []
    for cr in corridor_results:
        best: KillChainResult | None = None
        for eff in effectors:
            candidate = compute_kill_chain(cr, kill_chain_config, eff, threat_speed_ms)
            if best is None or candidate.margin_s > best.margin_s:
                best = candidate
        # best is always non-None here because effectors is non-empty
        assert best is not None  # noqa: S101
        results.append(best)

    failure_count = sum(1 for r in results if not r.engagement_feasible)
    single_count = sum(
        1 for r in results if r.engagement_feasible and not r.second_engagement_possible
    )
    _log.info(
        "Kill chain summary: %d corridors evaluated, %d failure(s), %d single-engagement.",
        len(results),
        failure_count,
        single_count,
    )
    return results


def required_time(config: KillChainConfig, effector: EffectorDefinition) -> float:
    """Return the total required kill-chain duration: T + I + D + E + A (seconds).

    Args:
        config: Kill-chain phase configuration.
        effector: Effector providing the Engage (E) phase duration.

    Returns:
        Sum of track + identify + decide + reaction + assess phase durations.
    """
    return (
        config.track_time_s
        + config.identify_time_s
        + config.decide_time_s
        + effector.reaction_time_s
        + config.assess_time_s
    )


# Private alias for internal use (public function is the stable API).
_required_time = required_time
