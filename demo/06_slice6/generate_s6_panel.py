"""
Assemble the Slice 6 demo outputs into a single overview panel.

Layout (3 columns × 3 rows):
  Row 1: Composite coverage | DJI Mavic overlay    | DJI Mavic polar
  Row 2: FPV overlay        | FPV polar             | Fixed-Wing overlay
  Row 3: Fixed-Wing polar   | (empty)               | (empty)

Run generate_s6_demo.py first to produce the individual PNGs.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

BASE = Path(__file__).parent

# (file, title) pairs in panel order
IMAGES = [
    (BASE / "composite_coverage.png",
     "Composite Coverage"),
    (BASE / "corridor_dji_mavic_3__low_slow_overlay.png",
     "DJI Mavic 3 — Corridor Overlay"),
    (BASE / "corridor_dji_mavic_3__low_slow_polar.png",
     "DJI Mavic 3 — Polar Diagram"),
    (BASE / "corridor_fpv_racing_drone__fast_approach_overlay.png",
     "FPV Racing Drone — Corridor Overlay"),
    (BASE / "corridor_fpv_racing_drone__fast_approach_polar.png",
     "FPV Racing Drone — Polar Diagram"),
    (BASE / "corridor_fixed_wing_isr__high_altitude_overlay.png",
     "Fixed-Wing ISR — Corridor Overlay"),
    (BASE / "corridor_fixed_wing_isr__high_altitude_polar.png",
     "Fixed-Wing ISR — Polar Diagram"),
]

NCOLS = 3
NROWS = 3

fig, axes = plt.subplots(NROWS, NCOLS, figsize=(27, 27))
fig.patch.set_facecolor("#1a1a2e")

for ax, (path, title) in zip(axes.flat, IMAGES):
    if path.exists():
        img = mpimg.imread(str(path))
        ax.imshow(img)
    else:
        ax.text(
            0.5, 0.5, f"Not found:\n{path.name}",
            ha="center", va="center",
            color="#ff6b6b", fontsize=10, transform=ax.transAxes,
            wrap=True,
        )
        ax.set_facecolor("#0d0d1a")
    ax.set_title(title, fontsize=12, fontweight="bold", color="white", pad=8)
    ax.axis("off")

# Blank out unused cells
for ax in axes.flat[len(IMAGES):]:
    ax.set_visible(False)

fig.suptitle(
    "Project Salus — Slice 6: Threat Corridor Analysis\n"
    "1.5 km × 1.5 km site · 36 approach bearings · 3 threat profiles",
    fontsize=16, fontweight="bold", color="white", y=0.995,
)
fig.tight_layout(rect=[0, 0, 1, 0.985])

out = BASE / "salus_s6_demo.png"
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close(fig)
print(f"Panel saved: {out}")
