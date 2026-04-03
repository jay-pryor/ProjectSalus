"""Kill-chain Gantt chart rendering (S7).

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

from salus.engine.kill_chain import required_time
from salus.engine.threat_corridor import CorridorResult
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
