# Tech Stack — Plain English Explanations

A reference guide explaining what each technology in the stack is, what it does, and why we use it.

---

## Foundational Concepts

### Raster vs Vector Geospatial Data

**Raster data** is a grid of cells (pixels), where each cell holds a value. Think of it like a photograph, except instead of colour values each pixel stores something like elevation in metres.

A DEM (Digital Elevation Model) is a raster — a grid where cell [row 150, col 200] might contain the value `342.7`, meaning that point on the ground is 342.7m above sea level. When we compute a viewshed, the output is also a raster — same grid, but each cell contains `1` (visible from the sensor) or `0` (not visible).

```
Raster example (5x5 DEM, values = elevation in metres):

342  344  348  351  350
341  343  347  355  349
340  342  346  360  348    <-- cell value 360 = a hill
339  341  344  352  347
338  340  343  349  346
```

Resolution matters — a 1m raster means each cell covers 1m x 1m on the ground. A 5m raster means 5m x 5m. Higher resolution = more detail but bigger files and slower computation.

**Vector data** is shapes defined by coordinates — points, lines, and polygons. Think of it like a drawing rather than a photograph.

- A **point** might be a sensor position: `(-34.928, 138.601)` at 5m height
- A **line** might be a threat approach corridor: a series of coordinates defining a path
- A **polygon** might be a site boundary or a coverage zone: a closed shape defined by its vertices

```
Vector example (site boundary as polygon):

     +----------------+
     |                |
     |   Site Area    |
     |       *        |   * = sensor position (point)
     |                |
     +----------------+

Defined as: [(-34.92, 138.59), (-34.92, 138.61),
             (-34.94, 138.61), (-34.94, 138.59)]
```

**The key difference:** Raster is continuous coverage (every cell has a value — good for terrain, coverage heat maps). Vector is discrete shapes (good for boundaries, sensor positions, zone definitions). Our tool uses both heavily — terrain and coverage analysis happens in raster, site boundaries and zone definitions are vector.

GeoJSON (the format site boundaries come in) is vector data. GeoTIFF (the format terrain models are stored in) is raster data.

---

## Geospatial & Terrain Layer

### GDAL (Geospatial Data Abstraction Library)

A C/C++ library (with Python bindings) that reads, writes, and processes raster and vector geospatial data. It's the Swiss army knife of geospatial computing — nearly every GIS tool on the planet uses it under the hood, including QGIS, ArcGIS, and Google Earth.

**What we use it for:**
- **Viewshed computation** — this is the big one. `gdal_viewshed` takes a DEM raster and a point (sensor position + height) and computes a visibility map: which cells can be seen from that point, accounting for terrain occlusion. This is the core of our radar/EO/IR coverage layer.
- **Raster operations** — reprojecting rasters between coordinate systems, resampling resolution, clipping to boundaries
- **CRS transforms** — converting between coordinate reference systems (uses PROJ under the hood)

There is genuinely no alternative for viewshed computation at this level. You'd have to write your own from scratch, which means implementing ray traversal across a raster grid, handling Earth curvature, and dealing with edge cases. GDAL's implementation is battle-tested across decades of use. Every other option in this space (GRASS GIS, QGIS) uses GDAL underneath anyway.

**The downside:** The Python API is notoriously ugly — it was auto-generated from the C++ API and doesn't feel Pythonic. That's why we also use rasterio for most raster I/O, and only use GDAL directly for viewshed and operations rasterio can't do.

---

### rasterio

A Python library that reads and writes raster geospatial files (GeoTIFF, etc.). It's a Pythonic wrapper around GDAL's raster functionality — same power, much cleaner API.

**What we use it for:**
- Reading DEM/DSM GeoTIFF files into NumPy arrays for processing
- Writing computed coverage rasters back out as GeoTIFF files
- Extracting metadata — what coordinate system is this raster in? What's the resolution? What's the bounding box?
- Clipping rasters to site boundaries

