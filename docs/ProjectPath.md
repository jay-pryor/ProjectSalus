---

# Project Salus — MVP Backlog

> **Current status: Slices 0 through 11 are complete.**
> All new slices and tasks must be inserted after Slice 11.
> Do not add work items above this line or within Slices 1–11.

---

### Slice 1 — Thinnest End-to-End: Load Terrain, Compute Viewshed, Render Map

_Goal: prove the entire pipeline works by loading a DEM, computing a single viewshed from a hardcoded point, and rendering a PNG map. No sensor database, no CLI, no report — just the thinnest possible vertical path through the system._

**S1-1: Implement SiteModel dataclass and GeoTIFF DEM loader**
- _What:_ Create `src/salus/models/site.py` with a Pydantic `SiteModel` holding a NumPy DEM array, resolution, bounding box, and CRS. Create `src/salus/ingest/terrain.py` with a `load_dem(path) -> SiteModel` function using rasterio to read a GeoTIFF. Write a unit test with a tiny synthetic GeoTIFF (generated in the test fixture with rasterio).
- _Why:_ The SiteModel is the foundational data structure that every engine module consumes. GeoTIFF import (rather than LiDAR) is the fastest path to a working terrain model because it skips PDAL complexity.

**S1-2: Implement single-point viewshed computation**
- _What:_ Create `src/salus/engine/viewshed.py` with a `compute_viewshed(site, observer_x, observer_y, observer_height, max_range) -> np.ndarray` function wrapping GDAL's `gdal.ViewshedGenerate` (or the `osgeo.gdal` viewshed API). Return a boolean 2D array (visible/not visible). Write a test with a flat DEM (all cells visible) and a DEM with a ridge (cells behind ridge not visible).
- _Why:_ Viewshed is the core computational primitive for radar and EO/IR coverage. Getting this working proves the GDAL integration and validates the Docker environment.

**S1-3: Render a basic coverage map as PNG**
- _What:_ Create `src/salus/report/maps.py` with a `render_coverage_map(site, coverage_array, output_path)` function using Matplotlib. Plot the DEM as a hillshade background, overlay the viewshed as a semi-transparent coloured mask, add a scale bar and north arrow. Output PNG.
- _Why:_ Visual output proves the pipeline works end-to-end. The map rendering function will be reused by every subsequent slice. This is the payoff moment — you can see terrain and coverage.

**S1-4: Wire up a minimal CLI entry point**
- _What:_ Create `src/salus/cli.py` with a Click group and a single `viewshed` subcommand: `salus viewshed --dem path/to/dem.tif --x 500 --y 300 --height 10 --range 2000 --output map.png`. Register as a `[project.scripts]` entry point. Test it manually.
- _Why:_ Even a minimal CLI makes the tool usable and testable without writing throwaway scripts. Establishes the CLI pattern that all future commands will follow.

