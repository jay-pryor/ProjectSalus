# cUAS Site Simulation Tool — Technical Architecture

### Working Document — Architecture Scoping & Discussion

---

## 1. System Overview

The tool takes **site terrain data + sensor/effector specifications + threat profiles** and produces a **coverage analysis report** showing where a proposed cUAS configuration provides detection/engagement coverage, where gaps exist, and how different configurations compare.

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  Site Data   │───▶│  Terrain &   │───▶│   Simulation  │───▶│    Report    │
│  Ingestion   │    │  Scene Model │    │    Engine      │    │  Generation  │
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
       ▲                                       ▲
       │                                       │
┌─────────────┐                        ┌───────────────┐
│  LiDAR /    │                        │  Sensor/      │
│  GIS Data   │                        │  Effector DB  │
└─────────────┘                        └───────────────┘
```

---

## 2. Core Components

### 2.1 — Site Data Ingestion

**Purpose:** Accept terrain and site definition data, convert to internal representation.

**Inputs:**
- LiDAR point cloud data (LAS/LAZ format)
- Satellite/aerial imagery (GeoTIFF) — optional overlay
- Site boundary definitions (GeoJSON polygons)
- Airspace constraint data (restricted zones, flight corridors)
- Manual annotations (buildings, infrastructure, exclusion zones)

**Key processing:**
- Point cloud → Digital Elevation Model (DEM) raster grid
- Point cloud → Digital Surface Model (DSM) including structures/vegetation
- Coordinate system normalisation (all data to a common CRS — likely GDA2020 / MGA zones for Australian sites)

**Technology options:**
| Option | Pros | Cons |
|--------|------|------|
| PDAL (Point Data Abstraction Library) | Industry standard, Python bindings, handles LAS/LAZ natively | Learning curve, pipeline-based |
| Open3D | Good 3D viz, Python native | Less mature for geospatial-specific workflows |
| laspy + rasterio | Lightweight, Pythonic | More manual assembly required |

**Open questions:**
- [ ] What resolution do we rasterise the DEM/DSM to? 1m? 5m? Site-dependent?
- [ ] Do we need to handle multiple LiDAR flights stitched together?
- [ ] Do we store the raw point cloud or only the derived raster?
- [ ] How do we handle sites where LiDAR isn't available — fall back to SRTM/open DEM data?

---

### 2.2 — Terrain & Scene Model

**Purpose:** Internal 3D representation of the site that the simulation engine queries.

**Core data structure:**
```
SiteModel:
  ├── dem_grid          # 2D array — ground elevation at each cell
  ├── dsm_grid          # 2D array — surface elevation (buildings, trees)
  ├── resolution        # metres per cell
  ├── bounds            # geographic bounding box
  ├── crs               # coordinate reference system
  ├── zones[]           # named polygonal zones (perimeter, inner, exclusion)
  ├── structures[]      # annotated buildings/infrastructure
  └── airspace_constraints[]  # restricted volumes, corridors