**Why we need it when we already have GDAL:** Compare the two APIs for reading a GeoTIFF:

```python
# GDAL (ugly)
from osgeo import gdal
ds = gdal.Open("terrain.tif")
band = ds.GetRasterBand(1)
data = band.ReadAsArray()
transform = ds.GetGeoTransform()
ds = None  # closing is implicit and error-prone

# rasterio (clean)
import rasterio
with rasterio.open("terrain.tif") as src:
    data = src.read(1)
    transform = src.transform
    crs = src.crs
```

Same result. rasterio is dramatically more pleasant to work with. It handles file closing properly, integrates cleanly with NumPy arrays, and has intuitive methods for common operations like reprojecting and masking. It's the standard choice — any Python geospatial project uses rasterio for raster I/O.

---

### PDAL (Point Data Abstraction Library)

A C++ library (with Python bindings) for processing point cloud data. If GDAL is the Swiss army knife for rasters, PDAL is the equivalent for point clouds (LiDAR data).

**What we use it for:** This is the LiDAR ingestion pipeline. A LiDAR survey produces a point cloud — millions of individual XYZ points with metadata. PDAL processes that into the terrain models we need:

1. **Read** LAS/LAZ files (the standard LiDAR formats — LAZ is compressed LAS)
2. **Ground classification** — separate ground points from buildings, vegetation, cars, etc. This is critical: we need to know which points are "the ground" (DEM) vs "the surface of everything" (DSM)
3. **Noise filtering** — remove erroneous points (birds, sensor artifacts)
4. **Rasterisation** — convert the classified point cloud into a grid (raster). Ground-only points → DEM. All points → DSM.

The output of PDAL is the GeoTIFF rasters that rasterio then reads.

**How it works:** PDAL uses a pipeline model — you define a chain of operations:

```json
{
    "pipeline": [
        "input.laz",
        { "type": "filters.smrf" },
        { "type": "filters.range", "limits": "Classification[2:2]" },
        { "type": "writers.gdal", "filename": "dem.tif", "resolution": 1.0 }
    ]
}
```

That says: read the LAZ file → run ground classification (SMRF algorithm) → keep only ground points → write to a 1m resolution GeoTIFF.

**When does PDAL NOT run?** When the user provides a pre-processed DEM/DSM directly (GeoTIFF). In that case we skip PDAL entirely and go straight to rasterio. This is the fallback path for sites where existing LiDAR coverage is available from government sources.

---

### pyproj

Python bindings for the PROJ library, which handles coordinate reference system (CRS) transformations.

**Why this matters:** Geospatial data comes in different coordinate systems. Your LiDAR might be in UTM Zone 53S. Your site boundary GeoJSON might be in WGS84 (latitude/longitude). A government DEM might be in GDA94. If you overlay them without transforming to a common CRS, everything is misaligned — sensors end up in the ocean.

**What we use it for:**
- Detecting what CRS incoming data is in
- Transforming everything to a common CRS at ingestion time (GDA2020 / MGA zones for Australian sites)
- Converting between geographic coordinates (lat/long) and projected coordinates (metres) — we need metres for all distance calculations

**Example of why this matters:**
```
WGS84:        -34.928, 138.601       (latitude, longitude -- degrees)
MGA Zone 54:  6131250, 281430        (easting, northing -- metres)

Same point. Different numbers. If your sensor is at one and your
terrain is in the other, the viewshed calculation is meaningless.
```

---

## Geometry Layer

### Shapely

A Python library that does 2D geometry — nothing more. It has no concept of maps, the Earth, or coordinate systems. It just manipulates shapes: points, lines, and polygons. Think of it as a digital geometry toolkit — ruler, protractor, compass, and the ability to combine, subtract, and intersect shapes.

**The shapes it works with:**
- **Point** — a single location, like a sensor position
- **LineString** — a path, like a threat approach corridor. Technically a sequence of straight line segments between coordinate points (no native curves), but you approximate curves with enough closely-spaced points that they're effectively smooth. A "circle" in Shapely is actually a 64-sided polygon — at our grid resolutions the difference is meaningless.
- **Polygon** — a closed area, like a site boundary or a coverage zone

