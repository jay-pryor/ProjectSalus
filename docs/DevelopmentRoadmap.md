# cUAS Simulation Tool — Development Roadmap

---

## MVP — Version 1.0

### Goal
A CLI pipeline that ingests site terrain data and sensor/effector configurations, runs layered coverage analysis with sensor-type-appropriate detection models, and outputs a professional PDF report suitable for inclusion in a defence proposal.

---

### MVP Scope

#### Data Ingestion
- [ ] LiDAR point cloud ingestion (LAS/LAZ)
- [ ] Point cloud → DEM (ground elevation) conversion
- [ ] Point cloud → DSM (surface elevation incl. structures/vegetation) conversion
- [ ] Pre-processed DEM/DSM import (GeoTIFF) as alternative to raw LiDAR
- [ ] CRS normalisation (GDA2020 / MGA zones)
- [ ] GeoJSON site boundary import
- [ ] Zone definition (perimeter, inner, critical assets, exclusion)

#### Sensor & Effector Database
- [ ] YAML/JSON-based sensor definitions
- [ ] YAML/JSON-based effector definitions
- [ ] Sensor fields: type, range, arc, elevation coverage, mounting height, LOS requirement, frequency bands
- [ ] Effector fields: type, range, arc, reaction time, defeat mechanism, LOS requirement
- [ ] Initial database populated from public datasheets (DroneShield, Dedrone, HENSOLDT, Echodyne, EOS, SAAB, RTX, etc.)

#### Simulation Engine — Layered Coverage Model
- [ ] **Radar / EO/IR layer:** Viewshed-based detection (GDAL viewshed), clipped to sensor range + azimuth/elevation arc
- [ ] **RF detection layer:** Free-space path loss + single knife-edge diffraction (ITU-R P.526), detection threshold comparison against sensor sensitivity
- [ ] **Acoustic layer:** Simple range circle with configurable ambient noise penalty
- [ ] **Effector layer:** Viewshed-based engagement zones for kinetic/DE effectors, range-based for RF jammers
- [ ] Multi-sensor coverage union per layer
- [ ] Composite coverage map (any sensor detects)
- [ ] Gap identification (site area minus coverage)

#### Threat Trajectory Analysis
- [ ] Threat profile definitions (drone type, speed, altitude, RCS, RF signature)
- [ ] `line_of_sight_3d` — point-to-point LOS check in 3D space (sensor to target at arbitrary altitude)
- [ ] `elevation_boresight_deg` field on sensor definitions — centres the elevation arc for 3D detection gating
- [ ] `sensor_can_detect_point` — full 3D detection predicate (LOS + range + azimuth + elevation arc)
- [ ] `DroneTrajectory` model — ordered 3D waypoints at configurable speed; piecewise linear segments approximate curved paths
- [ ] `analyse_trajectory` — step along trajectory at configurable `segment_length_m`, binary search refinement at detection transitions for sub-metre / sub-second timing precision
- [ ] Planning sweep: `find_worst_trajectories` across bearing × start altitude × dive angle parameter space
- [ ] Engagement calc mode: specific-trajectory analysis returning exact `DetectionEvent` (time, position, sensor) per detection crossing
- [ ] `--segment-length` CLI flag — runtime fidelity control (e.g., 10 m for fast planning pass, 0.5 m for engagement calc)
- [ ] Trajectory visualisation: approach path map with detection event markers, polar diagram of detection exposure by bearing

#### Adversarial Path Planning
- [ ] `build_detection_cost_grid` — batch-apply `sensor_can_detect_point` across the full site volume at configurable altitude bands; produces a 3D numpy array of per-cell detection exposure counts
- [ ] `find_adversarial_trajectory` — Dijkstra's graph search over the 3D cost grid; finds the minimum-detection-exposure route from threat origin to protected asset, automatically exploiting terrain masking and sensor coverage gaps; returns a standard `DroneTrajectory` for downstream analysis
- [ ] `--adversarial` CLI flag on `salus simulate` — triggers adversarial path discovery per threat profile, feeds discovered trajectory into `analyse_trajectory`, renders path overlaid on coverage heatmap with detection event markers

