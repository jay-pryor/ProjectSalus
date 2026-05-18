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

### Slice 14.1 — Shell and Module Infrastructure

_Goal: build the host application skeleton — the only part of the system that holds direct references to shared resources. This slice produces the shell (`shell.js`), state proxy, event bus, scoped map proxy, and mode manager. No user-facing modules are built here. The deliverable is a working shell that discovers, validates, and initialises a single dummy test module, proving every infrastructure component works end-to-end._

_Context: the architecture is defined in `docs/InterfaceArchitecture.md`. All subsequent module slices depend entirely on this one. The shell must be correct before any module work begins. Key invariants: modules never receive a reference to the shell, the raw state object, or the raw map instance — only the injected `api` object from Section 2.6._

**S14.1-1: Project scaffold and entry point**
- _What:_ Create `src/salus/viewer/interface/` as the interface application root. Create `index.html` with the MapLibreGL map container, nav bar placeholder, panel slot div, and `<script type="module" src="shell.js">`. Create `shell.js` as the entry point module. Add `modules/` directory at the interface root with a `.gitkeep`. Create `src/salus/data/state-schema.js` exporting the canonical `VALID_STATE_KEYS` set (all keys from InterfaceArchitecture.md Section 3) and `VALID_EVENTS` set (all events from Section 2.4) — these are the ground truth the proxy and bus validate against. Add `style.css` with the two-column layout (left: nav bar, right: map + panel slot overlay).
- _Why:_ The directory structure and canonical key/event sets are the foundations everything else imports. Exporting them from a single module means any module validation or test can import the ground truth rather than duplicating it. Establishing `interface/` as a separate tree from `static/` keeps the editing interface cleanly separated from the standalone viewer.

**S14.1-2: State Proxy with contract enforcement**
- _What:_ Create `src/salus/viewer/interface/state.js`. Export `createState(moduleContracts)` which takes a map of `{moduleId → {reads, writes}}` and returns a `{get, set, watch}` API. Internally: a plain object holds values; a `Map` of key → callback sets handles watchers. `set(moduleId, key, value)` checks (1) `key` is in `VALID_STATE_KEYS`, (2) `key` is in the calling module's `writes[]` — throws `StateContractViolation` if not, (3) value passes `isSerializable(value)` — throws `StateSerialiseViolation` if not, then writes the value and synchronously calls all watchers for that key with `(newValue, oldValue)`. `get(moduleId, key)` checks `key` is in the module's `reads[]` or `writes[]` and returns a deep-frozen value. `watch(key, callback)` pushes to the watcher set and returns an unsubscribe function. Implement `isSerializable(v)` as `JSON.parse(JSON.stringify(v))` round-trip equality. The shell's own `setState(key, value)` bypasses the proxy (for init and scenario load). Write unit tests for each violation path and for watcher notification.
- _Why:_ The state proxy is the single enforcement point for the entire data contract. Getting it right here means every module built afterwards gets the invariants for free. The synchronous watcher notification is correct for single-user; the interface (set → immediate watcher call) is the same one that will be replaced with optimistic-write + WebSocket sync for multi-user without changing any module code.

**S14.1-3: Event bus with scoped contract enforcement**
- _What:_ Create `src/salus/viewer/interface/bus.js`. Export `createBus(moduleContracts)` returning a `{createScopedBus(moduleId)}` factory. Each scoped bus has `emit(event, data)` — throws `EventContractViolation` if `event` not in module's `emits[]` or not in `VALID_EVENTS` — and `on(event, callback)` — throws if not in `subscribes[]`. Internally a single `EventTarget` instance handles dispatch; scoped handles are thin wrappers that enforce the contract before calling `dispatchEvent` / `addEventListener`. The unscoped bus (shell-only) can emit and subscribe to any event. Export `CORE_EVENTS` as the valid event set. Write tests: a module emitting an undeclared event throws; emitting a declared event fires the subscriber; a cross-module subscription to a declared event fires correctly.
- _Why:_ Scoped buses with enforced contracts mean the full event graph is always auditable from manifests — no implementation code reading required. The `EventTarget` under the hood means no custom pub/sub to maintain; native browser primitives handle dispatch efficiently.

**S14.1-4: Scoped map proxy**
- _What:_ Create `src/salus/viewer/interface/map-proxy.js`. Export `createMapProxy(mapInstance, layerIdPrefix)`. The proxy exposes only the methods listed in InterfaceArchitecture.md Section 2.6 `map:{}`: `addSource`, `removeSource`, `getSource`, `addLayer`, `removeLayer`, `getLayer`, `setLayoutProperty`, `setPaintProperty`, `on`, `off`, `getCanvas`, `flyTo`, `fitBounds`, `project`, `unproject`, `queryRenderedFeatures`. For `addSource(id, spec)` and `addLayer(spec)`, throw `LayerPrefixViolation` if `id` does not start with `layerIdPrefix + ':'`. All allowed methods delegate directly to the underlying map instance. The raw map instance is captured in a closure and is not on any property accessible from outside the factory function. Write tests using a mock map object.
- _Why:_ The scoped proxy enforces layer ID namespacing (preventing ID collisions between modules) and restricts destructive operations (`setStyle`, `remove`) that would corrupt the permanent terrain canvas. Closure-based encapsulation of the raw map means there is literally no way for a module to reach it — no `proxy._map`, no `Object.getPrototypeOf` trick, nothing.

**S14.1-5: Mode manager and navigation bar**
- _What:_ Create `src/salus/viewer/interface/mode-manager.js`. Export `createModeManager(container, state, bus, moduleRegistry)`. On `init()`: build the nav bar from `moduleRegistry` entries (one `<button>` per module, labelled from `manifest.label`, iconified from `manifest.icon`). Wire prerequisite gating: for each module, call `state.watch(key, checkPrerequisites)` for every key in `manifest.prerequisites[]` — enable the button when all prereqs are non-null, disable with tooltip otherwise. On button click: call `onUnmount()` callbacks on the currently active module's panel, update `state.ui.active_module_id` (bypassing proxy — shell-owned key), call `init(api)` on the new module if not yet initialised (lazy init), mount the new module's panel into the panel slot. Maintain a `navHistory` array; add a Back button that reverses the last transition. Write tests: button disabled when prereq null, enabled after prereq set, panel lifecycle callbacks fire in correct order.
- _Why:_ The mode manager is the only place that knows which module is active and which panels are mounted. Centralising this logic prevents modules from managing their own lifecycle (which would require them to know about each other). Lazy module init means expensive modules (Coverage Viewer, Kill Chain Analyser) only load their `index.js` when first activated — fast initial load regardless of how many modules are in `modules/`.

**S14.1-6: Module discovery, manifest validation, and API injection**
- _What:_ Create `src/salus/viewer/interface/registry.js`. Export `discoverModules(modulesDir)` which dynamically imports each subdirectory's `manifest.json` (via `fetch`) and validates it against the rules in InterfaceArchitecture.md Section 2.8: all required fields present, `id` unique, all `reads[]`/`writes[]` in `VALID_STATE_KEYS`, single-writer constraint (no two manifests share a `writes[]` key), all `emits[]`/`subscribes[]` in `VALID_EVENTS`, all `prerequisites[]` are keys that appear in some module's `writes[]`. Log and skip any invalid module; do not throw — a bad module should not crash the shell. Export `createModuleAPI(moduleId, manifest, state, bus, mapProxy, panelSlot)` which returns the complete injected `api` object from Section 2.6, with all state/bus/map methods pre-bound to `moduleId`. Write a test that loads a minimal valid manifest, detects a duplicate-writer violation across two manifests, and verifies the violating module is skipped.
- _Why:_ Manifest validation at startup turns architectural invariants into hard failures at load time rather than silent runtime bugs. The `createModuleAPI` factory is the only place that constructs the injected object — every module's entire capability set flows through it, making it easy to audit what any module can and cannot do.

---

### Slice 14.2 — FastAPI Backend API Layer

_Goal: expose the existing Salus Python engine behind a thin FastAPI HTTP/SSE layer that browser modules can call. No new simulation logic — this slice is purely a JSON/SSE wrapper around the engine's existing Pydantic models and CLI functions. The deliverable is a running server with all six endpoints, tested end-to-end against the engine._

_Context: the API spec is in `docs/InterfaceArchitecture.md` Section 6. The server starts alongside the interface when `salus interface` is run. It is a localhost-only service — no authentication, no CORS for external origins._

**S14.2-1: FastAPI application skeleton and health endpoint**
- _What:_ Create `src/salus/interface_api/` package with `app.py` defining the FastAPI app. Add `GET /api/health` returning `{"status": "ok", "version": ...}`. Add CORS middleware restricted to `http://localhost:*` only. Add structured logging (reuse the existing `salus` logger). Create `src/salus/interface_api/main.py` with a `uvicorn.run` entry point for use in tests. Add `fastapi` and `uvicorn` to `pyproject.toml` optional dependencies under `[project.optional-dependencies] interface = [...]`. Write a test that starts the server in a subprocess and hits `/api/health`.
- _Why:_ Starting with the skeleton and health endpoint establishes the app structure, dependency group, and test pattern before any real endpoint logic. The CORS restriction ensures the API never accidentally serves cross-origin requests in production.

**S14.2-2: Library endpoints (`/api/sensors` and `/api/effectors`)**
- _What:_ Add `GET /api/sensors` and `GET /api/effectors`. Each loads the full YAML database using the existing `load_sensors` / `load_effectors` functions from `ingest/sensors.py`, serialises via Pydantic's `.model_dump()`, and returns as JSON. Cache the result in-process (the database is read-only at runtime). Group results by `type` field in the response: `{"Radar": [...], "RF": [...], ...}`. Write tests asserting the response shape and that a known sensor from the YAML fixtures appears in the correct group.
- _Why:_ The Library Browser module and the viewer-export pipeline both need the sensor/effector catalogue. Serving it via API rather than bundling it at export time means the interface always shows the current database without requiring a re-export when sensor YAMLs are updated.

**S14.2-3: `/api/simulate` with SSE progress stream**
- _What:_ Add `POST /api/simulate`. Request body: `ScenarioConfig`-compatible JSON (the same structure `load_scenario` accepts). Response: `text/event-stream` SSE. In a background thread/async task, run the full simulation pipeline (ingest → viewshed → coverage → corridors → kill chain → saturation). At key checkpoints emit `data: {"type": "progress", "message": "...", "pct": N}`. On completion emit `data: {"type": "complete", "result": {...sim_results payload...}}`. On exception emit `data: {"type": "error", "message": "..."}` then close. Use FastAPI's `StreamingResponse` with a generator. Write a test that posts a minimal scenario and consumes the SSE stream, asserting the stream terminates with a `complete` event containing `sim_results`.
- _Why:_ SSE is the correct transport for long-running simulation progress — it is a unidirectional server-push stream over HTTP/1.1, requires no WebSocket handshake, and is natively supported by browser `EventSource`. Running the simulation in a background thread keeps the event loop free for other requests (e.g., the user cancelling).

**S14.2-4: `/api/optimise` with SSE progress stream**
- _What:_ Add `POST /api/optimise`. Request body: `{zones, constraints, sensor_library_filter, effector_library_filter, terrain}`. In a background task, run the greedy placement optimiser from `engine/placement.py`. Emit SSE progress events at each sensor placement step (`"Placing sensor 2/4 — coverage now 67%"`). On completion emit `{"type": "complete", "result": {...optimiser_results...}}` with `proposed_placements`, `score`, `coverage_pct`, `total_cost_aud`, `satisfied_constraints`, `violated_constraints`. Write a test using a synthetic flat DEM fixture.
- _Why:_ The optimiser can take seconds to minutes depending on candidate grid size and sensor count. SSE progress feedback is what separates "the UI is frozen" from "the UI shows meaningful progress." The step-by-step progress messages also let the user understand the algorithm is working.

**S14.2-5: `/api/report` endpoint and `salus interface` CLI command**
- _What:_ Add `POST /api/report`. Request body: `{report_config, sim_results, placements, zones, threat_corridors}`. Runs the existing `render_pdf` pipeline from `report/pdf.py`. Returns the PDF as a binary `application/pdf` stream (not SSE — PDF generation is fast enough for a synchronous response). Write a test asserting the response content-type and that the returned bytes are a valid PDF (check the `%PDF-` magic bytes). Add `salus interface --scenario scenario.yaml --port 5000` CLI command that starts `uvicorn` serving the FastAPI app and opens the `interface/index.html` in the default browser.
- _Why:_ The report endpoint completes the API surface. The `salus interface` command is the single entry point for the full interactive tool — one command starts both the backend and opens the frontend, no manual server management required.

---

### Slice 14.3 — Terrain Loader Module

_Goal: build the first real module. Its only job is loading a DEM and writing `terrain` state. Its value as the first module is disproportionate — it proves that manifest validation, API injection, state writes, event emission, and map layer addition all work correctly with real module code. Every subsequent module is built on the same pattern._

**S14.3-1: Manifest, panel HTML, and module skeleton**
- _What:_ Create `modules/terrain-loader/manifest.json` declaring `id: "terrain-loader"`, `label: "Load Terrain"`, `reads: []`, `writes: ["terrain"]`, `prerequisites: []`, `emits: ["terrain:loaded"]`, `subscribes: []`, `layer_id_prefix: "terrain-loader"`. Create `modules/terrain-loader/panel.html` with a file picker `<input type="file" accept=".tif,.tiff">` for DEM, an optional DSM picker, a CRS display field, a tile generation progress bar, and a bounds/resolution summary div (hidden until loaded). Create `modules/terrain-loader/index.js` exporting `{ init(api) }` — stub that mounts the panel and logs `"terrain-loader: init"`.
- _Why:_ Writing the manifest first forces a precise declaration of what this module does before any implementation. The stub `init` proves the discovery and injection pipeline works: if the module mounts its panel, the shell has found it, validated the manifest, constructed the API object, and called `init`. That is the entire infrastructure under test.

**S14.3-2: DEM/DSM loading, terrain state write, and terrain:loaded event**
- _What:_ Implement `modules/terrain-loader/index.js`. On DEM file selection: read the file as an `ArrayBuffer`, `POST` it to a new `POST /api/terrain/load` endpoint (add this to the FastAPI app — it runs `load_dem` on the file and returns the terrain metadata JSON: `{dem_path, dsm_path, crs_epsg, bounds_wgs84, centre_wgs84, resolution_m, tile_url_template, terrain_tile_count, terrain_min_zoom, terrain_max_zoom}`). Write the result to `api.state.set('terrain', terrainfMetadata)`. Emit `api.bus.emit('terrain:loaded', {})`. Update the CRS display and bounds summary in the panel. Show a progress bar during tile generation (poll `/api/terrain/tile-progress` via SSE while the server generates tiles). Use `api.state.watch('terrain', ...)` to re-render the panel summary whenever terrain changes (e.g., if loaded again).
- _Why:_ The `POST /api/terrain/load` endpoint is the cleanest seam: the browser passes a raw file, the Python backend runs the existing GDAL pipeline, and returns structured metadata. This keeps all GDAL work server-side and all rendering logic client-side. Emitting `terrain:loaded` is what unlocks nav buttons for all prerequisite-gated modules — this single event transitions the tool from "empty" to "usable."