**S1-5: Acquire or generate a test DEM for development**
- _What:_ Either download a small public-domain DEM tile (e.g., a 2km x 2km crop from Geoscience Australia's open LiDAR program or SRTM data), or write a script that generates a synthetic terrain GeoTIFF with hills, a valley, and a flat area. Place in `tests/fixtures/`. Document provenance.
- _Why:_ Every subsequent task needs realistic test data. A real DEM catches bugs that flat synthetic data misses (CRS issues, resolution edge cases, nodata handling).

---

### Slice 2 — Sensor Database and Sensor-Clipped Viewsheds

_Goal: load sensor definitions from YAML, clip viewsheds to sensor range/arc/elevation specs, and render a coverage map for a placed sensor rather than a raw point._

**S2-1: Define Sensor and Effector Pydantic models**
- _What:_ Create `src/salus/models/sensor.py` with Pydantic models for `SensorDefinition` (name, type enum [RF/Radar/EO_IR/Acoustic], max_range_m, min_range_m, azimuth_coverage_deg, elevation_coverage_deg, frequency_bands, requires_los, mounting_height_m, cost_aud) and `EffectorDefinition` (name, type enum [RF_Jammer/Kinetic/Directed_Energy/Cyber], max_range_m, min_range_m, engagement_arc_deg, reaction_time_s, simultaneous_engagements, reload_time_s, defeat_probability, requires_los, defeat_mechanism). Add field validators (range > 0, arc 0-360, etc.).
- _Why:_ The sensor model is referenced by every engine module. Pydantic validation catches bad data at load time rather than producing silent garbage results downstream.

**S2-2: Implement YAML sensor/effector database loader**
- _What:_ Create `src/salus/ingest/sensors.py` with `load_sensors(directory) -> list[SensorDefinition]` and `load_effectors(directory) -> list[EffectorDefinition]`. Each YAML file defines one or more sensors. Write a test with a sample YAML file. Create `src/salus/data/sensors/` and `src/salus/data/effectors/` directories.
- _Why:_ YAML loading is the bridge between the human-maintained sensor research (the 15 `products_and_specs.md` files already compiled) and the simulation engine. This must work before any sensor-aware analysis can proceed.

**S2-3: Create initial sensor YAML files from existing research (5-8 representative sensors)**
- _What:_ Convert specs from the existing `Resources/` markdown files into YAML sensor definitions. Start with a representative mix: 1-2 RF sensors (e.g., DroneShield RfOne Mk2), 1-2 radars (e.g., Echodyne EchoGuard, HENSOLDT Spexer), 1 EO/IR (e.g., HGH Spynel), 1 acoustic (e.g., DroneShield DroneSentinel). Use conservative values where specs are "not publicly disclosed". Document confidence level per field.
- _Why:_ The simulation is only as good as its input data. Having a small but real sensor database enables meaningful test runs. Starting small avoids boiling the ocean — the remaining ~25 vendors can be added incrementally.

**S2-4: Create initial effector YAML files (3-4 representative effectors)**
- _What:_ Convert effector specs from existing research into YAML. Include at least: 1 RF jammer (e.g., DroneShield DroneCannon), 1 kinetic/directed energy (e.g., EOS Slinger), 1 protocol-based (e.g., Department13 MESMER). Estimate reaction_time_s, simultaneous_engagements, reload_time_s from datasheets or reasonable defaults.
- _Why:_ Effectors are needed for kill chain and saturation analysis (Slices 6-7). Populating them now while sensor context is fresh avoids context-switching later.

**S2-5: Implement viewshed clipping to sensor range and azimuth arc**
- _What:_ Add `clip_viewshed_to_sensor(viewshed_array, site, sensor, placement) -> np.ndarray` to `viewshed.py`. Apply a circular range mask (max_range, min_range) and a wedge-shaped azimuth mask (based on sensor azimuth_coverage and placement bearing). The `SensorPlacement` model (position, bearing, sensor_ref) goes in `src/salus/models/scenario.py`.
- _Why:_ Raw viewsheds extend to the horizon — useless without sensor constraints. This transforms generic visibility into sensor-specific detection coverage, which is the fundamental unit of analysis.

**S2-6: Implement SensorPlacement and ScenarioConfig models**
- _What:_ Create `src/salus/models/scenario.py` with `SensorPlacement` (sensor_name, position [x,y], bearing_deg, height_override_m) and `ScenarioConfig` (site_dem_path, site_dsm_path, boundary_path, sensor_placements list, effector_placements list, threat_profiles list). Load from a YAML scenario file.
- _Why:_ A scenario file is the user's primary input to the tool — it defines what to simulate. Every CLI command beyond the raw viewshed test will take a scenario file as input.

**S2-7: Update CLI to accept a scenario file and render sensor-clipped coverage**
- _What:_ Add a `salus simulate` subcommand that loads a scenario YAML, loads the DEM, loads sensor definitions, computes and clips viewsheds for each LOS-requiring sensor, and outputs per-sensor coverage PNGs. Replace the hardcoded viewshed command.
- _Why:_ This is the first "real" user experience — configure sensors in YAML, run one command, get coverage maps. Validates the entire data flow from scenario definition through to visual output.

---

### Slice 3 — Site Boundaries, Zones, and DSM Support

_Goal: support site boundaries (GeoJSON), zone definitions, and DSM (surface model with buildings/vegetation) in addition to DEM._

**S3-1: Implement GeoJSON boundary and zone loader**
- _What:_ Create `src/salus/ingest/boundaries.py` with `load_boundary(path) -> shapely.Polygon` and `load_zones(path) -> list[Zone]`. Each zone has a name, type (perimeter/inner/critical_asset/exclusion), and geometry. Validate CRS matches site DEM. Add zones to `SiteModel`.
- _Why:_ Site boundaries define the analysis area — coverage stats are meaningless without knowing what area needs protecting. Zone definitions enable differentiated analysis (e.g., "100% coverage required on critical assets, 80% acceptable on perimeter").

**S3-2: Implement DSM loading and dual-surface site model**
- _What:_ Extend `SiteModel` to hold both `dem_array` and `dsm_array`. Extend `load_dem` (or add `load_dsm`) in `terrain.py`. Viewshed computation should use DSM for occlusion checks (buildings/trees block LOS) while sensor heights are relative to DEM (ground level). Handle the case where only DEM is provided (DSM = DEM).
- _Why:_ DSM captures buildings and vegetation that block sensor line-of-sight. Using only DEM would show coverage through buildings, producing dangerously optimistic results. Many real sites will have pre-processed DSM GeoTIFFs available.

**S3-3: Implement CRS normalisation**
- _What:_ Add CRS validation and reprojection to `terrain.py` and `boundaries.py` using pyproj/rasterio. If inputs are not in the site's target CRS (default GDA2020 / MGA), reproject on load. Log a warning when reprojection occurs. Fail with a clear error if CRS is undefined.
- _Why:_ Real-world data arrives in mixed CRS. A boundary in WGS84 geographic and a DEM in MGA Zone 55 projected will produce silently wrong results if not normalised. This is a common and dangerous failure mode in geospatial tools.

**S3-4: Clip coverage analysis to site boundary**
- _What:_ After computing coverage arrays, mask them to the site boundary polygon. Coverage percentage calculations use boundary area as the denominator, not the full raster extent. Render boundary outline on all maps.
- _Why:_ Without boundary clipping, coverage stats include irrelevant terrain outside the site. A sensor covering empty bushland 2km away inflates coverage percentage. The boundary is the contractual scope.

**S3-5: Render zone overlays on maps**
- _What:_ Update `maps.py` to draw zone boundaries with distinct colours and labels. Critical asset zones in red, perimeter in blue, exclusion zones hatched. Add a legend.
- _Why:_ Zone visualisation on coverage maps immediately shows whether critical areas are protected. This is a primary deliverable for the PDF report.

---

### Slice 4 — RF Propagation and Acoustic Layers

_Goal: add the RF detection and acoustic detection layers, so all four sensor types (Radar, EO/IR, RF, Acoustic) have coverage models._

**S4-1: Implement Free-Space Path Loss (FSPL) calculation**
- _What:_ Create `src/salus/engine/rf_propagation.py` with `compute_fspl(distance_m, frequency_hz) -> float` (dB loss). Implement the standard FSPL formula: `FSPL = 20*log10(d) + 20*log10(f) + 20*log10(4*pi/c)`. Write tests against known reference values.
- _Why:_ FSPL is the foundation of the RF detection model. RF sensors (passive spectrum analysers like DroneShield RfOne) detect drone control signals, and FSPL determines whether the signal is above the sensor's sensitivity threshold at a given range.

**S4-2: Implement single knife-edge diffraction (ITU-R P.526)**
- _What:_ Add `compute_knife_edge_loss(terrain_profile, tx_height, rx_height, frequency_hz) -> float` to `rf_propagation.py`. Extract terrain profile between two points from the DEM using bilinear interpolation along the path. Find the dominant obstruction, compute the Fresnel-Kirchhoff diffraction parameter (nu), and look up additional loss. Test against textbook examples.
- _Why:_ Knife-edge diffraction models RF signal bending over terrain obstacles. Without it, the RF model is either binary LOS (too pessimistic — RF diffracts over ridges) or pure FSPL (too optimistic — ignores terrain entirely). This is the ITU-recommended approach for single-obstruction scenarios.

**S4-3: Implement RF coverage grid computation for a sensor placement**
- _What:_ Add `compute_rf_coverage(site, sensor, placement, sensitivity_dbm) -> np.ndarray` that iterates over grid cells within sensor range, computes FSPL + knife-edge loss for each cell, compares received signal level against sensor sensitivity, and returns a boolean coverage array. Apply azimuth arc clipping. Vectorise where possible (FSPL for all cells at once, knife-edge only for cells near terrain obstacles).
- _Why:_ This completes the RF detection layer. RF sensors are typically the first to detect a drone (long range, 360-degree, no LOS required for signal detection), so this layer is high-value for coverage analysis.

**S4-4: Implement acoustic coverage model (range circle with noise penalty)**
- _What:_ Create `src/salus/engine/acoustic.py` with `compute_acoustic_coverage(site, sensor, placement, ambient_noise_db) -> np.ndarray`. Model as a simple range circle with configurable ambient noise penalty reducing effective range. No terrain occlusion (sound diffracts around obstacles at the frequencies relevant to drone detection). Apply range mask only.
- _Why:_ Acoustic sensors are the simplest model — range circles — but they fill an important niche: detecting drones that are RF-silent (autonomous/pre-programmed). Keeping the model simple is architecturally appropriate per the SimulationArchitecture doc.

**S4-5: Implement sensor-type dispatch in coverage computation**
- _What:_ Create a dispatcher function `compute_sensor_coverage(site, sensor, placement) -> np.ndarray` that routes to viewshed (Radar, EO_IR), RF propagation (RF), or acoustic (Acoustic) based on `sensor.type`. This becomes the single entry point the rest of the engine calls.
- _Why:_ Downstream code (coverage union, gap analysis, threat corridors) should not need to know which propagation model a sensor uses. The dispatcher centralises that logic and makes adding new sensor types trivial.

---

### Slice 5 — Multi-Sensor Coverage, Gaps, and Statistics

_Goal: combine individual sensor coverages into composite maps, identify gaps, and compute coverage statistics._

**S5-1: Implement per-layer coverage union**
- _What:_ Create `src/salus/engine/coverage.py` with `compute_layer_coverage(site, placements_by_type) -> dict[SensorType, np.ndarray]`. For each sensor type, union (logical OR) all individual sensor coverage arrays. Return per-layer coverage rasters.
- _Why:_ Individual sensor maps are useful for debugging, but the operationally meaningful view is "can any radar detect here?" This per-layer union is the basis for all aggregate analysis.

**S5-2: Implement composite coverage (any-sensor-detects) and gap identification**
- _What:_ Add `compute_composite_coverage(layer_coverages) -> np.ndarray` (logical OR across all layers) and `compute_gaps(composite, boundary_mask) -> np.ndarray` (boundary minus composite). Compute `GapAnalysis` result: gap area in m2, gap percentage, gap geometry as Shapely polygons (via raster-to-polygon conversion).
- _Why:_ The composite map and gap analysis are the headline deliverables of the tool. "Your site has 94% coverage with these gaps" is the primary value statement in the PDF report.

**S5-3: Implement coverage statistics computation**
- _What:_ Add `compute_coverage_stats(site, layer_coverages, composite, gaps, zones) -> CoverageStats`. Compute: total coverage %, per-layer coverage %, per-zone coverage %, gap area, redundancy map (how many sensors cover each cell), largest contiguous gap.
- _Why:_ Numbers complement maps. "Critical asset zone: 100% covered, 2.3x average redundancy. Perimeter: 87% covered, largest gap 340m2 on NE approach" — this is what goes into the executive summary.

**S5-4: Render per-layer and composite coverage maps**
- _What:_ Update `maps.py` to render: per-layer coverage maps (one per sensor type, distinct colour per type), composite coverage map (all layers overlaid), gap map (gaps highlighted in red against greyed-out coverage). Add contextily basemap tiles for geographic context.
- _Why:_ These maps are the visual core of the report. Adding basemap tiles (satellite or street map) makes coverage maps immediately interpretable by non-technical stakeholders.

**S5-5: Render redundancy heat map**
- _What:_ Add a redundancy map where cell colour indicates number of sensors covering it (1 = yellow, 2 = green, 3+ = dark green, 0 = red). Include in map outputs.
- _Why:_ Redundancy is a key resilience metric — if one sensor fails, is the area still covered? This map immediately shows single-points-of-failure in the configuration.

**S5-6: Update CLI `simulate` command to run full multi-sensor analysis**
- _What:_ Extend `salus simulate` to compute all sensor coverages, produce per-layer unions, composite, gaps, stats, and output all maps. Print summary stats to console. Accept `--output-dir` for map PNGs.
- _Why:_ This is the first command that produces operationally useful output. A user can now define a full sensor configuration, run one command, and get coverage maps and statistics.

---

### Slice 6 — Threat Corridors

_Goal: model drone approach corridors and assess coverage along each path._

**S6-1: Define ThreatProfile and ThreatCorridor models**
- _What:_ Create `src/salus/models/threat.py` with `ThreatProfile` (name, rcs_m2, rf_signature, max_speed_ms, typical_altitude_m, approach_vectors list, evasion_capability enum). Create `ThreatCorridor` (bearing_deg, altitude_m, width_m, start_distance_m). Add threat YAML files to `src/salus/data/threats/` with 2-3 representative profiles (e.g., "DJI Mavic low-slow", "Racing drone fast approach", "Fixed-wing ISR").
- _Why:_ Threat profiles tie sensor coverage to operational relevance. "94% coverage" means nothing without asking "against what threat, from what direction?"

**S6-2: Implement corridor coverage analysis**
- _What:_ Create `src/salus/engine/threat_corridor.py` with `analyse_corridor(site, composite_coverage, corridor, threat, protected_point) -> CorridorResult`. Sample the composite coverage along the corridor path at terrain resolution. Compute: coverage percentage along path, first detection distance, last uncovered segment before target, time-in-coverage (distance-in-coverage / drone speed).
- _Why:_ Corridor analysis transforms 2D coverage maps into operationally meaningful metrics: "A drone approaching from the NE at 50m AGL is first detected at 3.2km, spends 45 seconds in coverage before reaching the asset."

**S6-3: Implement worst-case corridor identification**
- _What:_ Add `find_worst_corridors(site, composite, threat, protected_point, num_bearings=36) -> list[CorridorResult]`. Test all approach bearings (every 10 degrees), rank by coverage percentage (ascending), return sorted. Identify the single worst-case approach.
- _Why:_ Defenders need to know their weakest direction. "Your worst approach vector is 047 degrees — only 62% covered due to ridge shadow on NE side." This drives sensor repositioning recommendations.

**S6-4: Render threat corridor overlay maps**
- _What:_ Update `maps.py` to render corridor paths on the composite coverage map, colour-coded by coverage percentage (red = poor, green = good). Mark first detection points. Add a polar diagram showing coverage percentage by bearing (radar chart).
- _Why:_ The corridor overlay is a key report visual. The polar diagram gives an instant 360-degree picture of site vulnerability.

**S6-5: Update CLI and scenario config for threat analysis**
- _What:_ Add threat profiles to `ScenarioConfig`. Add `--threats` flag to `salus simulate`. Output corridor analysis results to console and maps to output directory.
- _Why:_ Integrates threat analysis into the existing pipeline rather than requiring a separate command.

---

### Slice 6.1 — 3D LOS Primitive and Sensor Detection Point Query

_Goal: establish the geometric foundation for 3D detection. Replace the altitude-blind 2D composite lookup with a physically correct point-to-point line-of-sight check and a sensor detection predicate that operates in full 3D space. This is the primitive that all subsequent trajectory analysis builds on._

_Context: the current architecture computes a single 2D composite coverage map (targetHeight=0) and samples it for all threat altitudes, producing identical results regardless of whether a threat flies at 20 m or 150 m AGL. This slice fixes that at the geometric layer._

**S6.1-1: Implement `line_of_sight_3d` in `engine/viewshed.py`**
- _What:_ Add `line_of_sight_3d(site, x1, y1, z1_abs, x2, y2, z2_abs) -> bool` to `viewshed.py`. Ray-march from point 1 to point 2 in 3D, sampling the DEM at each horizontal step and checking whether terrain rises above the line connecting the two absolute-elevation endpoints. Returns True if no terrain occlusion is found. Write tests: unobstructed pair on flat terrain (True), pair with ridge between them (False), pair where target is elevated above the ridge (True).
- _Why:_ This is the foundational geometric primitive. Every sensor detection check in 3D reduces to "can the sensor see this point in 3D space?" The existing GDAL viewshed API takes a fixed targetHeight across the whole raster — it cannot answer a point query to a specific elevated position. This function does exactly that.

**S6.1-2: Add `elevation_boresight_deg` to `SensorDefinition` and update sensor YAMLs**
- _What:_ Add `elevation_boresight_deg: float = 0.0` to `SensorDefinition` in `models/sensor.py`. This defines the centre of the sensor's elevation arc (0 = horizontal, positive = upward, negative = downward). The existing `elevation_coverage_deg` field defines the arc width; `elevation_boresight_deg` defines where that arc is centred. Add the field to all existing sensor YAML files under `src/salus/data/sensors/` (most will be 0.0). Update field validators.
- _Why:_ `elevation_coverage_deg` was always stored but never used in any computation because there was no way to know where in the vertical plane the arc was centred. A ground radar covering -5° to +30° is fundamentally different from one covering +60° to +85°. Without this field, the sensor model cannot correctly gate detections by elevation angle.

**S6.1-3: Create `engine/trajectory.py` with `sensor_can_detect_point`**
- _What:_ Create `src/salus/engine/trajectory.py`. Implement `sensor_can_detect_point(site, sensor, placement, tx, ty, tz_agl) -> bool`. The function: (1) computes absolute target elevation as `dem[target_cell] + tz_agl`; (2) calls `line_of_sight_3d` from sensor absolute position to target absolute position (skipping LOS for `requires_los=False` sensors); (3) checks 3D slant range against `sensor.min_range_m` / `sensor.max_range_m`; (4) checks horizontal bearing against azimuth arc; (5) checks elevation angle against `elevation_boresight_deg ± elevation_coverage_deg / 2`. Returns True only if all checks pass. Write tests for each check failing independently.
- _Why:_ This is the first function that makes threat altitude actually affect detection outcomes. A drone at 150 m AGL visible over terrain that would block a 20 m drone, or outside a radar's elevation arc at close range, will now be modelled correctly.

---

### Slice 6.2 — DroneTrajectory Model

_Goal: define the data model for a 3D piecewise-linear drone trajectory. A trajectory is an ordered list of 3D waypoints; each consecutive pair defines one linear segment. Curved or complex paths are approximated by combining many shorter segments. Configurable segment length controls simulation fidelity._

**S6.2-1: Add `TrajectoryWaypoint` and `DroneTrajectory` to `models/threat.py`**
- _What:_ Add `TrajectoryWaypoint(x, y, z_agl)` — a single 3D point in CRS coordinates with AGL altitude. Add `DroneTrajectory(waypoints, speed_ms)` — an ordered list of `TrajectoryWaypoint` with minimum 2 waypoints validated, speed > 0 validated, all coordinates finite validated. Keep `ThreatCorridor` as-is — it remains valid as a convenience model for the existing horizontal corridor sweep. Add YAML serialisation round-trip tests.
- _Why:_ The trajectory model is deliberately minimal — just geometry and speed. It is decoupled from `ThreatProfile` because the same trajectory can be flown by different threats, and the same threat can fly different trajectories. Pydantic validation catches degenerate trajectories (single waypoint, NaN coordinates, zero speed) at load time.

**S6.2-2: Add `trajectory_path` to `ScenarioConfig` in `models/scenario.py`**
- _What:_ Add `trajectory_path: Path | None = None` to `ScenarioConfig`. This optional field points to a YAML file defining a `DroneTrajectory` for a specific named threat approach. Add path validation (same pattern as `site_dem_path`). Update `load_scenario` in `ingest/scenario.py` to resolve and load the trajectory if present.
- _Why:_ A scenario file should be able to specify a concrete trajectory for engagement calc runs (e.g., "simulate this specific known approach path"), separately from the bearing-sweep planning mode. Making it optional keeps the simple corridor-sweep workflow unchanged.

---

### Slice 6.3 — Trajectory Analysis Engine

_Goal: implement the core trajectory analysis — step along each segment of a 3D piecewise path at configurable resolution, determine per-sensor detection events, and use binary search to find the precise detection crossing to sub-metre accuracy._

**S6.3-1: Define `DetectionEvent` and `TrajectoryResult` in `engine/trajectory.py`**
- _What:_ Add frozen dataclasses: `DetectionEvent(sensor_name, time_s, position_x, position_y, position_z_agl, distance_to_asset_m, segment_index)` and `TrajectoryResult(detection_events, first_detection, time_to_asset_s, time_in_detection_s, time_undetected_s, asset_reached_undetected)`. `first_detection` is the earliest `DetectionEvent` across all sensors, or None if the asset is reached without detection. Write unit tests for both dataclasses.
- _Why:_ `DetectionEvent` captures everything needed for engagement calc downstream — not just that detection occurred, but exactly when, where, which sensor, and how far the drone still had to travel. This is the data that feeds the kill chain timeline in Slice 7.

**S6.3-2: Implement `analyse_trajectory` with binary search refinement**
- _What:_ Add `analyse_trajectory(site, sensor_placements, trajectory, segment_length_m=1.0) -> TrajectoryResult` to `engine/trajectory.py`. For each segment of the trajectory: generate sample points at `segment_length_m` intervals; at each sample, check all sensors using `sensor_can_detect_point`; when a detection state transition is found (undetected → detected), binary search within that interval to find the crossing point to within `segment_length_m / 100` tolerance. Aggregate all `DetectionEvent` objects, compute timing metrics from `speed_ms`. Write tests: fully undetected trajectory, fully detected, detection mid-path, detection after terrain masking.
- _Why:_ The binary search is what delivers sub-metre (and therefore sub-second) timing precision. Stepping at `segment_length_m` finds the interval; binary search pins the exact crossing. Setting `segment_length_m=10.0` gives fast planning-fidelity runs; `segment_length_m=0.5` gives engagement-calc precision — the same function, controlled by one parameter.

**S6.3-3: Refactor `find_worst_corridors` to delegate to `analyse_trajectory`**
- _What:_ Update `find_worst_corridors` in `engine/threat_corridor.py` to construct a two-waypoint `DroneTrajectory` for each bearing (start point at `start_distance_m` in the bearing direction, endpoint at `protected_point`, both at `threat.typical_altitude_m` AGL) and call `analyse_trajectory`. Map `TrajectoryResult` fields back to `CorridorResult` fields for backward compatibility. The 2D composite coverage path is fully retired for corridor analysis. Write regression tests comparing old and new outputs on simple flat-terrain cases.
- _Why:_ This makes the horizontal corridor sweep a thin wrapper over the general trajectory engine rather than a separate implementation. Backward compatibility is maintained — all S6 CLI outputs and tests continue to work. The refactor also fixes the core defect: corridor coverage now correctly varies by threat altitude.

---

### Slice 6.4 — Worst-Trajectory Sweep

_Goal: extend the planning-mode sweep from a 1D bearing search to a 3D parameter space sweep — bearing × start altitude × dive angle — so the worst-case approach can be identified across all realistic threat geometries, not just horizontal corridors._

**S6.4-1: Implement `find_worst_trajectories` in `engine/trajectory.py`**
- _What:_ Add `find_worst_trajectories(site, sensor_placements, threat, protected_point, num_bearings=36, altitudes_m=None, dive_angles_deg=None, segment_length_m=5.0) -> list[TrajectoryResult]`. Default `altitudes_m` to `[threat.typical_altitude_m]` and `dive_angles_deg` to `[0]` (horizontal) if not provided. For each (bearing, altitude, dive_angle) combination, construct a two-waypoint trajectory: start point is `(start_distance_m, bearing, altitude)` from the protected point; end point is the protected point at 0 m AGL. Sort results by `time_in_detection_s` ascending (least covered, i.e. worst-case, first). Write tests: single bearing returns one result; full sweep returns `num_bearings × len(altitudes) × len(dive_angles)` results; worst result has lowest time_in_detection_s.
- _Why:_ A drone operator planning an attack will select the bearing AND the altitude AND the dive profile that minimises detection time. The 1D bearing sweep of S6-3 only finds the worst bearing at a single altitude and zero dive angle — it misses the true worst case. This sweep exposes the full parameter space. Default values preserve backward-compatible behaviour for simple cases.

**S6.4-2: Add trajectory sweep parameters to `ScenarioConfig`**
- _What:_ Add optional fields to `ScenarioConfig`: `sweep_altitudes_m: list[float] | None = None`, `sweep_dive_angles_deg: list[float] | None = None`, `sweep_segment_length_m: float = 5.0`. These control the planning sweep when `find_worst_trajectories` is invoked via the CLI. Validate that all altitudes are non-negative finite values, all dive angles are in [-90, 0] (descending), segment length is positive.
- _Why:_ Exposing these as scenario-level parameters lets users configure a high-fidelity engagement sweep (`segment_length_m=0.5`, multiple altitudes and dive angles) vs a fast planning sweep (`segment_length_m=10.0`, single altitude, horizontal only) without changing code.

---

### Slice 6.5 — Trajectory Visualisation and CLI

_Goal: render trajectory analysis results as maps, and wire the full 3D trajectory engine into the CLI so both planning sweeps and specific-trajectory engagement calcs are accessible from `salus simulate`._

**S6.5-1: Add `render_trajectory_map` to `report/maps.py`**
- _What:_ Add `render_trajectory_map(site, composite_coverage, trajectory_results, protected_point, output_path, title, sensor_positions)`. Render the top-down coverage map as a background. Draw each trajectory path as a 3D-projected line (colour-coded by time_in_detection_s — red = low detection exposure, green = high). Mark `DetectionEvent` positions as circle markers labelled with sensor name and time. Mark the protected point as a star. For the polar diagram, extend `render_corridor_polar_diagram` to accept `TrajectoryResult` lists and colour bars by a secondary dimension (altitude or dive angle) if a multi-parameter sweep was run.
- _Why:_ The existing corridor overlay map and polar diagram were designed for 1D bearing sweeps. The new map needs to show 3D trajectory paths and detection event positions, which requires a different rendering approach. The protected point and sensor positions remain anchors on all maps.

**S6.5-2: Update `cli.py` for 3D trajectory analysis**
- _What:_ In the `simulate` command: (1) if `sc.trajectory_path` is set, load the `DroneTrajectory`, call `analyse_trajectory` for each matched threat, print `TrajectoryResult` (first detection time/position/sensor, time to asset, time in detection, asset reached undetected), and render `render_trajectory_map`; (2) if no trajectory is set, run `find_worst_trajectories` using `sc.sweep_altitudes_m`, `sc.sweep_dive_angles_deg`, and `sc.sweep_segment_length_m` (defaulting to single-altitude horizontal sweep for backward compatibility). Add `--segment-length` CLI flag to override `sweep_segment_length_m` at runtime.
- _Why:_ The `--segment-length` flag is the primary fidelity knob — users can run `salus simulate --segment-length 10` for a fast planning pass and `salus simulate --segment-length 0.5` for a precision engagement calc without editing the scenario file. Both modes use the same underlying engine.

**S6.5-3: Update scenario YAML documentation and add trajectory YAML example**
- _What:_ Add a sample `trajectory_example.yaml` to `demo/06_slice6/` showing a diving FPV approach (3 waypoints: high altitude far out → medium altitude mid-range → asset at low altitude). Update `docs/SimulationArchitecture.md` data flow section to show the trajectory analysis path alongside the existing coverage map path.
- _Why:_ A worked example YAML is the fastest way for a user to understand the trajectory format. It also serves as a regression test input for the trajectory engine.

---

### Slice 6.6 — Adversarial Path Planning

_Goal: autonomously discover the worst-case drone approach route — the path that minimises detection exposure by exploiting terrain masking and sensor coverage gaps — without the analyst needing to prescribe or guess it. This answers the question: "Is there a route into this site that we haven't noticed?"_

_Context: the planning sweep in S6.4 searches over bearing × altitude × dive angle but all candidates are straight-line approaches. A sophisticated adversary would exploit valley masking, fly behind terrain features, and thread through sensor gaps along a complex waypointed route. Adversarial path planning finds that route automatically using a 3D detection cost grid and graph search._

**S6.6-1: Build 3D detection cost grid in `engine/path_planner.py`**
- _What:_ Create `engine/path_planner.py`. Implement `build_detection_cost_grid(site, sensors, placements, altitude_bands_m) -> DetectionCostGrid`. For each DEM cell (row, col) at each altitude band, call `sensor_can_detect_point` for every sensor-placement pair and record the detection count. `DetectionCostGrid` is a dataclass holding the 3D numpy array (shape: `[n_altitude_bands, rows, cols]`), the altitude band list, site origin, and resolution. Write tests: flat DEM with one sensor — cells inside range and arc have detection count ≥ 1, cells outside have count 0. Write test that a ridge blocks detection on the far side (count 0 behind ridge even within range).
- _Why:_ `sensor_can_detect_point` is the correct primitive for this — the cost grid is simply a batched application of it across the full site volume. Building it once per sensor layout change amortises the cost across all path queries. The grid makes the search phase fast: path search reads precomputed values rather than calling `sensor_can_detect_point` at every node expansion.

**S6.6-2: Implement `find_adversarial_trajectory` using Dijkstra's graph search**
- _What:_ Add `find_adversarial_trajectory(site, cost_grid, origin_x, origin_y, origin_z_agl, asset_x, asset_y, speed_ms, altitude_transition_cost) -> DroneTrajectory` to `engine/path_planner.py`. Treat the 3D grid as a weighted directed graph: each node is a `(row, col, altitude_band_idx)` triple; edges connect to the 8 horizontal neighbours at the same altitude band and to the same cell at adjacent altitude bands (altitude transitions). Edge weight = detection count at the destination node × cell area + altitude_transition_cost × altitude_step. Run Dijkstra's from the grid node nearest `(origin_x, origin_y, origin_z_agl)` to the node nearest the asset. Convert the resulting node path to a `DroneTrajectory` by mapping each node back to its (x, y, z_agl) centroid as a `TrajectoryWaypoint`. Write tests: on flat DEM with a single sensor, path routes around the sensor's detection radius. On terrain with a valley, path follows the valley even if it is longer in distance.
- _Why:_ Dijkstra's is exact (finds the true minimum-cost path) and runs in O((V + E) log V) time — tractable for a 3 km × 3 km site at 5 m resolution across 5 altitude bands (~1.8 M nodes). The returned `DroneTrajectory` is a standard model that feeds directly into `analyse_trajectory` (S6.3) for the full detection timeline, and can be written to YAML for repeat analysis or sharing.

**S6.6-3: Wire adversarial path planning into CLI and reports**
- _What:_ Add `--adversarial` flag to `salus simulate`. When set, requires `--protected-point` and at least one threat profile. For each threat profile: determine threat origin (use worst-corridor bearing from S6.4 at `typical_altitude_m` as start point, or accept `--origin` coordinates); call `build_detection_cost_grid` for the configured altitude bands; call `find_adversarial_trajectory`; run `analyse_trajectory` on the result; render the discovered path on a new `render_adversarial_map` output (path overlaid on coverage heatmap with detection events marked). Add `render_adversarial_map` to `report/maps.py`. Write integration test that runs the full adversarial pipeline on a synthetic ridge DEM and asserts the path goes around the ridge rather than over it.
- _Why:_ The adversarial path planner is a premium capability — it is what distinguishes Salus from a coverage mapper. Making it accessible via a single CLI flag (`salus simulate --adversarial`) ensures customers can run it without programming. The integration test protects the core claim: that the discovered path actually exploits terrain.

---

### Slice 7 — Kill Chain Timeline (D-T-I-D-E-A)

_Goal: model the engagement timeline from first detection through to drone neutralisation and determine whether the kill chain can complete before the drone reaches the asset._

**S7-1: Define KillChainConfig and KillChainResult models**
- _What:_ Add to `models/scenario.py`: `KillChainConfig` with phase durations (track_time_s, identify_time_s, decide_time_s, assess_time_s — these are operator/C2 constants) and per-effector values (reaction_time_s from effector definition). `KillChainResult` holds: available_time_s, required_time_s, margin_s, first_detection_range_m, engagement_feasible bool, second_engagement_possible bool.
- _Why:_ The kill chain is what separates this tool from a simple coverage mapper. "Can you actually shoot it down before it arrives?" is the question decision-makers ask.

**S7-2: Implement kill chain timeline computation**
- _What:_ Create `src/salus/engine/kill_chain.py` with `compute_kill_chain(corridor_result, kill_chain_config, effectors) -> KillChainResult`. Calculate: available_time = first_detection_range / drone_speed. required_time = sum of all phase durations. margin = available - required. Check second engagement: margin > effector reload_time + engage_time + assess_time.
- _Why:_ This is the core value calculation. A 10-second margin means the system works. A negative margin means the drone gets through. The second-engagement check assesses resilience to a miss.

**S7-3: Implement kill chain for all corridors and worst-case identification**
- _What:_ Add `compute_all_kill_chains(corridor_results, kill_chain_config, effectors) -> list[KillChainResult]`. Identify corridors where kill chain fails (margin < 0). Identify corridors where only one engagement is possible (no second chance).
- _Why:_ A configuration might have great coverage but still fail the kill chain on certain corridors due to late detection. This analysis surfaces those critical gaps.

**S7-4: Render kill chain timeline diagrams**
- _What:_ Create `src/salus/report/charts.py` with a Gantt-style horizontal bar chart showing the kill chain phases (D-T-I-D-E-A) as coloured segments on a time axis, with available time shown as the total bar width. Green if margin > 0, red if negative. Show one diagram per corridor or a summary of worst/best/average.
- _Why:_ The timeline diagram is one of the most compelling visuals in the report — it makes the engagement feasibility immediately intuitive to non-technical reviewers.

---

### Slice 8 — Multi-Target Engagement and Saturation Analysis

_Goal: model simultaneous drone threats and determine when the defence configuration becomes saturated._

**S8-1: Define SaturationScenario and SaturationResult models**
- _What:_ Add `SaturationScenario` to models: list of simultaneous targets (each with approach_vector, altitude, speed, threat_profile_ref), priority_rule enum (closest_to_asset / highest_threat / user_defined). `SaturationResult`: simultaneous_engagement_capacity, saturation_threshold_n, unengaged_targets per scenario, per-effector utilisation.
- _Why:_ The saturation model answers "how many drones before the defence is overwhelmed?" This is a critical procurement argument: "you need N effectors to handle M simultaneous threats."

**S8-2: Implement effector allocation algorithm**
- _What:_ Create `src/salus/engine/saturation.py` with `allocate_effectors(targets, effectors, placements, priority_rule) -> AllocationResult`. Sort targets by priority. For each target, find available effectors with LOS and range. Allocate until effector simultaneous_engagement capacity exhausted. Track unengaged targets.
- _Why:_ This is a constrained assignment problem. The greedy priority-based allocation is operationally realistic (defenders engage the most dangerous threat first) and computationally simple.

**S8-3: Implement saturation threshold sweep**
- _What:_ Add `find_saturation_threshold(effectors, placements, site, threat_profile, max_targets=20) -> int`. Incrementally increase target count from 1 to max_targets (distributed across worst-case corridors). For each count, run allocation. The saturation threshold is the N where at least one target is unengaged.
- _Why:_ The threshold number is a headline metric: "Your configuration can simultaneously engage up to 7 targets; at 8+, threats begin getting through." This directly informs how many effectors to purchase.

**S8-4: Implement reload/re-engagement timeline**
- _What:_ Extend saturation analysis with a temporal dimension: after first engagement volley, effectors with reload_time_s become available again. Model a 60-second engagement window. Track how many total engagements are possible, and the re-engagement cycle time.
- _Why:_ Real attacks are not instantaneous — they unfold over time. A jammer with 0s reload can re-engage immediately. A kinetic system with a 10s reload creates a vulnerability window. This temporal model captures that.

**S8-5: Render saturation analysis charts**
- _What:_ Add to `charts.py`: (1) a bar chart of targets-vs-unengaged for N=1..20, with saturation threshold marked; (2) a timeline chart showing effector busy/idle status during a scenario; (3) a table of per-effector utilisation.
- _Why:_ These charts make the saturation analysis actionable. The bar chart is the headline visual; the timeline shows which specific effector is the bottleneck.

**S8-6: Update scenario config and CLI for saturation analysis**
- _What:_ Add saturation scenarios to `ScenarioConfig` YAML. Add `--saturation` flag to `salus simulate`. Output saturation metrics to console and charts to output directory.
- _Why:_ Integrates saturation analysis into the existing pipeline.

---

### Slice 9 — Greedy Placement Optimisation

_Goal: automatically suggest sensor positions that maximise coverage._

**S9-1: Implement candidate position grid generation**
- _What:_ Create `src/salus/engine/placement.py` with `generate_candidate_positions(site, boundary, step_m, exclusion_zones) -> list[Position]`. Generate a grid of candidate positions within the site boundary, excluding exclusion zones. Filter positions on steep slopes or water bodies if detectable from the DEM.
- _Why:_ The candidate grid defines the search space. Step size controls the trade-off between optimality and computation time (10m step on a 2km site = 40,000 candidates).

**S9-2: Implement greedy placement algorithm**
- _What:_ Add `greedy_place_sensors(site, sensors_to_place, candidates, existing_coverage) -> list[SensorPlacement]`. For each sensor to place: compute coverage for all candidate positions, score each by uncovered area newly covered, place at best position, update coverage, repeat. Support a target coverage threshold to stop early.
- _Why:_ Greedy placement gives a good-enough starting configuration that users can refine. Globally optimal placement is NP-hard; the greedy heuristic is O(n*m) where n=sensors, m=candidates — tractable for MVP.

**S9-3: Implement placement scoring with zone weighting**
- _What:_ Extend the scoring function to weight coverage by zone: critical_asset cells count 3x, inner zone 2x, perimeter 1x. Support user-configurable weights. The placement algorithm then prioritises covering high-value areas.
- _Why:_ Uniform coverage scoring would place sensors to cover empty perimeter instead of critical assets. Zone weighting aligns automated placement with operational priorities.

**S9-4: Add placement optimisation to CLI**
- _What:_ Add `salus optimise` subcommand: takes a scenario with sensors to place (type + count) and outputs recommended placements. Optionally write an updated scenario YAML with placements filled in, which can then be fed to `salus simulate`.
- _Why:_ The optimise-then-simulate workflow lets users generate a starting configuration, review the maps, then manually adjust placements and re-simulate.

---

### Slice 10 — Configuration Comparison (A vs B)

_Goal: run two configurations against the same site and produce a side-by-side comparison._

**S10-1: Implement configuration comparison engine**
- _What:_ Create `src/salus/engine/comparison.py` (or add to `coverage.py`) with `compare_configs(result_a, result_b) -> ComparisonResult`. Compute: coverage delta (where B covers that A does not and vice versa), per-zone coverage difference, cost difference, engagement capacity difference, saturation threshold difference.
- _Why:_ Configuration comparison is the "what-if" capability that makes the tool valuable for procurement decisions. "Config B costs $200K more but closes the NE gap and raises saturation threshold from 5 to 9."

**S10-2: Render comparison maps and charts**
- _What:_ Add to `maps.py`: side-by-side coverage maps (A left, B right), delta map (green = B-only coverage, red = A-only coverage, grey = both). Add to `charts.py`: comparison statistics table, grouped bar chart of per-zone coverage for A vs B.
- _Why:_ Visual comparison is immediately compelling. The delta map highlights exactly where the configurations differ, focusing attention on the decision-relevant areas.

**S10-3: Add comparison to CLI**
- _What:_ Add `salus compare --config-a scenario_a.yaml --config-b scenario_b.yaml --output-dir comparison/` subcommand. Runs both simulations, then generates comparison outputs.
- _Why:_ Completing the comparison CLI makes all analytical capabilities accessible from the command line.

---

### Slice 11 — Effector Coverage Layer

_Goal: model effector engagement zones (where can effectors actually neutralise a drone?)._

**S11-1: Implement effector coverage computation**
- _What:_ Add effector coverage to the engine: viewshed-based engagement zones for kinetic/DE effectors (LOS required), range-based circles for RF jammers (LOS not required for omnidirectional jamming). Clip to effector range and engagement arc. Output as a separate coverage layer.
- _Why:_ Detection coverage without effector coverage is incomplete — knowing where you can see a drone is different from knowing where you can stop it. The effector layer reveals "detection without engagement capability" gaps.

**S11-2: Render effector coverage maps**
- _What:_ Add effector coverage as a distinct map layer (e.g., blue overlay). Render a "detection-without-engagement" gap map: areas with sensor coverage but no effector coverage.
- _Why:_ "You can detect it here but can't do anything about it" is a critical finding. This map directly drives effector placement decisions.

---

### Slice 11.5 — Bearing-Aware Placement Optimisation

_Goal: extend the greedy sensor and effector placement optimiser to jointly optimise position and boresight bearing, so that directional sensors and effectors are pointed in the direction that maximises coverage rather than defaulting to north._

_Context: S9 implemented greedy placement but hardcodes `bearing_deg=0.0` for every placed unit. For 360° sensors (RF, acoustic) this is harmless. For directional radars and effectors with narrow engagement arcs it can produce significantly suboptimal configurations. The fix is architecturally straightforward: viewshed computation is bearing-independent, so bearings can be swept cheaply as arc masks applied to a single precomputed viewshed — no additional ray-marching required._

**S11.5-1: Precompute and cache viewsheds per candidate position**
- _What:_ Refactor `greedy_place_sensors` in `engine/placement.py` to separate viewshed computation from scoring. For each placement step, compute and cache a viewshed array for every candidate position before any bearing sweep begins. Replace the current inline `compute_sensor_coverage` call with a two-phase approach: (1) compute all M viewsheds, (2) score all M × B (position, bearing) pairs using arc masks applied to cached viewsheds. Apply the same refactor to effector placement if a symmetric function exists. Write tests confirming that caching produces identical scores to the non-cached path.
- _Why:_ Viewshed ray-marching is O(rows × cols) per position and dominates runtime. Bearing sweep is just a cheap arc-mask operation. Separating the two ensures the bearing sweep adds only ~15–25% overhead rather than a full B× multiplication of the expensive step. This is the prerequisite structural change before adding bearing candidates.

**S11.5-2: Add candidate bearing sweep to the scoring loop**
- _What:_ Add `bearing_step_deg: float = 10.0` parameter to `greedy_place_sensors` (and any effector equivalent). For each candidate position, generate bearing candidates `[0, bearing_step_deg, 2×bearing_step_deg, …, 360 − bearing_step_deg]`. For each (position, bearing) pair, apply the azimuth arc mask to the cached viewshed and score. Skip the bearing sweep entirely for sensors where `azimuth_coverage_deg == 360` — their score is bearing-independent. Return the `SensorPlacement` / `EffectorPlacement` with the optimal bearing filled in rather than always `0.0`. Write tests: a 90° arc sensor on a flat site should point toward the largest uncovered area; a 360° sensor returns an arbitrary (but valid) bearing; `bearing_step_deg=90` produces 4 candidates.
- _Why:_ This is the core capability gap. A directional radar placed at the optimal position but pointing the wrong direction provides far less coverage than the model currently assumes. The greedy choice of (position, bearing) jointly is still a valid greedy heuristic — it just evaluates B times as many candidates per step at negligible additional cost.

**S11.5-3: Expose `bearing_step_deg` in CLI and `ScenarioConfig`**
- _What:_ Add `placement_bearing_step_deg: float = 10.0` to `ScenarioConfig` in `models/scenario.py` with validation (must be in (0, 360], must divide evenly into 360 within float tolerance, or simply require it to be a positive finite value). Pass through to `greedy_place_sensors` in the `salus optimise` CLI command. Add `--bearing-step` CLI flag to `salus optimise` to override at runtime. Document that `--bearing-step 90` gives a fast 4-direction sweep and `--bearing-step 5` gives fine-grained optimisation.
- _Why:_ `bearing_step_deg` is the precision knob — coarser steps run faster for planning passes, finer steps find the true optimum for final configurations. Exposing it at the CLI and scenario level gives users control without code changes.

---

### Slice 12 — LiDAR Ingestion Pipeline

_Goal: accept raw LiDAR point clouds and convert to DEM/DSM, completing the full ingestion pipeline._

**S12-1: Implement LAS/LAZ point cloud loading via PDAL**
- _What:_ Create `src/salus/ingest/lidar.py` with `load_point_cloud(path) -> pdal.Pipeline` result. Support LAS and LAZ formats. Read header metadata (CRS, point count, bounds). Validate CRS is defined.
- _Why:_ LiDAR is the primary input format for defence site surveys. While GeoTIFF import works for development, real engagements will provide LAS/LAZ files from survey flights.

**S12-2: Implement point cloud to DEM conversion (ground classification + rasterisation)**
- _What:_ Add `point_cloud_to_dem(pipeline, resolution_m, output_path) -> SiteModel`. Use PDAL's SMRF or PMF ground classification filter, then rasterise ground-classified points using PDAL's writers.gdal. Handle nodata interpolation for cells without ground returns.
- _Why:_ DEM extraction requires separating ground points from vegetation/structure points. PDAL's built-in ground classifiers are well-validated for this — no need to reimplement.

**S12-3: Implement point cloud to DSM conversion**
- _What:_ Add `point_cloud_to_dsm(pipeline, resolution_m, output_path) -> SiteModel`. Rasterise all first-return points (highest point per cell). This captures buildings, vegetation, and other above-ground features.
- _Why:_ DSM from LiDAR captures actual structure heights rather than estimated values. Combined with the DEM, it gives precise building and tree heights for occlusion modelling.

**S12-4: Add LiDAR ingestion to CLI**
- _What:_ Add `salus ingest --lidar path/to/cloud.laz --resolution 1.0 --output-dem dem.tif --output-dsm dsm.tif` subcommand. Runs the full LiDAR-to-raster pipeline.
- _Why:_ Completes the LiDAR path through the system. Users can now go from raw survey data to coverage analysis in two commands: `salus ingest` then `salus simulate`.

---

### Slice 12.5 — Vegetation and Canopy Layer

_Goal: model tree cover as a semi-permeable obstacle so that sensor coverage in forested terrain reflects the sensor's actual ability to see through vegetation, rather than treating all above-ground obstructions as opaque._

_Context: S3-2 introduced DSM loading, which lumps buildings and vegetation into a single surface. S12 derives precise DEM and DSM from LiDAR. This slice uses those two surfaces to isolate the vegetation layer (CHM = DSM − DTM) and applies sensor-specific penetration factors during viewshed computation. The result is a probabilistic coverage model for cells where the LOS ray passes through canopy, rather than the current binary blocked/unblocked result._

**S12.5-1: Derive and ingest Canopy Height Model (CHM)**
- _What:_ Add `derive_canopy_height_model(dem_path, dsm_path, output_path) -> np.ndarray` to `src/salus/ingest/terrain.py`. Compute CHM = DSM − DTM, clamped to [0, ∞) (negative values mean DEM/DSM misregistration — clamp and warn). Add `canopy_height_m: np.ndarray | None = None` to `SiteModel`. Extend `load_dem` (or add a companion `load_canopy`) to accept an optional CHM GeoTIFF and attach it to the returned `SiteModel`. Write tests: zero CHM on flat open terrain, positive CHM where DSM > DEM, clamp-and-warn on negative cells.
- _Why:_ The CHM is the vegetation-specific surface — it isolates tree canopy height from terrain and building height. It cannot be derived until both DEM and DSM are available, which S12 provides. Clamping rather than erroring on negative cells handles minor DSM/DEM registration offsets that appear in real LiDAR products.

**S12.5-2: Add `vegetation_penetration` to `SensorDefinition` and sensor YAMLs**
- _What:_ Add `vegetation_penetration: float = 0.0` (range 0.0–1.0) to `SensorDefinition` in `models/sensor.py`. This represents the fraction of signal that passes through a unit of canopy (0.0 = fully blocked, 1.0 = fully transparent). Add field validation (must be in [0, 1]). Update all existing sensor YAML files: RF sensors (~0.6), radar (0.2–0.4 depending on band), EO/IR (0.0), acoustic (0.9 — sound diffracts around/through foliage). Document the physical basis (Bouguer–Lambert attenuation) in the field docstring.
- _Why:_ RF spectrum sensors detect drone control signals that partially penetrate light canopy. Radar attenuates significantly through dense foliage. EO/IR cannot see through leaves at all. Without this field the model either ignores vegetation (overestimates coverage) or treats it as a solid wall (underestimates coverage). Both are wrong for forested sites.

**S12.5-3: Modify viewshed computation for canopy attenuation**
- _What:_ In `engine/viewshed.py`, add `compute_viewshed_through_canopy(site, observer_x, observer_y, observer_height, max_range, vegetation_penetration) -> np.ndarray`. When `site.canopy_height_m` is present and `vegetation_penetration > 0`, ray-march each LOS ray and accumulate a per-cell transmission coefficient: `T *= vegetation_penetration ** (canopy_height_m[cell] / reference_height_m)` for each cell along the ray where canopy height > 0. Return a float32 array of transmission values (0.0–1.0) rather than a boolean array. When `site.canopy_height_m` is None or `vegetation_penetration == 0.0`, fall back to the existing binary viewshed computation unchanged. Write tests: open terrain returns identical output to binary viewshed; single canopy cell with penetration=0.0 blocks ray; with penetration=0.5 returns partial transmission; full canopy path gives exponentially decaying transmission.
- _Why:_ The Bouguer–Lambert model (exponential attenuation proportional to path length through the medium) is the standard for signal propagation through vegetation. Accumulating `penetration^height` per cell approximates this using the CHM without requiring per-voxel density data. The fallback to binary viewshed ensures backward compatibility — sites without a CHM are unaffected.

**S12.5-4: Update coverage computation and statistics for probabilistic coverage**
- _What:_ In `engine/coverage.py`, add `VEGETATION_COVERAGE_THRESHOLD: float = 0.5` as a named module-level constant. When layer coverage arrays contain float values (from canopy-attenuated viewsheds), apply this threshold to produce the boolean coverage arrays that downstream gap analysis, composite coverage, and statistics computation already expect. Expose the threshold as an optional parameter on `compute_layer_coverage` and `compute_coverage_stats`. Write tests: a 0.6-transmission cell is covered at the default threshold; a 0.4-transmission cell is not; threshold override works correctly.
- _Why:_ All downstream analysis (gap maps, zone stats, kill chain, saturation) is built on boolean coverage grids. Introducing a threshold at the coverage layer boundary keeps all downstream code unchanged while giving users a meaningful knob: "a cell counts as covered if at least 50% of the signal passes through". Defence customers may want to set this higher (e.g., 0.7) for critical asset zones in dense canopy.

**S12.5-5: Render vegetation-aware coverage maps**
- _What:_ Update `report/maps.py` to optionally overlay the CHM as a green-tinted semi-transparent layer when `site.canopy_height_m` is present, so maps clearly show where forested areas are relative to coverage gaps. Add a note to the map legend when canopy attenuation was applied ("Coverage shown at X% transmission threshold"). No new map function required — extend the existing `render_composite_coverage_map` and `render_gap_map` with an optional `show_canopy: bool = True` parameter.
- _Why:_ Without visualising the canopy layer, users cannot distinguish coverage gaps caused by terrain shadowing from gaps caused by vegetation attenuation — two very different operational findings. Showing canopy on the map makes the relationship between forest cover and coverage gaps immediately legible.

---

### Slice 13 — PDF Report Generation

_Goal: produce a professional PDF report suitable for inclusion in a defence proposal._

**S13-1: Create Jinja2 HTML report template structure**
- _What:_ Create `src/salus/report/templates/` with `base.html` (page layout, headers, footers, page numbers, branding), `cover.html` (title page), `executive_summary.html`, `site_overview.html`, `coverage_analysis.html`, `gap_analysis.html`, `threat_analysis.html`, `kill_chain.html`, `saturation.html`, `comparison.html` (optional), `assumptions.html`, `appendix_sensors.html`. Use CSS print media for page breaks, margins, landscape pages for maps.
- _Why:_ Templating separates content from layout. Jinja2 templates can be iterated on without changing Python code. The same templates work for WeasyPrint PDF rendering and direct HTML viewing.

**S13-2: Implement report data assembly**
- _What:_ Create `src/salus/report/pdf.py` with `assemble_report_data(scenario, sim_results) -> ReportData`. Collect into a single data structure: all maps (as embedded base64 PNGs), the kill chain timeline Gantt charts (from S7-4), the saturation analysis charts (from S8-5), coverage statistics, sensor specs, assumptions, and configuration details. This structure is what all Jinja2 templates consume.
- _Why:_ Clean separation between data assembly (Python) and presentation (Jinja2+HTML). The ReportData structure also serves as the data source for the interactive viewer (Slice 14).

**S13-3: Implement WeasyPrint PDF rendering**
- _What:_ Add `render_pdf(report_data, template_dir, output_path)` to `pdf.py`. Render each template section with Jinja2, concatenate, pass to WeasyPrint for PDF conversion. Handle landscape pages for maps, ensure images are high-DPI (300dpi minimum for print).
- _Why:_ WeasyPrint produces professional PDFs from HTML/CSS without LaTeX. The PDF is the primary commercial deliverable (Tier 1 output).

**S13-4: Add executive summary narrative generation**
- _What:_ Implement `generate_executive_summary(stats, kill_chain_results, saturation_results) -> str`. Produce 3-5 paragraphs of templated natural language: "The assessed configuration provides X% coverage of the site boundary, with Y% coverage of critical asset zones. The kill chain analysis indicates..." Use conditional logic for different result profiles (good/adequate/poor).
- _Why:_ Decision-makers read the executive summary, not the maps. Automated narrative generation saves hours of report writing per engagement.

**S13-5: Add assumptions and limitations section**
- _What:_ Create a structured assumptions section: terrain model source and resolution, sensor spec confidence levels, propagation model limitations (no multipath, no atmospheric effects), binary detection model (no Pd curves), threat model constraints (straight-line approach, constant speed). This is critical for credibility.
- _Why:_ Defence customers expect explicit documentation of model limitations. Omitting this undermines credibility. Including it demonstrates rigour.

**S13-6: Add sensor specifications appendix**
- _What:_ Auto-generate an appendix table listing all sensors and effectors used in the configuration, with their key parameters (range, arc, type). Mark fields where values were estimated or conservative defaults were used.
- _Why:_ Traceability from results back to input assumptions. Reviewers need to verify that the sensor specs used in the analysis match reality.

**S13-7: Add `salus report` CLI subcommand**
- _What:_ Add `salus report --scenario scenario.yaml --output report.pdf` that runs the full pipeline (ingest + simulate + report) end-to-end. Alternatively, accept pre-computed results from `salus simulate --save-results results.json` to avoid re-running the simulation.
- _Why:_ The report command is the top-level user action: "give me the report." Supporting pre-computed results enables iterate-on-report-template without re-running expensive simulations.

---

### Slice 14 — Interactive Standalone Viewer

_Goal: produce a self-contained HTML/JS package that can be opened in a browser without a server. The viewer uses MapLibreGL for 3D terrain navigation — users can tilt, rotate, and pitch the camera to understand terrain relief and sensor line-of-sight in three dimensions._

**S14-1: Design viewer data export format (JSON)**
- _What:_ Create `src/salus/viewer/export.py` with `export_viewer_data(report_data, output_path)`. Export coverage layers as GeoJSON polygons (not rasters — too large), gap polygons, corridor paths with coverage stats, kill chain summaries, saturation stats, sensor placement points. All coordinates in WGS84 for MapLibreGL compatibility. Pre-process the site DEM into raster-dem tiles (via GDAL `gdal2tiles` or equivalent) at sufficient resolution for close-range terrain inspection; bundle tiles with the viewer package.
- _Why:_ The viewer is a pre-computed data display tool — zero simulation capability by design. The JSON export format defines the viewer's capabilities and limitations. Raster-dem tiles are required for MapLibreGL's 3D terrain layer.

**S14-2: Implement data sanitisation for export**
- _What:_ Create `src/salus/viewer/sanitise.py` with `sanitise_for_export(viewer_data, config) -> ViewerData`. Strip exact sensor specifications (replace ranges with "band" categories), round coordinates to configurable precision, omit proprietary fields. Sanitisation level configurable (full/redacted/minimal).
- _Why:_ The interactive viewer leaves your hands — it goes to the customer. Sanitisation prevents reverse-engineering exact sensor capabilities. This is a hard requirement for defence customers and for protecting vendor IP.

**S14-3: Build MapLibreGL-based interactive 3D map viewer**
- _What:_ Create `src/salus/viewer/static/index.html` and `app.js`. MapLibreGL map with 3D terrain enabled (pitch up to 85°, full rotate/tilt navigation). Toggle-able coverage layers (radar, RF, EO/IR, acoustic, effector, composite) draped on the terrain surface, gap highlights, sensor/effector placement markers, threat corridor overlays. Layer control panel. Click-to-inspect for gaps (area, location). Basemap tile selector (offline-capable raster tiles as default; optional satellite if available).
- _Why:_ MapLibreGL's 3D terrain mode lets reviewers tilt and fly around the site to understand how terrain relief creates coverage gaps and blocks line-of-sight — something a flat 2D map cannot convey. It works offline (air-gapped networks) because all terrain tiles and data are pre-computed and bundled.

**S14-4: Add kill chain and saturation display to viewer**
- _What:_ Add a sidebar panel to the viewer showing kill chain timeline (as an SVG Gantt chart) and saturation metrics (bar chart). Link corridors on the map to their kill chain results — click a corridor to see its engagement timeline.
- _Why:_ Integrating analytical results with the map creates a unified exploration experience. Stakeholders can trace from "this corridor" to "this is why it's dangerous."

**S14-5: Implement viewer packaging**
- _What:_ Add `package_viewer(viewer_data, output_dir)` to `export.py`. Copy static assets (HTML, JS, CSS) and write the JSON data file into a single directory. The result is a self-contained folder that works when opened directly in a browser (`file://` protocol). Optionally zip for distribution.
- _Why:_ The package must be fully self-contained — no CDN dependencies, no server. All JS libraries (MapLibreGL) and terrain tiles bundled locally. This enables air-gapped deployment.

**S14-6: Add `salus viewer` CLI subcommand**
- _What:_ Add `salus viewer --scenario scenario.yaml --output viewer/ --sanitise redacted` that runs simulation, exports data, sanitises, and packages the viewer.
- _Why:_ Completes the viewer pipeline as a single command.

---

### Iterative Improvement Phase

_Goal: surface and fix real-world issues through structured exploration and direct observation before final polish. Sits between S14 and S15 so that iteration happens on a complete, working tool but before the database is fully populated._

_There are two ways tasks enter this phase:_
- _**Triage** — you notice something wrong or improvable while using the tool. Describe it; it becomes an I-task._
- _**Exploration** — we run a designed simulation scenario (from `demo/explore/`) to stress a specific part of the tool. Issues that surface become I-tasks._

_All I-tasks follow the full Forge workflow (12 steps, G1–G8, L1+L2 reviews). Tasks are numbered sequentially: I-1, I-2, I-3, ... Gate proofs go in `.forge/gate-proofs/I-N.yaml`._

_Exploration scenarios are stored in `demo/explore/` with the naming convention `ENN_short_description/` (e.g. `E01_compound_defence_baseline/`, `E02_coastal_radar_layering/`). Each scenario that generates I-tasks is noted in the task's description._

<!-- I-tasks are appended below as they are identified -->

**I-1: Fix 3D terrain not rendering in interactive viewer**
- _Source:_ Triage — terrain displays flat (no visible hills) when the viewer is loaded.
- _Root cause:_ The `salus://` protocol handler returns `new ArrayBuffer(0)` for tiles outside the DEM bounds. When the map is pitched (default 50°), MapLibreGL requests adjacent tiles that fall outside the site's extent. An empty ArrayBuffer is not a valid PNG; the raster-dem decoder fails, silently disabling terrain for the entire source. Additionally, `fitBounds` was not explicitly preserving pitch.
- _Fix:_ Replace the empty-ArrayBuffer fallback with a pre-computed flat Terrarium PNG (R=128, G=0, B=0 = 0 m elevation, 757 bytes). Ensure `fitBounds` passes `pitch` explicitly. Raise exaggeration to 2.0 for better visual impact on modest terrain.
- _Acceptance criteria:_
  - Hills and ridges are visible when the viewer loads with default pitch 50°.
  - Tilting and orbiting the map reveals terrain relief.
  - Protocol handler never resolves with empty ArrayBuffer for any tile request.

**I-2: Dramatic terrain and walled compound for 3D viewer testing**
- _Source:_ Triage — the default E01 test scenario used flat terrain, making it impossible to visually verify 3D rendering was working.
- _Fix:_ New `demo/explore/E01_dramatic_terrain/generate.py` that synthesises a DEM with prominent ridgelines (500 m peak), a valley, and a walled compound in the valley floor.
- _Acceptance criteria:_
  - `generate.py` produces a GeoTIFF DEM and runs `salus viewer-export` without error.
  - The output viewer shows visible ridgelines and a compound footprint.

**I-3: Fix 3D terrain rendering — serve terrain tiles as HTTP files**
- _Source:_ Triage — after I-1 the terrain still rendered flat because MapLibreGL v3 fetches `raster-dem` tiles inside a Web Worker; `addProtocol` handlers on the main thread are not proxied to the worker.
- _Fix:_ `package_viewer` writes terrain tiles to `output_dir/tiles/{z}/{x}/{y}.png`; `app.js` uses standard HTTP URLs; terrain style property set in initial style object; hillshade layer added for visual depth; `viewer_data.js` no longer embeds tile base64.
- _Acceptance criteria:_
  - 3D terrain (hills, ridges) is visible when the viewer is loaded in a browser.
  - Hillshade layer provides light/shadow depth cues.
  - `viewer_data.js` contains no terrain tile base64 data.
  - `terrain_tile_count` in `SALUS_DATA` payload reflects actual tiles written.

**I-4: Per-type sensor symbols with bearing wedge in interactive viewer**
- _Source:_ Triage — all sensors displayed as identical white circles with no indication of type or pointing direction.
- _Fix:_ Add `sensor_type` and `azimuth_coverage_deg` to GeoJSON feature properties (looked up from `sim_results.sensor_defs`); update viewer JS to colour markers by type, show type abbreviation badge, and draw a bearing wedge for sector sensors.
- _Acceptance criteria:_
  1. Each sensor marker circle is coloured by type using `LAYER_COLOURS`: Radar=orange (`#f97316`), RF=purple (`#a855f7`), EO_IR=green (`#22c55e`), Acoustic=cyan (`#06b6d4`); fallback `#f8fafc` if type unknown.
  2. Each sensor circle shows a type abbreviation centred on the circle: `R` (Radar), `RF` (RF), `E` (EO_IR), `A` (Acoustic).
  3. For `azimuth_coverage_deg < 360` and `bearing_deg` present: a filled sector wedge is drawn at the sensor position, centred on `bearing_deg`, spanning the full `azimuth_coverage_deg` arc, coloured to match the sensor type at ~25% opacity with a solid outline.
  4. For `azimuth_coverage_deg == 360` or `bearing_deg` null/absent: no wedge is drawn.
  5. GeoJSON feature properties include `sensor_type` (string) and `azimuth_coverage_deg` (number).
  6. Sensor name label below the circle is preserved.
  7. Click popup, hover cursor, and all existing layer-control behaviour is preserved.
  8. All existing tests pass; new tests cover the added properties.

---

### Slice 15 — Populate Full Sensor/Effector/Threat Database

_Goal: populate the YAML database with all sensors from the research files to enable realistic configurations._

**S15-1: Convert remaining sensor vendor research to YAML (batch 1: radar systems)**
- _What:_ Create YAML definitions for all radar systems across the ~15 populated vendor files: Echodyne EchoGuard/EchoShield, HENSOLDT Spexer 2000, SAAB Giraffe/Arthur, L3Harris, QinetiQ, Raytheon KuRFS, etc. Estimate fields not publicly disclosed; document confidence per field.
- _Why:_ Radars are the primary detection layer for most cUAS configurations. A complete radar database enables realistic multi-vendor configuration comparisons.

**S15-2: Convert remaining sensor vendor research to YAML (batch 2: RF and EO/IR systems)**
- _What:_ Create YAML definitions for RF passive sensors (DroneShield RfOne, Dedrone DedroneSensor, DEWC, etc.) and EO/IR cameras (various vendors). These are typically sector sensors with known azimuth coverage.
- _Why:_ RF and EO/IR sensors fill the detection layers that complement radar. Real configurations always mix sensor types.

**S15-3: Convert remaining effector research to YAML**
- _What:_ Create YAML definitions for all effectors: jammers (DroneShield DroneCannon, Department13 MESMER, DEWC), kinetic (EOS Slinger), directed energy systems. Estimate engagement parameters where not publicly available.
- _Why:_ The effector database enables kill chain and saturation analysis with real products rather than placeholders.

**S15-4: Create comprehensive threat profile YAML library**
- _What:_ Create YAML threat profiles for common drone types encountered in cUAS scenarios: commercial multirotors (DJI Mavic, Matrice, FPV racing drones), fixed-wing (various wingspans), Group 1/2/3 military UAS. Include RCS estimates, RF signature characteristics, speed profiles, typical operating altitudes.
- _Why:_ Threat profiles are needed for corridor and kill chain analysis. A library of pre-defined threats lets users select appropriate scenarios without needing to research drone specifications themselves.

---

### Slice 16 — CLI Polish and End-to-End Workflow

_Goal: polish the CLI into a cohesive, well-documented tool with proper error handling and logging._

**S16-1: Implement structured logging throughout the pipeline**
- _What:_ Add Python `logging` with configurable verbosity (`--verbose` / `--quiet` flags). Log key pipeline stages (loading DEM, computing viewsheds, running corridors). Log timing for performance profiling. Use `rich` or plain formatting for console output.
- _Why:_ Users need to understand what the tool is doing, especially when simulations take minutes. Logging also aids debugging when results look wrong.

**S16-2: Implement comprehensive error handling and input validation**
- _What:_ Add clear error messages for common failure modes: missing files, CRS mismatch, sensor name not found in database, invalid scenario YAML structure, out-of-bounds sensor placements. Use Click's error handling for CLI-level errors. Validate all inputs at ingestion time, not at compute time.
- _Why:_ Failing fast with a clear message saves hours of debugging. "Sensor 'RfOne' not found in database. Available sensors: ..." is infinitely better than a KeyError traceback.

**S16-3: Implement `salus run` unified command**
- _What:_ Add a `salus run --scenario scenario.yaml --output-dir output/ --pdf --viewer --compare scenario_b.yaml` command that runs the entire pipeline end-to-end: ingest, simulate, report, viewer. Individual subcommands remain available for debugging. This is the primary user-facing command.
- _Why:_ Most users want to run everything at once. The unified command with optional flags is simpler than remembering the sequence of subcommands.

**S16-4: Write CLI help text and usage examples**
- _What:_ Write comprehensive `--help` text for all commands and options. Create `docs/usage.md` with worked examples showing common workflows: basic viewshed, full site analysis, configuration comparison, placement optimisation.
- _Why:_ Good documentation is part of the product. The user may be running this months after building it, or handing it to a colleague.

**S16-5: Add `--dry-run` mode**
- _What:_ Add `--dry-run` flag that validates all inputs (loads DEM, parses scenario, resolves sensor names, checks placements within boundary) without running the simulation. Reports what would be computed.
- _Why:_ Dry run catches configuration errors without waiting for a 10-minute simulation to fail halfway through. Essential for iterative scenario development.

---

### Slice 17 — Docker, Testing, and CI Readiness

_Goal: ensure the project is reproducible, tested, and ready for reliable development iteration._

**S17-1: Finalise Dockerfile and docker-compose for development**
- _What:_ Ensure the Dockerfile builds a complete environment with GDAL, PDAL, and all Python dependencies. Add a `docker-compose.yml` for easy `docker compose run salus simulate ...` usage. Pin all system-level dependencies. Test on a clean Docker build.
- _Why:_ Docker is the only reliable way to distribute GDAL/PDAL environments. A broken build environment kills development velocity. The Dockerfile is also the foundation for future air-gapped deployment (Tier 3).

**S17-2: Write integration tests for the end-to-end pipeline**
- _What:_ Create integration tests that run the full pipeline: load test DEM, define a scenario with 3-4 sensors, run simulation, verify coverage stats are within expected ranges, verify maps are generated, verify PDF is produced. Use the synthetic or real test DEM from S1-5.
- _Why:_ Unit tests verify components; integration tests verify they work together. The end-to-end test catches interface mismatches between modules.

**S17-3: Write unit tests for all engine modules**
- _What:_ Ensure each engine module has tests: viewshed (flat terrain, ridged terrain, sensor clipping), RF propagation (FSPL against reference values, knife-edge against textbook examples), acoustic (range circle), coverage (union, gaps, stats), corridors, kill chain (positive/negative margins), saturation (under/over threshold), placement (greedy improves coverage).
- _Why:_ Engine modules are pure computation — they must produce correct results. Tests serve as documentation of expected behaviour and catch regressions.

**S17-4: Set up pre-commit hooks (ruff, mypy, pytest)**
- _What:_ Configure `ruff` for linting/formatting, `mypy` for type checking (Pydantic models make this valuable), and `pytest` as a pre-commit check. Add to `pyproject.toml` configuration.
- _Why:_ Code quality tools catch issues before they accumulate. Type checking is particularly valuable for a geometry-heavy codebase where array shape mismatches are common bugs.

**S17-5: Write a README with setup instructions**
- _What:_ Write `README.md` covering: what the tool does, prerequisites (Docker), quickstart (build + run with example scenario), project structure overview, development setup, running tests.
- _Why:_ The README is the first thing anyone sees. It must enable someone (including future-you) to get from zero to running in under 10 minutes.

---

## Summary Statistics

| Slice | Name | Tasks | Cumulative |
|-------|------|-------|------------|
| 0 | Project Skeleton | 1 | 1 |
| 1 | Thinnest End-to-End (DEM + Viewshed + Map) | 5 | 6 |
| 2 | Sensor Database + Sensor-Clipped Viewsheds | 7 | 13 |
| 3 | Site Boundaries, Zones, DSM | 5 | 18 |
| 4 | RF Propagation + Acoustic Layers | 5 | 23 |
| 5 | Multi-Sensor Coverage, Gaps, Stats | 6 | 29 |
| 6 | Threat Corridors (2D baseline) | 5 | 34 |
| 6.1 | 3D LOS Primitive + Sensor Detection Point Query | 3 | 37 |
| 6.2 | DroneTrajectory Model | 2 | 39 |
| 6.3 | Trajectory Analysis Engine | 3 | 42 |
| 6.4 | Worst-Trajectory Sweep | 2 | 44 |
| 6.5 | Trajectory Visualisation + CLI | 3 | 47 |
| 6.6 | Adversarial Path Planning | 3 | 50 |
| 7 | Kill Chain Timeline (D-T-I-D-E-A) | 4 | 54 |
| 8 | Multi-Target Saturation | 6 | 60 |
| 9 | Greedy Placement Optimisation | 4 | 64 |
| 10 | Configuration Comparison (A vs B) | 3 | 67 |
| 11 | Effector Coverage Layer | 2 | 69 |
| 12 | LiDAR Ingestion | 4 | 73 |
| 13 | PDF Report Generation | 7 | 80 |
| 14 | Interactive Standalone Viewer | 6 | 86 |
| 15 | Populate Full Sensor/Effector/Threat DB | 4 | 90 |
| 16 | CLI Polish + End-to-End Workflow | 5 | 95 |
| 17 | Docker, Testing, CI Readiness | 5 | 100 |

**Total: 100 tasks across 24 slices (including Slice 0).**

---

## Dependency Notes

- **Slices 1-5 are strictly sequential** — each builds on the previous.
- **Slices 6 → 6.1 → 6.2 → 6.3 → 6.4 → 6.5 → 6.6 are sequential** — each sub-slice depends on the previous. Slice 6 (2D corridors) is a prerequisite for 6.1 because 6.3 refactors `find_worst_corridors` to delegate to the new trajectory engine. Slice 6.6 depends on 6.1 (`sensor_can_detect_point`) and 6.3 (`analyse_trajectory`) but not on 6.4 or 6.5 — those are parallel outputs of 6.3.
- **Slice 7 (kill chain) depends on Slice 6.3** — it consumes `TrajectoryResult.first_detection` and `DetectionEvent` instead of `CorridorResult.first_detection_distance_m`. Slices 8-11 depend on Slice 5 and can be done in any order relative to each other, but 7 must precede them in the kill chain pipeline.
- **Slices 9-11 (placement, comparison, effectors)** depend on Slice 5 and can be done in any order.
- **Slice 12 (LiDAR)** is independent of Slices 6-11 — it only depends on Slice 1 (SiteModel). It is placed late because GeoTIFF import is sufficient for development and LiDAR adds PDAL complexity. Move it earlier if real LiDAR data arrives.
- **Slice 13 (PDF report)** depends on all analytical slices (5-11 and 6.x) being complete, since the report includes all of them.
- **Slice 14 (viewer)** depends on Slice 13 (shares ReportData structure and map rendering).
- **Slice 15 (database population)** can be done at any time after Slice 2 (YAML loader exists). It is placed late because development can proceed with 5-8 representative sensors. Move individual batches earlier if realistic configurations are needed for testing.
- **Slices 16-17 (polish, testing)** are shown last but testing should happen continuously — the tasks here represent the final pass to ensure comprehensive coverage.

---

### Critical Files for Implementation
- `/workspaces/ProjectSalus/SimulationArchitecture.md` - Defines the complete project structure, module layout (`src/salus/` tree), data models, and technology stack that the backlog implements
- `/workspaces/ProjectSalus/DevelopmentRoadmap.md` - Defines MVP scope checklist, all feature requirements, and delivery model that determines what "done" means
- `/workspaces/ProjectSalus/Resources/DroneShield/products_and_specs.md` - Representative example of the sensor research data (15 populated vendor files) that needs conversion to YAML sensor definitions in Slices 2 and 15
- `/workspaces/ProjectSalus/To-Do.md` - Current task tracking file that this backlog would replace or extend