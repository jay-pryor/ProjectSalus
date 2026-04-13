"""
Assemble the Slice 5 demo outputs into a single overview panel.
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

BASE = Path(__file__).parent / "05_slice5" / "maps"

images = [
    (BASE / "layers" / "layer_radar.png",    "Radar Layer"),
    (BASE / "layers" / "layer_rf.png",       "RF Layer"),
    (BASE / "layers" / "layer_acoustic.png", "Acoustic Layer"),
    (BASE / "composite.png",                 "Composite Coverage"),
    (BASE / "gaps.png",                      "Gap Map"),
    (BASE / "redundancy.png",                "Redundancy Map"),
]

fig, axes = plt.subplots(2, 3, figsize=(24, 16))
fig.patch.set_facecolor("#1a1a2e")

for ax, (path, title) in zip(axes.flat, images):
    if path.exists():
        img = mpimg.imread(str(path))
        ax.imshow(img)
    else:
        ax.text(0.5, 0.5, "Not generated", ha="center", va="center",
                color="white", fontsize=12, transform=ax.transAxes)
    ax.set_title(title, fontsize=13, fontweight="bold", color="white", pad=8)
    ax.axis("off")

fig.suptitle(
    "Project Salus — Slice 5: Multi-Sensor Coverage Analysis\n"
    "1.5 km × 1.5 km site · 2× Radar · 1× RF · 1× Acoustic",
    fontsize=16, fontweight="bold", color="white", y=0.98,
)
fig.tight_layout(rect=[0, 0, 1, 0.96])

out = Path(__file__).parent / "salus_s5_demo.png"
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close(fig)
print(f"Panel saved: {out}")