```

**Key capabilities needed:**

**Coverage viewshed (planning mode):** Pre-computed raster — for each grid cell, can any sensor see a ground-level target there? Used for coverage maps, gap analysis, and redundancy maps. Computed once per sensor placement using GDAL `ViewshedGenerate`.

**Point LOS query (trajectory mode):** `line_of_sight_3d(site, x1, y1, z1_abs, x2, y2, z2_abs) -> bool` — can point A see point B in 3D space? Ray-marches from A to B sampling the DEM at each horizontal step, checking whether terrain rises above the line. This is the primitive for trajectory analysis where target altitude matters.

The distinction is critical: the planning viewshed assumes a ground-level target and produces a 2D footprint efficiently. The point LOS query handles arbitrary 3D positions (e.g., a drone at 150 m AGL mid-dive) and is called per-sample along a trajectory.

**Performance consideration:**
- Planning viewsheds: GDAL's C-based viewshed algorithm handles a full raster in milliseconds. Pre-computed once per sensor per scenario.
- Point LOS queries: O(distance / DEM resolution) per call. For trajectory analysis at 1 m segment length over a 1.5 km corridor, this is ~1500 LOS checks per sensor per trajectory. Acceptable even with many sensors.
- Trajectory sweep (worst-case search over bearing × altitude × dive angle): the dominant cost. Parallelisable across parameter combinations.

**Open questions:**
- [ ] Do we model vegetation as solid occlusion or partial attenuation?
- [ ] How do we handle buildings — solid block occlusion from DSM, or do we need explicit building geometry?
- [ ] Do we need temporal modelling (seasonal vegetation changes)?

---

### 2.3 — Sensor & Effector Database

**Purpose:** Structured data store of all sensor/effector types and their performance characteristics.

**Sensor model (detection systems):**
```
Sensor:
  ├── name                    # e.g. "DroneShield RfOne"
  ├── type                    # RF, Radar, EO/IR, Acoustic
  ├── max_range_m             # maximum detection range
  ├── min_range_m             # minimum detection range (blind zone)
  ├── azimuth_coverage_deg    # degrees (e.g. 360 for omni, 90 for sector)
  ├── elevation_coverage_deg  # vertical arc width in degrees (e.g. 30 = ±15° from boresight)
  ├── elevation_boresight_deg # centre of elevation arc (0 = horizontal, +ve = up, -ve = down)
  ├── frequency_bands[]       # operating frequencies (for RF/radar)
  ├── detection_probability_curve  # Pd vs range vs RCS (post-MVP)
  ├── environment_factors          # rain, wind, clutter degradation (post-MVP)
  ├── requires_los            # true for EO/IR/radar, false for some RF
  ├── mounting_height_m       # typical installation height
  ├── power_requirements_w
  ├── weight_kg
  └── cost_aud                # if known
```

Note: `elevation_coverage_deg` and `elevation_boresight_deg` together define the sensor's vertical detection arc. For trajectory analysis, a target is checked against `boresight ± coverage/2`. For planning viewsheds, these fields are used to clip the raster viewshed. A sensor with `elevation_boresight_deg=10, elevation_coverage_deg=40` covers -10° to +30° elevation.

**Effector model (countermeasure systems):**
```
Effector:
  ├── name              # e.g. "EOS Slinger"
  ├── type              # RF Jammer, Kinetic, Directed Energy, Cyber/Protocol
  ├── max_range_m
  ├── min_range_m
  ├── engagement_arc    # azimuth coverage
  ├── engagement_elevation
  ├── reaction_time_s   # time from track to engagement
  ├── simultaneous_engagements  # how many targets at once
  ├── requires_los      # true for kinetic/DE, varies for RF
  ├── legal_constraints  # civilian vs defence use restrictions
  └── defeat_mechanism   # what it actually does to the drone