**S14.3-3: Terrain DEM raster source and hillshade map layer**
- _What:_ After terrain state is written, call `api.map.addSource('terrain-loader:terrain-dem', {type: 'raster-dem', tiles: [terrain.tile_url_template], tileSize: 256, minzoom: terrain.terrain_min_zoom, maxzoom: terrain.terrain_max_zoom})`. Set `api.map` terrain property via a shell-level hook (expose `api.map.setTerrainSource(sourceId)` — add this single method to the map proxy for the terrain-loader module only, since no other module should ever change terrain). Add a `terrain-loader:hillshade` layer for depth cues. In `api.panel.onUnmount()`, remove the hillshade layer and source. Fly to `terrain.bounds_wgs84` on load.
- _Why:_ The raster-dem source and hillshade layer are the visual payoff — the 3D terrain appears as soon as terrain is loaded. This also tests the map proxy: prefixed IDs accepted, non-prefixed rejected, `onUnmount` cleanup verified. The special `setTerrainSource` method is the only architectural exception — terrain is a canvas-level operation that genuinely belongs to one module.

---

### Slice 14.4 — Library Browser Module

_Goal: browse the sensor and effector catalogue and initiate placement by dragging a sensor onto the map. This module has no prerequisites and no state writes — it is a pure read + event-emitter that feeds the Placement Editor._

**S14.4-1: Manifest, panel HTML, and library population**
- _What:_ Create `modules/library-browser/manifest.json` with `reads: ["sensor_library", "effector_library"]`, `writes: []`, `prerequisites: []`, `emits: ["placement:pending"]`, `subscribes: []`. On `init(api)`: call `GET /api/sensors` and `GET /api/effectors` to fetch library data; call `api.state.set` to write both... wait — library-browser has no writes. Instead, the shell pre-loads `sensor_library` and `effector_library` into state on startup from the API before any module is initialised (see Slice 14.14 for the startup load sequence). Library Browser reads them via `api.state.get('sensor_library')` at mount time and `api.state.watch` thereafter. Panel HTML: two collapsible sections (Sensors, Effectors), each with sub-groups by type. Each entry row: type badge, name, expand arrow, drag handle. Expanded view: spec table rendered from `SPEC_DISPLAY_FIELDS` constant array at top of `index.js`.
- _Why:_ Pre-loading `sensor_library` and `effector_library` into state at shell startup (rather than per-module fetch) means any module that needs the library has it immediately without waiting for a fetch. The `SPEC_DISPLAY_FIELDS` constant is the extensibility hook — adding a field to the library browser requires changing exactly one line.

**S14.4-2: Drag-and-drop placement initiation**
- _What:_ Add HTML5 `draggable="true"` to each library entry's drag handle. On `dragstart`, store the sensor/effector definition in `event.dataTransfer` as JSON. Add `dragover` / `drop` event listeners to the map canvas via `api.map.on('dragover', ...)` / `api.map.on('drop', ...)`. On drop: call `api.map.unproject({x: event.offsetX, y: event.offsetY})` to convert pixel coordinates to `{lat, lng}`. Emit `api.bus.emit('placement:pending', {lat, lng, definition})`. Clean up `dragover` and `drop` listeners in `api.panel.onUnmount()`. Add a ghost marker (a translucent circle following the cursor during drag) via a temporary GeoJSON source `library-browser:drag-ghost`.
- _Why:_ Drag-and-drop is the most natural placement UX: the user physically moves a sensor from the list to the location. Emitting `placement:pending` decouples the library browser from the placement editor — the library browser does not know or care what happens next; it only declares the intent. The ghost marker provides immediate visual feedback that the drag is in progress.

**S14.4-3: Keyboard-accessible placement and spec card detail**
- _What:_ Add a "Place" button to each spec card (visible on expand) that, when clicked, sets the cursor to a crosshair and waits for a map click to emit `placement:pending` with the clicked coordinates. This is the keyboard/accessibility path for users who cannot drag. Add a dismiss key (Escape) to cancel placement mode. Display full spec card: max range (formatted in km), azimuth coverage (degrees + visual arc icon), cost (AUD), type badge, confidence indicators for estimated fields (from a `confidence: estimated | measured` YAML field). Remove the ghost source in `api.panel.onUnmount()`.
- _Why:_ Drag-and-drop is fast but mouse-only. The click-to-place fallback makes the tool usable with keyboard navigation and on touch devices. The spec card confidence indicator is important for defence customers — they need to know which performance parameters are vendor-published vs. estimated from open-source intelligence.

---

### Slice 14.5 — Placement Editor Module

_Goal: the sole writer of `placements`. Accepts `placement:pending` events from the Library Browser and Gap Analysis modules, finalises position, allows bearing adjustment, and renders all placed sensors and effectors on the map. This is the most interaction-heavy module in the system._

**S14.5-1: Manifest, panel HTML, and placement list**
- _What:_ Create `modules/placement-editor/manifest.json` with `reads: ["terrain", "sensor_library", "effector_library"]`, `writes: ["placements"]`, `prerequisites: ["terrain"]`, `emits: ["placement:added", "placement:removed", "placement:moved"]`, `subscribes: ["placement:pending", "optimiser:complete"]`. Panel HTML: a scrollable placement list where each entry shows the sensor type badge, name, numeric bearing input, optional height override input, and a remove (×) button. An "Import YAML" and "Export YAML" button at the bottom. On `init(api)`: read the initial `placements` state with `api.state.get('placements')` (one-time initial render — mark with comment per SHOULD rule 2 in `interface-modules.md`). Subscribe to `api.state.watch('placements', renderList)` for all subsequent updates.
- _Why:_ The placement list in the panel is the textual counterpart to the map markers. Users often need to set exact bearings numerically (e.g., "sensor must face 047°") rather than visually. The import/export YAML buttons are the save/restore hook: users can share a placement configuration without re-running the full simulation.