**The operations we care about:**

- `polygon.contains(point)` — "is this sensor inside the site boundary?"
- `polygon.union(other_polygon)` — merge two coverage areas into one combined shape
- `polygon.difference(other_polygon)` — subtract one shape from another. Site boundary minus total coverage = gap areas
- `polygon.intersection(other_polygon)` — where do two shapes overlap? Used for "what percentage of the critical zone is covered?"
- `point.buffer(distance)` — turn a point into a circle. A sensor with a 2km range becomes a 2km radius circle

**Where it fits in our pipeline:**

Each sensor produces a coverage shape (viewshed result, clipped to range and azimuth arc). Shapely merges all those shapes together (union), then subtracts them from the site boundary (difference) to find the gaps. That's the core of the gap analysis.

**One gotcha:** Shapely works in whatever units you give it. If your coordinates are in metres (which ours will be after pyproj normalises everything), `buffer(2000)` means 2000 metres. If you accidentally fed it lat/long degrees, `buffer(2000)` would mean 2000 degrees — which is nonsensical. This is why CRS normalisation at ingestion matters.

---

### GeoPandas

You know what a spreadsheet is — rows of data, each row has the same columns. Pandas is the Python library that gives you that: tabular data you can filter, sort, group, and calculate on. It's the standard tool for working with structured data in Python.

GeoPandas is Pandas with one extra trick: one of the columns can contain Shapely geometry. So instead of just numbers and text, a row can also have a Point, a LineString, or a Polygon attached to it.

**Why that matters for us:**

Without GeoPandas, managing spatial data means juggling individual variables — `sensor1_position`, `sensor2_position`, `zone1_polygon`, `zone2_polygon` — and writing loops to check relationships between them. With GeoPandas, everything is in a table:

```
name        type     range_m   geometry
RF-01       RF       8000      POINT (281150 6131150)
RF-02       RF       8000      POINT (281400 6131300)
Radar-01    Radar    15000     POINT (281250 6131250)
```

Now "which sensors are inside the critical zone?" is a one-liner spatial join, not a manual loop. "What's the total coverage area per sensor type?" is a group-by operation. Filtering to just radar sensors is `sensors[sensors.type == "Radar"]`.

**File I/O:** Loading a GeoJSON site boundary is just `geopandas.read_file("site.geojson")` — it handles the parsing, builds the geometry objects, and gives you back a table ready to query. Fiona (below) is what actually does that file reading under the hood, but you never need to think about it — GeoPandas calls it for you.

---

### Fiona

A Python library for reading and writing geospatial vector file formats — GeoJSON, Shapefiles, GeoPackage, KML, etc. It's the I/O backend that GeoPandas uses under the hood.

You'll almost certainly never call it directly. It's the engine behind `geopandas.read_file()` and `gdf.to_file()`. When GeoPandas reads your site boundary GeoJSON, Fiona is doing the actual file parsing.

It's in our dependency list because it ships with GeoPandas and we pin the version explicitly. The only time you'd ever interact with Fiona directly is if something goes wrong with file loading — a corrupted GeoJSON, a weird character encoding in a Shapefile, that sort of thing.

---

## Scientific Computing Layer

### NumPy

The foundational number-crunching library for Python. Its core contribution is the **ndarray** — a multi-dimensional array of numbers that you can perform operations on as a whole, rather than looping through individual elements.

**Why that matters:**

When rasterio reads a GeoTIFF terrain file, what comes back is a NumPy 2D array. A 2km x 2km site at 1m resolution = a 2000x2000 grid = 4 million cells, each holding an elevation value. When GDAL computes a viewshed, the output is also a NumPy array — same grid, but each cell is 1 (visible) or 0 (not visible).

Almost everything in the simulation engine is operations on these arrays:

