# Project Salus — Interface Architecture

> **Status:** Reference document. Not yet in the ProjectPath.md implementation
> backlog — tracked as a future phase after Slice 14. This document is the
> authoritative design reference for any engineer building the interactive
> interface.
>
> **See also:** [`docs/SimulationEngine.md`](SimulationEngine.md) — the Python
> backend engine that this interface drives. The backend API (Section 6) is a
> thin FastAPI wrapper around the engine's existing Pydantic models.

---

## 1. Guiding Principles

These are not guidelines — they are invariants enforced by the architecture
itself. Each principle names the mechanism that makes it structurally
unbreakable, not merely advisable.

1. **Modules never talk to each other directly.**
   Enforced by dependency injection: modules receive no reference to the shell,
   to other modules, or to the raw state object. A module cannot import another
   module because it is never given anything to import. The only handles a
   module receives at initialisation are the restricted API object described in
   Section 2.6.

2. **The shared state is the integration contract.**
   Enforced by a `Proxy` wrapping the state object. Every read and write is
   intercepted at runtime. A write to an undeclared key throws immediately with
   a named error. A write of a non-serialisable value (function, class instance,
   DOM reference) throws immediately. Declared contracts come from each module's
   `manifest.json`, validated by the shell at startup before any module code
   is loaded.

3. **The 3D terrain canvas is permanent.**
   Enforced by the restricted map proxy: modules are given a scoped map handle
   that exposes only additive operations (`addSource`, `addLayer`, etc.) scoped
   to that module's layer ID prefix. Destructive operations (`setStyle`,
   `remove`, full style replacement) are not on the proxy and cannot be called.

4. **Shipping a subset means not including the files.**
   Enforced by dynamic module discovery: the shell scans the `modules/`
   directory at startup and loads whatever is present. There are no
   compile-time flags, no import lists, no feature toggles. Removing a module
   means removing its directory. The shell and all other modules are unaffected.

5. **State is always serialisable.**
   Enforced by the state Proxy (same mechanism as principle 2): any attempted
   write of a non-serialisable value is rejected at the point of the call with
   a clear error, before the value enters the state object.

6. **Reactive reads use `watch()`, never `get()` after `set()`.**
   A module must never call `api.state.get(key)` in the same synchronous call
   stack immediately after calling `api.state.set(key, ...)` and expect to
   read back its own write. All UI that reacts to state changes must be driven
   by `api.state.watch()`. This is not just a style preference — it is the
   single rule that makes the architecture portable to multi-user without
   rewriting modules. Enforced by a test harness that introduces a deliberate
   async delay between `set()` and watcher notification (Section 9.3), and by
   code review (Section 9).

---

## 2. Architecture

### 2.1 Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                              SHELL                                   │
│                                                                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────────┐    │
│  │   Module     │  │   State Proxy   │  │     Event Bus        │    │
│  │  Registry    │  │  (contract      │  │  (EventTarget-based) │    │
│  │  (discovery  │  │   enforcement)  │  │                      │    │
│  │  + manifest  │  └────────┬────────┘  └──────────┬───────────┘    │
│  │  validation) │           │                      │                │
│  └──────┬───────┘           │                      │                │
│         │          ┌────────▼──────────────────────▼──────────┐     │
│         └─────────►│            Mode Manager                  │     │
│                    │  (nav bar, prerequisite gating,           │     │
│                    │   module panel lifecycle)                 │     │
│                    └──────────────────────────────────────────┘     │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │              3D Terrain Canvas (MapLibreGL)                   │   │
│  │  Shell owns the map instance. Modules receive a scoped proxy. │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                    Module Panel Slot                          │   │
│  │  One module panel mounted at a time. Shell manages lifecycle. │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
         ▲ injects restricted API object — no other reference passes down
         │
    ┌────┴──────────────────────────────────────────────────┐
    │  modules/  (discovered dynamically, never imported)   │
    │    terrain-loader/   placement-editor/   coverage-viewer/ ...  │
    └───────────────────────────────────────────────────────┘