```

**MVP simplification:** For the first version, we likely model sensors as:
- A detection volume defined by range + azimuth arc + elevation arc
- Binary LOS check (can see / can't see) against the DSM
- No probabilistic detection curves — just "in range + has LOS = detected"

This is defensible for site planning purposes and dramatically simplifies the engine.

**Open questions:**
- [ ] Where does the data come from? Public datasheets → manually entered → validated?
- [ ] Do we model sensor fusion (e.g. RF cues radar to look at a specific bearing)?
- [ ] How do we handle sensors that don't require LOS (e.g. RF detection through terrain)?
- [ ] Do we model false alarm rates or only detection coverage?

---

### 2.4 — Simulation Engine

**Purpose:** The core analysis logic. Places sensors/effectors on the site model and calculates coverage.

#### 2.4.1 — Viewshed / Coverage Calculation

For each sensor placed at position (x, y, z):
1. Compute viewshed from that position using the DSM
2. Clip viewshed to sensor's max range, azimuth arc, and elevation limits
3. Result = a coverage polygon/raster for that sensor

Multiple sensors → union of coverage areas = total detection coverage.
Gaps = site area minus total coverage.

**Approach options:**

| Approach | Description | Complexity | Accuracy |
|----------|-------------|------------|----------|
| **Raster viewshed** | For each sensor, compute visibility at every grid cell | Medium | Good for terrain occlusion |
| **Ray-casting** | Cast rays from sensor at regular angular intervals, check terrain intersection | Medium | Good, resolution-dependent |
| **QGIS/GDAL viewshed** | Use existing viewshed algorithms from GIS libraries | Low (wrapping) | Well-validated |
| **Full RF propagation (ITM/Longley-Rice)** | Physics-based signal propagation modelling | Very High | Overkill for MVP |

**Recommendation for MVP:** Raster viewshed using GDAL's `gdal_viewshed` or equivalent, wrapped in Python. This is a solved problem in GIS — no need to reimplement.

#### 2.4.2 — Threat Trajectory Modelling

A drone threat is modelled as a 3D piecewise-linear trajectory — an ordered list of waypoints through which it flies at constant speed. Each consecutive pair of waypoints defines one linear segment. Complex or curved approaches are approximated by combining many shorter segments. Configurable `segment_length_m` controls simulation fidelity (shorter = more precise, slower).

**Two operating modes:**

**Planning mode (worst-case sweep):** Sweeps a parameter space of bearing × start altitude × dive angle to find the approach geometry that minimises detection exposure. Uses `find_worst_trajectories`. Results drive coverage maps, polar diagrams, and gap analysis.

**Engagement calc mode (specific trajectory):** Analyses a single named trajectory defined in a YAML file. Returns exact detection events — which sensor, at what time, at what position — with sub-metre precision via binary search refinement at each detection transition. Used for kill chain timeline input.

**Detection along a trajectory:**

At each sample point `(x, y, z_agl)` along the path, each sensor is checked with `sensor_can_detect_point`:
1. LOS check: `line_of_sight_3d` from sensor position to target's absolute 3D position
2. Range check: 3D slant distance within `[min_range_m, max_range_m]`
3. Azimuth check: horizontal bearing within sensor's azimuth arc
4. Elevation check: vertical angle within `elevation_boresight_deg ± elevation_coverage_deg / 2`

When a state transition (undetected → detected) is found between two adjacent samples, binary search narrows the crossing to `segment_length_m / 100` tolerance — giving sub-centimetre and therefore sub-millisecond timing precision, bounded only by the user's chosen fidelity.

**Data models:**
```
TrajectoryWaypoint:
  ├── x              # CRS easting (metres)
  ├── y              # CRS northing (metres)
  └── z_agl          # altitude above ground level (metres)

DroneTrajectory:
  ├── waypoints[]    # ordered list of TrajectoryWaypoint, minimum 2
  └── speed_ms       # constant flight speed (metres per second)

DetectionEvent:
  ├── sensor_name
  ├── time_s                    # seconds from trajectory start
  ├── position (x, y, z_agl)   # position at moment of detection
  ├── distance_to_asset_m       # how far the drone still had to travel
  └── segment_index             # which waypoint segment the event occurred on

TrajectoryResult:
  ├── detection_events[]        # all detection events, chronological
  ├── first_detection           # earliest DetectionEvent, or None
  ├── time_to_asset_s           # total flight time from start to asset
  ├── time_in_detection_s       # total time spent inside at least one sensor's coverage
  ├── time_undetected_s         # total time outside all sensor coverage
  └── asset_reached_undetected  # True if drone arrives without any detection
```

**Threat profile (unchanged — describes the platform, not the path):**
```
ThreatProfile:
  ├── name                  # e.g. "DJI Mavic 3 — Low Slow"
  ├── rcs_m2                # radar cross section
  ├── rf_signature          # known/unknown protocol and frequency
  ├── max_speed_ms          # metres per second
  ├── typical_altitude_m    # used as default altitude in planning sweeps
  ├── approach_vectors[]    # informational — planning sweeps test all bearings
  └── evasion_capability    # none / basic / advanced
```

#### 2.4.3 — Configuration Comparison

The "what-if" engine:
- Config A: 4x RF sensors + 2x radar + 1x jammer → coverage = X%
- Config B: 6x RF sensors + 1x radar + 2x jammers → coverage = Y%
- Delta analysis: where does B cover that A doesn't? Cost difference?

This is essentially running the coverage calculation multiple times with different sensor placements and comparing results.

#### 2.4.4 — Kill Chain Timeline Modelling

For each threat corridor, model the full engagement sequence:

**D-T-I-D-E-A: Detect → Track → Identify → Decide → Engage → Assess**

Each phase has a time budget:
- **Detect:** Determined by sensor coverage — when does the drone enter a detection zone?
- **Track:** Sensor-specific track establishment time (e.g. radar needs N returns to form a track)
- **Identify:** Classification latency — manual operator or AI-assisted
- **Decide:** C2 decision loop — rules of engagement, authority to engage
- **Engage:** Effector reaction time + time-of-flight (from specs: `reaction_time_s`)
- **Assess:** Battle damage assessment — confirm drone neutralised

**Core calculation:**
```
available_time = detection_range / drone_speed
required_time  = track_time + identify_time + decide_time + engage_time + assess_time
margin         = available_time - required_time