#### Kill Chain Timeline Modelling
- [ ] Model engagement sequence: detect → track → identify → decide → engage → assess (D-T-I-D-E-A)
- [ ] Time budget per phase (sensor track latency, C2 decision time, effector reaction time)
- [ ] Engagement envelope — can the kill chain complete before the drone reaches the asset?
- [ ] Engagement margin calculation (available time minus required time)
- [ ] Second engagement opportunity check (is there time to re-engage if first attempt fails?)

#### Multi-Target Engagement & Saturation Analysis
- [ ] Simultaneous target scenarios (up to 20 targets for MVP)
- [ ] Per-target approach vector and altitude definition
- [ ] Effector allocation by priority (closest to asset first)
- [ ] Effector capacity tracking (simultaneous engagements, reload time)
- [ ] Saturation threshold calculation (N at which effectors are fully committed)
- [ ] Unengaged target count per scenario

#### Placement Optimisation (Greedy Heuristic)
- [ ] Candidate position evaluation across site grid
- [ ] Greedy placement — each sensor placed at position maximising uncovered area
- [ ] Iterative recalculation until all sensors placed or coverage target met

#### Configuration Comparison
- [ ] Run simulation for Config A and Config B
- [ ] Delta analysis — where does B cover that A doesn't?
- [ ] Side-by-side statistics comparison (coverage, engagement capacity, saturation threshold, cost)

#### Report Generation
- [ ] PDF output via WeasyPrint or LaTeX
- [ ] Site overview map with zone boundaries
- [ ] Per-layer coverage heat maps (radar, RF, EO/IR)
- [ ] Composite coverage map
- [ ] Gap analysis map with dead zones highlighted
- [ ] Threat corridor overlay
- [ ] Configuration comparison (if applicable)
- [ ] Coverage statistics (% area covered, gap area, redundancy)
- [ ] Assumptions & limitations section
- [ ] Sensor specifications appendix

---

## Post-MVP Enhancements

### Phase 2 — Simulation Fidelity

**RF Propagation Improvements**
- [ ] Multi-knife-edge diffraction (Deygout or Bullington method) for complex terrain with multiple ridgelines
- [ ] Ground reflection / multipath modelling
- [ ] Atmospheric absorption (frequency-dependent, relevant for mmWave radar and higher bands)
- [ ] Building penetration loss modelling (material-dependent attenuation)
- [ ] Vegetation attenuation modelling (ITU-R P.833 or similar, seasonal variation)
- [ ] Clutter modelling (ground clutter effects on radar performance)

**Parametric Uncertainty and Coverage Confidence Bands**
- [ ] `UncertaintyConfig` model formalising the plausible parameter ranges from `EstimationModels.md` (drone RCS, radar performance factor, RF sensitivity, mounting height)
- [ ] Monte Carlo sampler: N realisations sampling uncertain parameters, re-running the coverage engine each time
- [ ] P10/P50/P90 coverage and gap statistics — "coverage is 88–96% depending on parameter assumptions"
- [ ] Per-cell confidence map showing fraction of runs each cell was covered (highlights where coverage is robust vs. assumption-dependent)
- [ ] `--uncertainty` / `--n-runs` CLI flags; confidence map and histogram outputs

**Probabilistic Detection Modelling**
- [ ] Replace binary "detected / not detected" with probability of detection (Pd) curves
- [ ] Pd as a function of range, RCS, SNR, and environment
- [ ] Cumulative probability of detection along a threat corridor (probability of detection across multiple sensor exposures)
- [ ] False alarm rate modelling (Pfa) and its effect on operator workload
- [ ] Swerling target models for radar (RCS fluctuation)