- **Coverage union** — "can any sensor see this cell?" is `numpy.maximum(sensor1, sensor2, sensor3, ...)`. One line, runs on the entire grid at once.
- **Gap detection** — `gaps = site_mask & ~composite_coverage`. Boolean array operation — site cells that are NOT covered.
- **Range clipping** — build a distance array from the sensor position, then `coverage = viewshed & (distance <= max_range)`. Every cell evaluated simultaneously.
- **RF propagation** — the free-space path loss formula applied to every cell's distance in one vectorised call.

**The performance angle:**

Python `for` loops are slow. Looping over 4 million cells to check "is this cell visible AND within range?" takes seconds. NumPy does the same thing in milliseconds because the actual computation runs in compiled C code underneath. You express the operation on the whole array, NumPy handles the fast iteration internally. This is called *vectorisation*.

```python
# Slow — Python loop over every cell (~3 seconds)
for row in range(2000):
    for col in range(2000):
        if viewshed[row, col] == 1 and distance[row, col] <= 5000:
            result[row, col] = 1

# Fast — NumPy vectorised (~5 milliseconds, same result)
result = (viewshed == 1) & (distance <= 5000)
```

That 600x speedup is why the entire simulation engine is essentially NumPy array maths. Every module takes arrays in, returns arrays out.

---

### SciPy

SciPy builds on top of NumPy. Where NumPy gives you fast array operations, SciPy adds specialised mathematical tools — interpolation, signal processing, optimisation, spatial data structures, image processing.

For the MVP, it's a supporting player rather than a star. We use it for a few specific things:

**Terrain profile extraction:** When checking whether an RF signal can reach from a sensor to a target, we need the elevation at every point along the line between them. The problem is, that line doesn't align neatly with our grid cells — it cuts diagonally across them. `scipy.ndimage.map_coordinates` interpolates the elevation values along that arbitrary path, giving us a smooth terrain profile even between grid cells. That profile is what we feed into the knife-edge diffraction model — we scan along it to find the highest obstruction blocking the signal path.

**Distance matrices:** `scipy.spatial.distance` efficiently computes distances from one point to many others. When evaluating candidate sensor positions during placement optimisation ("which position covers the most uncovered area?"), we need distances from each candidate to every grid cell. SciPy does this fast.

**Labelling connected regions:** `scipy.ndimage.label` takes a binary array (like our gap raster — 1 for gap, 0 for covered) and identifies distinct connected regions. Instead of "you have gaps," it tells you "you have 3 separate dead zones" and which cells belong to each. Useful for the gap analysis section of the report.

**Post-MVP it becomes much more central** — probabilistic detection curves, advanced RF modelling, and optimisation algorithms all live in SciPy. But for now, it's a utility belt.

---

## RF Propagation

### No External Library — Custom Implementation

This one's different — there's no external library. The RF models we need are straightforward physics equations that we implement ourselves in about 50 lines of NumPy. Two formulas:

#### 1. Free-Space Path Loss (FSPL)

The baseline model. In open air with no obstacles, radio signals weaken with distance:

```
FSPL (dB) = 20·log₁₀(d) + 20·log₁₀(f) + 20·log₁₀(4π/c)
```

In plain English: **signal strength drops with the square of distance**. Double the distance, signal is 4x weaker (6 dB loss). This gives us the best-case detection range.

The logic is simple: a drone transmits at a known power, the signal weakens over distance per this formula, and the sensor has a minimum sensitivity. If `transmit_power - path_loss > sensitivity`, the sensor detects the drone. If not, it doesn't.

#### 2. Single Knife-Edge Diffraction (ITU-R P.526)

FSPL assumes open air. When there's a hill or building between sensor and drone, radio waves don't just stop — they bend (diffract) over the obstruction. This model calculates how much extra signal loss that bending causes.

Imagine the obstruction as a knife blade between sensor and drone. The more it blocks the direct path, the more signal is lost. The maths produces a single parameter (nu) based on how far the obstruction pokes above the direct line, and the distances involved. That gives an additional dB loss on top of FSPL.

