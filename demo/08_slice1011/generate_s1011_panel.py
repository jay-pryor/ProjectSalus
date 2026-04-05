"""
Assemble the Slice 10–11 demo outputs into a single overview panel.

Layout (3 columns × 3 rows):
  Row 1: S10 — delta map        | S10 — side by side     | S10 — bar chart
  Row 2: S10 — statistics table | S11 — effector coverage | S11 — detection gap
  Row 3: (empty)                | (empty)                 | (empty)

Run generate_s1011_demo.py first to produce the individual PNGs.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

BASE = Path(__file__).parent

IMAGES = [
    (BASE / "delta.png", "S10 — Coverage Delta (A vs B)"),
    (BASE / "side_by_side.png", "S10 — Side-by-Side Coverage"),
    (BASE / "comparison.png", "S10 — Per-Zone Bar Chart"),
    (BASE / "statistics.png", "S10 — Scalar Metrics Table"),
    (BASE / "effector_coverage.png", "S11 — Effector Engagement Zone"),
    (BASE / "detection_gap.png", "S11 — Detection-Without-Engagement Gap"),
]

NCOLS = 3
NROWS = 2

fig, axes = plt.subplots(NROWS, NCOLS, figsize=(33, 22))
fig.patch.set_facecolor("#1a1a2e")
fig.suptitle(
    "Project Salus — Slices 10 & 11\nConfiguration Comparison · Effector Coverage · Detection Gap",
    fontsize=18,
    fontweight="bold",
    color="white",
    y=0.98,
)

for ax, (path, title) in zip(axes.flat, IMAGES):
    if path.exists():
        img = mpimg.imread(str(path))
        ax.imshow(img)
    else:
        ax.text(
            0.5,
            0.5,
            f"Not found:\n{path.name}\n\nRun generate_s1011_demo.py first.",
            ha="center",
            va="center",
            color="#ff6b6b",
            fontsize=11,
            transform=ax.transAxes,
            wrap=True,
        )
        ax.set_facecolor("#0d0d1a")
    ax.set_title(title, fontsize=13, fontweight="bold", color="white", pad=10)
    ax.axis("off")

plt.tight_layout(rect=[0, 0, 1, 0.95])
out = BASE / "salus_s1011_demo.png"
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close(fig)
print(f"Panel saved → {out}")