**Sensor Fusion Modelling**
- [ ] Model sensor cueing (e.g. RF detection cues radar to search a specific bearing)
- [ ] Fused detection probability (combined Pd from multiple independent sensors)
- [ ] Track correlation — likelihood that detections from different sensors are recognised as the same target
- [ ] Classification confidence modelling (detect vs track vs identify)

**Environmental Effects**
- [ ] Weather degradation (rain attenuation for radar/EO, wind for acoustic)
- [ ] Time-of-day modelling (EO performance day vs night, IR performance thermal crossover)
- [ ] Seasonal vegetation changes (canopy density affecting LOS and RF propagation)
- [ ] Atmospheric ducting effects on radar

---

### Phase 3 — Advanced Analysis

**Placement Optimisation (Advanced)**
- [ ] Genetic algorithm or simulated annealing for near-optimal placement
- [ ] Constraint-aware placement (exclusion zones, power availability, mounting points)
- [ ] Budget-constrained optimisation — best coverage for $X budget
- [ ] Redundancy-aware optimisation — ensure N-sensor coverage of critical zones

**Swarm Threat Modelling (Advanced)**
- [ ] Coordinated swarm approach vectors (simultaneous multi-axis attack)
- [ ] Sequential engagement capacity over a sustained attack window (extended duration scenarios)
- [ ] Adaptive threat routing (drones reroute based on detected effector positions)
- [ ] Decoy / distraction modelling (low-value targets drawing effector attention)
- [ ] Swarm size scaling beyond MVP's 20-target cap

**Communications & Network Modelling**
- [ ] Can each sensor communicate back to the C2 node from its position?
- [ ] RF backhaul link budget (LOS, range, bandwidth)
- [ ] Network topology resilience — what happens if a comms node fails?
- [ ] Latency modelling (sensor-to-C2 delay impact on engagement timeline)

---

### Phase 4 — Tier 2: Hosted Simulation Platform

The web platform that enables Panel members to configure and run simulations themselves, via a hosted service. The simulation engine stays on our infrastructure — customers never receive the software.

**Web Application (FastAPI + Frontend)**
- [ ] FastAPI backend wrapping the simulation engine
- [ ] Browser-based UI for site boundary drawing and sensor placement
- [ ] Drag-and-drop sensor placement with real-time coverage preview
- [ ] Interactive 3D terrain visualisation (Cesium, Deck.gl, or Three.js)
- [ ] What-if configuration builder (select sensors from database, define threats, compare)
- [ ] Simulation job queue (Redis + Celery — simulations run server-side)
- [ ] Export: PDF report + standalone interactive viewer package (same outputs as Tier 1)

**Multi-Tenancy & Access Control**
- [ ] User authentication (per-customer accounts)
- [ ] Project/site management (multiple sites, multiple configurations per site)
- [ ] Sensor database access controls (customers see specs relevant to their panel category)
- [ ] Usage tracking and metering (for subscription billing)
- [ ] Audit trail for all simulation runs

**Interactive Viewer (Standalone Deliverable — Shared Across Tiers)**
- [ ] Self-contained HTML/JS package (no server required, works offline/air-gapped)
- [ ] Zoomable/pannable coverage maps (Leaflet or Deck.gl)
- [ ] Toggle layers on/off (radar, RF, EO/IR, acoustic, effectors)
- [ ] Kill chain timeline visualisation
- [ ] Engagement capacity / saturation results
- [ ] Click-to-inspect gap details
- [ ] Data is pre-computed JSON — viewer has zero simulation capability
- [ ] Sanitisation controls (strip exact sensor specs, round coordinates before export)

---

### Phase 5 — Advanced Platform & Compliance

**3D Modelling Upgrade**
- [ ] True 3D scene model (buildings as geometry, not just DSM height bumps)
- [ ] Import BIM/IFC building models for complex installations
- [ ] Multi-level building coverage (rooftop sensors, ground-level dead zones)
- [ ] Urban canyon modelling