**S14.5-2: Map layers — type-coloured markers, bearing lines, labels**
- _What:_ In `index.js`, after panel mount, add map sources and layers (all prefixed `placement-editor:`): (1) `placement-editor:sensors-source` — GeoJSON FeatureCollection of sensor placements; (2) `placement-editor:sensors-circle` — circle layer, data-driven fill-color from `sensor_type` using `LAYER_COLOURS` (Radar=#f97316, RF=#a855f7, EO_IR=#22c55e, Acoustic=#06b6d4); (3) `placement-editor:sensors-label` — symbol layer with sensor name below circle; (4) `placement-editor:sensors-type-badge` — symbol layer with type abbreviation (R/RF/E/A) centred on circle; (5) `placement-editor:bearing-lines-source` — GeoJSON lines; (6) `placement-editor:bearing-lines` — line layer, red, width 2, only for sensors where `azimuth_coverage_deg < 360`. Bearing line endpoints use the WGS84 latitude correction (`/ Math.cos(lat * Math.PI / 180)`) on the longitude offset. Watch `placements` state and rebuild both GeoJSON sources whenever it changes. Remove all sources and layers in `onUnmount`.
- _Why:_ The map layers are the primary spatial view of the configuration. Data-driven colour by sensor type (matching the Library Browser badges) gives instant visual parsing of sensor coverage composition. The latitude correction on bearing lines ensures they match actual viewshed angles at all latitudes — the bug that caused misaligned wedges in I-4 must not reappear here.

**S14.5-3: Placement interaction — click, drag, scroll-to-rotate, right-click remove**
- _What:_ Add map event listeners via `api.map.on(...)`. On click on `placement-editor:sensors-circle`: highlight the placement in the panel list (scroll to it) and set a selected state. On mousedown + drag on a selected marker: update the placement's `{lat, lng}` in a local working copy; on mouseup commit to `api.state.set('placements', updated)` and emit `placement:moved`. On wheel over a selected directional marker: increment/decrement `bearing_deg` by 5° per scroll tick, update state. On right-click on any marker: remove from `placements` array, `api.state.set`, emit `placement:removed`. Cursor changes: `crosshair` when placement:pending mode active, `grab` when hovering a marker, `pointer` otherwise (use `api.map.getCanvas().style.cursor`). Clean up all listeners in `onUnmount`.
- _Why:_ The drag, scroll-to-rotate, and right-click interactions are the core UX of the placement editor. They must feel immediate — state updates should rebuild the GeoJSON source synchronously so the marker moves with the cursor. Using `watch()` to drive the map redraw (not a direct `get()` after `set()`) means multi-user sync will work without changes here.

**S14.5-4: Receive `placement:pending` and `optimiser:complete`**
- _What:_ Subscribe to `api.bus.on('placement:pending', handler)` and `api.bus.on('optimiser:complete', handler)`. `placement:pending` handler: if the event includes `{lat, lng, definition}`, enter "confirm placement" mode — show a ghost marker at the coordinates, display a bearing dial in the panel, and on confirmation (Enter or "Place" button) add the new placement to state and emit `placement:added`. `optimiser:complete` handler: show a modal overlay on the map displaying the proposed placements as ghost markers (distinct orange dashed style), with "Apply" and "Discard" buttons. Apply merges the proposed placements into `placements` state; Discard removes the ghost markers. Store both bus subscriptions in `unsubs` array; call `unsubs.forEach(u => u())` in `onUnmount`.
- _Why:_ The `placement:pending` flow decouples "I want to place this sensor" (Library Browser or Gap Analysis) from "I am the one who writes placements" (Placement Editor). The optimiser modal is important UX: auto-applying optimiser results without user confirmation would be jarring — the user should review the proposed layout before committing. Storing unsubs in an array and iterating in a single cleanup block follows the SHOULD rule in `interface-modules.md`.

**S14.5-5: Import/export scenario YAML and bearing wedge map layer**
- _What:_ "Export YAML" button: call `JSON.stringify` on current `placements` state and format as a YAML-equivalent JSON structure, then trigger a browser file download named `placements.json`. "Import YAML" button: open a file picker, parse the JSON file, validate against expected schema (each entry must have `sensor_name`, `lat`, `lng`, `bearing_deg`), write to `api.state.set('placements', imported)`. Add bearing wedge map layers: `placement-editor:wedges-source` and `placement-editor:wedges-fill` — for each sensor with `azimuth_coverage_deg < 360`, generate a filled sector polygon (GeoJSON Polygon) centred on the sensor, spanning the bearing arc, radius ~0.002 degrees (~200m visual indicator), filled with sensor type colour at 20% opacity. Rebuild wedges on every `placements` state change.
- _Why:_ Export/import gives persistence before the full scenario save/load system (Slice 14.14) is built. The bearing wedge is the immediate visual indicator of which direction a directional sensor is pointing — far more useful on the map than just a line. The 20% opacity fill does not obscure the terrain.

---

### Slice 14.6 — Budget Tracker Module

_Goal: compute the running cost of current placements against a user-defined budget. This module has no prerequisites and no map behaviour — it is a pure panel module. Its sole write is `constraints`, which the Optimiser reads to gate sensor selection._

**S14.6-1: Manifest, panel UI, and cost calculation**
- _What:_ Create `modules/budget-tracker/manifest.json` with `reads: ["placements", "sensor_library", "effector_library"]`, `writes: ["constraints"]`, `prerequisites: []`, `emits: ["constraint:updated"]`, `subscribes: ["placement:added", "placement:removed"]`. Panel HTML: a budget input field (AUD), a total cost vs budget progress bar (green below budget, red over), a breakdown table (one row per placement: name, type, unit cost, subtotal), an over-budget warning banner, and a CSV export button. On `init(api)`: one-time `get` of `placements` for initial render (comment marked), then `watch('placements', recalculate)`. Cost lookup: find the sensor/effector definition in `sensor_library`/`effector_library` by `sensor_name`, read `cost_aud`. Write `{max_cost_aud: budgetInput, allowed_sensor_ids: null, ...}` to `constraints` state on every budget input change.
- _Why:_ The budget tracker is a discipline tool — it stops users from designing configurations that exceed procurement budgets. Writing to `constraints` is the integration point with the Optimiser: if the user sets a $2M budget, the optimiser will only select sensors that fit within it. The real-time cost breakdown is also useful for client presentations ("here is the exact BOM for this configuration").

**S14.6-2: Bus subscriptions and CSV export**
- _What:_ Subscribe to `placement:added` and `placement:removed` bus events (in addition to the `placements` watch) so the panel count and total update immediately — both mechanisms should produce identical results (idempotent recalculation). CSV export: build a `text/csv` string from the breakdown table, trigger a `<a>` download with filename `salus-bom-{date}.csv`. The CSV columns: sensor name, type, quantity, unit cost (AUD), line total (AUD). Bottom row: grand total. Store bus unsubs in `unsubs` array; `onUnmount` iterates.
- _Why:_ The bus subscriptions are slightly redundant with the state watch — both fire when placements change — but subscribing to placement events means the panel updates immediately even before the state write propagates, making the UI feel more responsive. In the multi-user case, bus events will be the primary notification mechanism for remote changes. CSV export is the budget handoff: the analyst exports the BOM, sends it to procurement, without needing to install or run the tool.

**S14.6-3: Max-sensor and max-effector constraints**
- _What:_ Add two numeric inputs to the panel: "Max sensors" and "Max effectors". When changed, update `constraints.max_sensors` and `constraints.max_effectors` in state and emit `constraint:updated`. Add a validation indicator next to each placement count (green check if within limits, red warning if exceeded). The limits are advisory in the editor (no hard enforcement) but the Optimiser will respect them. Write a test that sets `max_sensors: 3`, adds 4 placements, and checks the validation indicator shows a warning.
- _Why:_ Sensor count limits reflect real-world procurement constraints: "we have budget for 4 sensors maximum." The Optimiser needs these limits to produce feasible configurations. Showing the advisory warning in the editor surface the constraint violation early, before the user runs the simulation.

---

### Slice 14.7 — Threat Corridor Editor and Zone/Priority Editor Modules

_Goal: two drawing modules that share the same interaction pattern — the user draws polygons or routes on the terrain canvas. Building them together lets the drawing interaction logic be established once and applied to both._

**S14.7-1: Threat Corridor Editor manifest, panel, and draw mode**
- _What:_ Create `modules/threat-corridor-editor/manifest.json` with `reads: ["terrain"]`, `writes: ["threat_corridors"]`, `prerequisites: ["terrain"]`, `emits: ["corridor:added", "corridor:removed"]`, `subscribes: []`. Panel HTML: draw mode toggle button, a route list (name, threat profile selector, altitude input, speed input), a protected point picker button. Draw mode: on activate, set cursor to `crosshair`; each map click adds a waypoint to a working route (green dot at each click); double-click finalises the route (must have ≥2 waypoints); on finalise, show a name + threat profile form in the panel, on confirm write to `threat_corridors` state and emit `corridor:added`. Each active route is drawn as a dashed line (`threat-corridor-editor:routes-line`) with a directional arrow at each segment midpoint (`threat-corridor-editor:routes-arrow`). Route colour reflects assigned threat profile (one colour per profile from a fixed palette). Protected point is a pulsing circle (`threat-corridor-editor:protected-point`).
- _Why:_ Threat corridors are the foundation of kill chain analysis — without defined ingress routes, the engagement timeline calculation has no geometry to work with. Drawing directly on the terrain gives the analyst immediate spatial context: they can see the ridgelines and sensor placements while tracing the most dangerous approach route.

**S14.7-2: Threat Corridor Editor — route editing and map layer cleanup**
- _What:_ Add route editing: clicking an existing route in the map or panel list enters edit mode — each waypoint becomes a draggable marker, the user can add waypoints by clicking the line, remove waypoints by right-clicking, and drag waypoints to adjust the path. Confirm edit with a "Done" button. Remove route: trash icon in the panel list, emit `corridor:removed`, remove from state. In `onUnmount`: remove all map sources and layers (`threat-corridor-editor:routes-source`, `threat-corridor-editor:routes-line`, `threat-corridor-editor:routes-arrow`, `threat-corridor-editor:protected-point-source`, `threat-corridor-editor:protected-point`), remove all map event listeners, call `unsubs.forEach(u => u())`.
- _Why:_ Routes are rarely right on the first draw. Edit mode is essential: the analyst draws an approximate route, sees it in context with terrain and sensor coverage (after simulation), then refines it to probe the exact approach geometry. Complete `onUnmount` cleanup is critical for the drawing module because it adds multiple map event listeners that would continue firing if not removed.

**S14.7-3: Zone and Priority Editor manifest, panel, and draw mode**
- _What:_ Create `modules/zone-editor/manifest.json` with `reads: ["terrain"]`, `writes: ["zones"]`, `prerequisites: ["terrain"]`, `emits: ["zone:added", "zone:removed"]`, `subscribes: []`. Panel HTML: draw mode toggle, zone type selector (Priority / Exclusion), zone list with labels and coverage threshold inputs (for priority zones only). Draw mode: MapLibreGL polygon drawing interaction — user clicks to place polygon vertices, double-click closes the polygon (minimum 3 points). On close: show name + type form, on confirm write to `zones` state. Map layers: `zone-editor:priority-fill` (semi-transparent green fill, solid outline), `zone-editor:priority-label` (coverage threshold %), `zone-editor:exclusion-fill` (hatched red, using background-pattern or stripes from a canvas-generated pattern), `zone-editor:exclusion-outline` (dashed red). Watch `zones` state and rebuild both sources on change. Full `onUnmount` cleanup.
- _Why:_ Priority zones tell the optimiser and gap analysis where coverage matters most. Exclusion zones tell the optimiser where sensors cannot be placed (buildings, restricted areas). Both are spatial constraints that must be drawn directly on the terrain to be meaningful. The hatch pattern on exclusion zones is a standard cartographic convention that immediately communicates "no placement allowed here" to any engineer reading the map.

**S14.7-4: Zone polygon editing and coverage threshold UI**
- _What:_ Add polygon editing to the zone editor: click a zone in the panel or map to enter edit mode (each vertex becomes a draggable handle, edge midpoints show insert handles). Confirm with "Done". Delete zone: remove from `zones` state, emit `zone:removed`. Coverage threshold: the priority zone input accepts a percentage (0–100). Validate it is a valid number before writing to state (throw a user-visible validation error in the panel if not). Exclusion zone notes: optional free-text "reason" field (e.g., "Communications mast footprint") stored in state. Write tests: adding a zone writes the correct state; removing a zone emits `zone:removed`; an invalid threshold value is rejected with a visible error.
- _Why:_ Polygon editing is necessary because hand-drawn polygons on a map are imprecise. The engineer draws an approximate shape, sees the coverage results, then refines the boundary to match the actual physical perimeter. The coverage threshold is an operational specification: "this zone requires 95% coverage at all times" is a contractual statement that drives the optimiser and generates a pass/fail indicator in the coverage viewer.

**S14.7-5: MapLibreGL draw library integration**
- _What:_ Integrate `maplibre-gl-draw` (fork of `mapbox-gl-draw`) as the polygon/route drawing interaction engine for both the corridor editor and zone editor. This replaces the manual click-waypoint approach with a battle-tested drawing library that handles vertex snapping, polygon closure, and touch input. The library must be bundled locally (no CDN). Each module activates its own draw mode using the shared `addControl`-equivalent API — but since the map proxy does not expose `addControl`, use `api.map.on('click', ...)` directly and manage draw state in the module. Alternatively, expose `api.map.addDrawControl(mode)` / `api.map.removeDrawControl()` as two additional allowed proxy methods specific to draw operations. Write the decision in an architecture note comment in `map-proxy.js`. Test that draw state is correctly cleaned up on module unmount.
- _Why:_ Writing polygon drawing from scratch (click-vertex-vertex-close) produces a brittle UX compared to `maplibre-gl-draw`, which handles hover states, snapping, undo, and touch correctly. The proxy extension decision (expose `addDrawControl` or use `on('click')`) is an intentional architectural choice point — document it explicitly so future reviewers understand why the boundary was drawn there.

---

### Slice 14.8 — Simulation Runner Module

_Goal: serialise the current state into a `ScenarioConfig`, POST it to `/api/simulate`, stream progress, and write `sim_results`. This module is the integration point between the frontend and the Python engine._

**S14.8-1: Manifest, panel HTML, and pre-flight checklist**
- _What:_ Create `modules/simulation-runner/manifest.json` with `reads: ["terrain", "placements", "threat_corridors", "zones"]`, `writes: ["sim_results"]`, `prerequisites: ["terrain", "placements"]`, `emits: ["simulation:started", "simulation:progress", "simulation:complete", "simulation:failed"]`, `subscribes: []`. Panel HTML: a pre-flight checklist showing the current readiness state (terrain loaded ✓, sensors placed ✓/✗, corridors defined ✓/✗, zones defined optional), a "Run Simulation" button (disabled if checklist not satisfied), a progress log div, an elapsed timer, a Cancel button (hidden when not running), a result summary div (hidden until complete). On `init(api)`: use `api.state.watch` on `terrain`, `placements`, `threat_corridors`, `zones` to update the checklist in real time.
- _Why:_ The pre-flight checklist is a UX safeguard — it prevents the user from running a simulation with a misconfigured state (no terrain loaded, no sensors placed). Showing exactly which prerequisites are satisfied makes the tool self-guiding: a new user can see "I need to place sensors before I can run." The checklist state is purely reactive from `watch()` calls — it is always in sync with the current state without any manual update triggers.

**S14.8-2: State serialisation and POST /api/simulate**
- _What:_ On "Run Simulation" click: serialise the relevant state keys into a `ScenarioConfig` JSON body. The serialisation mapping: `terrain.dem_path` → scenario `site_dem_path`, `placements.sensors` → scenario `sensor_placements`, `placements.effectors` → scenario `effector_placements`, `threat_corridors` → scenario threat corridors, `zones` → scenario zones. Construct the JSON body and `fetch('/api/simulate', {method: 'POST', body: JSON.stringify(body)})`. Emit `api.bus.emit('simulation:started', {})`. Set `running = true` and show the Cancel button. Write a test that intercepts the fetch, asserts the request body matches the expected `ScenarioConfig` structure, and returns a mock SSE stream.
- _Why:_ The serialisation step is where the frontend data model (state schema from InterfaceArchitecture.md Section 3) maps to the backend data model (Pydantic `ScenarioConfig`). This mapping must be explicit and tested. Using `fetch` (not `EventSource`) for the initial request allows sending a request body — `EventSource` is GET-only, so the SSE stream is obtained from the fetch response's readable stream.

**S14.8-3: SSE progress stream consumer and cancellation**
- _What:_ Consume the SSE stream from the fetch response body using the `ReadableStream` API (`response.body.getReader()`). For each `data:` line: parse the JSON, dispatch on `type`: `progress` → append message to the log, update progress bar `pct`, emit `api.bus.emit('simulation:progress', {message, pct})`; `complete` → proceed to write results; `error` → show error in panel, emit `simulation:failed`, set `running = false`. Cancel: store an `AbortController`, pass `{signal: controller.signal}` to fetch. When Cancel is clicked, call `controller.abort()`. Handle `AbortError` by showing "Simulation cancelled" in the log. Update elapsed timer with `setInterval` while running; clear it in all terminal states (complete, error, abort). Remove the interval in `onUnmount` if still running.
- _Why:_ The `ReadableStream` API is the correct tool for consuming SSE from a POST response — it gives line-by-line control over the stream bytes. `AbortController` is the standard way to cancel a fetch mid-stream. Clearing the interval in `onUnmount` prevents timer callbacks firing after the module is deactivated (a classic source of phantom UI updates).

**S14.8-4: Results write and simulation:complete event**
- _What:_ On receiving `{"type": "complete", "result": simResults}` from the SSE stream: write `api.state.set('sim_results', simResults)`. Emit `api.bus.emit('simulation:complete', {coverage_pct: simResults.stats.coverage_pct})`. Show the result summary in the panel: composite coverage %, largest gap area, worst corridor coverage %. Hide the Cancel button. Set `running = false`. Stale indicator: if `placements` or `threat_corridors` state changes after a successful simulation (via `watch`), show a "Results may be stale — re-run simulation" banner. Clear the stale indicator on next successful completion.
- _Why:_ Writing `sim_results` to state immediately triggers `watch` callbacks in every subscribed analysis module (Coverage Viewer, Gap Analysis, Kill Chain Analyser, Saturation Analyser, Report Configurator) — those modules update without any direct communication with the simulation runner. The stale indicator is a subtle but important UX feature: it tells the analyst when their analysis results no longer reflect the current configuration, preventing decisions based on outdated data.

---

### Slice 14.9 — Coverage Viewer and Gap Analysis Modules

_Goal: display simulation results on the 3D terrain as toggleable coverage layers, and provide a ranked gap list with suggested remediations._

**S14.9-1: Coverage Viewer manifest, panel, and layer toggles**
- _What:_ Create `modules/coverage-viewer/manifest.json` with `reads: ["terrain", "placements", "sim_results"]`, `writes: []`, `prerequisites: ["terrain", "sim_results"]`, `emits: []`, `subscribes: ["simulation:complete"]`. Panel HTML: a layer control section with a toggle row per layer type (Radar, RF, EO_IR, Acoustic, Composite, Gaps, Effectors) each with a colour swatch and visibility checkbox. A statistics section: composite coverage %, per-zone compliance table (zone name, required %, actual %, pass/fail icon). A colour legend. On `simulation:complete` bus event: rebuild all map layers from the new `sim_results`. Use `api.state.watch('sim_results', rebuildLayers)` for any subsequent state-driven updates (e.g., if state is loaded from a saved scenario).
- _Why:_ Layer toggles let the analyst see each sensor type's contribution in isolation — turning off RF to see "what would radar alone cover?" is a frequent analytical task. Per-zone compliance is the pass/fail summary: "critical asset zone: 100% ✓, north perimeter: 74% ✗ (required 80%)." This is the most client-visible result of the entire simulation.

**S14.9-2: Coverage Viewer map layers**
- _What:_ For each coverage layer in `sim_results.layers` (keyed by sensor type + "composite" + "gaps" + "effector"): add a GeoJSON fill layer (`coverage-viewer:{type}-fill`) with the appropriate colour (matching `LAYER_COLOURS` extended with composite=blue at 30% opacity, gaps=red at 40% opacity) and a GeoJSON outline layer (`coverage-viewer:{type}-outline`). Layer sources are GeoJSON FeatureCollections from `sim_results.layers`. Bearing indicator lines: add `coverage-viewer:bearing-lines-source` and `coverage-viewer:bearing-lines` — a line for each directional sensor in `sim_results.sensor_placements` showing the left and right bearing extremities, using WGS84 latitude correction. All layers draped on the terrain (use `type: "fill"` — MapLibreGL drapes fill layers on terrain by default with `fill-extrusion-height: 0`). Full layer and source removal in `onUnmount`.
- _Why:_ Draping coverage fills on the 3D terrain is what makes the viewer qualitatively different from a flat 2D map — the analyst can tilt the camera and see exactly how terrain relief creates the gap in coverage on the north ridge. The bearing indicator lines on the Coverage Viewer are the full-simulation equivalent of the placement editor's preview lines — they should match exactly.

**S14.9-3: Gap Analysis manifest, panel, and ranked gap list**
- _What:_ Create `modules/gap-analysis/manifest.json` with `reads: ["terrain", "sim_results", "zones", "sensor_library"]`, `writes: []`, `prerequisites: ["terrain", "sim_results"]`, `emits: ["placement:pending"]`, `subscribes: ["simulation:complete"]`. Panel HTML: a sorted gap list (ranked by severity score = gap area × zone priority weight), each row showing gap ID, area (m²), severity badge (Critical/High/Medium based on zone overlap), a "Fly to" button. On gap row click: `api.map.flyTo` to the gap centroid and zoom to show the gap clearly. Suggestion card: for each gap, display a "Suggested sensor" card showing the sensor type and position from `sim_results` gap suggestions (if present) with a "Place this" button. "Place this" emits `api.bus.emit('placement:pending', {lat, lng, definition})`. `simulation:complete` bus subscription rebuilds the list.
- _Why:_ The gap list translates the visual gap map into actionable findings. "Gap #3: 1,240 m², Critical severity (overlaps protected asset zone), suggested placement: RF sensor at 51.234°N, -0.456°W" gives the analyst a precise remediation action. Emitting `placement:pending` sends the analyst directly to the Placement Editor with the suggested sensor pre-selected — the cross-module workflow (analysis → placement) works without either module knowing about the other.

**S14.9-4: Coverage Viewer click-to-inspect and gap highlight**
- _What:_ Add `api.map.on('click', 'coverage-viewer:gaps-fill', handler)`. On click: show an inspect popup (via a temporary `<div>` positioned over the click point, not a MapLibreGL popup — avoids map lifecycle conflicts) displaying the gap area, coverage percentage at that point, and which sensor types cover/don't cover it. Highlight the selected gap polygon by adjusting the fill opacity of `coverage-viewer:gaps-fill` using `api.map.setLayoutProperty`. Link the clicked gap to the Gap Analysis panel if it is active (emit a `gap:selected` internal event — wait, this is not a declared event. Instead: write a `ui.selected_gap_id` into the `ui` state key via a shell-level mechanism, or coordinate via a shared `sim_results.selected_gap_id` sub-key. Resolve this by having Coverage Viewer emit `placement:pending` directly for gap-click with the suggested sensor — simpler and already within declared contracts). Clean up click listener in `onUnmount`.
- _Why:_ Click-to-inspect makes the coverage map interactive rather than a static display. The analyst can click on a red gap polygon and immediately see "this area is uncovered because it is in the radar's blind zone below 10° elevation but within RF range — consider adding an EO/IR sensor here." The gap highlight is the visual link between the click and the data.

**S14.9-5: Zone compliance indicators on Coverage Viewer map**
- _What:_ Add a zone compliance overlay to the Coverage Viewer map: `coverage-viewer:zone-compliance-source` (GeoJSON FeatureCollection of zone polygons with a `compliance_status` property: "pass" / "fail" / "marginal"), `coverage-viewer:zone-compliance-outline` (thick outline, colour-coded: green=pass, red=fail, yellow=marginal). On hover: show a tooltip with the zone name, required coverage %, actual coverage %, and status. This layer is toggled independently from the coverage fill layers. Test: given a `sim_results` fixture with a zone at 74% vs 80% requirement, assert the compliance layer contains a "fail" feature for that zone.
- _Why:_ Zone compliance on the map spatially anchors the pass/fail table in the panel. The analyst can see exactly which geographic area is failing rather than just reading a number. The thick coloured outline (not a fill, to avoid obscuring the underlying coverage) is immediately legible even on a complex multi-layer map.

---

### Slice 14.10 — Kill Chain Analyser and Saturation Analyser Modules

_Goal: two read-only analysis modules that consume `sim_results` and `threat_corridors`. Kill Chain shows the D-T-I-D-E-A timeline per corridor; Saturation shows multi-drone capacity._

**S14.10-1: Kill Chain Analyser manifest, panel, and corridor selector**
- _What:_ Create `modules/kill-chain-analyser/manifest.json` with `reads: ["terrain", "sim_results", "threat_corridors"]`, `writes: []`, `prerequisites: ["terrain", "sim_results"]`, `emits: []`, `subscribes: ["simulation:complete"]`. Panel HTML: a route/corridor selector dropdown (populated from `threat_corridors` state). For the selected corridor: a D-T-I-D-E-A timeline bar (rendered as an SVG horizontal Gantt chart — each phase is a coloured segment, the full bar width is `time_to_asset_s`, phases after first detection are rendered, phases before detection are greyed). A margin indicator (green if margin > 0, red if negative, with ± seconds). First detection range and sensor name. Available time vs required time. Kill chain gap warning if margin < 0. `simulation:complete` bus subscription triggers a re-render for the currently selected corridor.
- _Why:_ The kill chain timeline is the primary operational answer: "can you stop it in time?" The SVG Gantt chart makes the timeline immediately legible without requiring the analyst to read numbers — a red bar extending past the available time boundary is instantly understood as "the drone arrives before the kill chain completes." This is one of the most compelling visuals in a briefing.

**S14.10-2: Kill Chain Analyser map integration and worst-corridor highlighting**
- _What:_ Add map layers for the selected corridor: `kill-chain-analyser:selected-corridor-source`, `kill-chain-analyser:selected-corridor-line` (thick line in corridor colour), `kill-chain-analyser:detection-event-source`, `kill-chain-analyser:detection-event-circles` (circle markers at each `DetectionEvent.position`, labelled with sensor name and time). `kill-chain-analyser:engagement-marker` (star at the first engagement point — `first_detection_range` back from the asset). Fly to the corridor bounding box when a corridor is selected. Add a "Worst corridor" button that selects the corridor with the lowest kill chain margin. Update all map layers on corridor selection change. Full `onUnmount` cleanup of all sources, layers, and map listeners.
- _Why:_ Combining the Gantt chart (temporal) with the map markers (spatial) lets the analyst trace "this is where the drone was first detected, this is how long the kill chain took from that point, and this is why there wasn't enough time — the detection happened too close to the asset." Spatial and temporal views are complementary; neither alone tells the full story.

**S14.10-3: Saturation Analyser manifest, panel, and threshold calculator**
- _What:_ Create `modules/saturation-analyser/manifest.json` with `reads: ["terrain", "sim_results"]`, `writes: []`, `prerequisites: ["terrain", "sim_results"]`, `emits: []`, `subscribes: ["simulation:complete"]`. Panel HTML: a "simultaneous threats" range slider (1–20). An effector utilisation bar chart (one bar per effector, showing % time busy across the scenario). An "unengaged threats" count badge. A saturation threshold indicator: "System saturates at N simultaneous threats." The saturation data is read from `sim_results.saturation_result`. On slider change, filter the saturation result to show the selected threat count. `simulation:complete` subscription resets the slider to 1 and rebuilds charts.
- _Why:_ The saturation threshold is a headline procurement metric: "this configuration handles up to 6 simultaneous drones; at 7, at least one gets through unengaged." The slider lets the client interactively probe "what if we faced 8 drones?" without re-running the simulation. Since `saturation_result` contains pre-computed data for all N from 1–20, slider changes are instantaneous — no backend call needed.

**S14.10-4: Saturation Analyser map behaviour and chart rendering**
- _What:_ Add map layers showing simultaneous approach vectors for the selected threat count: `saturation-analyser:approach-vectors-source`, `saturation-analyser:approach-vectors-line` (one line per threat, colour-coded by engagement status: green=engaged, red=unengaged, orange=engaged after reload). An "overwhelmed effectors" highlight: `saturation-analyser:overwhelmed-effectors-source`, `saturation-analyser:overwhelmed-effectors-circle` (red pulsing ring on any effector fully committed at the selected N). Render the targets-vs-unengaged bar chart as an SVG or `<canvas>` element in the panel using the pre-computed data from `sim_results.saturation_result`. Full `onUnmount` cleanup.
- _Why:_ The colour-coded approach vector lines (green=stopped, red=getting through) on the map make the saturation scenario immediately understandable in a briefing: "at this threat count, these specific vectors are undefended." The overwhelmed-effector highlight spatially identifies the bottleneck: "the jammer in the NW corner is the limiting effector — adding a second jammer there raises the threshold from 6 to 11."

---

### Slice 14.11 — Optimiser Module

_Goal: compute optimal sensor/effector placements by posting constraints and zone definitions to the backend optimiser, streaming progress, and presenting proposed placements for user review before applying them. This is the second backend-integration module after the Simulation Runner._

**S14.11-1: Manifest, panel, and objective configuration**
- _What:_ Create `modules/optimiser/manifest.json` with `reads: ["terrain", "zones", "constraints", "sensor_library", "effector_library", "threat_corridors"]`, `writes: ["optimiser_results"]`, `prerequisites: ["terrain", "zones"]`, `emits: ["optimiser:started", "optimiser:complete", "optimiser:failed"]`, `subscribes: ["zone:added", "zone:removed", "constraint:updated"]`. Panel HTML: an objective selector (radio buttons: Maximise composite coverage / Maximise critical-zone coverage / Minimise cost at target coverage), a constraint summary panel (reads from `constraints` state — budget, max sensors, max effectors, allowed sensor IDs), a "Run Optimiser" button, a progress indicator, an Apply/Discard proposed placements section (hidden until results arrive). On `zone:added`, `zone:removed`, `constraint:updated` bus events: show a "Parameters changed — re-run optimiser" notice.
- _Why:_ The objective selector is the primary UX decision point: the analyst chooses whether to optimise for coverage, zone protection, or cost. This choice maps directly to the scoring function in the backend `greedy_place_sensors` engine. The constraint summary panel gives the analyst a final check before running: "am I optimising with the right budget and sensor limits?"

**S14.11-2: POST /api/optimise with SSE progress stream**
- _What:_ On "Run Optimiser" click: serialise `{zones, constraints, sensor_library_filter: constraints.allowed_sensor_ids, effector_library_filter: constraints.allowed_effector_ids, terrain, objective}` as the request body. `fetch('/api/optimise', ...)` with `AbortController`. Consume the SSE stream: `progress` events → update progress bar and log (e.g., "Placing sensor 2/5 — coverage now 67%"); `complete` → write `api.state.set('optimiser_results', result)`, emit `optimiser:complete`; `error` → show error, emit `optimiser:failed`. Show proposed placements as ghost markers on the map (`optimiser:ghost-sensors` source/layers — grey dashed circles with green tint, not in the `placements` state). Emit `optimiser:started` on POST. Cancel button uses `AbortController.abort()` same pattern as Simulation Runner.
- _Why:_ Reusing the SSE streaming pattern from Slice 14.8 means this module is straightforward to implement once the pattern is established. The ghost markers are a critical UX decision: proposed placements are shown visually but not written to `placements` state until the user approves. This prevents the Coverage Viewer and Gap Analysis from reacting to unapproved proposals.

**S14.11-3: Apply/Discard proposed placements and score summary**
- _What:_ On `optimiser_results` state written: show the Apply/Discard section with the result summary: proposed configuration score, coverage %, total cost AUD, satisfied/violated constraints (from `optimiser_results.satisfied_constraints`, `violated_constraints`). "Apply" button: merge `optimiser_results.proposed_placements` into `placements` state via `api.state.set('placements', merged)` — emit `placement:added` for each new placement via `api.bus.emit`. Remove ghost marker layers. "Discard" button: remove ghost markers, clear `optimiser_results` state (`api.state.set('optimiser_results', null)`). After Apply, the Simulation Runner's stale banner will appear, prompting the user to re-run the simulation with the new placements.
- _Why:_ The Apply/Discard flow is essential: optimiser results are proposals, not decisions. The analyst reviews the proposed layout against the terrain and existing placements before committing. After Apply, the natural next step is re-simulation — the stale banner on the Simulation Runner guides the user there without requiring explicit instruction.

**S14.11-4: Bus event reactivity and state change invalidation**
- _What:_ Subscribe to `zone:added`, `zone:removed`, `constraint:updated` bus events. On any of these: if `optimiser_results` is non-null, set a stale flag and show a notice: "Zone or constraint changed — previous optimiser results may no longer be valid. Re-run to update." Also `api.state.watch('zones', checkStale)` and `api.state.watch('constraints', checkStale)` for redundancy (in case state is loaded from file rather than changed via events). Clear the stale flag when a new optimiser run completes. Write tests: add a zone after optimiser has run → stale notice appears; re-run → stale notice clears.
- _Why:_ The optimiser result is only valid for the zone and constraint state that existed when it was computed. If the user adds a new zone after running the optimiser, the proposed placements may not satisfy it. The stale notice prevents the user from applying an outdated result. Using both bus events and state watches is the correct belt-and-braces approach: events catch real-time changes, watches catch loaded state.

---

### Slice 14.12 — Scenario Comparison Module

_Goal: load a saved scenario B (a previously exported `viewer_data.js` file) and render a side-by-side or overlay comparison against the current simulation results._

**S14.12-1: Manifest, panel, and scenario B loading**
- _What:_ Create `modules/scenario-comparison/manifest.json` with `reads: ["terrain", "sim_results"]`, `writes: ["scenario_b_sim_results"]`, `prerequisites: ["terrain", "sim_results"]`, `emits: ["comparison:loaded"]`, `subscribes: []`. Panel HTML: a "Load Scenario B" file picker (`<input type="file" accept=".js,.json">`), a loaded indicator (filename + timestamp), a comparison summary table (side by side: coverage %, cost AUD, largest gap m², worst corridor coverage %, kill chain margin best/worst), an overlay mode selector (Overlay diff / Swipe divider). On file select: read the file as text, attempt `eval()` (for `.js`) or `JSON.parse()` (for `.json`) to extract the `sim_results` payload, validate it has the expected structure, write to `api.state.set('scenario_b_sim_results', parsed)`, emit `comparison:loaded`.
- _Why:_ Loading the existing `viewer_data.js` format means the scenario B file is already a natural output of the existing `salus viewer` command — no new export format required. An analyst runs `salus viewer` on configuration B, receives a `viewer_data.js`, and loads it directly into the comparison module. The comparison table immediately answers the procurement question: "is Config B worth the $300K additional cost?"

**S14.12-2: Overlay diff map layers**
- _What:_ When scenario B is loaded: compute the diff by comparing `sim_results.layers.composite` (FeatureCollection) against `scenario_b_sim_results.layers.composite` using polygon set operations (Turf.js or server-side — add `POST /api/compare` endpoint that does the spatial diff in Python using Shapely and returns three GeoJSON layers: A-only, B-only, both). Add map layers: `scenario-comparison:a-only-fill` (red, "A covers, B does not"), `scenario-comparison:b-only-fill` (green, "B covers, A does not"), `scenario-comparison:both-fill` (grey, "both cover"). Toggle A-only and B-only visibility independently from the panel. Placement markers: show scenario A sensors in solid circles, scenario B sensors as outlined circles on a separate layer for spatial comparison. Full `onUnmount` cleanup.
- _Why:_ The spatial diff is the most value-dense output of the comparison module. "The red polygons show where Config A uniquely covers; the green shows where Config B improves coverage" — this is immediately actionable. Using a server-side spatial diff (Shapely) avoids implementing polygon boolean operations in JavaScript and reuses the existing Python geometry stack.

**S14.12-3: Swipe divider and scenario B sensor placement display**
- _What:_ Implement the swipe divider: a vertical drag handle across the map canvas. Left of the handle shows scenario A layers; right shows scenario B layers (achieved by setting `clip` bounds on each layer group — MapLibreGL supports `clip` expressions on layer paint). The handle position is stored as `x_fraction` (0–1) and updated on drag. Add scenario B sensor placement markers as a separate layer (`scenario-comparison:b-sensors-source`, `scenario-comparison:b-sensors-circle`) shown only in swipe mode. Add a summary statistics row above the map ("A: 78% | B: 89% | Delta: +11pp") that updates as the divider moves (showing the proportional mix of A and B coverage visible). Full cleanup in `onUnmount`.
- _Why:_ The swipe divider is the most visceral comparison tool: the analyst drags the handle across the terrain and sees exactly how the two configurations differ at each location. The rolling statistics header ("A: 78% | B: 89%") reinforces that B is better overall, while the spatial swipe shows *where* the improvement occurs.

---

### Slice 14.13 — Report Configurator Module

_Goal: configure the customer PDF report from within the interface and trigger generation via the backend. The analyst does not need to leave the browser to produce a deliverable._

**S14.13-1: Manifest, panel, and configuration form**
- _What:_ Create `modules/report-configurator/manifest.json` with `reads: ["sim_results", "placements", "zones", "threat_corridors", "report_config"]`, `writes: ["report_config"]`, `prerequisites: ["sim_results"]`, `emits: ["report:generated"]`, `subscribes: []`. Panel HTML: a configuration form with fields for client name (text input), logo upload (`<input type="file" accept="image/*"`), sanitisation level selector (None / Minimal / Redacted / Full — descriptions for each), a module content checklist (toggle each report section: Executive Summary, Site Overview, Coverage Analysis, Gap Analysis, Threat Analysis, Kill Chain, Saturation, Comparison, Recommendations, Assumptions, Appendix). Write form changes to `api.state.set('report_config', config)` on each input change using `watch` to keep the form in sync with any externally loaded `report_config` state.
- _Why:_ The report configurator centralises all output customisation. The sanitisation level selector is operationally important: a deliverable to a defence customer gets "Redacted" (exact ranges → band categories, coordinates rounded), while an internal working report uses "None." The module content checklist lets the analyst omit sections not relevant to a given engagement (e.g., omit Comparison if only one configuration was assessed).

**S14.13-2: Map screenshot capture and report generation request**
- _What:_ Add a "Capture Map View" button that calls `api.map.getCanvas().toDataURL('image/png')` to capture the current map state as a base64 PNG and stores it in local module state as `capturedMapView`. A thumbnail preview of the captured view appears in the panel. "Generate Report" button: POST to `/api/report` with `{report_config: api.state.get('report_config'), sim_results, placements, zones, threat_corridors, map_screenshot: capturedMapView}`. Show a spinner while waiting. On response (PDF binary): create an `<a>` element with `href = URL.createObjectURL(blob)` and `download = "salus-report-{date}.pdf"`, programmatically click it to trigger download. Emit `api.bus.emit('report:generated', {filename})`.
- _Why:_ The map screenshot gives the PDF report a current-state terrain view that reflects exactly what the analyst was looking at when they generated the report. The `getCanvas()` call is on the allowed map proxy method list precisely for this purpose. The browser-native blob download approach requires no file system access and works in any deployment (local, web, air-gapped).

**S14.13-3: Sanitisation preview and report_config state persistence**
- _What:_ Add a sanitisation preview panel: when "Redacted" or "Full" is selected, show a sample table of affected sensor fields before and after sanitisation ("max_range_m: 3500 → 'Long range'", "position_lat: 51.2345 → 51.23"). This preview uses a client-side simulation of the sanitisation rules (mirror the logic from `sanitise.py` in JavaScript) — no backend call needed. Add a `report_config` state persistence: on panel mount, one-time `get('report_config')` to populate the form with any previously set config (e.g., loaded from a saved scenario). Ensure all form field values are driven by `watch('report_config', updateForm)` for full reactivity. Test: set sanitisation level to Redacted, assert the preview shows rounded coordinates; set client name, reload the module, assert client name is preserved from state.
- _Why:_ The sanitisation preview prevents surprises: the analyst can see exactly which fields will be redacted before generating the report, and can adjust the level if the result is too aggressive or too permissive. Driving the form from `watch('report_config')` means saved scenarios restore the last report configuration automatically — the analyst does not need to re-enter client details after loading a scenario file.

---

### Slice 14.14 — Scenario Persistence and Deployment Configurations

_Goal: save and restore the complete session state as a JSON file, pre-load libraries at shell startup, and validate the two primary deployment configurations (minimal viewer-only and full analyst suite)._

**S14.14-1: Shell startup library pre-load**
- _What:_ In `shell.js`, before any module is initialised: `fetch('/api/sensors')` and `fetch('/api/effectors')` in parallel (using `Promise.all`). Write the responses directly to state via the shell's bypass path: `state.setState('sensor_library', sensors)` and `state.setState('effector_library', effectors)`. Show a loading screen while fetching; on completion, proceed to module discovery and nav bar construction. If the API is unavailable (e.g., minimal viewer-only deployment), fall back to `SALUS_DATA.sensor_library` and `SALUS_DATA.effector_library` from `viewer_data.js` if present, or empty arrays. Write a test that stubs the API to return a known library and asserts the state is populated before any module init is called.
- _Why:_ Every module that reads `sensor_library` or `effector_library` needs this data immediately. Pre-loading at shell startup (not per-module) means the data is available the moment any module calls `api.state.get('sensor_library')` — no module needs to handle the loading state. The fallback to `viewer_data.js` makes the same shell code work for both the minimal deployment (no API, pre-generated data) and the full deployment (API running).

**S14.14-2: Scenario save and load**
- _What:_ Add a "Save Scenario" and "Load Scenario" button to the shell nav bar (not in any module — these are shell-level operations). "Save Scenario": `JSON.stringify` the entire state (excluding `ui` key) via the shell's direct state read. Trigger a download named `scenario-{date}.salus.json`. "Load Scenario": file picker accepting `.salus.json`. On file load: parse and validate the JSON (check top-level keys match expected state schema), then write each key to state via the shell bypass path. Show a confirmation modal before overwriting a session with active placements. After loading, the Mode Manager re-evaluates all prerequisite gates (the `watch` subscriptions on prereq keys fire automatically as state is written). Write a test: save a state with placements and sim_results, load it back, assert placements and sim_results match.
- _Why:_ Scenario save/load is the persistence layer for multi-session work. An analyst does a session on Monday, saves the scenario, loads it on Wednesday, continues from where they left off — all placements, zones, corridors, and results restored. The shell owns this operation (not a module) because it requires accessing the full state directly, bypassing the proxy.

**S14.14-3: Minimal deployment configuration (viewer-only)**
- _What:_ Define the "minimal" deployment configuration from InterfaceArchitecture.md Section 8: only the Terrain Loader and Coverage Viewer modules are present in `modules/`. The FastAPI backend is not running. `viewer_data.js` provides pre-generated `sim_results`, `sensor_placements`, and optionally `sensor_library`. Write a `deploy-minimal.sh` script that copies only the minimal module directories, `index.html`, `shell.js`, `style.js`, and the static assets into an output directory. Test by running the shell with only these two modules: confirm that Coverage Viewer activates only after terrain loads, that no other nav buttons appear (no other modules present), and that the system does not throw errors from the missing API.
- _Why:_ The minimal configuration is the customer deliverable format — a self-contained viewer package with no editing capability and no backend dependency. Validating it explicitly confirms that module discovery (finding only two modules) and the API fallback (graceful degradation when `/api/sensors` returns 404) both work correctly.

**S14.14-4: Full deployment configuration validation and `salus interface` integration**
- _What:_ Write an end-to-end integration test (using Playwright or similar browser automation) that: starts the FastAPI backend on a test port, opens `index.html` in a headless browser, waits for all 14 modules to appear in the nav bar, loads a test DEM via the Terrain Loader, verifies the nav bar enables the Placement Editor after terrain is loaded, drags a test sensor onto the map, runs a simulation, waits for `sim_results` state to be written, activates the Coverage Viewer and asserts coverage layers appear on the map. Update `salus interface --scenario scenario.yaml` to: start the FastAPI server, pre-generate terrain tiles if not present, open the interface in the default browser, and gracefully handle Ctrl+C shutdown (stop uvicorn cleanly). Document the two deployment configurations in `docs/InterfaceArchitecture.md` Section 8 with the actual `deploy-*.sh` scripts referenced.
- _Why:_ The integration test is the end-to-end proof that all 14 modules work together through the full workflow (load terrain → place sensors → run simulation → view results). Without this test, integration bugs between modules (wrong event name, missing state key, incorrect serialisation) can survive code review and only surface during a demo. The `salus interface` command is the single user-facing entry point — it must handle all setup transparently.

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

**I-5: Sensor/effector library panel with drag-and-drop placement**
- _Source:_ Enhancement — the viewer shows sensors from the scenario file but there is no way to interactively try different sensor placements without editing YAML and re-running the simulation.
- _Goal:_ Add a collapsible floating panel on the left side of the viewer that lists every sensor and effector in the embedded library, grouped by type. The user can expand entries to inspect key specs, then drag a sensor or effector from the panel and drop it onto the map to visually place it. Placed markers use the same type-coloured rendering as scenario sensors (I-4). Sector sensors get a rotate handle so the user can adjust bearing. All placements are tracked in memory in a form that is ready for future scenario export and simulation triggering.
- _Architecture notes:_
  - **Library data embedded at export time.** `viewer-export` loads all sensor and effector YAMLs from `src/salus/data/sensors/` and `src/salus/data/effectors/`, groups them by `type`, and serialises them into `viewer_data.js` as `SALUS_DATA.sensor_library` and `SALUS_DATA.effector_library`. No server is required at view time.
  - **Spec fields configurable via constant.** A single `SPEC_DISPLAY_FIELDS` array at the top of `app.js` (array of `{key, label}` objects) controls which YAML fields appear in the expand view. Adding, removing, or relabelling fields requires changing only that one array.
  - **User placements tracked in `userPlacements`.** Each entry: `{id, lat, lng, bearing_deg, definition}` where `definition` is the full library object. A `getUserPlacementsAsGeoJSON()` helper function is present but not yet wired to any export button. This is the hook for future scenario save / simulation trigger I-tasks.
  - **Drag-and-drop via HTML5.** Panel entries are `draggable`. The map canvas listens for `dragover` / `drop`. On drop, pixel coordinates are converted to `map.unproject()` lat/lng.
  - **Rotate handle.** For placed sector sensors (azimuth_coverage_deg < 360), a small circular handle marker is placed offset from the sensor. Dragging the handle recomputes bearing from the sensor centre and redraws the wedge. Omnidirectional sensors (azimuth = 360) get no handle.
  - **Separate MapLibre source/layer for user placements.** User-placed sensors are kept in a dedicated GeoJSON source (`user-placements`) and layer (`user-placement-circles`, `user-placement-wedges`, `user-placement-labels`) so existing scenario layers are untouched and the placement data can be extracted cleanly.
  - **No viewshed computation in this task.** A disabled "Run Simulation" button placeholder may be included as a visual cue, but triggering Python-side computation is out of scope.
- _Acceptance criteria:_
  1. A "Library" toggle button is always visible on the left side of the viewer.
  2. Clicking the toggle opens a floating panel; clicking it again (or an ✕ on the panel) collapses it. State (open/closed, scroll position, expanded entries) is preserved between toggles within the session.
  3. The panel has two top-level collapsible sections: **Sensors** and **Effectors**.
  4. Sensors are sub-grouped by type: Radar, RF, EO_IR, Acoustic. Effectors are sub-grouped by type matching the `type` field in each YAML. Sub-groups with zero entries are hidden.
  5. Each entry row shows the sensor/effector name, its type abbreviation badge (coloured per `LAYER_COLOURS`), an expand/collapse arrow, and a drag handle icon.
  6. Clicking the expand arrow reveals a spec table rendered from `SPEC_DISPLAY_FIELDS`. Fields with `null` values display as "—".
  7. Dragging the drag handle and dropping it onto the map canvas places a marker at the drop location. The marker uses the same circle + abbreviation badge rendering as I-4 scenario sensors.
  8. Placed sector sensors (azimuth_coverage_deg < 360) are drawn with a bearing wedge at default bearing 0° (North) and receive a rotate handle — a small circle offset from the marker in the direction of the current bearing.
  9. Dragging the rotate handle updates the sensor's bearing and redraws the wedge in real time.
  10. Omnidirectional sensors (azimuth_coverage_deg == 360) receive no wedge and no rotate handle.
  11. `userPlacements` is a module-level array. `getUserPlacementsAsGeoJSON()` returns a valid GeoJSON FeatureCollection of all current placements.
  12. `SPEC_DISPLAY_FIELDS` is a single array constant at the top of `app.js`; no other code change is needed to add, remove, or relabel a displayed field.
  13. `viewer-export` embeds `sensor_library` and `effector_library` into `SALUS_DATA` in `viewer_data.js`, grouped by type, each entry containing all YAML fields.
  14. All existing scenario sensor markers, coverage layers, terrain, layer controls, click popups, and bearing wedges are unaffected.
  15. All existing tests pass; new tests cover: library serialisation in `viewer-export`, `getUserPlacementsAsGeoJSON()` output shape.

**I-6: Resolve Opus-tier triage bugs (#1, #2, #5, #7, #8, #9, #12)**
- _Source:_ Triage sweep `docs/BugTriage.md` (2026-04-17). Seven bugs flagged as architectural/critical and routed to Opus. Defects logged as D-406 through D-412 in `.forge/defect-register.yaml`.
- _Goal:_ Make the broken interface↔backend contract paths work end-to-end so the live shell renders correct results panels, the report generator stops returning 422, the libraries populate, the path-traversal vulnerability is closed, and concurrent terrain loads stop clobbering each other.
- _Architecture notes:_
  - **Canonical state shapes are the contract.** `docs/Technical/InterfaceArchitecture.md` §3 defines `zones: {priority, exclusion}` with inner fields `{label, geometry, min_coverage_pct | reason}`, and `threat_corridors: ThreatCorridor[]` with `protected_point` denormalised. Editors that wrote non-canonical shapes broke every consumer; the fix is to make the editors emit canonical and accept legacy on read for backward compatibility with saved scenarios.
  - **Permissive backend bodies for UI-shaped POSTs.** `/api/report` is called by report-configurator with the UI report_config (no DEM path). The backend reconstructs the minimum ScenarioConfig server-side from `placements` rather than rejecting the body.
  - **Per-session terrain state.** `_terrain_session` (single global) replaced with `_terrain_sessions` keyed by per-load `session_id`; tile URL templates are session-qualified so two concurrent loads serve disjoint tiles.
  - **DEM allowlist.** `_validate_dem_path` enforces an allowlist (default: `_TERRAIN_DATA_DIR`; extensible via `SALUS_ALLOWED_DEM_DIRS`). Pytest fixtures register `tmp_path` automatically.
  - **Library bootstrap from shell.** No module owns `sensor_library` / `effector_library` writes — the shell fetches `/api/sensors` and `/api/effectors` once at startup and seeds state.
  - **Stats alias surface.** `worst_corridor_coverage_pct` added to `export_viewer_data`'s stats dict (the `coverage_pct` and `largest_gap_area_m2` aliases were already added in D-405).
- _Acceptance criteria:_
  1. `pytest tests/` passes (the bundled regression tests now include `test_simulate_rejects_path_outside_allowlist`, `test_terrain_concurrent_loads_keep_disjoint_tile_paths`, and the rewritten `test_report_accepts_ui_report_config_without_dem_path`).
  2. `node --test src/salus/viewer/interface/tests/*.js` passes (zone-editor, threat-corridor-editor, kill-chain-analyser tests updated to canonical shapes).
  3. `/api/simulate` returns HTTP 403 when `site_dem_path` resolves outside `_ALLOWED_DEM_DIRS`.
  4. Two concurrent `POST /api/terrain/load` calls receive distinct `session_id` values and disjoint `tile_url_template` URLs.
  5. `POST /api/report` with the UI report_config (no `site_dem_path`) returns a PDF (`application/pdf`).
  6. Shell bootstraps `sensor_library` and `effector_library` from `/api/sensors` and `/api/effectors`.
  7. `zone-editor` writes `{priority: PriorityZone[], exclusion: ExclusionZone[]}` with canonical inner fields (`label`, `geometry`, `min_coverage_pct` | `reason`).
  8. `threat-corridor-editor` writes a flat `ThreatCorridor[]` with `protected_point` on each entry.
  9. `export_viewer_data` includes `stats.worst_corridor_coverage_pct` whenever any corridor result has a `coverage_pct`.
  10. `docs/BugTriage.md` Opus section is annotated with the resolution and defect IDs.

**I-7: Resolve Sonnet-tier triage bugs (#3, #4, #6, #13, #14, #15, #16, #18, #19, #21, #22, #23, #27, #28, #29, #30)**
- _Source:_ Triage sweep `docs/BugTriage.md`. Sixteen medium/clear-scope bugs routed to Sonnet. Defects logged as D-429 through D-443 in `.forge/defect-register.yaml`.
- _Goal:_ Fix manifest contract gaps, data-flow errors, model validation holes, and JS event-listener leaks identified in the Sonnet triage tier.
- _Acceptance criteria:_
  1. `pytest tests/` passes including new regression tests for each fixed bug.
  2. `node --test src/salus/viewer/interface/tests/*.js` passes.
  3. `docs/BugTriage.md` Sonnet section is annotated with resolution and defect IDs.

**I-8: Resolve Haiku-tier triage bugs (#10, #11, #17, #20, #24, #25, #26, #31, #32, #33, #34, #35)**
- _Source:_ Triage sweep `docs/BugTriage.md`. Twelve mechanical/trivial bugs. Defects logged as D-444 through D-455 in `.forge/defect-register.yaml`.
- _Goal:_ Fix missing dependencies, over-exports, over-strict prerequisites, dead manifest declarations, model validation bounds, and empty no-op subscriptions.
- _Acceptance criteria:_
  1. `mercantile` and `Pillow` present in the `interface` extra in `pyproject.toml`.
  2. `Dockerfile` installs `.[dev,interface]`.
  3. `scenario-comparison/index.js` exports only `{ init }`.
  4. `optimiser` manifest `prerequisites` contains only `["terrain"]` (zones removed).
  5. `_test-module` removed from `modules/index.json`.
  6. `scenario-comparison` manifest `reads` includes `"scenario_b_sim_results"`.
  7. `coverage-viewer` manifest `reads` does not include `"placements"`.
  8. `SiteModel.resolution` has `gt=0` constraint.
  9. `SanitiseConfig.coordinate_precision` has `ge=0` bound (converted to Pydantic field or validated dataclass).
  10. `PlacementWeights` has `model_config = ConfigDict(extra="forbid")`.
  11. `gap-analysis/index.js` removes the empty `simulation:complete` subscription; manifest `subscribes` updated to `[]`.
  12. `kill-chain-analyser/index.js` removes the no-op terrain watch; manifest `reads` updated to remove `"terrain"`.
  13. `optimiser/index.js` sends `[]` instead of `null` when `allowed_sensor_ids` is absent.
  14. `docs/BugTriage.md` Haiku section annotated with resolution and defect IDs.

**I-11: Restore terrain fidelity and solid appearance in the interactive interface**
- _Source:_ Triage — firing up `salus interface --scenario demo/explore/E01_dramatic_terrain/scenario.yaml` shows the DEM rendered at noticeably lower resolution than the older standalone `salus viewer` export, and the terrain appears semi-translucent because the page background bleeds through the hillshade.
- _Root causes:_
  - `_compute_zoom_levels` in `src/salus/interface_api/app.py` hard-caps `max_zoom` at 13. For a 5 m DEM the ideal zoom is ~15; clamping to 13 quarters the linear resolution. The older standalone exporter (`src/salus/viewer/export.py`) uses a fixed `_TERRAIN_MAX_ZOOM = 16`.
  - `shell.js` initialises MapLibre with an empty style (`sources: {}`, `layers: []`) and `#map` has no CSS background, so the body's `#0d0d1a` shows through any unshaded area.
  - The terrain-loader's hillshade paint uses a soft brown shadow (`#473B24`) with no explicit highlight or viewport illumination anchor — much lower contrast than the standalone viewer's `#1a1a2e` shadow + white highlight.
- _Fix:_
  - Replace the absolute `max_zoom=13` cap with a tile-budget walk-down (`_TERRAIN_TILE_BUDGET = 500`): start from the resolution-ideal zoom (capped at 16) and step down until the total tile count across the 6-zoom pyramid stays within budget. Small-area DEMs now generate up to z=16; very large DEMs naturally back off to keep tile generation tractable.
  - Add an opaque `background` layer to the MapLibre initial style in `shell.js` so the hillshade has a solid colour underneath rather than the page bleeding through.
  - Update the terrain-loader hillshade paint properties to match the standalone viewer: `hillshade-shadow-color: #1a1a2e`, explicit `hillshade-highlight-color: #ffffff`, `hillshade-illumination-anchor: viewport`.
- _Acceptance criteria:_
  1. `_compute_zoom_levels` accepts optional `bounds_wgs84` and `tile_budget` arguments; when bounds are supplied, returned (min,max) zooms yield a total tile count ≤ budget.
  2. For `dramatic_terrain.tif` (5 m / 2 km square), `_compute_zoom_levels` returns `max_zoom == 15` or `16` (within the 500-tile budget), not 13.
  3. For a synthetic large-area / low-resolution DEM, the walk-down picks a lower max_zoom rather than blowing the budget.
  4. The MapLibre style instantiated in `shell.js` contains exactly one initial layer of type `background` with a non-transparent paint colour.
  5. The terrain-loader hillshade layer paint includes the three updated properties (`hillshade-shadow-color`, `hillshade-highlight-color`, `hillshade-illumination-anchor`).
  6. `pytest tests/` passes, including updated/new tests for the budget logic.
  7. `node --test src/salus/viewer/interface/tests/*.js` passes.
  8. Defect register records D-479, D-480, D-481 (open → resolved with commit hash).

**I-12: Modular PDF report architecture — protocol, orchestrator, and first migrated section**
- _Source:_ Enhancement — the current PDF generator (`src/salus/report/pdf.py`) is monolithic: `assemble_report_data()` builds all data and `render_pdf()` renders all 10 sections in one Jinja2 pass through `base.html`. To enable (a) per-customer curation of report contents, (b) a fast single-section dev loop in future tasks, and (c) eventual sharing of analysis code with the viewer, the report needs a formal module contract.
- _Goal:_ Add a `ReportModule` protocol, a `build_report` orchestrator, and one migrated section (`executive_summary`) as proof. No behaviour change to the existing pipeline — the new path runs alongside the old until subsequent I-tasks migrate the remaining 9 sections.
- _Architecture notes:_
  - **Protocol-first migration.** Each section becomes a `ReportModule` with a `ModuleManifest` (`id`, `title`, `placement` ∈ {"body","appendix"}, `page_break_before`, `landscape`, `optional`), an `is_applicable(sim) -> bool` predicate, and a `render(sim, ctx) -> RenderedSection` method.
  - **Self-contained sections in v1.** No module-to-module references; cross-section TOC/anchor support deferred.
  - **Orchestrator at `src/salus/report/builder.py`.** Takes `SimulationResults`, an ordered list of modules, and an output path. Calls `is_applicable` then `render` on each; concatenates HTML fragments; wraps in `base.html`; runs WeasyPrint once. Inapplicable modules are skipped with a logged info message.
  - **Existing code untouched.** `assemble_report_data()` and `render_pdf()` remain unchanged. CLI continues to use the old path. New code is purely additive.
  - **First migration target: `executive_summary`.** Smallest non-trivial section (prose + stats summary, no charts/maps). Reuses `generate_executive_summary()` and the `executive_summary.html` template — the module is a thin adapter that calls these and returns the rendered fragment.
- _Acceptance criteria:_
  1. `src/salus/report/modules/_base.py` defines `ModuleManifest` (frozen dataclass), `RenderedSection`, `RenderContext`, and `ReportModule` (runtime-checkable Protocol with `manifest`, `is_applicable`, and `render`).
  2. `src/salus/report/builder.py` defines `build_report(sim, modules, output_path, template_dir=None) -> Path` that constructs the `RenderContext`, calls `is_applicable` then `render` on each module in order, wraps the concatenated fragments in `base.html`, and runs WeasyPrint to produce a PDF. Inapplicable modules are skipped with `_log.info`. Returns the resolved `Path`.
  3. `src/salus/report/modules/executive_summary.py` defines `ExecutiveSummaryModule` implementing `ReportModule`. `manifest` has `id="executive_summary"`, `title="Executive Summary"`, `placement="body"`, `page_break_before=True`, `landscape=False`, `optional=True`. `is_applicable` returns `True` whenever `sim.stats` is present. `render` invokes `generate_executive_summary()` and renders the existing `executive_summary.html` template with the same variables the legacy path provides.
  4. `build_report(sim, [ExecutiveSummaryModule()], output_path)` produces a valid single-section PDF (non-zero bytes, opens cleanly, contains the executive-summary heading).
  5. Existing `assemble_report_data()` and `render_pdf()` are untouched. All existing tests in `tests/test_report_pdf.py` pass without modification.
  6. New unit tests in `tests/test_report_module_contract.py` cover: (a) `ExecutiveSummaryModule` conforms to the `ReportModule` Protocol via `isinstance(m, ReportModule)`; (b) `build_report` skips a module whose `is_applicable` returns False and still produces a valid PDF when at least one applicable module remains; (c) the HTML fragment produced by `ExecutiveSummaryModule.render` contains the same executive-summary text that `generate_executive_summary()` returns for a known fixture.
  7. The CLI (`src/salus/cli.py`) is not modified.
- _Out of scope (later I-tasks):_ standalone-render dev path, YAML profile loader, migration of the remaining 9 sections, refactoring `maps.py`/`charts.py`, any change to the existing single-pass `render_pdf` entry point.

**I-13: Hard-fail on boundary load failure in `report` and `viewer` commands**
- _Source:_ Triage (bug-hunt 2026-05-11, finding O-6 in `.forge/bug-triage-2026-05-11.md`) — when a scenario references a boundary file that becomes unreadable or has invalid geometry, the `simulate` command exits cleanly with `sys.exit(1)` per D-116, but the `report` (`cli.py:2148`) and `viewer` (`cli.py:2326`) commands print a one-line warning and silently fall back to `bitmask = np.ones((site.rows, site.cols), dtype=bool)` (full DEM). The coverage-stats denominator silently grows from the intended boundary area to the entire DEM — a scenario whose real coverage is 45% will be reported as 78% in the PDF/viewer with no operator-visible signal that anything went wrong. For a defence-proposal output this is the textbook "looks complete, isn't" failure mode.
- _Root cause:_ The two `except Exception` blocks below an inner `try` that wraps `load_boundary` + `boundary_mask` only emit a click.echo warning and continue with the full-DEM fallback. The simulate command's analogous block (`cli.py:534`) correctly mirrors the D-116 policy by exiting non-zero, but the report and viewer commands were never aligned.
- _Fix:_ Replace the silent-fallback `except` blocks in the `report` (line 2148-2154) and `viewer` (line 2326-2329) commands with the same pattern simulate already uses: `click.echo(f"Error loading boundary: {exc}", err=True); sys.exit(1)`. Successful boundary loads are unchanged; scenarios that have no `boundary_path` continue to use the full-DEM bitmask (this is the documented intent in that case, not a fallback).
- _Acceptance criteria:_
  1. Invoking `salus report` with a scenario whose `boundary_path` points to a non-existent file exits with non-zero status and writes `Error loading boundary: ...` to stderr; no `Coverage:` summary line is printed.
  2. Invoking `salus viewer` with the same input behaves identically (non-zero exit, error on stderr, no viewer package written).
  3. Invoking either command with a scenario that has no `boundary_path` continues to succeed and uses the full-DEM bitmask (documented intent in that case).
  4. Existing `salus simulate` behaviour is unchanged (already mirrors D-116).
  5. New tests in `tests/test_cli.py` cover the three paths above for both `report` and `viewer`.
  6. `pytest tests/` passes.
  7. Defect register records D-482, D-483 (open → resolved with commit hash).

**I-14: Refuse non-localhost binds by default and bound /api/simulate + /api/optimise concurrency**
- _Source:_ Triage (bug-hunt 2026-05-11, findings O-7 + O-10 in `.forge/bug-triage-2026-05-11.md`) — the interface API declares itself as a localhost-only service with no authentication, but `salus interface --host 0.0.0.0` is accepted with no warning. Combined with `/api/simulate` (and `/api/optimise`) spawning `threading.Thread(daemon=True)` per request with no pool or semaphore, any peer reachable on the network can OOM-kill the process with a handful of concurrent requests. The two issues are coupled: the DoS surface only matters once the bind address makes the API reachable beyond the operator's machine.
- _Root cause:_ The `salus interface` command's `--host` option (`cli.py:2398-2403`) treats any string as a valid bind address. `/api/simulate` (`app.py:1137-1142`) and `/api/optimise` (`app.py:1162-1167`) start an unbounded number of background threads — one per HTTP request — with no shared semaphore or worker pool. Both endpoints carry out GB-scale NumPy work; ten concurrent requests are sufficient to exhaust memory.
- _Fix:_
  1. Add an explicit `--allow-public` flag to the `interface` command. With the flag absent, refuse any bind address that is not in the loopback set (`127.0.0.1`, `::1`, `localhost`) — print a one-line error to stderr explaining that `--allow-public` is required for non-localhost binds and `sys.exit(1)`. With the flag present and a non-localhost bind, print a multi-line warning block to stderr listing the unauthenticated attack surface (no auth, 500 MB uploads accepted, GB-scale compute trivially triggered) before invoking `uvicorn.run`. Loopback binds with or without the flag are unchanged.
  2. Introduce a module-level `threading.BoundedSemaphore` in `interface_api/app.py` shared by `/api/simulate` and `/api/optimise`. Default capacity is 2; override via the `SALUS_MAX_CONCURRENT_SIMULATIONS` environment variable (positive integer; invalid values fall back to the default with a warning). Each handler attempts a non-blocking `acquire`; on failure it raises `HTTPException(status_code=503, detail="Server at capacity, retry later.")` with a `Retry-After: 5` header. The worker thread releases the slot in a `finally` block so a crashed worker does not permanently consume a slot. Path-traversal validation continues to run before the semaphore acquire.
- _Acceptance criteria:_
  1. `salus interface --host 0.0.0.0` (no `--allow-public`) exits non-zero and writes a clear error to stderr; uvicorn is never invoked.
  2. `salus interface --host 192.168.1.10 --allow-public` invokes `uvicorn.run(host="192.168.1.10")` and writes a multi-line warning containing the strings "no authentication", "500 MB", and "GB-scale" to stderr before starting.
  3. `salus interface --host 127.0.0.1`, `--host ::1`, `--host localhost`, and the default (no `--host`) all start without an error or warning, with or without `--allow-public`.
  4. `POST /api/simulate` returns 503 with a `Retry-After` header when the bounded semaphore is already saturated; the response body's `detail` mentions capacity.
  5. `POST /api/optimise` returns 503 under the same saturation condition, sharing the same semaphore as `/api/simulate`.
  6. A simulate worker that raises during pipeline execution still releases its semaphore slot — a subsequent request when no other work is in flight is accepted (no permanent leak).
  7. `SALUS_MAX_CONCURRENT_SIMULATIONS=1` reduces the cap to one; invalid values (`0`, `"abc"`, negative) fall back to the default and log a warning.
  8. Existing `/api/simulate` and `/api/optimise` happy-path tests pass unchanged when the cap is at its default and only one request is in flight.
  9. Defect register records D-497 and D-500 (open → resolved with commit hash).
- _Out of scope:_ token / shared-secret authentication, full TLS termination, rate limiting beyond the concurrency cap, applying the cap to terrain tile generation (different memory profile — handled separately if needed), changes to CORS policy.

**I-15: Viewer trust-boundary fixes — sanitiser redacts proprietary library + scenario-load deep validation**
- _Source:_ Triage (bug-triage 2026-05-11, findings O-8 + O-9). Group 5 — both findings are the same "trust boundary" policy question for the viewer, addressed together.
- _O-8 (D-498):_ `sanitise_for_export()` does not touch the `sensor_library`/`effector_library` payloads loaded by `package_viewer` from the full sensor YAML (including `max_range_m`, vendor `name`, `cost_aud`, `frequency_bands`). A REDACTED customer-delivered standalone viewer ships the full proprietary sensor DB. `_range_band` and `_RANGE_BANDS` exist but no caller invokes the helper.
- _O-9 (D-499):_ `validateScenarioPayload` only checks that JSON top-level keys are a subset of `SCENARIO_KEYS` then writes every value into state. A crafted `.salus.json` with HTML/JS payload in any string field (sensor name, threat name, terrain path) reaches downstream renderers — the Load Scenario path bypasses the fetch trust boundary that CSP/CORS guards.
- _Fix policy (decided here):_
  1. **D-498:** Move sensor/effector library loading into `export_viewer_data()` so libraries become part of `ViewerData` — a single trust boundary that the sanitiser controls. `sanitise_for_export()` redacts the libraries per level: MINIMAL preserves them; REDACTED retains only a public-fields whitelist (`type`, `azimuth_coverage_deg`, `elevation_coverage_deg`, `requires_los`) and replaces `max_range_m` with a `range_band` label produced via the (now-callable) `_range_band` helper; FULL clears both libraries to `{}`. The entry's `name` is replaced with `f"{type}-{i}"`. `package_viewer()` reads the libraries from `ViewerData` instead of re-loading from disk, so no proprietary data can re-enter the pipeline after sanitisation.
  2. **D-499:** `validateScenarioPayload` performs deep structural validation: reject non-plain-object roots; reject keys not in `SCENARIO_KEYS`; recursively walk values and accept only plain JSON primitives (null/boolean/number/string) and plain arrays/objects; reject `__proto__`/`constructor`/`prototype` keys at any depth; cap max recursion depth (32) and per-string length (100_000 chars); reject any string containing an HTML-opener pattern (`<` followed by `[!?/A-Za-z]`) or a `javascript:` URI as defence-in-depth against XSS in downstream renderers.
- _Acceptance criteria:_
  1. `ViewerData` carries `sensor_library` and `effector_library` fields (`default_factory=dict`); `export_viewer_data()` populates them via `_load_sensor_library`; `package_viewer()` reads them from `ViewerData` (no disk reload at packaging time).
  2. `sanitise_for_export()` at MINIMAL leaves libraries unchanged.
  3. `sanitise_for_export()` at REDACTED produces library entries containing only the public-fields whitelist plus `name = f"{type}-{i}"` and `range_band` (banded from `max_range_m`); no vendor `name`, `cost_aud`, `frequency_bands`, `mounting_height_m`, `vegetation_penetration`, `min_range_m`, `elevation_boresight_deg`, or notes remain.
  4. `sanitise_for_export()` at FULL clears both libraries to `{}`.
  5. `sanitise_for_export()` does not mutate the input `ViewerData` (deep-copy invariant preserved for the library fields).
  6. End-to-end: a viewer packaged with REDACTED level has no `max_range_m`, vendor `name`, or `cost_aud` strings anywhere in `viewer_data.js`.
  7. `validateScenarioPayload({ __proto__: {} })` returns `false`; same for `constructor`/`prototype` keys at any depth.
  8. `validateScenarioPayload({ placements: [{ sensor_name: "<script>alert(1)</script>" }] })` returns `false`.
  9. `validateScenarioPayload({ placements: [{ url: "javascript:alert(1)" }] })` returns `false`.
  10. `validateScenarioPayload` with a string exceeding 100_000 chars returns `false`.
  11. `validateScenarioPayload` with object nesting depth > 32 returns `false`.
  12. All existing `validateScenarioPayload` and `applyScenarioPayload` tests in `test-shell.js` continue to pass (no regressions for safe payloads).
  13. `pytest tests/` passes. `node --test src/salus/viewer/interface/tests/test-shell.js` passes.
  14. Defect register records D-498 and D-499 (open → resolved with commit hash).
- _Out of scope:_ Resolving D-551 (`_range_band` NaN fall-through) — callers guard `max_range_m` validity before invoking `_range_band`, so the helper's NaN behaviour is moot in I-15; D-551 remains open for a separate fix. Resolving O-7/O-10 (covered by I-14). Per-key JSON-schema (Pydantic-style) validation in JS — the structural + denylist approach is sufficient defence-in-depth without dragging a JSON-schema library into the bundle.

**I-16: PDF report section-criticality policy — hard-fail required sections, audit-log optional failures**
- _Source:_ Triage (bug-triage 2026-05-11, findings O-5 + O-12). Group 3 — both findings share the same root cause (`except Exception → log warning → return None` in `report/pdf.py` for both map/chart helpers and the Jinja template loop), and the same fix policy (section criticality + a programmatic failure channel).
- _O-5 (D-496):_ `_render_to_b64`, `_render_gap_map_to_b64`, `_render_kill_chain_chart_to_b64`, and `_render_saturation_chart_to_b64` all wrap rendering in `except Exception → log warning → return None`. The composite map, gap map, per-layer maps, kill-chain chart, and saturation chart can each fail silently — the PDF is then produced with the missing image gated out by the templates' `{% if report.X_b64 %}` guards, and `render_pdf` returns a `Path` to a clean-looking-but-incomplete PDF. For a defence-proposal artefact this is the textbook "looks complete, isn't" failure mode.
- _O-12 (D-502):_ The `render_pdf` Jinja loop catches `TemplateError` and `TemplateNotFound` with a warning log and drops the section. The PDF still renders, missing kill_chain / saturation / threat_analysis (or any future section) depending on which template broke. Caller has no programmatic signal.
- _Fix policy (decided here — section criticality):_
  1. **REQUIRED sections** (structural, every PDF must include them) — `cover`, `executive_summary`, `site_overview`, `coverage_analysis`, `gap_analysis`, `assumptions`, `appendix_sensors`. Failure of the section's template (`TemplateError`, `TemplateNotFound`) OR failure of its mandatory map asset (composite_map for site_overview, gap_map for gap_analysis) → raise a new `ReportRenderError(RuntimeError)`. No half-baked PDF is produced.
  2. **OPTIONAL sections** (data-gated, only present when the upstream analysis ran) — `threat_analysis`, `kill_chain`, `saturation`. Failure of the section's template or its chart asset → append a one-line failure description to `ReportData.section_failures: list[str]`, omit the section from the PDF, and let `render_pdf` return its `Path` normally. The chart's `..._b64` field is set to `None`.
  3. **Optional assets in required sections** — per-layer coverage maps in `coverage_analysis.layer_maps_b64`. Failure of an individual layer map → append to `section_failures` with the layer name, skip that layer; the surrounding `coverage_analysis` section still renders with its tables and any layer maps that did render.
  4. **Programmatic signal** — `ReportData` gains `section_failures: list[str] = field(default_factory=list)`. The `salus report` CLI command checks `report_data.section_failures` after `render_pdf` returns and emits a multi-line warning block to stderr listing each omitted/degraded section. The `POST /api/report` handler logs each entry as a `_log.warning(...)` (the binary PDF body cannot carry structured warnings; the operator audit-trails them in the application log).
- _Acceptance criteria:_
  1. `ReportRenderError(RuntimeError)` is defined in `src/salus/report/pdf.py` and exported via the module's public namespace.
  2. `ReportData.section_failures: list[str]` field is added with `field(default_factory=list)`. Default behaviour for a successful render: empty list.
  3. `_render_to_b64` and `_render_gap_map_to_b64` return type changes from `str | None` to `str`. Any exception during the inner render raises `ReportRenderError` from the original exception (chained with `from`); the temp file is still cleaned up in the `finally` block.
  4. `_render_kill_chain_chart_to_b64` and `_render_saturation_chart_to_b64` keep `str | None` return type. `None` is returned **only** when the upstream inputs are unavailable (no `kill_chain_results` / no `saturation_result`) — the legitimate "no chart applicable" case. On actual render failure they append a `"<section>: <reason>"` entry to a new `section_failures: list[str]` argument and return `None`; the caller (`assemble_report_data`) propagates the list into `ReportData.section_failures`.
  5. Per-layer map rendering in `assemble_report_data` catches individual layer failures, appends `"coverage_analysis.<layer_name>: <reason>"` to `section_failures`, and skips that layer in `layer_maps_b64`. The composite map failure still raises.
  6. `render_pdf` template loop: for sections in the REQUIRED set, `TemplateError` and `TemplateNotFound` raise `ReportRenderError`. For sections in the OPTIONAL set, both exceptions append `"<section>: <reason>"` to `report_data.section_failures` and skip the section.
  7. `render_pdf` builds `section_names` so that optional sections are only attempted when (a) their gating data is present AND (b) their chart asset rendered successfully (or the section is text-only, e.g., `threat_analysis`). A section already known to have failed (`section_failures` populated by `assemble_report_data`) is dropped.
  8. The `salus report` CLI catches `ReportRenderError` separately from generic `Exception`, writes `Error rendering PDF: <reason>` to stderr, and exits non-zero. On success, if `report_data.section_failures` is non-empty, it writes a multi-line block to stderr beginning `Warning: PDF rendered with degraded sections:` followed by one bullet per failure. Exit status is 0 in that case (the PDF is still useful) — but the operator sees the audit trail.
  9. `POST /api/report` calls `_log.warning("report request: section %s omitted — %s", ...)` for each entry in `section_failures`. The response body remains the PDF stream.
  10. New tests in `tests/test_report_pdf.py`:
      - `test_required_map_failure_raises`: monkeypatch `render_composite_coverage_map` to raise → `assemble_report_data` raises `ReportRenderError`.
      - `test_gap_map_failure_raises`: monkeypatch `render_gap_map` to raise → `assemble_report_data` raises `ReportRenderError`.
      - `test_optional_chart_failure_records`: monkeypatch `render_kill_chain_chart` to raise → `assemble_report_data` returns `ReportData` with `kill_chain_chart_b64 is None`, `section_failures` non-empty, and a `kill_chain` entry.
      - `test_per_layer_failure_records_and_continues`: monkeypatch the layer-map render to raise for one layer → `assemble_report_data` succeeds, `section_failures` lists the layer, other layers render normally.
      - `test_required_template_error_raises`: write a `tmp_path / "cover.html"` with a Jinja syntax error and pass it as `template_dir` (with all other templates symlinked / copied) → `render_pdf` raises `ReportRenderError`.
      - `test_optional_template_not_found_records`: pass a `template_dir` with `kill_chain.html` missing while `kill_chain_results` is present → `render_pdf` returns Path, `report_data.section_failures` lists `kill_chain`.
      - `test_section_failures_default_empty`: a clean render produces `section_failures == []`.
  11. Existing tests in `tests/test_report_pdf.py` continue to pass without modification.
  12. `pytest tests/` passes.
  13. Defect register records D-496 and D-502 (open → resolved with commit hash).
- _Out of scope:_ Migrating sections to the modular contract from I-12 (already in progress as a separate effort) — this fix lives entirely in the legacy single-pass `assemble_report_data` / `render_pdf` path. Per-section "render with red stamp" alternative (rejected; omit-and-audit is simpler and matches the operator-visible CLI warning). Restructuring `interface_api/app.py::report_pdf` to construct `ReportData` from JSON dict — that path bypasses `assemble_report_data` and therefore cannot exercise the new policy; logging on `section_failures` is still wired so any callers that *do* go through the policy path are audited.

**I-17: Canopy attenuation overhaul — 3D LOS attenuation, occluder-bounded rays, honest perimeter and observer cells**
- _Source:_ Triage (bug-triage 2026-05-11, findings O-3 + O-4 + O-15 + O-16, all in `compute_viewshed_through_canopy`). The four findings are coupled — they all stem from the original 2D ray-march accumulating a single `t_ray` scalar along integer-rounded ray paths — and the triage notes explicitly call for handling them as one canopy-attenuation overhaul rather than four separate patches.
- _O-3 (D-494):_ `transmission` was initialised to zeros and only updated for cells a rounded ray stepped through. Cells the binary viewshed marks visible but that fall between integer-rounded ray paths (typically the perimeter) silently stayed `0.0` — indistinguishable from terrain-blocked — so coverage layers shrank at the perimeter without warning.
- _O-4 (D-495):_ When a ray hit a terrain-blocked cell the old code did `continue` without resetting the running `t_ray`, so a visible cell beyond the occluder received a transmission value contaminated by canopy along a geometrically irrelevant path.
- _O-15 (D-505):_ The observer's own cell transmission was forced to `1.0` unconditionally, concealing the misconfiguration where the sensor is physically buried under canopy (`canopy_height_m[obs] > observer_height`).
- _O-16 (D-506):_ Attenuation was applied for every visible canopy cell regardless of where the 3D line-of-sight ray passed vertically through the cell — a ray skimming the canopy top and a trunk-piercing ray got identical penalty.
- _Fix policy (decided here):_
  1. **D-494 — honest perimeter:** Initialise `transmission = binary.astype(np.float32)` so visible cells start at `1.0` and non-visible at `0.0`. Visible cells that no discrete ray happens to land on retain the `1.0` baseline rather than dropping to fully-blocked. Track ray-touched cells in a separate boolean mask and apply `max`-over-rays results only to touched cells.
  2. **D-495 — occluder-bounded rays:** Walk each ray only up to (not past) the first cell that is not visible in the binary viewshed; stop the ray there. Cells beyond an occluder are reached by other ray angles whose 2D paths do not cross the blocker. Per-target attenuation accumulators are computed per target cell from the ray segment in front of it, never carried across an occluder.
  3. **D-506 — 3D LOS attenuation:** For each visible target cell `k` on a ray, interpolate the LOS elevation linearly from the observer (`obs_z = dem[obs] + observer_height`) to the target surface elevation (`site.surface_array()`). For each cell `j` between the observer and `k`, apply the canopy penalty `penetration ** (canopy_height_m[j] / _CANOPY_REFERENCE_HEIGHT_M)` only when the interpolated `los_z` at `j` falls below the canopy top (`dem[j] + canopy_height_m[j]`). A ray skimming above the canopy receives no penalty.
  4. **D-505 — honest observer cell:** When the observer is at/above the canopy top at its own cell, or there is no canopy there, transmission is `1.0`. When the observer is below the canopy top, the on-cell value reflects the canopy depth above the sensor: `penetration ** ((canopy_height_m[obs] - observer_height) / _CANOPY_REFERENCE_HEIGHT_M)`.
  5. **NaN / negative CHM** retain the existing conservative-open policy: NaN canopy cells (nodata) and clamped-negative values contribute no attenuation.
- _Acceptance criteria:_
  1. `transmission` is initialised from the binary viewshed (`binary.astype(np.float32)`); a visible cell that no ray reaches keeps `1.0`, never `0.0`.
  2. A visible cell beyond a terrain occluder never receives canopy attenuation accumulated from cells on the far side of the occluder; rays stop at the first non-visible cell.
  3. Canopy attenuation at intermediate cell `j` is applied only when the interpolated LOS elevation at `j` is below `dem[j] + canopy_height_m[j]`; a target reached by a ray that stays above all canopy along its path has transmission `1.0`.
  4. The observer cell transmission is `1.0` when `observer_height >= canopy_height_m[obs]` (or the obs-cell CHM is NaN / ≤ 0); otherwise it equals `penetration ** ((canopy_height_m[obs] - observer_height) / _CANOPY_REFERENCE_HEIGHT_M)` and is strictly `< 1.0`.
  5. NaN and negative canopy cells contribute no attenuation (existing D-245 / D-247 policy preserved).
  6. All returned transmission values remain float32 in `[0.0, 1.0]`; non-visible cells stay `0.0`.
  7. When `site.canopy_height_m is None` or `vegetation_penetration == 0.0`, the function still short-circuits to the binary viewshed cast to float32 (unchanged).
  8. `pytest tests/test_canopy.py` passes, including new tests for perimeter cells (D-494), occluder isolation (D-495), observer-under-canopy (D-505), and above-canopy skimming rays (D-506).
  9. `pytest tests/` passes with no regressions in dependent coverage / report tests.
  10. Defect register records D-494, D-495, D-505, D-506 (open → resolved with commit hash).
- _Out of scope:_ Replacing the angular ray-march with an exact LOS rasterisation (Bresenham / supercover) — the integer-rounded ray sampling is retained; D-494's baseline-`1.0` policy is the agreed mitigation for cells it misses. Vertical sub-cell modelling of canopy density profiles (uniform-column canopy assumption retained). Per-frequency-band canopy penetration (single `vegetation_penetration` scalar retained).

---

**I-18: Terrain canvas persists across module navigation — terrain-loader stops tearing down the permanent 3D canvas on unmount**
- _Source:_ User-reported viewer bug (2026-05-16): the rendered terrain disappears whenever a non-map module panel (e.g. the Sensor/Effector Library Browser) is opened. Logged as D-592.
- _Diagnosis:_ `mode-manager.activateModule` runs the outgoing module's `runUnmount()` before mounting the incoming module. `terrain-loader`'s `onUnmount` calls `_cleanupMapLayers(api)`, which removes the `terrain-loader:terrain-dem` raster-dem source, removes the `terrain-loader:hillshade` layer, and clears the 3D terrain via `setTerrainSource(null)`. Navigating from terrain-loader to any other module therefore destroys the terrain rendering; modules with no map output (library-browser, budget-tracker, report-configurator, …) never restore it, so the canvas stays blank until the user navigates back to terrain-loader and `init()` re-adds the layers.
- _Conflict:_ This directly violates InterfaceArchitecture.md §1 principle 3 ("The 3D terrain canvas is permanent"). The terrain source / hillshade layer / 3D terrain are the shared base canvas every other module renders on top of — they are not module-private decoration and must outlive a terrain-loader unmount. The blanket "clean up all map layers in onUnmount" rule (Interface Module Standard §15) does not apply to the permanent base canvas.
- _Fix policy (decided here):_
  1. Remove the `_cleanupMapLayers(api)` call from terrain-loader's `onUnmount`. onUnmount still tears down its panel-scoped resources: the DEM-input `change` listener, the `terrain` `watch()` subscription, and the in-flight adopt-fetch cancellation flag.
  2. The `_cleanupMapLayers` helper is retained — it is still called inside `_applyMapLayers` so a *new* terrain load (or first session adoption) replaces any prior canvas idempotently.
  3. In `init()`'s pre-loaded-terrain branch, only call `_applyMapLayers` when the terrain source is not already on the map (`api.map.getSource(SOURCE_ID)` is null). On a re-mount the permanent canvas is already present, so re-adding it is skipped — avoiding a remove/re-add flicker of the base layer.
- _Acceptance criteria:_
  1. After `terrain-loader` `init()` runs with terrain present, firing all `onUnmount` callbacks leaves the `terrain-loader:terrain-dem` source and `terrain-loader:hillshade` layer on the map — `removeSource` / `removeLayer` are not called.
  2. `onUnmount` does not call `setTerrainSource(null)`; the 3D terrain canvas stays bound after navigation away from terrain-loader.
  3. `onUnmount` still unsubscribes the `terrain` watch and removes the DEM-input `change` listener (no leaked subscriptions or listeners).
  4. Re-running `init()` after an unmount, with the terrain source already present, does not call `addSource` / `addLayer` again — the permanent canvas is reused, not rebuilt.
  5. A first `init()` with pre-loaded terrain and no existing source still adds the source, hillshade layer, and 3D terrain exactly as before.
  6. A new terrain upload (`_loadTerrain`) and first session adoption (`_adoptLatestSessionIfAvailable`) still replace the canvas via `_applyMapLayers` (unchanged behaviour).
  7. `node --test src/salus/viewer/interface/tests/test-terrain-loader.js` passes; the two obsolete onUnmount-teardown tests are replaced by persistence assertions, and a re-mount idempotence test is added.
  8. Defect register records D-592 (open → resolved with commit hash).
- _Out of scope:_ Promoting the terrain source/layers to shell-owned state — terrain-loader remains the sole creator of the canvas. Reworking the `removeSource`-before-`setTerrainSource(null)` ordering inside `_cleanupMapLayers` (the helper is no longer on the unmount path; its upload-replace use is unaffected). Changes to any other module.

---

**I-19: Terrain-loader SSE client consumes named events; in-flight tile-progress stream closed on unmount**
- _Source:_ User-reported viewer bug (2026-05-18): loading a DEM through the terrain-loader file input fails with "Error: SSE connection error during tile generation" even though server-side tile generation succeeds (tiles written to disk, session registered). Logged as D-595. This task also resolves the deferred D-594 (the pre-existing `_pollTileProgress` EventSource leak on unmount).
- _Diagnosis (D-595):_ The backend SSE formatter `_sse_event` (`interface_api/app.py`) emits every terrain-tile-progress event with a named `event:` line (`event: progress` / `event: complete` / `event: error`) — a deliberate D-404 change so `simulation-runner` / `optimiser` can dispatch by event type. `terrain-loader`'s `_pollTileProgress` consumes the stream with `EventSource.onmessage`, which by the SSE specification fires *only* for unnamed (`message`) events. Every progress / complete / error event is therefore silently missed; the stream then closes normally and `EventSource.onerror` fires, rejecting the load with a false "SSE connection error during tile generation". Server-side generation has in fact completed and the session is valid (`/api/terrain/sessions/latest` returns it) — the only working path today is a browser reload, which adopts the latest session and bypasses the poll entirely.
- _Diagnosis (D-594):_ `_pollTileProgress` creates an `EventSource` but `onUnmount` holds no handle to it. Navigating away mid-tile-generation leaves the SSE connection open, and its handlers continue to mutate DOM nodes of an unmounted panel.
- _Fix policy (decided here):_
  1. Replace the `es.onmessage` handler in `_pollTileProgress` with `es.addEventListener('progress' | 'complete' | 'error', …)` so the named events the backend emits are actually received. The JSON-payload contract (`data.pct`, `data.message`) is unchanged.
  2. The `'error'` listener must distinguish a server-sent SSE `error` *message* (a `MessageEvent` carrying a JSON `event.data` payload — reject with `data.message`) from a transport-level `EventSource` failure (a plain `Event` with no `data` — reject with the generic "SSE connection error during tile generation").
  3. Thread a shared mutable SSE context (`{ es: null }`) from `init()` through `_loadTerrain` into `_pollTileProgress`; the `EventSource` is stored on it when opened and cleared when it closes. `onUnmount` closes any still-open `EventSource` via that context (D-594).
  4. No server-side change — `_sse_event`'s `event:` line is the correct shared SSE contract; only the terrain-loader client is out of step with it.
- _Acceptance criteria:_
  1. `_pollTileProgress` registers listeners for the `progress`, `complete` and `error` SSE event types (not `onmessage`); a `progress` event updates the progress bar and status text; a `complete` event resolves the promise and closes the stream.
  2. A server-sent `error` event (a message carrying a JSON `data` payload) rejects the load with that payload's `message`.
  3. A transport-level `EventSource` failure (an error event with no `data`) rejects with "SSE connection error during tile generation".
  4. A successful `complete` no longer produces a spurious rejection — a normal DEM upload via the file input resolves, writes `terrain` state, emits `terrain:loaded`, and applies the map layers.
  5. `onUnmount` closes an in-flight tile-progress `EventSource` when one is open; after unmount no SSE handler mutates the panel (D-594).
  6. `onUnmount` still removes the DEM-input `change` listener, unsubscribes the `terrain` watch, and preserves the permanent terrain canvas (I-18 behaviour unchanged).
  7. `node --test src/salus/viewer/interface/tests/test-terrain-loader.js` passes; the `MockEventSource` gains `addEventListener` plus named-event emit support; tests cover progress / complete / error dispatch and the unmount-closes-EventSource path.
  8. Defect register records D-595 (open → resolved) and D-594 (deferred → resolved), each with commit hash.
- _Out of scope:_ Changing `_sse_event` or any backend SSE endpoint. Migrating terrain-loader off `EventSource` onto the fetch-reader SSE parser `simulation-runner` uses. Changes to any other module.

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
| 11.5 | Bearing-Aware Placement Optimisation | 3 | 72 |
| 12 | LiDAR Ingestion | 4 | 76 |
| 12.5 | Vegetation and Canopy Layer | 5 | 81 |
| 13 | PDF Report Generation | 7 | 88 |
| 14 | Interactive Standalone Viewer | 6 | 94 |
| 14.1 | Interface Shell and Module Infrastructure | 6 | 100 |
| 14.2 | FastAPI Backend API Layer | 5 | 105 |
| 14.3 | Terrain Loader Module | 3 | 108 |
| 14.4 | Library Browser Module | 3 | 111 |
| 14.5 | Placement Editor Module | 5 | 116 |
| 14.6 | Budget Tracker Module | 3 | 119 |
| 14.7 | Threat Corridor + Zone Editors | 5 | 124 |
| 14.8 | Simulation Runner Module | 4 | 128 |
| 14.9 | Coverage Viewer + Gap Analysis | 5 | 133 |
| 14.10 | Kill Chain + Saturation Analysers | 4 | 137 |
| 14.11 | Optimiser Module | 4 | 141 |
| 14.12 | Scenario Comparison Module | 3 | 144 |
| 14.13 | Report Configurator Module | 3 | 147 |
| 14.14 | Scenario Persistence + Deployment | 4 | 151 |
| 15 | Populate Full Sensor/Effector/Threat DB | 4 | 155 |
| 16 | CLI Polish + End-to-End Workflow | 5 | 160 |
| 17 | Docker, Testing, CI Readiness | 5 | 165 |

**Total: 165 tasks across 38 slices (including Slice 0). Slices 14.1–14.14 are the interface application phase.**

---

## Dependency Notes

- **Slices 1-5 are strictly sequential** — each builds on the previous.
- **Slices 6 → 6.1 → 6.2 → 6.3 → 6.4 → 6.5 → 6.6 are sequential** — each sub-slice depends on the previous. Slice 6 (2D corridors) is a prerequisite for 6.1 because 6.3 refactors `find_worst_corridors` to delegate to the new trajectory engine. Slice 6.6 depends on 6.1 (`sensor_can_detect_point`) and 6.3 (`analyse_trajectory`) but not on 6.4 or 6.5 — those are parallel outputs of 6.3.
- **Slice 7 (kill chain) depends on Slice 6.3** — it consumes `TrajectoryResult.first_detection` and `DetectionEvent` instead of `CorridorResult.first_detection_distance_m`. Slices 8-11 depend on Slice 5 and can be done in any order relative to each other, but 7 must precede them in the kill chain pipeline.
- **Slices 9-11 (placement, comparison, effectors)** depend on Slice 5 and can be done in any order.
- **Slice 12 (LiDAR)** is independent of Slices 6-11 — it only depends on Slice 1 (SiteModel). It is placed late because GeoTIFF import is sufficient for development and LiDAR adds PDAL complexity. Move it earlier if real LiDAR data arrives.

**Interface Application (Slices 14.1–14.14):**
- **14.1 (Shell)** is a strict prerequisite for all 14.x slices. Build this first; nothing else can be tested without it.
- **14.2 (FastAPI)** can proceed in parallel with 14.3–14.6 but is a hard prerequisite for 14.8 (Simulation Runner), 14.11 (Optimiser), and 14.13 (Report Configurator). Library browser endpoints (14.2-2) are needed before 14.4 works end-to-end.
- **14.3 (Terrain Loader)** must precede 14.5 (Placement Editor), 14.7 (corridor + zone editors), 14.8 (simulation runner), and all analysis modules, since `terrain` is a prerequisite for those modules.
- **14.4 (Library Browser)** can be done in parallel with 14.3. It emits `placement:pending` which 14.5 consumes — both must exist before that cross-module flow can be tested.
- **14.5 (Placement Editor)** depends on 14.3 (terrain) and 14.4 (library browser for drag-drop).
- **14.6 (Budget Tracker)** depends only on 14.1 (shell). Can be built any time after the shell exists.
- **14.7 (corridor + zone editors)** depend on 14.3 (terrain prerequisite). Build after 14.3.
- **14.8 (Simulation Runner)** depends on 14.2 (API), 14.3 (terrain), 14.5 (placements). This slice and everything after it requires all preceding modules to be functional.
- **14.9 (Coverage Viewer + Gap Analysis)** depends on 14.8 (sim_results). The gap analysis emits `placement:pending`, so it also depends on 14.5 to close that loop.
- **14.10 (Kill Chain + Saturation)** depends on 14.8. Can be built in parallel with 14.9.
- **14.11 (Optimiser)** depends on 14.2 (API), 14.7 (zones), 14.6 (constraints). Emits `optimiser:complete` consumed by 14.5.
- **14.12 (Scenario Comparison)** depends on 14.8 (sim_results). Requires `POST /api/compare` added in 14.12-2 (can add to FastAPI in 14.2 sprint or in 14.12 itself).
- **14.13 (Report Configurator)** depends on 14.2 (API `/api/report`) and 14.8 (sim_results).
- **14.14 (Persistence + Deployment)** should be last — it validates the complete system and exercises all modules in integration.
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