**How it works in the simulation:**

For each RF sensor, for each cell on the grid:
1. Calculate FSPL from distance
2. Extract the terrain profile between sensor and cell (that's where SciPy comes in)
3. Find the highest obstruction along that profile
4. If it blocks the direct path, calculate the diffraction loss
5. Total loss = FSPL + diffraction loss
6. Compare against the link budget — does enough signal survive for detection?

The result is an RF coverage raster, similar to viewshed output but accounting for the fact that RF can partially get around obstacles.

**Why not use an existing RF tool (SPLAT!, Radio Mobile)?** Those solve long-range propagation over hundreds of kilometres with atmospheric effects. Our use case is short-range (under 10km) where FSPL + terrain diffraction dominates. The integration overhead isn't worth it for two equations.

**Why only single knife-edge?** Real terrain might have multiple ridgelines. We only model the worst single obstruction. Multi-knife-edge (Deygout, Bullington methods) is Phase 2.

---

## Visualisation & Mapping Layer

### Matplotlib (+ Seaborn for styling)

The standard Python plotting library. It produces static images — charts, heat maps, scatter plots, anything you'd put in a printed report. Been around since 2003, used in virtually every scientific Python project.

**For us, it renders every visual that goes into the PDF report:**

- **Coverage heat maps** — the viewshed/RF coverage array rendered as a colour-coded image. Green for covered, red for gaps, graduated colours for signal strength.
- **Site overview maps** — site boundary, sensor positions as markers, zone boundaries as overlays, all composited into one image.
- **Gap analysis maps** — dead zones highlighted, overlaid on terrain.
- **Threat corridor overlays** — approach paths drawn across the coverage map, colour-coded by coverage percentage.
- **Kill chain timeline diagrams** — horizontal bar charts showing the D-T-I-D-E-A phases and whether the kill chain completes before the drone arrives.
- **Saturation charts** — engagement capacity vs. number of simultaneous targets.
- **Configuration comparison** — side-by-side maps or difference maps showing where Config B covers that Config A doesn't.

**Why Matplotlib over something fancier (Plotly, Bokeh)?** Those produce interactive HTML widgets — great for dashboards, but they don't embed in PDFs. Matplotlib outputs high-resolution PNGs that embed cleanly into a printed report. It's also extremely customisable — defence reports have specific formatting expectations (professional colour schemes, scale bars, north arrows, coordinate grids), and Matplotlib gives full control over every pixel. The interactive visualisation stuff comes later with the standalone viewer in Phase 4.

**On aesthetics:** Matplotlib's defaults are ugly, but the library is very capable when styled properly. Built-in style sheets like Seaborn's dramatically improve the look with minimal effort. Seaborn is a wrapper around Matplotlib that produces better-looking statistical charts (bar charts, distributions, comparisons) out of the box. For the geospatial maps, a custom Salus style sheet (colours, fonts, line weights) defined once and applied globally keeps everything looking professional.

---

### contextily

A small library that does one thing: fetches map tiles (OpenStreetMap, satellite imagery, etc.) and places them behind your Matplotlib plots as a basemap.

**Why we need it:**

Without contextily, our coverage maps are coloured blobs on a blank background or raw elevation data. Technically correct, but if someone's reading the report they're squinting going "where is this? Is that a hill or a suburb?"

With contextily, you add one line — `ctx.add_basemap(ax, ...)` — and suddenly there's a real street map underneath with roads, buildings, and labels. The coverage overlay is immediately interpretable.

**Offline/air-gapped operation:** contextily can cache tiles locally. For Tier 3 (classified environments with no internet), we'd pre-download the tiles for the site area and bundle them. For normal operation, it pulls tiles on demand from free tile servers.

**Why not Folium or Leaflet?** Those produce interactive HTML maps you can pan and zoom in a browser. Great for the standalone viewer later, but they don't embed in a PDF. contextily bridges that gap — real map tiles, but rendered into a static Matplotlib image that goes straight into the report.

---

## Report Generation Layer

### Jinja2

Jinja2 is a templating engine. It takes a template (an HTML file with placeholders) and fills in the placeholders with actual data to produce a finished document.

If you've ever done a mail merge — write one letter template, fill it with different names and addresses to produce 50 letters — it's exactly that concept, but for HTML.

**How we use it:**

The PDF report has a consistent structure every time — executive summary, site overview, coverage maps, gap analysis, threat corridors, kill chain, etc. But the content changes for every simulation run. Jinja2 lets us define the report layout once as HTML templates, then fill them with the results of each run:

```html
<h1>Coverage Analysis — {{ site_name }}</h1>
<p>Total area covered: {{ coverage_pct }}%</p>
<p>Dead zones identified: {{ gap_count }}</p>
<img src="{{ coverage_map_path }}" />
```

The simulation engine produces the numbers and Matplotlib produces the map images. Jinja2 stitches them together into a complete HTML document. Then WeasyPrint (below) turns that HTML into a PDF.

**Why HTML as the intermediate format?** It's flexible, easy to style with CSS, and everyone knows how to read it. It means the same templates can produce both the PDF report and a browser-viewable HTML version if we ever want that. It also means report layout is CSS — much easier to tweak than programmatic layout code.

---

### WeasyPrint

WeasyPrint takes HTML + CSS and renders it to PDF. That's its entire job.

After Jinja2 produces the finished HTML report (text, tables, embedded map images, charts), WeasyPrint converts it to a polished, paginated PDF with proper page breaks, headers/footers, page numbers, and print-quality image rendering.

**Why WeasyPrint over alternatives?**

- **ReportLab** — Python-native PDF generation, but you build the layout programmatically. Every paragraph, table, and image placement is Python code. Verbose and tedious for a complex multi-page report.
- **LaTeX** — produces beautiful technical documents, but adds a heavy system dependency (a full LaTeX distribution is hundreds of MB) and template authoring is its own skill.
- **WeasyPrint** — you write HTML and CSS, which is dramatically easier to author and maintain. The output quality is comparable to LaTeX for our purposes. No massive system dependency.

**The report workflow end-to-end:**

```
Simulation results (numbers, arrays)
        ↓
Matplotlib → map/chart PNGs
        ↓
Jinja2 + HTML templates → complete HTML document
        ↓
WeasyPrint → final PDF report
```

---

## Data & Configuration Layer

### PyYAML

PyYAML reads and writes YAML files. YAML is a human-readable data format — similar to JSON but cleaner to read and edit by hand.

**Why YAML over JSON for our sensor/effector database?**

These files will be manually authored and maintained — someone reads a DroneShield datasheet and types the specs into a file. YAML is much friendlier for that:

```yaml
# YAML — easy to read, easy to edit, supports comments
name: DroneShield RfOne
type: RF
max_range_m: 8000
azimuth_coverage: 360
frequency_bands:
  - 2.4 GHz
  - 5.8 GHz
requires_los: false
```

```json
{
    "name": "DroneShield RfOne",
    "type": "RF",
    "max_range_m": 8000,
    "azimuth_coverage": 360,
    "frequency_bands": ["2.4 GHz", "5.8 GHz"],
    "requires_los": false
}
```

Same data. YAML has no braces, no quotes on keys, supports comments. When you're maintaining a database of 30+ sensors by hand, that readability matters.

PyYAML loads a YAML file into a Python dictionary, which we then pass to Pydantic (below) for validation.

---

### Pydantic

Pydantic validates data. You define a model — "a sensor must have a name (string), a max range (positive number), a type (one of RF/Radar/EO-IR/Acoustic)" — and Pydantic checks that incoming data matches that shape. If it doesn't, you get a clear error message instead of something breaking mysteriously downstream.

**Why we need it:**

The sensor database is hand-authored YAML. Humans make mistakes. Someone types `max_range_m: "eight thousand"` instead of `max_range_m: 8000`, or forgets the `type` field entirely. Without validation, that bad data flows silently into the simulation engine and produces garbage results — or crashes mid-run with an unhelpful error 10 steps removed from the actual problem.

Pydantic catches it at load time with a clear error telling you exactly what's wrong and where.

**The pattern:** PyYAML reads the file into a raw dictionary. Pydantic validates that dictionary against the model definition. If it passes, you get a clean, typed Python object. If it fails, you get a specific error. This applies to everything that comes from external input — sensor definitions, effector definitions, threat profiles, scenario configurations, site zone metadata. Validate at the boundary, trust the data once it's inside.

---

## CLI Layer

### Click

Click is a CLI (command-line interface) framework. It lets you define the commands a user types to run the tool.

Python has a built-in option for this (`argparse`), but it's tedious for anything beyond a single command. Click uses decorators — annotations above your functions — to define commands, arguments, and options cleanly:

```python
@click.group()
def salus():
    """cUAS Site Simulation Tool"""
    pass

@salus.command()
@click.argument("lidar_path")
@click.option("--resolution", default=1.0, help="Output raster resolution in metres")
def ingest(lidar_path, resolution):
    """Ingest LiDAR data and produce DEM/DSM."""
    ...

@salus.command()
@click.argument("scenario_path")
def simulate(scenario_path):
    """Run coverage simulation for a scenario."""
    ...
```

That gives you:
- `salus ingest site.laz --resolution 2.0`
- `salus simulate scenario.yaml`
- `salus --help` (auto-generated help text)

**Why Click over argparse?** Subcommands. Our tool isn't one single action — it's `ingest`, `simulate`, `report`, `compare`, maybe `place`. Click handles subcommand routing cleanly. With argparse you'd be manually wiring up subparsers, which gets messy fast.

**The architectural point:** `cli.py` is a thin orchestration layer. It parses arguments, calls the appropriate engine modules, and handles output. The engine modules themselves don't know they're being called from a CLI — which means when we wrap the same engine in a FastAPI web backend for Tier 2, we don't touch the engine code at all. We just write a new entry point that calls the same functions.

---

## Infrastructure

### conda-forge

Installing our geospatial dependencies — GDAL, PDAL, rasterio — is notoriously painful. They're not pure Python; they're Python wrappers around C/C++ libraries that need to be compiled against system libraries. A plain `pip install gdal` frequently fails with cryptic compiler errors, version mismatches, or missing system headers.

conda-forge solves this. It's a community repository of pre-built binary packages for the conda package manager. Instead of compiling GDAL from source on your machine, you download a pre-built binary that just works. `conda install -c conda-forge gdal rasterio pdal` and you're done.

**Why not just pip for everything?** For most of our dependencies (Click, Pydantic, PyYAML, Jinja2, Matplotlib) pip works perfectly — they're pure Python or have well-maintained wheels. The geospatial C/C++ libraries are the exception. The practical approach is: use conda for the hard stuff (GDAL, PDAL, rasterio, pyproj), pip for the rest.

---

### Docker

Docker packages an entire application — code, dependencies, operating system libraries, everything — into a self-contained image that runs identically on any machine.

**Why we need it:**

1. **Reproducibility** — "works on my machine" isn't acceptable when delivering to defence customers. A Docker image guarantees the exact same environment every time, on any machine.

2. **The GDAL problem, solved permanently** — instead of every developer (or deployment target) fighting with GDAL installation, we build one Docker image with everything pre-installed and tested. Run the container, it works.

3. **Air-gapped deployment** — Tier 3 is on-premise deployment in classified networks with no internet. A Docker image is a single file you can carry in on approved media. No downloading packages, no resolving dependencies, no hoping the target machine has the right system libraries.

The Dockerfile essentially says: start from a base Linux image, install conda-forge packages, install pip packages, copy in our code, set the entry point to `salus`. Anyone, anywhere, runs the same thing.