if margin > 0:  engagement succeeds (with margin seconds to spare)
if margin < 0:  drone reaches asset before kill chain completes
if margin > required_time:  second engagement opportunity exists
```

**Effector data model additions:**
```
Effector (additional fields):
  ├── reaction_time_s           # time from "engage" command to effect on target
  ├── simultaneous_engagements  # how many targets at once
  ├── reload_time_s             # time before effector can re-engage
  ├── defeat_probability        # likelihood of single engagement success (0-1)
```

#### 2.4.5 — Multi-Target Engagement & Saturation Analysis

Model simultaneous threats (capped at 20 for MVP) to assess configuration capacity under load.

**Approach:**
1. User defines N simultaneous targets, each with an approach vector and altitude
2. Each effector has a `simultaneous_engagements` capacity and a `reload_time_s`
3. Effectors are allocated to targets by priority (closest to asset first, or user-defined)
4. When an effector is fully committed, remaining targets are unengaged
5. After `reload_time_s`, the effector becomes available again for re-engagement

**Output metrics:**
- Simultaneous engagement capacity (max targets engaged at once)
- Saturation threshold (N at which effectors are fully committed)
- Re-engagement cycle time (worst-case reload across all effectors)
- Unengaged targets per scenario (how many get through)

**MVP constraint:** Targets follow straight-line approach vectors at constant speed. No evasion, coordination, or adaptive routing. This is a queuing/allocation problem, not an agent-based simulation.

#### 2.4.6 — Placement Optimisation (Greedy Heuristic)

Automated suggestion of sensor positions using a greedy approach:
1. Evaluate candidate positions across the site (grid sampling or user-nominated points)
2. Place first sensor at position that maximises coverage of uncovered area
3. Recalculate uncovered area, place next sensor at new best position
4. Repeat until all sensors placed or coverage target met

This is not globally optimal but provides a useful starting recommendation that users can manually refine. Genetic algorithm / simulated annealing variants deferred to post-MVP.

**Open questions:**
- [ ] How do we handle overlapping coverage — is double-coverage (redundancy) a positive attribute to score?
- [ ] Do we model time-of-day effects (EO/IR performance at night vs day)?
- [ ] How do we handle the difference between detection and tracking? A sensor might detect at 2km but only track reliably at 1km.
- [ ] Do we need to model comms connectivity (can the sensor talk to the C2 from its position)?
- [ ] What default values do we use for kill chain phase durations (track, identify, decide) when not specified by the user?

---

### 2.5 — Report Generation

**Purpose:** Produce a professional PDF deliverable that can be included in a defence proposal.

**Report contents:**
1. Executive summary — site overview, configuration assessed, key findings
2. Site description — terrain map, zone definitions, airspace constraints
3. Coverage analysis — heat maps showing detection/engagement coverage
4. Gap analysis — identified dead zones, blind spots, vulnerable corridors
5. Threat corridor assessment — worst-case approach analysis
6. Kill chain timeline — engagement feasibility per corridor, margin analysis
7. Engagement capacity — simultaneous targets, saturation threshold, unengaged targets
8. Configuration comparison (if multiple configs assessed)
9. Recommendations — suggested additional sensors, repositioning
8. Assumptions & limitations — explicit documentation of model limitations
9. Appendices — sensor specifications used, data sources, methodology

**Technology options:**
| Option | Pros | Cons |
|--------|------|------|
| WeasyPrint (HTML/CSS → PDF) | Full layout control, web tech | CSS print layout quirks |
| ReportLab | Python native PDF generation | Verbose API, manual layout |
| LaTeX (via Jinja2 templates) | Professional output, excellent for technical docs | LaTeX dependency, steeper template authoring |
| Matplotlib/Folium → PDF | Good for map generation | Less control over full document layout |
| Quarto / Pandoc | Markdown → PDF, good for technical reports | External dependency |

**Map/visualisation generation:**
- Coverage heat maps: Matplotlib or Folium (interactive HTML) or QGIS rendering
- 3D terrain views: Pyvista, Plotly 3D, or Three.js (if web-based)
- Site boundary overlays: GeoPandas + Matplotlib

**Open questions:**
- [ ] Do we produce a static PDF, an interactive HTML report, or both?
- [ ] Do we need to match a specific Defence report template/format?
- [ ] How do we handle classification markings on reports?

---

## 3. Technology Stack

### Language: Python 3.11+

Python is the clear choice — best geospatial ecosystem, best scientific computing ecosystem, fastest to build with Claude Code, adequate performance with NumPy vectorisation.

**Python 3.11+** specifically for:
- Performance improvements (10-60% faster than 3.10)
- `tomllib` in stdlib (for config files)
- Improved error messages during development

### Project Structure

```
salus/
├── pyproject.toml              # Project metadata, dependencies, entry points
├── src/
│   └── salus/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point
│       ├── config.py           # Configuration loading
│       ├── ingest/             # Data ingestion module
│       │   ├── __init__.py
│       │   ├── lidar.py        # LAS/LAZ → DEM/DSM pipeline
│       │   ├── terrain.py      # Pre-processed DEM/GeoTIFF import
│       │   └── boundaries.py   # GeoJSON site boundary & zone parsing
│       ├── models/             # Data models
│       │   ├── __init__.py
│       │   ├── site.py         # SiteModel (DEM, DSM, zones, structures)
│       │   ├── sensor.py       # Sensor & Effector definitions
│       │   ├── threat.py       # ThreatProfile definitions
│       │   └── scenario.py     # Scenario config (placements, threats, comparison)
│       ├── engine/             # Simulation engine
│       │   ├── __init__.py
│       │   ├── viewshed.py     # Viewshed computation (radar/EO/IR layer)
│       │   ├── rf_propagation.py   # RF coverage (FSPL + knife-edge diffraction)
│       │   ├── acoustic.py     # Acoustic range model
│       │   ├── coverage.py     # Multi-layer coverage union, gap analysis
│       │   ├── threat_corridor.py  # Threat approach analysis
│       │   ├── kill_chain.py   # D-T-I-D-E-A timeline modelling
│       │   ├── saturation.py   # Multi-target engagement & saturation
│       │   └── placement.py    # Greedy placement optimisation
│       ├── report/             # Report generation
│       │   ├── __init__.py
│       │   ├── maps.py         # Coverage/gap/corridor map rendering
│       │   ├── charts.py       # Statistics charts, kill chain diagrams
│       │   ├── pdf.py          # PDF assembly
│       │   └── templates/      # Jinja2 HTML templates for report sections
│       ├── viewer/             # Interactive viewer export
│       │   ├── __init__.py
│       │   ├── export.py       # Package pre-computed results into viewer
│       │   ├── sanitise.py     # Strip sensitive data before export
│       │   └── static/         # Viewer HTML/JS/CSS assets
│       │       ├── index.html
│       │       ├── app.js      # Leaflet/Deck.gl viewer logic
│       │       └── style.css
│       └── data/               # Bundled reference data
│           ├── sensors/        # YAML sensor definitions
│           ├── effectors/      # YAML effector definitions
│           └── threats/        # YAML threat profile definitions
├── tests/
│   ├── test_ingest/
│   ├── test_engine/
│   ├── test_report/
│   └── test_viewer/
├── Dockerfile                  # Reproducible build environment
└── docs/
```

**Key design principles:**
- Each module has a clear single responsibility
- `engine/` modules are pure computation — no I/O, no side effects, easily testable
- `models/` are dataclasses — no business logic, just structured data
- `ingest/` handles all external data formats — isolates format dependencies
- `report/` produces the PDF deliverable
- `viewer/` produces the standalone interactive HTML package — pre-computed data only, zero simulation capability
- `viewer/sanitise.py` controls what data leaves your hands — strips exact sensor specs, rounds coordinates, omits proprietary parameters
- Any module can be imported independently — no circular dependencies
- The `cli.py` orchestrates the pipeline but the engine doesn't know it's being called from a CLI (enabling future FastAPI wrapper for Tier 2)

### Core Dependencies

#### Geospatial & Terrain
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **GDAL** (via `gdal` bindings) | Viewshed computation, raster operations, CRS transforms | Industry standard. `gdal_viewshed` is the core of our radar/EO coverage layer. Nothing else does this as well. |
| **rasterio** | GeoTIFF read/write, raster manipulation | Pythonic API over GDAL for raster I/O. Cleaner than raw GDAL bindings. |
| **PDAL** (via `pdal` Python bindings) | LiDAR point cloud processing (LAS/LAZ → DEM/DSM) | Industry standard for point cloud pipelines. Handles ground classification, filtering, rasterisation. |
| **pyproj** | Coordinate reference system transforms | Wraps PROJ. Needed for CRS normalisation to GDA2020/MGA. |
| **Shapely** | Geometric operations (polygons, intersections, unions) | Fast 2D geometry. Used for zone boundaries, coverage polygon operations, gap geometry. |
| **GeoPandas** | Geospatial dataframes | Combines Pandas + Shapely. Used for site boundaries, zone management, spatial joins. |
| **Fiona** | GeoJSON/Shapefile I/O | Backend for GeoPandas file reading. Handles GeoJSON site boundary imports. |

#### Scientific Computing
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **NumPy** | Array operations, raster maths | Foundation for all grid-based calculations. Viewshed clipping, coverage union, gap detection. |
| **SciPy** | Terrain profile extraction, interpolation, optimisation | `scipy.ndimage` for raster analysis, `scipy.interpolate` for terrain profiles along ray paths. |

#### RF Propagation
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **No external dependency** | FSPL + knife-edge diffraction | These are straightforward formulas (ITU-R P.526). Implemented directly in `rf_propagation.py` using NumPy. Adding a dependency for two equations is overkill. |

#### Visualisation & Mapping
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **Matplotlib** | Coverage heat maps, gap maps, charts, statistics plots | Standard Python plotting. Produces publication-quality PNGs for PDF embedding. Full control over styling. |
| **contextily** | Basemap tiles for coverage maps | Adds OpenStreetMap/satellite basemaps behind coverage overlays. Makes maps immediately readable. Works offline with cached tiles. |

#### Report Generation
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **Jinja2** | HTML report templating | Mature, fast, well-understood. Templates for each report section. Same templates work for PDF and interactive HTML output. |
| **WeasyPrint** | HTML → PDF conversion | Renders Jinja2 HTML output to professional PDF. Better layout control than ReportLab, no LaTeX dependency. Handles embedded images, tables, multi-page layouts. |

#### Data & Configuration
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **PyYAML** | Sensor/effector/threat database files | Human-readable, easy to edit manually. Better than JSON for data that humans will maintain. |
| **Pydantic** | Data validation & models | Validates sensor specs, scenario configs, and threat profiles on load. Catches bad data early. Serialises cleanly. Works well with YAML via dict intermediary. |

#### CLI
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **Click** | CLI framework | Clean decorator-based CLI definition. Subcommands (`salus ingest`, `salus simulate`, `salus report`). Better than argparse for multi-command tools. |

#### Testing
| Package | Purpose | Why This One |
|---------|---------|-------------|
| **pytest** | Test framework | Standard. Fixtures for test site models, sensor configs. |
| **pytest-cov** | Coverage reporting | Track test coverage of engine modules. |

### Dependency Summary

```toml
# pyproject.toml [project.dependencies]
dependencies = [
    "gdal>=3.6",
    "rasterio>=1.3",
    "pdal>=3.2",
    "pyproj>=3.5",
    "shapely>=2.0",
    "geopandas>=0.13",
    "fiona>=1.9",
    "numpy>=1.24",
    "scipy>=1.10",
    "matplotlib>=3.7",
    "contextily>=1.3",
    "jinja2>=3.1",
    "weasyprint>=59",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.3",
    "pytest-cov>=4.1",
    "ruff>=0.1",
]
```

### What's NOT in the Stack (and Why)

| Excluded | Reason |
|----------|--------|
| Django / Flask / FastAPI | No web UI in MVP. When needed, FastAPI is the likely choice — add it then. |
| PostgreSQL / PostGIS | Flat files (GeoTIFF, GeoJSON, YAML) are sufficient for single-operator MVP. Add when multi-user. |
| Open3D | Overkill for 2.5D terrain. PDAL + rasterio handles everything we need. |
| SPLAT! / Radio Mobile | Considered for RF propagation wrapping, but our MVP RF model (FSPL + knife-edge) is simpler than what these tools solve. Not worth the integration overhead. |
| Folium | Considered for interactive maps, but Matplotlib handles static map generation for PDF. Folium can be added later for interactive HTML reports. |
| ReportLab | WeasyPrint is more flexible (HTML/CSS vs programmatic layout). |
| LaTeX | Professional output but adds a heavy system dependency. WeasyPrint achieves similar quality from HTML. |
| Celery / task queue | No async processing needed for single-operator CLI. Add with web UI. |

### Environment & Packaging

| Concern | Approach |
|---------|----------|
| **Package manager** | `pip` with `pyproject.toml`. Consider `uv` for faster installs. |
| **Virtual environment** | `venv` or `conda` (conda may be easier for GDAL/PDAL system dependencies). |
| **GDAL/PDAL system deps** | These are the hardest packages to install. Use `conda-forge` channel which provides pre-built binaries, or Docker. |
| **Reproducibility** | Pin exact versions in a lockfile (`pip freeze > requirements.lock` or `uv lock`). |
| **Docker** | Provide a Dockerfile for reproducible builds, especially for deployment to defence environments where "works on my machine" isn't acceptable. |
| **Offline deployment** | Bundle all wheels + Docker image for air-gapped environments. No runtime internet dependency. |

### Future Stack Additions (Post-MVP)

| When | Addition | Purpose |
|------|----------|---------|
| Phase 2 | `scikit-learn` | ML-based clutter/environment classification |
| Phase 4 | `FastAPI` | REST API for web UI backend |
| Phase 4 | `Cesium` / `Deck.gl` | 3D interactive terrain visualisation |
| Phase 4 | `PostgreSQL + PostGIS` | Multi-user site data storage |
| Phase 4 | `Redis + Celery` | Async simulation job queue |
| Phase 4 | `Folium` or `Leaflet` | Interactive HTML coverage maps |

---

## 4. Data Flow — End to End

```
1. RECEIVE site LiDAR data (LAS/LAZ) + site boundary (GeoJSON)
                    │
