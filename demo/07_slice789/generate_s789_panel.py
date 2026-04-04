"""
Assemble the Slice 7–8–9 demo outputs into a single overview panel.

Layout (3 columns × 3 rows):

  Row 1:  Manual Coverage (S9)   | Optimised Coverage (S9)  | Kill Chain Summary (S7)
  Row 2:  Saturation Threshold   | Re-engagement Timeline   | Effector Utilisation
          (S8)                   | (S8)                      | (S8)
  Row 3:  [full-width annotation banner]

Run generate_s789_demo.py first to produce the individual PNGs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BASE = Path(__file__).parent

# (file, row_label, title) in panel order.
IMAGES = [
    (BASE / "coverage_manual.png",         "S9", "Manual Placement"),
    (BASE / "coverage_optimised.png",      "S9", "Greedy Optimiser"),
    (BASE / "killchain_summary.png",       "S7", "Kill Chain Summary"),
    (BASE / "saturation_threshold.png",    "S8", "Saturation Threshold"),
    (BASE / "saturation_timeline.png",     "S8", "Re-engagement Timeline"),
    (BASE / "saturation_utilisation.png",  "S8", "Effector Utilisation"),
]

SLICE_COLOURS = {
    "S7": "#e67e22",   # orange
    "S8": "#9b59b6",   # purple
    "S9": "#27ae60",   # green
}

NCOLS = 3
NROWS = 2

fig, axes = plt.subplots(NROWS, NCOLS, figsize=(27, 18))
fig.patch.set_facecolor("#1a1a2e")

for ax, (path, slice_tag, title) in zip(axes.flat, IMAGES):
    ax.set_facecolor("#0d0d1a")
    if path.exists():
        img = mpimg.imread(str(path))
        ax.imshow(img, aspect="auto")
    else:
        ax.text(
            0.5, 0.5,
            f"Missing:\n{path.name}\n\nRun generate_s789_demo.py first.",
            ha="center", va="center",
            color="#ff6b6b", fontsize=10,
            transform=ax.transAxes,
        )
    ax.axis("off")

    # Slice badge in the top-left corner of each cell.
    colour = SLICE_COLOURS.get(slice_tag, "#ffffff")
    badge = FancyBboxPatch(
        (0.01, 0.91), 0.12, 0.07,
        boxstyle="round,pad=0.01",
        transform=ax.transAxes,
        facecolor=colour, edgecolor="none", zorder=5,
    )
    ax.add_patch(badge)
    ax.text(
        0.07, 0.945, slice_tag,
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=11, fontweight="bold", color="white", zorder=6,
    )

    ax.set_title(title, fontsize=13, fontweight="bold", color="white", pad=6)

fig.suptitle(
    "Project Salus — Slices 7, 8 & 9\n"
    "Kill Chain Timeline  ·  Multi-Target Saturation  ·  Sensor Placement Optimisation",
    fontsize=18, fontweight="bold", color="white", y=0.995,
)

# Slice legend below the title.
legend_x = [0.20, 0.50, 0.80]
legend_labels = ["S7 Kill Chain", "S8 Saturation", "S9 Placement"]
legend_colours = ["#e67e22", "#9b59b6", "#27ae60"]
for x, label, col in zip(legend_x, legend_labels, legend_colours):
    fig.text(
        x, 0.972, f"■  {label}",
        ha="center", va="top",
        fontsize=11, color=col, fontweight="bold",
    )

fig.tight_layout(rect=[0, 0, 1, 0.965])

out = BASE / "salus_s789_demo.png"
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close(fig)
print(f"Panel saved: {out}")