```

### 2.2 Shell

The shell is the host application. It owns every shared resource and is the
only part of the system that holds direct references to them. Its
responsibilities are:

- **Module discovery:** Scan `modules/` at startup. For each subdirectory,
  read and validate `manifest.json`. Reject and log any module with an invalid
  manifest. Never import or execute module code at this stage.
- **Manifest validation:** See Section 2.7 for the full validation ruleset.
- **State construction:** Instantiate the plain state object and wrap it in
  the contract-enforcing Proxy. The raw object never leaves the shell.
- **Event bus construction:** Instantiate the `EventTarget`-based bus. The raw
  bus is passed into the injected API; modules cannot reach the underlying
  `EventTarget` directly.
- **Map construction:** Instantiate the MapLibreGL map. The raw map instance
  never leaves the shell. Each module receives a scoped proxy (Section 2.5).
- **Mode manager construction:** Build the navigation bar from validated
  manifests. Wire prerequisite gating logic.
- **Module initialisation:** When a module is first activated, dynamically
  import its `index.js` and call `module.init(api)` with the injected API
  object for that module (Section 2.6). The module receives nothing else.
- **Panel lifecycle:** Mount and unmount module panels into the panel slot as
  modes change.

The shell contains no simulation logic and no knowledge of any specific
module's internals.

### 2.3 State Proxy

The shared state is a plain JS object wrapped in a `Proxy`. The Proxy
intercepts all property access and performs the following checks on every
operation:

**On `set(key, value)`:**
1. Resolve the calling module's identity (passed via a closure at API
   construction time — modules cannot spoof this).
2. Check that `key` appears in that module's declared `writes[]`. If not,
   throw `StateContractViolation: module 'X' attempted to write 'Y' but only
   declared writes: [...]`.
3. Check that `value` is serialisable: no functions, no class instances with
   custom prototypes, no DOM nodes, no `undefined`. If not serialisable, throw
   `StateSerialiseViolation: module 'X' attempted to write non-serialisable
   value to 'Y'`.
4. Write the value and notify all watchers registered on `key`.

**On `get(key)`:**
1. Resolve the calling module's identity.
2. Check that `key` appears in that module's declared `reads[]` or `writes[]`.
   If not, throw `StateContractViolation: module 'X' attempted to read 'Y'
   but did not declare it`.
3. Return the value (deep-frozen to prevent mutation without going through
   `set`).

The shell itself reads and writes the state directly (bypassing the Proxy)
for initialisation and scenario load/save operations.

### 2.4 Event Bus

A thin wrapper around the native `EventTarget` API. Modules receive a scoped
bus handle that enforces their declared event contracts:

- `emit(event, data)` — allowed only for events listed in the module's
  `emits[]`. Throws `EventContractViolation` otherwise.
- `on(event, callback)` — allowed only for events listed in the module's
  `subscribes[]`. Throws `EventContractViolation` otherwise.

The underlying `EventTarget` is never exposed. This ensures the event graph
remains auditable from manifests alone — you can always determine which
modules can emit or receive any given event without reading implementation
code.

Core events:

| Event | Emitted by | Typical subscribers |
|---|---|---|
| `terrain:loaded` | Terrain Loader | Mode Manager (unlock nav) |
| `placement:pending` | Library Browser, Gap Analysis | Placement Editor |
| `placement:added` | Placement Editor | Budget Tracker |
| `placement:removed` | Placement Editor | Budget Tracker |
| `placement:moved` | Placement Editor | — |
| `simulation:started` | Simulation Runner | Shell (show spinner) |
| `simulation:progress` | Simulation Runner | Simulation Runner panel |
| `simulation:complete` | Simulation Runner | Coverage Viewer, Gap Analysis, Kill Chain Analyser, Saturation Analyser, Report Configurator |
| `simulation:failed` | Simulation Runner | Shell (show error) |
| `zone:added` | Zone / Priority Editor | Optimiser |
| `zone:removed` | Zone / Priority Editor | Optimiser |
| `constraint:updated` | Budget Tracker | Optimiser |
| `optimiser:started` | Optimiser | Shell (show spinner) |
| `optimiser:complete` | Optimiser | Placement Editor |
| `optimiser:failed` | Optimiser | Shell (show error) |
| `corridor:added` | Threat Corridor Editor | — |
| `corridor:removed` | Threat Corridor Editor | — |
| `comparison:loaded` | Scenario Comparison | — |
| `report:generated` | Report Configurator | — |
| `scenario:loaded` | Shell | All modules (re-render) |
| `scenario:saved` | Shell | — |

### 2.5 Mode Manager

Manages which module panel is active. Responsibilities:

- Build the navigation bar from validated manifests at startup.
- Gate each nav button: a module's button is enabled only when all keys listed
  in its `prerequisites[]` are non-null in the current state. Display a tooltip
  naming the unsatisfied prerequisites when disabled.
- On mode switch: call `panel.unmount()` on the outgoing module, call
  `panel.mount()` on the incoming module, update `state.ui.active_module_id`.
- Maintain `state.ui.nav_history` so Back navigation works.
- Support an optional guided workflow mode (Load → Place → Simulate → View)
  for first-time users alongside free navigation for experienced users.

### 2.6 Module API Contract

This is the complete object injected into `module.init(api)`. It is the only
external reference a module ever receives. Modules must not attempt to reach
beyond it.

```javascript
// Injected API — constructed fresh per module by the shell
{
  moduleId: string,             // the module's declared id; use for logging

  state: {
    // Read a declared key. Throws StateContractViolation if key not in reads[].
    // Returns a deep-frozen value — mutate only via set().
    //
    // IMPORTANT: Do not call get() immediately after set() expecting to read
    // back your own write. get() is for one-time reads at initialisation time
    // (e.g. populating a panel when it first mounts). For any UI or logic that
    // reacts to state changes, use watch() instead. This rule exists so that
    // the state layer can be made async (multi-user WebSocket sync) without
    // rewriting any module.
    get(key: string): any,

    // Write a declared key. Throws StateContractViolation if key not in writes[].
    // Throws StateSerialiseViolation if value contains non-serialisable data.
    // Currently synchronous. Designed to become async (returning a Promise)
    // if the state layer is moved to a backend for multi-user sync — modules
    // that follow the watch() pattern will require no changes in that case.
    set(key: string, value: any): void,

    // THE STANDARD PATTERN for reactive reads. Callback fires whenever the
    // key's value changes, receiving (newValue, oldValue). All UI rendering
    // and logic that depends on state must be driven by watch(), not by
    // polling or post-set get() calls. Returns an unsubscribe function —
    // call it inside api.panel.onUnmount() to prevent memory leaks.
    watch(key: string, callback: Function): () => void,
  },

  bus: {
    // Emit a declared event. Throws EventContractViolation if event not in emits[].
    emit(event: string, data?: any): void,

    // Subscribe to a declared event. Throws EventContractViolation if not in subscribes[].
    // Returns an unsubscribe function.
    on(event: string, callback: Function): () => void,
  },

  // Scoped map proxy. Layer and source IDs must begin with moduleId + ':'.
  // Shell enforces the prefix at addLayer/addSource call time.
  map: {
    addSource(id: string, spec: object): void,
    removeSource(id: string): void,
    getSource(id: string): object | undefined,
    addLayer(spec: object, beforeId?: string): void,
    removeLayer(id: string): void,
    getLayer(id: string): object | undefined,
    setLayoutProperty(layerId: string, name: string, value: any): void,
    setPaintProperty(layerId: string, name: string, value: any): void,
    on(event: string, layerIdOrHandler: any, handler?: Function): void,
    off(event: string, layerIdOrHandler: any, handler?: Function): void,
    getCanvas(): HTMLCanvasElement,   // read-only; cursor changes only
    flyTo(options: object): void,
    fitBounds(bounds: array, options?: object): void,
    project(lngLat: object): object,
    unproject(point: object): object,
    queryRenderedFeatures(point: object, options?: object): array,
    // NOT available: setStyle(), remove(), addControl(), removeControl(),
    //                getStyle(), setTerrain(), setBearing(), setPitch()
    //                (camera writes go through flyTo/fitBounds only)
  },

  panel: {
    // Mount this module's root HTML element into the panel slot.
    mount(element: HTMLElement): void,
    // Called by the shell when the module is deactivated — clean up listeners.
    onUnmount(callback: Function): void,
  },
}
```

### 2.7 Module Directory Structure

Every module is a self-contained directory under `modules/`. The shell
discovers modules by scanning this directory — nothing else registers them.

```
modules/
  terrain-loader/
    manifest.json     ← contract declaration (see below)
    index.js          ← exports { init(api) } — entry point, nothing else
    panel.js          ← panel UI logic, imported by index.js
    panel.html        ← panel markup, loaded by panel.js
    map-layers.js     ← MapLibreGL layer definitions, imported by index.js
  placement-editor/
    ...