2. INGEST & PROCESS
   ├── Convert point cloud → DEM + DSM rasters
   ├── Normalise CRS to GDA2020
   └── Validate coverage and resolution
                    │
3. DEFINE SCENARIO
   ├── Select sensors/effectors from database
   ├── Place sensors at specified positions (or request auto-placement)
   ├── Define threat profiles to assess
   └── Define site zones (perimeter, inner, critical assets)
                    │
4. SIMULATE
   ├── Compute viewshed for each radar/EO/IR sensor (GDAL viewshed, targetHeight=0)
   ├── Compute RF coverage for each RF sensor (FSPL + knife-edge)
   ├── Compute acoustic coverage for each acoustic sensor (range circle)
   ├── Apply sensor range/arc limits to each layer
   ├── Union coverage per layer → composite coverage map
   ├── Calculate gap areas
   │
   ├── [Planning mode] Sweep bearing × altitude × dive angle
   │     └── For each combination: construct 2-waypoint DroneTrajectory, run analyse_trajectory
   │         → find_worst_trajectories → ranked TrajectoryResult list → polar diagram + overlay map
   │
   ├── [Engagement calc mode] Load named DroneTrajectory YAML
   │     └── analyse_trajectory with fine segment_length_m
   │         → DetectionEvent list (exact time, position, sensor per detection crossing)
   │         → TrajectoryResult → kill chain input
   │
   ├── Run kill chain timeline for each trajectory (D-T-I-D-E-A) using DetectionEvent timing
   ├── Run saturation analysis (N targets, effector allocation)
   ├── (If auto-place) run greedy placement optimisation
   └── (If comparison) repeat for Config B, compute delta
                    │
