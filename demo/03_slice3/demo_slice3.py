"""Slice 3 demo — synthetic terrain, viewshed, boundary clip, zone overlays."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from shapely.geometry import MultiPolygon, Polygon

from salus.engine.coverage import boundary_mask, clip_coverage_to_boundary, coverage_percentage
from salus.engine.viewshed import _viewshed_numpy
from salus.ingest.terrain import load_dem
from salus.models.zone import Zone, ZoneType
from salus.report.maps import render_coverage_map

OUTPUT = Path("demo_slice3_output.png")

# ---------------------------------------------------------------------------
# 1. Build a synthetic 300×300 DEM with a ridge and a raised platform
# ---------------------------------------------------------------------------
print("Building synthetic DEM …")
ROWS, COLS = 300, 300
LEFT, BOTTOM, RIGHT, TOP = 500_000, 6_100_000, 500_300, 6_100_300

dem = np.full((ROWS, COLS), 50.0)

# Central ridge running east-west (rows 130-170, peak at row 150)
for r in range(130, 171):
    height = 130.0 - abs(r - 150) * 4.0
    dem[r, :] = max(height, 50.0)

# Raised platform in the south-east corner (a "critical asset")
dem[220:270, 220:270] = 70.0

with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
    dem_path = Path(tmp.name)

transform = from_bounds(LEFT, BOTTOM, RIGHT, TOP, COLS, ROWS)
with rasterio.open(
    dem_path, "w", driver="GTiff",
    height=ROWS, width=COLS, count=1,
    dtype="float64", crs=CRS.from_epsg(28354), transform=transform,
) as dst:
    dst.write(dem, 1)

site = load_dem(dem_path)
print(f"  {site.rows}×{site.cols} cells at {site.resolution:.1f} m, EPSG:{site.crs_epsg}")

# ---------------------------------------------------------------------------
# 2. Compute viewshed from sensor on the north side of the ridge
# ---------------------------------------------------------------------------
obs_x = 500_150.0   # centre east-west
obs_y = 6_100_260.0  # well north of ridge
obs_h = 8.0

print(f"\nComputing viewshed from ({obs_x}, {obs_y}), height={obs_h} m …")
coverage = _viewshed_numpy(site, obs_x, obs_y, obs_h, None)
raw_pct = coverage.sum() / coverage.size * 100
print(f"  Raw visible area: {raw_pct:.1f}% of full raster")

# ---------------------------------------------------------------------------
# 3. Define a site boundary (inset rectangle — not the full raster)
# ---------------------------------------------------------------------------
bnd_margin = 20.0  # 20 m inset from raster edges
min_x, max_x, min_y, max_y = site.extent
boundary = Polygon([
    (min_x + bnd_margin, min_y + bnd_margin),
    (max_x - bnd_margin, min_y + bnd_margin),
    (max_x - bnd_margin, max_y - bnd_margin),
    (min_x + bnd_margin, max_y - bnd_margin),
])

# ---------------------------------------------------------------------------
# 4. Clip coverage to boundary and compute bounded percentage
# ---------------------------------------------------------------------------
clipped = clip_coverage_to_boundary(coverage, site, boundary)
bmask = boundary_mask(site, boundary)
bounded_pct = coverage_percentage(clipped, bmask)
print(f"  Boundary-clipped coverage: {bounded_pct:.1f}% of site area")

# ---------------------------------------------------------------------------
# 5. Define zones
# ---------------------------------------------------------------------------
# Perimeter — a wide belt inside the boundary
mid_x = (min_x + max_x) / 2
mid_y = (min_y + max_y) / 2

zones = [
    Zone(
        name="Outer Perimeter",
        zone_type=ZoneType.perimeter,
        geometry=boundary.buffer(-5).difference(boundary.buffer(-25)),
    ),
    Zone(
        name="HQ Building",
        zone_type=ZoneType.critical_asset,
        geometry=Polygon([
            (500_130, 6_100_240), (500_170, 6_100_240),
            (500_170, 6_100_275), (500_130, 6_100_275),
        ]),
    ),
    Zone(
        name="SE Asset",
        zone_type=ZoneType.critical_asset,
        geometry=Polygon([
            (500_215, 6_100_025), (500_275, 6_100_025),
            (500_275, 6_100_075), (500_215, 6_100_075),
        ]),
    ),
    Zone(
        name="No-Fly Zone",
        zone_type=ZoneType.exclusion,
        geometry=Polygon([
            (500_050, 6_100_120), (500_100, 6_100_120),
            (500_100, 6_100_160), (500_050, 6_100_160),
        ]),
    ),
    Zone(
        name="Inner Compound",
        zone_type=ZoneType.inner,
        geometry=Polygon([
            (500_120, 6_100_100), (500_200, 6_100_100),
            (500_200, 6_100_130), (500_120, 6_100_130),
        ]),
    ),
]

# ---------------------------------------------------------------------------
# 6. Render
# ---------------------------------------------------------------------------
print(f"\nRendering → {OUTPUT} …")
render_coverage_map(
    site,
    clipped,
    OUTPUT,
    title=f"Slice 3 Demo — Site Coverage ({bounded_pct:.1f}% within boundary)",
    sensor_positions=[(obs_x, obs_y)],
    boundary=boundary,
    zones=zones,
)
print(f"  Done. Open {OUTPUT.resolve()}")

dem_path.unlink()