```

`manifest.json` full schema:

```json
{
  "id": "placement-editor",
  "label": "Place Sensors",
  "icon": "pin",
  "reads": ["terrain", "sensor_library", "effector_library"],
  "writes": ["placements"],
  "prerequisites": ["terrain"],
  "emits": ["placement:added", "placement:removed", "placement:moved"],
  "subscribes": ["placement:pending", "optimiser:complete"],
  "layer_id_prefix": "placement-editor",
  "description": "Drag and drop sensors and effectors onto the terrain."
}
```

`index.js` contract — every module must export exactly this shape:

```javascript
// modules/placement-editor/index.js
export function init(api) {
  // api is the injected object from Section 2.6.
  // Do not import other modules here.
  // Do not reach outside api.
}
```

### 2.8 Manifest Validation Rules

The shell validates every `manifest.json` at startup before loading any module
code. A module with a failing validation is skipped and logged; it does not
crash the shell.

| Rule | Check |
|---|---|
| Required fields | `id`, `label`, `reads`, `writes`, `emits`, `subscribes` are all present |
| ID uniqueness | No two loaded modules share the same `id` |
| Valid state keys | All entries in `reads[]` and `writes[]` are keys defined in the canonical state schema (Section 3) |
| Single writer | No state key in `writes[]` is also declared in another loaded module's `writes[]` |
| Valid events | All entries in `emits[]` and `subscribes[]` are events listed in the canonical event registry (Section 2.4) |
| Reachable prerequisites | All entries in `prerequisites[]` are state keys in `writes[]` of some other loaded module |
| Layer prefix | `layer_id_prefix` (defaults to `id`) is unique across loaded modules |

---

## 3. Shared State Schema

The canonical state schema. Only keys defined here are valid in `reads[]` and
`writes[]` declarations. The shell rejects any module that references an
unknown key.

```
SharedState {
  terrain: {
    dem_path: string | null,
    dsm_path: string | null,
    crs_epsg: number | null,
    bounds_wgs84: [west, south, east, north] | null,
    centre_wgs84: [lon, lat] | null,
    resolution_m: number | null,
    tile_url_template: string | null,
    terrain_tile_count: number,
    terrain_min_zoom: number,
    terrain_max_zoom: number
  } | null,

  sensor_library: SensorDefinition[],
  effector_library: EffectorDefinition[],

  placements: {
    sensors: SensorPlacement[],       ← position_x/y, sensor_name, bearing_deg,
    effectors: EffectorPlacement[]      height_override_m
  },

  zones: {
    priority: PriorityZone[],         ← polygon (GeoJSON), label, min_coverage_pct
    exclusion: ExclusionZone[]        ← polygon (GeoJSON), label, reason
  },

  threat_corridors: ThreatCorridor[], ← waypoints, threat_profile, altitude_m,
                                        protected_point

  constraints: {
    max_cost_aud: number | null,
    allowed_sensor_ids: string[] | null,
    allowed_effector_ids: string[] | null,
    max_sensors: number | null,
    max_effectors: number | null,
    placement_rules: PlacementRule[]  ← e.g. min_separation_m, boundary_required
  },

  sim_results: {
    layers: { [key: string]: GeoJSONFeatureCollection },
    sensor_placements: GeoJSONFeatureCollection,
    stats: CoverageStats,
    corridor_results: CorridorResult[],
    kill_chain_results: KillChainResult[],
    saturation_result: SaturationResult | null,
    sanitised: boolean,
    generated_at: string
  } | null,

  optimiser_results: {
    proposed_placements: {
      sensors: SensorPlacement[],
      effectors: EffectorPlacement[]
    },
    score: number,
    coverage_pct: number,
    total_cost_aud: number,
    satisfied_constraints: string[],
    violated_constraints: string[],
    generated_at: string
  } | null,

  scenario_b_sim_results: SimResults | null,   ← used by Scenario Comparison only

  report_config: {
    client_name: string,
    sanitise_level: "none" | "minimal" | "redacted" | "full",
    include_modules: string[],
    logo_path: string | null
  },

  ui: {
    active_module_id: string | null,
    nav_history: string[],
    pending_simulation: boolean,
    pending_optimiser: boolean
  }
}
```

`ui` is a shell-owned key. No module declares it in `writes[]`. The shell
updates it directly (bypassing the Proxy write-path) when modes change.

---

## 4. Module Inventory and I/O Map

### 4.1 Terrain Loader

**Purpose:** Load a DEM (and optionally DSM) GeoTIFF. Trigger terrain tile
generation and configure the 3D canvas.

**Panel UI:** File picker for DEM and DSM paths. CRS display. Tile generation
progress bar. Bounds and resolution summary once loaded.

**Map behaviour:** Calls `api.map.addSource` and `api.map.addLayer` to add the
`terrain-loader:terrain-dem` raster-dem source and hillshade layer.

| | State keys |
|---|---|
| Reads | — |
| Writes | `terrain` |
| Prerequisites | — |

**Emits:** `terrain:loaded`

---

### 4.2 Sensor / Effector Library Browser

**Purpose:** Browse the sensor and effector catalogue. View specifications.
Drag systems from the panel onto the terrain canvas to initiate placement.

**Panel UI:** Filterable list by type. Spec card per system. Drag handle.

**Map behaviour:** Ghost marker follows cursor during drag. On drop, emits
`placement:pending`; the Placement Editor finalises position and bearing.

| | State keys |
|---|---|
| Reads | `sensor_library`, `effector_library` |
| Writes | — |
| Prerequisites | — |

**Emits:** `placement:pending`

---

### 4.3 Placement Editor

**Purpose:** Add, move, rotate, and remove sensor and effector placements.
Sole writer of `placements`.

**Panel UI:** Placement list with inline bearing and height controls.
Import/export placements as scenario YAML.

**Map behaviour:** Sensor markers with type-coded circles, bearing indicator
lines, and type-badge labels. Click to select; drag to reposition; scroll
to rotate bearing; right-click to remove.

| | State keys |
|---|---|
| Reads | `terrain`, `sensor_library`, `effector_library` |
| Writes | `placements` |
| Prerequisites | `terrain` |

**Emits:** `placement:added`, `placement:removed`, `placement:moved`
**Subscribes to:** `placement:pending`, `optimiser:complete`

---

### 4.4 Threat Corridor Editor

**Purpose:** Draw threat ingress routes on the terrain. Assign drone type,
altitude, and speed to each route.

**Panel UI:** Draw mode toggle (click waypoints, double-click to finish).
Route list with threat profile selector. Protected point picker.

**Map behaviour:** Dashed lines with directional arrows, colour-coded by threat
profile. Protected point as a pulsing target icon.

| | State keys |
|---|---|
| Reads | `terrain` |
| Writes | `threat_corridors` |
| Prerequisites | `terrain` |

**Emits:** `corridor:added`, `corridor:removed`

---

### 4.5 Zone and Priority Editor

**Purpose:** Draw priority zones (minimum coverage required) and exclusion
zones (no sensor/effector placement allowed).

**Panel UI:** Polygon draw tool. Zone type selector. Zone list with labels and
coverage thresholds.

**Map behaviour:** Priority zones as filled polygons with threshold label.
Exclusion zones as hatched polygons.

| | State keys |
|---|---|
| Reads | `terrain` |
| Writes | `zones` |
| Prerequisites | `terrain` |

**Emits:** `zone:added`, `zone:removed`

---

### 4.6 Simulation Runner

**Purpose:** Serialise current state into a scenario, post to the backend API,
stream progress, write results.

**Panel UI:** Pre-flight checklist. Run button. Live progress log. Elapsed time.
Cancel. Result summary on completion.

**Map behaviour:** Stale indicator on previous result layers while running.
New result layers added on completion (delegated to Coverage Viewer via
`simulation:complete`).

**Backend contract:** `POST /api/simulate` — request body is a
`ScenarioConfig`-compatible JSON object. Response is an SSE stream of progress
messages terminating in a final `sim_results` JSON payload.

| | State keys |
|---|---|
| Reads | `terrain`, `placements`, `threat_corridors`, `zones` |
| Writes | `sim_results` |
| Prerequisites | `terrain`, `placements` |

**Emits:** `simulation:started`, `simulation:progress`, `simulation:complete`, `simulation:failed`

---

### 4.7 Coverage Viewer

**Purpose:** Display simulation results as toggleable layers on the 3D terrain.

**Panel UI:** Layer toggles (per sensor type, composite, gaps). Coverage
statistics. Colour legend. Per-zone compliance indicators.

**Map behaviour:** Fill and outline layers per coverage type. Bearing indicator
lines for directional sensors. Type-badge labels. Gap polygons.

| | State keys |
|---|---|
| Reads | `terrain`, `placements`, `sim_results` |
| Writes | — |
| Prerequisites | `terrain`, `sim_results` |

**Emits:** —
**Subscribes to:** `simulation:complete`

---

### 4.8 Gap Analysis

**Purpose:** Rank uncovered areas by severity. Suggest sensor placements that
would close each gap.

**Panel UI:** Ranked gap list with severity score, area, and priority zone
overlap. Click gap to fly camera to it. Suggestion card per gap.

**Map behaviour:** Highlight selected gap polygon. Ghost placement marker on
suggestion hover.

| | State keys |
|---|---|
| Reads | `terrain`, `sim_results`, `zones`, `sensor_library` |
| Writes | — |
| Prerequisites | `terrain`, `sim_results` |

**Emits:** `placement:pending`
**Subscribes to:** `simulation:complete`

---

### 4.9 Kill Chain Analyser

**Purpose:** Visualise the detect–track–identify–engage chain per threat
corridor. Highlight kill chain gaps.

**Panel UI:** Route selector. Per-route timeline: detection range, engagement
window, available vs required time, margin. Kill chain gap warnings.

**Map behaviour:** Corridor lines colour-coded by kill chain status. Markers at
first detection and first engagement points. Engagement envelopes on hover.

| | State keys |
|---|---|
| Reads | `terrain`, `sim_results`, `threat_corridors` |
| Writes | — |
| Prerequisites | `terrain`, `sim_results` |

**Emits:** —
**Subscribes to:** `simulation:complete`

---

### 4.10 Saturation Analyser

**Purpose:** Evaluate system capacity under simultaneous multi-drone attack.

**Panel UI:** Simultaneous threat count selector. Per-effector utilisation bar
chart. Unengaged threat list. Saturation threshold indicator.

**Map behaviour:** Simultaneous approach vectors as separate corridor lines.
Overwhelmed effectors highlighted on map.

| | State keys |
|---|---|
| Reads | `terrain`, `sim_results` |
| Writes | — |
| Prerequisites | `terrain`, `sim_results` |

**Emits:** —
**Subscribes to:** `simulation:complete`

---

### 4.11 Budget and BOM Tracker

**Purpose:** Running cost of current placements against budget. Writes budget
constraint for the optimiser.

**Panel UI:** Total cost vs budget bar. Cost breakdown table. Budget input
field. Over-budget alert. CSV export.

**Map behaviour:** None.

| | State keys |
|---|---|
| Reads | `placements`, `sensor_library`, `effector_library` |
| Writes | `constraints` |
| Prerequisites | — |

**Emits:** `constraint:updated`
**Subscribes to:** `placement:added`, `placement:removed`

---

### 4.12 Optimiser

**Purpose:** Compute optimal placements satisfying all constraints. Proposes
results for review before applying.

**Panel UI:** Objective selector. Constraint summary. Run button. Progress
indicator. Apply / Discard proposed placements.

**Map behaviour:** Ghost markers for proposed placements (distinct style, not
yet in `placements`).

**Backend contract:** `POST /api/optimise` — request body includes `zones`,
`constraints`, and the relevant subset of `sensor_library`/`effector_library`.
Response is an SSE stream terminating in `optimiser_results`.

| | State keys |
|---|---|
| Reads | `terrain`, `zones`, `constraints`, `sensor_library`, `effector_library`, `threat_corridors` |
| Writes | `optimiser_results` |
| Prerequisites | `terrain`, `zones` |

**Emits:** `optimiser:started`, `optimiser:complete`, `optimiser:failed`
**Subscribes to:** `zone:added`, `zone:removed`, `constraint:updated`

---

### 4.13 Scenario Comparison

**Purpose:** Load a saved scenario B and compare against current sim results.

**Panel UI:** Load scenario B file picker. Summary comparison table (coverage
%, cost, gap area, kill chain margin). Overlay diff / split-view toggle.

**Map behaviour:** Overlay mode: colour-coded diff layer (green = newly covered,
red = lost, grey = both). Split mode: swipe divider across map.

| | State keys |
|---|---|
| Reads | `terrain`, `sim_results` |
| Writes | `scenario_b_sim_results` |
| Prerequisites | `terrain`, `sim_results` |

**Emits:** `comparison:loaded`

---

### 4.14 Report Configurator

**Purpose:** Configure and generate the customer-deliverable PDF report.

**Panel UI:** Module content checklist. Sanitisation level selector. Client
name and logo upload. Generate button. Download link on completion.

**Map behaviour:** Captures a screenshot of the current map view as a report
figure.

**Backend contract:** `POST /api/report` with `report_config` and relevant
state keys. Returns a PDF binary stream.

| | State keys |
|---|---|
| Reads | `sim_results`, `placements`, `zones`, `threat_corridors`, `report_config` |
| Writes | `report_config` |
| Prerequisites | `sim_results` |

**Emits:** `report:generated`

---

## 5. Data Flow Diagram

```
Terrain Loader ──────────────────── writes: terrain
  │
  ├──► Placement Editor ──────────── reads: sensor_library, effector_library
  │      └─ writes: placements
  │
  ├──► Threat Corridor Editor
  │      └─ writes: threat_corridors
  │
  ├──► Zone / Priority Editor
  │      └─ writes: zones
  │             │
  │             └──► Optimiser ────── reads: zones, constraints, libraries
  │                    └─ writes: optimiser_results
  │                           │
  │                           └──► (event) optimiser:complete
  │                                    └──► Placement Editor (apply proposed)
  │
  ├──► Budget Tracker ─────────────── reads: placements, libraries
  │      └─ writes: constraints
  │
  ▼
