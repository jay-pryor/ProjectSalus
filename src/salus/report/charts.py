"""Kill-chain Gantt chart rendering (S7) and saturation analysis charts (S8).

Produces a horizontal stacked-bar diagram showing D-T-I-D-E-A phase durations
against available time for each approach corridor.  Green margin = feasible;
red background = kill chain fails before drone reaches asset.

D-T-I-D-E-A phase mapping:
    D (Detect)   — the detection event itself; this is the timeline origin (t=0).
                   It is not rendered as a coloured segment because it has no
                   configurable duration in KillChainConfig.
    T (Track)    — track_time_s (blue bar)
    I (Identify) — identify_time_s (orange bar)
    D (Decide)   — decide_time_s (yellow bar)
    E (Engage)   — effector.reaction_time_s (red bar)
    A (Assess)   — assess_time_s (purple bar)
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker

from salus.engine.kill_chain import required_time
from salus.engine.threat_corridor import CorridorResult
from salus.models.saturation import ReengagementResult, SaturationResult
from salus.models.scenario import KillChainConfig, KillChainResult
from salus.models.sensor import EffectorDefinition

matplotlib.use("Agg")

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase colour palette (colourblind-friendly)
# ---------------------------------------------------------------------------
_PHASE_COLOURS: dict[str, str] = {
    "Track": "#4e9af1",  # blue
    "Identify": "#f4a942",  # orange
    "Decide": "#f1c84e",  # yellow
    "Engage": "#e05252",  # red
    "Assess": "#9b59b6",  # purple
}

# Colour for the "margin" bar (remaining time after required phases).
_MARGIN_COLOUR_FEASIBLE: str = "#2ecc71"  # green
_MARGIN_COLOUR_INFEASIBLE: str = "#e74c3c"  # red

# Default figure dimensions.
_DEFAULT_FIG_WIDTH: float = 12.0
_DEFAULT_BAR_HEIGHT: float = 0.7
_MIN_BARS_FOR_SUMMARY: int = 1


def render_kill_chain_chart(
    corridor_results: list[CorridorResult],
    kill_chain_results: list[KillChainResult],
    kill_chain_config: KillChainConfig,
    effector: EffectorDefinition,
    output_path: str | Path,
    title: str = "Kill-Chain Timeline",
) -> Path:
    """Render a Gantt-style kill-chain timeline chart for all corridors.

    Each row represents one approach corridor.  Coloured segments show the
    T-I-D-E-A phase durations stacked from the left; the margin (or deficit)
    fills the remaining width.  A vertical dashed line marks the available
    time for each corridor.

    Args:
        corridor_results: Corridor analysis results (same order as
            ``kill_chain_results``).
        kill_chain_results: Computed kill-chain results, one per corridor.
        kill_chain_config: Phase durations used (for legend).
        effector: Effector used in the analysis (for legend and phase times).
        output_path: Where to write the PNG file.  Parent directories are
            created if absent.
        title: Chart title.

    Returns:
        Resolved Path to the written PNG file.

    Raises:
        ValueError: If ``corridor_results`` and ``kill_chain_results`` have
            different lengths, or if either list is empty.
    """
    if len(corridor_results) != len(kill_chain_results):
        raise ValueError(
            f"corridor_results and kill_chain_results must have the same length, "
            f"got {len(corridor_results)} and {len(kill_chain_results)}"
        )
    if not corridor_results:
        raise ValueError("corridor_results must not be empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_bars = len(corridor_results)
    fig_height = max(4.0, n_bars * (_DEFAULT_BAR_HEIGHT + 0.4) + 2.0)
    fig, ax = plt.subplots(figsize=(_DEFAULT_FIG_WIDTH, fig_height))

    phase_durations = [
        ("Track", kill_chain_config.track_time_s),
        ("Identify", kill_chain_config.identify_time_s),
        ("Decide", kill_chain_config.decide_time_s),
        ("Engage", effector.reaction_time_s),
        ("Assess", kill_chain_config.assess_time_s),
    ]

    max_time = max(
        (
            r.available_time_s
            for r in kill_chain_results
            if math.isfinite(r.available_time_s) and r.available_time_s > 0.0
        ),
        default=required_time(kill_chain_config, effector) * 1.5,
    )
    # Extend axis to show any overrun clearly.
    ax_max = max_time * 1.15

    for idx, (cr, kc) in enumerate(zip(corridor_results, kill_chain_results)):
        y = n_bars - 1 - idx  # top bar = index 0

        if not math.isfinite(kc.available_time_s) or kc.available_time_s <= 0.0:
            # No detection — draw a "no detection" placeholder bar.
            ax.barh(
                y,
                ax_max * 0.05,
                left=0.0,
                height=_DEFAULT_BAR_HEIGHT,
                color="#cccccc",
                edgecolor="white",
            )
            ax.text(
                ax_max * 0.06,
                y,
                "no detection",
                va="center",
                ha="left",
                fontsize=8,
                color="#888888",
            )
            continue

        # Draw phase segments.
        left = 0.0
        for phase_name, phase_dur in phase_durations:
            ax.barh(
                y,
                phase_dur,
                left=left,
                height=_DEFAULT_BAR_HEIGHT,
                color=_PHASE_COLOURS[phase_name],
                edgecolor="white",
                linewidth=0.5,
            )
            left += phase_dur

        # Draw margin or deficit.
        margin = kc.margin_s
        if not math.isfinite(margin):
            _log.warning(
                "Non-finite margin for corridor %.1f° — skipping bar",
                cr.corridor.bearing_deg,
            )
            continue
        if margin >= 0.0:
            ax.barh(
                y,
                margin,
                left=left,
                height=_DEFAULT_BAR_HEIGHT,
                color=_MARGIN_COLOUR_FEASIBLE,
                edgecolor="white",
                linewidth=0.5,
            )
        else:
            # Required time exceeds available time — show overrun in red.
            ax.barh(
                y,
                abs(margin),
                left=kc.available_time_s,
                height=_DEFAULT_BAR_HEIGHT,
                color=_MARGIN_COLOUR_INFEASIBLE,
                edgecolor="white",
                linewidth=0.5,
                alpha=0.6,
            )

        # Vertical dashed line at available_time.
        ax.axvline(
            x=kc.available_time_s,
            ymin=(y - _DEFAULT_BAR_HEIGHT / 2 + 0.5) / (n_bars + 0.5),
            ymax=(y + _DEFAULT_BAR_HEIGHT / 2 + 0.5) / (n_bars + 0.5),
            color="black",
            linewidth=1.0,
            linestyle="--",
            alpha=0.7,
        )

        # Margin annotation.
        margin_label = f"{margin:+.1f}s"
        margin_x = kc.available_time_s + 0.01 * ax_max
        ax.text(
            margin_x,
            y,
            margin_label,
            va="center",
            ha="left",
            fontsize=7,
            color=_MARGIN_COLOUR_FEASIBLE if margin >= 0.0 else _MARGIN_COLOUR_INFEASIBLE,
            fontweight="bold",
        )

    # Y-axis labels (bearing + feasibility indicator).
    y_labels = []
    for idx, (cr, kc) in enumerate(zip(corridor_results, kill_chain_results)):
        indicator = "✓" if kc.engagement_feasible else "✗"
        y_labels.append(f"{indicator} {cr.corridor.bearing_deg:.0f}°")

    ax.set_yticks(range(n_bars))
    ax.set_yticklabels(list(reversed(y_labels)), fontsize=9)
    ax.set_xlim(0.0, ax_max)
    ax.set_xlabel("Time from first detection (s)", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Legend.
    legend_handles = [
        mpatches.Patch(color=_PHASE_COLOURS[name], label=f"{name} ({dur:.1f}s)")
        for name, dur in phase_durations
    ]
    legend_handles.append(mpatches.Patch(color=_MARGIN_COLOUR_FEASIBLE, label="Margin (feasible)"))
    legend_handles.append(
        mpatches.Patch(color=_MARGIN_COLOUR_INFEASIBLE, label="Overrun (infeasible)")
    )
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        fontsize=8,
        framealpha=0.8,
    )

    try:
        plt.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)

    _log.info("Kill-chain chart written to %s", output_path)
    return output_path.resolve()


def render_kill_chain_summary_chart(
    corridor_results: list[CorridorResult],
    kill_chain_results: list[KillChainResult],
    kill_chain_config: KillChainConfig,
    effector: EffectorDefinition,
    output_path: str | Path,
    title: str = "Kill-Chain Summary (Worst / Best / Average)",
) -> Path:
    """Render a three-row summary chart: worst, average, and best corridors.

    Selects the corridor with the smallest margin (worst), the one closest to
    the mean margin (average), and the one with the largest margin (best).
    Renders them as a compact Gantt chart with a single page.

    Args:
        corridor_results: Corridor analysis results.
        kill_chain_results: Computed kill-chain results (same order).
        kill_chain_config: Phase durations.
        effector: Effector used.
        output_path: Output PNG path.
        title: Chart title.

    Returns:
        Resolved Path to the written PNG.

    Raises:
        ValueError: If lists are empty or have mismatched lengths.
    """
    if len(corridor_results) != len(kill_chain_results):
        raise ValueError(
            f"corridor_results and kill_chain_results must have the same length, "
            f"got {len(corridor_results)} and {len(kill_chain_results)}"
        )
    if not corridor_results:
        raise ValueError("corridor_results must not be empty")

    margins = [r.margin_s for r in kill_chain_results]
    mean_margin = sum(margins) / len(margins)

    worst_idx = min(range(len(margins)), key=lambda i: margins[i])
    best_idx = max(range(len(margins)), key=lambda i: margins[i])
    avg_idx = min(range(len(margins)), key=lambda i: abs(margins[i] - mean_margin))

    # Deduplicate (worst/avg/best may overlap when n<3).
    seen: set[int] = set()
    selected_indices: list[int] = []
    for idx in [worst_idx, avg_idx, best_idx]:
        if idx not in seen:
            selected_indices.append(idx)
            seen.add(idx)

    sub_cr = [corridor_results[i] for i in selected_indices]
    sub_kc = [kill_chain_results[i] for i in selected_indices]

    return render_kill_chain_chart(
        sub_cr,
        sub_kc,
        kill_chain_config,
        effector,
        output_path,
        title=title,
    )


# ---------------------------------------------------------------------------
# Saturation analysis charts (S8)
# ---------------------------------------------------------------------------

# Colours for the saturation threshold bar chart.
_SAT_ENGAGED_COLOUR: str = "#2ecc71"  # green — fully handled
_SAT_UNENGAGED_COLOUR: str = "#e74c3c"  # red — unengaged targets
_SAT_THRESHOLD_LINE_COLOUR: str = "#c0392b"  # dark red — threshold marker

# Colours for the engagement timeline Gantt bars.
_TIMELINE_FIRING_COLOUR: str = "#3498db"  # blue — active engagement
_TIMELINE_RELOAD_COLOUR: str = "#bdc3c7"  # grey — reloading
_TIMELINE_IDLE_COLOUR: str = "#ecf0f1"  # light grey — idle bar background

# Colour for the utilisation bar chart.
_UTIL_COLOUR: str = "#9b59b6"  # purple


def render_saturation_threshold_chart(
    threshold_data: dict[int, int],
    saturation_threshold_n: int,
    output_path: str | Path,
    title: str = "Saturation Threshold Analysis",
) -> Path:
    """Render a bar chart of unengaged targets versus simultaneous target count.

    Each bar represents the number of unengaged targets for a given number of
    simultaneous attackers.  A vertical dashed line marks the saturation
    threshold (the first N where at least one target is unengaged).

    Args:
        threshold_data: Mapping from target count N to number of unengaged
            targets at that N.  Must not be empty.
        saturation_threshold_n: The saturation threshold value to mark.
        output_path: Output PNG path.  Parent directories are created if absent.
        title: Chart title.

    Returns:
        Resolved Path to the written PNG.

    Raises:
        ValueError: If ``threshold_data`` is empty.
    """
    if not threshold_data:
        raise ValueError("threshold_data must not be empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ns = sorted(threshold_data.keys())
    unengaged = [threshold_data[n] for n in ns]
    colours = [_SAT_UNENGAGED_COLOUR if u > 0 else _SAT_ENGAGED_COLOUR for u in unengaged]

    fig, ax = plt.subplots(figsize=(_DEFAULT_FIG_WIDTH, 5.0))

    ax.bar(ns, unengaged, color=colours, edgecolor="white", linewidth=0.5)

    # Mark saturation threshold.
    if saturation_threshold_n in threshold_data:
        ax.axvline(
            x=saturation_threshold_n,
            color=_SAT_THRESHOLD_LINE_COLOUR,
            linewidth=2.0,
            linestyle="--",
            label=f"Saturation threshold (N={saturation_threshold_n})",
        )
        ax.legend(fontsize=9, framealpha=0.8)

    ax.set_xlabel("Simultaneous targets", fontsize=10)
    ax.set_ylabel("Unengaged targets", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(ns)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    try:
        plt.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)

    _log.info("Saturation threshold chart written to %s", output_path)
    return output_path.resolve()


def render_engagement_timeline_chart(
    reengagement_result: ReengagementResult,
    effector_timing: dict[str, tuple[float, float]],
    output_path: str | Path,
    title: str = "Effector Re-engagement Timeline",
) -> Path:
    """Render a Gantt chart of effector firing events over the engagement window.

    Shows each effector as a row with alternating firing (blue) and reload
    (grey) segments, illustrating the temporal capacity of the effector network.

    Args:
        reengagement_result: Pre-computed re-engagement timeline.
        effector_timing: Mapping from effector name to
            ``(reaction_time_s, reload_time_s)`` for computing shot positions.
            Must contain an entry for every key in
            ``reengagement_result.per_effector_engagements``.
        output_path: Output PNG path.
        title: Chart title.

    Returns:
        Resolved Path to the written PNG.

    Raises:
        ValueError: If ``reengagement_result.per_effector_engagements`` is
            empty, or if ``effector_timing`` is missing a required key.
    """
    per_eff = reengagement_result.per_effector_engagements
    if not per_eff:
        raise ValueError("reengagement_result.per_effector_engagements must not be empty")

    missing = [name for name in per_eff if name not in effector_timing]
    if missing:
        raise ValueError(f"effector_timing is missing keys: {missing}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    window_s = reengagement_result.window_s
    effector_names = sorted(per_eff.keys())
    n_rows = len(effector_names)

    fig_height = max(3.0, n_rows * (_DEFAULT_BAR_HEIGHT + 0.5) + 1.5)
    fig, ax = plt.subplots(figsize=(_DEFAULT_FIG_WIDTH, fig_height))

    for row_idx, name in enumerate(effector_names):
        y = n_rows - 1 - row_idx
        reaction_s, reload_s = effector_timing[name]
        cycle_s = reaction_s + reload_s

        # Draw window background.
        ax.barh(
            y,
            window_s,
            left=0.0,
            height=_DEFAULT_BAR_HEIGHT,
            color=_TIMELINE_IDLE_COLOUR,
            edgecolor="#cccccc",
            linewidth=0.3,
        )

        # Draw firing segments.
        t = 0.0
        fired = False
        while t + reaction_s <= window_s:
            fired = True
            fire_start = t
            fire_end = min(t + reaction_s, window_s)
            ax.barh(
                y,
                fire_end - fire_start,
                left=fire_start,
                height=_DEFAULT_BAR_HEIGHT,
                color=_TIMELINE_FIRING_COLOUR,
                edgecolor="white",
                linewidth=0.3,
            )
            t += reaction_s
            if reload_s > 0.0:
                reload_start = t
                reload_end = min(t + reload_s, window_s)
                ax.barh(
                    y,
                    reload_end - reload_start,
                    left=reload_start,
                    height=_DEFAULT_BAR_HEIGHT,
                    color=_TIMELINE_RELOAD_COLOUR,
                    edgecolor="white",
                    linewidth=0.3,
                )
                t += reload_s
            if cycle_s <= 0.0:
                break
        if not fired:
            _log.warning(
                "Effector '%s': reaction_time %.1fs exceeds window %.1fs"
                " — no engagements rendered.",
                name,
                reaction_s,
                window_s,
            )

    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(list(reversed(effector_names)), fontsize=9)
    ax.set_xlim(0.0, window_s)
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fire_patch = mpatches.Patch(color=_TIMELINE_FIRING_COLOUR, label="Engaging")
    reload_patch = mpatches.Patch(color=_TIMELINE_RELOAD_COLOUR, label="Reloading")
    ax.legend(handles=[fire_patch, reload_patch], fontsize=8, framealpha=0.8, loc="lower right")

    try:
        plt.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)

    _log.info("Engagement timeline chart written to %s", output_path)
    return output_path.resolve()


def render_effector_utilisation_chart(
    saturation_result: SaturationResult,
    output_path: str | Path,
    title: str = "Effector Utilisation at Saturation Threshold",
) -> Path:
    """Render a bar chart of per-effector utilisation at the saturation threshold.

    Each bar shows the fraction of an effector's simultaneous engagement
    capacity that was used in the last fully-handled scenario before saturation.

    Args:
        saturation_result: Completed saturation sweep result.
        output_path: Output PNG path.
        title: Chart title.

    Returns:
        Resolved Path to the written PNG.

    Raises:
        ValueError: If ``saturation_result.per_effector_utilisation`` is empty.
    """
    utilisation = saturation_result.per_effector_utilisation
    if not utilisation:
        raise ValueError("saturation_result.per_effector_utilisation must not be empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    names = sorted(utilisation.keys())
    values = [utilisation[n] * 100.0 for n in names]

    fig, ax = plt.subplots(figsize=(_DEFAULT_FIG_WIDTH, max(3.0, len(names) * 0.6 + 2.0)))

    bars = ax.barh(
        range(len(names)),
        values,
        color=_UTIL_COLOUR,
        edgecolor="white",
        linewidth=0.5,
    )

    # Annotate each bar with the percentage.
    for bar, pct in zip(bars, values):
        ax.text(
            min(pct + 1.0, 105.0),
            bar.get_y() + bar.get_height() / 2.0,
            f"{pct:.0f}%",
            va="center",
            ha="left",
            fontsize=8,
        )

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(0.0, 110.0)
    ax.set_xlabel("Utilisation (%)", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.axvline(x=100.0, color="#e74c3c", linewidth=1.0, linestyle="--", alpha=0.6)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    try:
        plt.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)

    _log.info("Effector utilisation chart written to %s", output_path)
    return output_path.resolve()
