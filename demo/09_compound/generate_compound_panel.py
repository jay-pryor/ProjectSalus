"""
Assemble the compound demo outputs into a single overview panel.

Layout (3 cols × 3 rows):
  Row 1: sensor composite      | S10 delta          | S10 side-by-side
  Row 2: S10 statistics table  | S11 effector zone   | S11 detection gap
  Row 3: (S10 bar chart spans full width — centred)

Run generate_compound_demo.py first.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

BASE = Path(__file__).parent

TOP_IMAGES = [
    (BASE / "sensor_composite.png",     "Sensor Composite Coverage (optimised)"),
    (BASE / "s10_delta.png",            "S10 — Coverage Delta (A vs B)"),
    (BASE / "s10_side_by_side.png",     "S10 — Side-by-Side Comparison"),
]
MID_IMAGES = [
    (BASE / "s10_statistics.png",       "S10 — Scalar Metrics Table"),
    (BASE / "s11_effector_coverage.png","S11 — Effector Engagement Zone"),
    (BASE / "s11_detection_gap.png",    "S11 — Detection-Without-Engagement Gap"),
]
BOT_IMAGE = (BASE / "s10_comparison.png", "S10 — Per-Zone Coverage Bar Chart")


def _load(path: Path, ax):
    if path.exists():
        ax.imshow(mpimg.imread(str(path)))
    else:
        ax.text(0.5, 0.5, f"Not found:\n{path.name}",
                ha="center", va="center", color="#ff6b6b", fontsize=10,
                transform=ax.transAxes)
        ax.set_facecolor("#0d0d1a")


fig = plt.figure(figsize=(36, 30))
fig.patch.set_facecolor("#1a1a2e")
fig.suptitle(
    "Project Salus — Compound Defence\n"
    "Realistic Terrain  ·  Wall & Building Obstacles  ·  Hill Approach Corridors  ·  "
    "Greedy Sensor & Effector Placement",
    fontsize=17, fontweight="bold", color="white", y=0.985,
)

gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.12, wspace=0.06,
                       top=0.96, bottom=0.02, left=0.01, right=0.99)

# Top row — 3 equal panels
for col, (path, title) in enumerate(TOP_IMAGES):
    ax = fig.add_subplot(gs[0, col])
    _load(path, ax)
    ax.set_title(title, fontsize=12, fontweight="bold", color="white", pad=8)
    ax.axis("off")

# Middle row — 3 equal panels
for col, (path, title) in enumerate(MID_IMAGES):
    ax = fig.add_subplot(gs[1, col])
    _load(path, ax)
    ax.set_title(title, fontsize=12, fontweight="bold", color="white", pad=8)
    ax.axis("off")

# Bottom row — bar chart centred (occupy middle column, flanked by blank)
ax_bot = fig.add_subplot(gs[2, :])
path, title = BOT_IMAGE
_load(path, ax_bot)
ax_bot.set_title(title, fontsize=12, fontweight="bold", color="white", pad=8)
ax_bot.axis("off")

out = BASE / "salus_compound_demo.png"
fig.savefig(out, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close(fig)
print(f"Panel saved → {out}")