5. GENERATE OUTPUTS
   ├── Render per-layer coverage heat maps (radar, RF, EO/IR, acoustic)
   ├── Render composite coverage map
   ├── Render gap analysis maps
   ├── Render threat corridor overlays
   ├── Render kill chain timeline diagrams
   ├── Compile statistics (% coverage, gap area, engagement capacity, saturation threshold)
   ├── Assemble narrative sections
   ├── Output PDF report
   │
   ├── Sanitise results (strip sensitive specs, round coordinates)
   ├── Export pre-computed data as JSON (coverage polygons, gaps, corridors, kill chain, saturation)
   └── Package standalone interactive viewer (HTML/JS + JSON data)
   └── Output PDF
```

---

## 5. MVP Scope — What's In, What's Out

### In (MVP)
- LiDAR ingestion (single flight, LAS/LAZ)
- Pre-processed DEM/DSM import (GeoTIFF fallback)
- DEM/DSM generation from point cloud
- GeoJSON site boundary import
- Sensor database (manual YAML entries from public datasheets)
- Layered coverage model: viewshed for radar/EO/IR, RF propagation (FSPL + single knife-edge diffraction) for RF sensors, range circle for acoustic
- Range + arc clipping per sensor
- Multi-sensor coverage union per layer + composite
- Gap identification
- Threat trajectory analysis — both planning sweep (bearing × altitude × dive angle) and specific-trajectory engagement calcs with sub-metre detection precision via binary search
- Kill chain timeline modelling (D-T-I-D-E-A with time budgets and margin calculation), fed by `DetectionEvent` timing from trajectory analysis
- Multi-target engagement & saturation analysis (up to 20 simultaneous targets)
- Greedy heuristic placement optimisation
- Configuration comparison (A vs B) including engagement capacity
- PDF report with coverage maps, kill chain analysis, saturation metrics, and statistics

### Out (Post-MVP)
- Advanced RF propagation (multi-knife-edge, multipath, atmospheric, building penetration)
- Probabilistic detection modelling (Pd curves, Swerling models)
- Sensor fusion modelling (cueing, fused Pd, track correlation)
- Advanced placement optimisation (genetic algorithm, budget-constrained)
- Advanced swarm modelling (coordinated evasion, adaptive routing, decoys, >20 targets)
- Communications/network modelling
- Web UI
- Multi-user access / authentication
- Real-time sensor data integration
- Sensor fusion modelling
- Weather/atmospheric effects
- 3D interactive visualisation
- API for integration with C2 systems
- Classification-marked report generation

---

## 6. Key Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| LiDAR → DEM/DSM conversion quality | Coverage analysis accuracy depends on terrain model quality | Use PDAL's well-tested ground classification; validate against known elevations |
| Viewshed computation performance | Slow viewsheds block iteration speed | Use GDAL's C-based viewshed; precompute and cache; limit resolution for draft runs |
| Sensor data accuracy | "Garbage in, garbage out" — bad sensor specs = bad coverage predictions | Document all assumptions; use conservative (pessimistic) range values; flag data confidence levels |
| Coordinate system mismatches | LiDAR in one CRS, boundaries in another → misaligned analysis | Enforce CRS normalisation at ingestion; reject mismatched data early |
| Report credibility | Technical buyers will scrutinise methodology | Rigorous assumptions document; independent technical validation; acknowledge what the model does NOT do |

---

## 7. Open Architecture Questions for Discussion

1. **Modelling fidelity vs speed:** The simplified LOS + range model is fast but doesn't account for RF propagation effects (multipath, atmospheric absorption, ground clutter). At what point do we need to add physics-based modelling, and can we do it incrementally?

2. **Sensor layering:** Should each sensor type (RF, radar, EO/IR, acoustic) be modelled as a separate coverage layer with different rules, or should we abstract all sensors to a common "detection volume" model?

3. **2D vs 2.5D vs 3D:** Resolved. Planning coverage maps remain 2.5D (2D raster with elevation). Trajectory analysis is full 3D — `line_of_sight_3d` and `sensor_can_detect_point` operate in 3D space, making threat altitude and dive angle first-class inputs. True volumetric 3D (overhanging structures, multi-level buildings) is deferred to Phase 5.

4. **Engagement modelling:** For effectors, do we just model "can engage" (LOS + range), or do we need to model engagement timelines (detect → track → identify → decide → engage → assess)?

5. **Data pipeline flexibility:** Should the tool accept pre-processed DEMs (e.g. from state government LiDAR programs) as well as raw point clouds? This would broaden the input sources significantly.

6. **Offline vs connected:** Should the tool work entirely offline (important for classified environments), or can it pull data from web services (elevation APIs, satellite imagery)?

---

*This is a living document. Update as architectural decisions are made.*