Simulation Runner ────── reads: terrain, placements, threat_corridors, zones
  └─ writes: sim_results
       │
       └──► (event) simulation:complete
                ├──► Coverage Viewer
                ├──► Gap Analysis ──────► (event) placement:pending
                │                                    └──► Placement Editor
                ├──► Kill Chain Analyser
                ├──► Saturation Analyser
                └──► Report Configurator
```

---

## 6. Backend API

The frontend is static HTML/JS. All compute-heavy operations are delegated to
the existing Salus Python engine (documented in [`docs/SimulationEngine.md`](SimulationEngine.md)),
exposed via a thin FastAPI layer. This API is only ever called from localhost —
it is not a public-facing service. The request/response bodies are JSON
representations of the engine's existing Pydantic models — no new schema is
introduced.

### Endpoints

| Method | Path | Request body | Response |
|---|---|---|---|
| `POST` | `/api/simulate` | `ScenarioConfig` JSON | SSE stream → final `sim_results` JSON |
| `POST` | `/api/optimise` | `OptimiserRequest` JSON | SSE stream → final `optimiser_results` JSON |
| `POST` | `/api/report` | `ReportRequest` JSON | PDF binary stream |
| `GET` | `/api/sensors` | — | `SensorDefinition[]` JSON |
| `GET` | `/api/effectors` | — | `EffectorDefinition[]` JSON |
| `GET` | `/api/health` | — | `{"status": "ok"}` |

### Scenario serialisation

The Simulation Runner serialises the relevant state keys into a
`ScenarioConfig`-compatible JSON body — the same structure the existing
`salus` CLI accepts as a scenario YAML. The API layer is a JSON wrapper around
the existing Pydantic models with no new schema.

### SSE progress stream format

```
data: {"type": "progress", "message": "Computing viewshed 2/4...", "pct": 50}