**API & Integration**
- [ ] REST API for headless simulation runs (programmatic access for Tier 2 customers)
- [ ] Integration with C2 platforms (Lattice, Cortex, DroneSentry-C2)
- [ ] Import/export in NATO-standard formats
- [ ] Real-time sensor data overlay (actual vs simulated coverage comparison)

**Tier 3: On-Premise Deployment (Classified Environments)**
- [ ] Air-gapped Docker deployment package
- [ ] Classification marking engine (UNCLASS, PROTECTED, SECRET headers/footers)
- [ ] Data handling controls for classified sensor specifications
- [ ] DISP-compliant deployment architecture
- [ ] Licence enforcement (time-limited keys, usage metering)
- [ ] Audit trail for compliance

---

## Delivery Model

### Three-Tier Approach

```
Tier 1 — Report as a Service
  You run the simulation. Client receives PDF + interactive viewer.
  Pricing: Per-engagement ($15K–$120K)

Tier 2 — Hosted Simulation Access
  Client configures and runs simulations via web platform on your infrastructure.
  Engine stays server-side. Client never receives the software.
  Pricing: Annual subscription ($50K–$150K/year per Panel member)

Tier 3 — On-Premise Deployment
  Software deployed inside classified/air-gapped networks.
  Only when security requirements demand it.
  Pricing: $200K+ per installation + annual support
```

### Delivery Sequence

If development proceeds faster than anticipated, both Tier 1 and Tier 2 will be implemented before approach to market.

**Default plan:**
- Tier 1 available at market approach (MVP complete)
- Tier 2 available at Phase 4 completion (or at market approach if ahead of schedule)
- Tier 3 only when a specific contract demands it (Phase 5)

**Accelerated plan (if ahead of schedule):**
- Tier 1 + Tier 2 both available at market approach
- Stronger value proposition from day one — offer the report service and the platform simultaneously
- Panel members can start with a Tier 1 engagement to validate, then upgrade to Tier 2 subscription

### What Each Tier Delivers

| Output | Tier 1 | Tier 2 | Tier 3 |
|--------|--------|--------|--------|
| PDF report | Yes | Yes (self-service export) | Yes |
| Interactive viewer (standalone HTML) | Yes | Yes (self-service export) | Yes |
| Sensor placement configuration | No (you do it) | Yes | Yes |
| Threat scenario definition | No (you do it) | Yes | Yes |
| What-if comparison | No (you do it) | Yes | Yes |
| Simulation engine access | Never | Hosted only | On-premise |
| Sensor database access | Never | Read-only via UI | Local copy |
| Source code | Never | Never | Never |

---

## Roadmap Summary

| Phase | Focus | Estimated Effort | Dependency |
|-------|-------|-----------------|------------|
| **MVP (v1.0)** | Tier 1: Layered coverage, kill chain, saturation, greedy placement, PDF report, interactive viewer | ~12–16 weeks | None |
| **Phase 2** | Simulation fidelity (RF propagation, Pd curves, sensor fusion, weather) | ~8–12 weeks | MVP complete |
| **Phase 3** | Advanced analysis (advanced placement, advanced swarm, comms/network) | ~6–10 weeks | Phase 2 |
| **Phase 4** | Tier 2: Hosted simulation platform (web UI, multi-tenancy, job queue) | ~12–16 weeks | MVP minimum |
| **Phase 5** | Tier 3 + advanced platform (3D, API, classification, on-prem deployment) | ~10–14 weeks | Phase 4 |

Phases 2–4 can overlap. Phase 4 can begin once the MVP engine is stable. If development is ahead of schedule, Phase 4 runs in parallel with Phase 2/3 to deliver Tier 1 + Tier 2 at market approach.

---

*Living document. Update as scope decisions are made and priorities shift based on customer feedback.*