data: {"type": "progress", "message": "Vectorising coverage...", "pct": 90}

data: {"type": "complete", "result": { ...sim_results payload... }}
```

On error: `data: {"type": "error", "message": "..."}` followed by stream close.

---

## 7. Technology Recommendations

| Concern | Recommendation | Rationale |
|---|---|---|
| 3D terrain canvas | MapLibreGL v3.x | Already in use; handles terrain tiles, GeoJSON, symbol layers |
| Module system | Native ES modules (`type="module"`) | No build step; each module is a plain `.js` file; browser-native dynamic import |
| Shared state + Proxy | Vanilla JS | No framework dependency; Proxy is native and sufficient for this scale |
| Event bus | `EventTarget` (native) | Zero dependencies; standard pub/sub; works with the scoped wrapper described in Section 2.4 |
| Panel UI | Plain HTML + CSS | Internal tool; no React/Vue overhead needed |
| Backend API | FastAPI (Python) | Lightweight; native async SSE; Pydantic models already exist |
| Polygon/route drawing | `maplibre-gl-draw` (fork of `mapbox-gl-draw`) | Standard canvas drawing tool; integrates with MapLibreGL |
| Save/load | `JSON.stringify(state)` → file download | State schema is fully serialisable by design; no database needed |
| State schema types | JSDoc or TypeScript `.d.ts` | Optional but strongly recommended; catches contract mismatches at edit time rather than runtime |

---

## 8. Deployment Configurations

Because module inclusion is purely file-based, any subset of modules can be
shipped. Examples:

**Minimal (no backend):**
Terrain Loader + Coverage Viewer. Terrain and `viewer_data.js` are
pre-generated. No simulation, no placement editing.

**Field planning kit:**
Terrain Loader + Library Browser + Placement Editor + Simulation Runner +
Coverage Viewer + Budget Tracker. No optimiser, no reporting.

**Full analyst suite:**
All modules. Requires the FastAPI backend running locally.

**Customer deliverable:**
Terrain Loader + Coverage Viewer only, with pre-generated sanitised
`viewer_data.js`. No backend, no editable placements.

---

## 9. Module Code Review Checklist

Every pull request that introduces or modifies a module must be reviewed
against this checklist. Items marked **[ARCH]** are architectural invariants —
a PR that fails any of them must not be merged regardless of other quality.
Items marked **[MULTI]** are the specific rules that preserve the multi-user
migration path.

### 9.1 Module isolation **[ARCH]**

- [ ] `index.js` does not `import` any file from another module's directory
- [ ] `index.js` does not access `window.*`, `document.*`, or any global except
      those provided by the injected `api` object
- [ ] No module-level variables hold references to other modules, the shell,
      the raw map instance, or the raw state object
- [ ] The module exports only `{ init(api) }` — no other named exports

### 9.2 State contract **[ARCH]**

- [ ] Every state key the module reads is declared in `manifest.json` `reads[]`
- [ ] Every state key the module writes is declared in `manifest.json` `writes[]`
- [ ] No state key is written that is declared as `writes[]` by another module
- [ ] All values written to state are plain serialisable objects (no class
      instances, no functions, no DOM references, no `undefined`)

### 9.3 Reactive reads **[MULTI]**

This is the rule that keeps multi-user migration cheap. Violations here do
not break the single-user build today, but they will require module rewrites
if the state layer is made async. They must be caught in review.

- [ ] No call to `api.state.get(key)` appears in the same synchronous call
      stack as a preceding `api.state.set(key, ...)` on the same key
- [ ] All UI elements that display state values are populated inside a
      `api.state.watch()` callback, not in a one-time `get()` at mount time
      (exception: populating a panel's initial render before any user action is
      acceptable with `get()`, but subsequent updates must come from `watch()`)
- [ ] Every `watch()` subscription is unsubscribed inside `api.panel.onUnmount()`

**How to test this mechanically:** The module test harness (see below)
injects a state implementation where `set()` notifies watchers after a 10 ms
delay. Any test that calls `set()` then immediately asserts via `get()` will
fail because the read returns the pre-write value. Write tests that await
watcher callbacks instead.

```javascript
// WRONG — will fail in test harness and break under async state
api.state.set('placements', updated)
renderList(api.state.get('placements'))  // reads stale value

// CORRECT — driven by watch()
api.state.watch('placements', (placements) => renderList(placements))
api.state.set('placements', updated)     // watch callback fires, UI updates
```

### 9.4 Event contracts **[ARCH]**

- [ ] Every event emitted is declared in `manifest.json` `emits[]`
- [ ] Every event subscribed to is declared in `manifest.json` `subscribes[]`
- [ ] Event subscriptions are cleaned up in `api.panel.onUnmount()`

### 9.5 Map layer scoping **[ARCH]**

- [ ] Every `addSource` and `addLayer` call uses an ID prefixed with
      `{moduleId}:` (e.g. `placement-editor:sensors-circle`)
- [ ] The module does not call any map method not listed in Section 2.6
- [ ] All map event listeners are removed in `api.panel.onUnmount()`

### 9.6 Manifest completeness

- [ ] `manifest.json` passes all validation rules in Section 2.8
- [ ] `description` accurately reflects the module's current behaviour

---

## 10. Multi-User Migration Path

**Decision:** Build single-user first. The architecture described in this
document is designed so that adding multi-user support is a shell-level change
that does not require rewriting any module.

### What single-user gets right by design

The state abstraction (`api.state.get/set/watch`) is already an interface, not
a direct object reference. Modules are completely unaware of where state lives
or how it is persisted. This is the seam at which multi-user sync plugs in.

### What changes when going multi-user

| Component | Single-user | Multi-user |
|---|---|---|
| State storage | Local JS Proxy in shell | Backend database (e.g. Redis or Postgres) |
| State sync | Local — no network | WebSocket broadcast from backend |
| `api.state.set()` | Writes to local Proxy | Writes locally (optimistic) + sends to backend via WebSocket |
| `api.state.watch()` | Fires on local Proxy write | Also fires on incoming WebSocket update from other clients |
| Shell | No auth | Adds user identity; namespaces state by session |
| Conflict resolution | N/A | Last-write-wins per key (simplest); or per-key optimistic locking |

### What does not change

Every module. The event bus. The mode manager. The manifest system. The
backend simulation, optimise, and report endpoints. The module API contract
interface (Section 2.6) remains identical — `set()` may become a Promise in
the multi-user implementation, but optimistic local writes mean the synchronous
call pattern still works in practice.

### The one prerequisite: Principle 6 must hold

If any module has been written with `get()` after `set()` patterns rather than
`watch()`, it will silently misbehave once state writes become async. The code
review checklist (Section 9.3) and the async test harness exist specifically to
prevent this debt from accumulating. Keep them enforced from day one.

---

## 11. Open Questions

These must be resolved before implementation begins:

1. **Optimiser algorithm:** The backend currently uses a greedy placement
   strategy. Is this sufficient for multi-zone, multi-constraint problems, or
   does it need a metaheuristic (simulated annealing, genetic algorithm)?

2. **Terrain tile serving:** Currently a bare Python HTTP server is started
   manually. The FastAPI backend should serve tiles at `/tiles/{z}/{x}/{y}.png`
   alongside the API — confirm this is the intended deployment model.

3. **Effector engagement envelopes:** The Kill Chain module needs to render
   effector engagement envelopes on the map. These are not currently in
   `sim_results`. Does the backend need a new `effector_coverage` GeoJSON layer,
   or is this computed client-side from `placements` + `effector_library`?

4. **Scenario B in Comparison module:** Loading scenario B — does this require
   re-running the simulation in-session, or loading a previously exported
   `viewer_data.js`? The latter is simpler and avoids a second backend call.
