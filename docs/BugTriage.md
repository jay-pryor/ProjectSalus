# Bug Triage

Generated from codebase sweep 2026-04-17. Organised by who fixes it.

---

## Opus — architectural / critical

All seven Opus-tier items resolved in I-6 (2026-04-28). Fixes recorded in
`.forge/defect-register.yaml` as D-406 through D-412 and in
`.forge/gate-proofs/I-6.yaml`.

**#1 sim_results field name mismatch** — RESOLVED (D-412, I-6)
`simulation-runner` reads `simResults.stats.coverage_pct`, `stats.largest_gap_area_m2`, `stats.worst_corridor_coverage_pct`. Backend emits `total_coverage_pct`, `largest_contiguous_gap_m2`; no corridor-coverage field exists. Results panel always shows `—`.
_Fix:_ `export_viewer_data` now writes `worst_corridor_coverage_pct` (D-412); the legacy aliases `coverage_pct` and `largest_gap_area_m2` were already added in D-405.

**#2 zone-editor writes wrong state shape** — RESOLVED (D-410, I-6)
Writer produces `{ zones: [{type:'priority'|'exclusion', ...}] }`. All consumers expect `{ priority: [], exclusion: [] }`. Zone compliance display, gap severity scoring, and the simulation pre-flight zones indicator are all permanently broken.
_Fix:_ `_writeState` now emits canonical `{priority, exclusion}` outer buckets and canonical inner fields (`label`, `min_coverage_pct`/`reason`, `geometry` as a closed GeoJSON Polygon). `_readCanonical` accepts both shapes for legacy scenarios.

**#5 report-configurator POST body rejected by backend** — RESOLVED (D-409, I-6)
Backend calls `ScenarioConfig.model_validate(request.report_config)` on the client's UI state object `{client_name, logo, sanitisation_level, sections}`. Always fails — `site_dem_path` missing. Every report generation returns a validation error.
_Fix:_ `/api/report` now accepts the UI report_config shape and reconstructs a minimal `ScenarioConfig` server-side from `placements`. `_extract_sim_stats` handles both nested-stats and legacy-flat sim_results.

**#7 sensor_library / effector_library never populated** — RESOLVED (D-408, I-6)
No module writes these keys and the shell never calls `GET /api/sensors` or `GET /api/effectors`. Library-browser renders empty; budget-tracker calculates zero costs; optimiser finds no sensors.
_Fix:_ Shell fetches both endpoints at startup and seeds state via `state.setState()`. Failures fall back to `{}` so consumers render cleanly.

**#8 Path traversal in /api/terrain/load and /api/simulate** — RESOLVED (D-407, I-6)
`ScenarioConfig.site_dem_path` and `OptimiserRequest.terrain` accept arbitrary filesystem paths. No directory restriction enforced.
_Fix:_ Added `_ALLOWED_DEM_DIRS` allowlist + `_validate_dem_path` guard. Called from `/api/simulate` (DEM/DSM/boundary) and `/api/optimise` (terrain). Returns HTTP 403 for paths outside the allowlist. Pytest fixtures register `tmp_path` and `tests/fixtures/`.

**#9 Global terrain session race condition** — RESOLVED (D-406, I-6)
`_terrain_session` is a single global dict. Concurrent `/api/terrain/load` calls silently overwrite each other's session, swap SSE progress streams, and old session temp dirs are never cleaned up.
_Fix:_ Replaced with `_terrain_sessions: dict[str, dict]` keyed by per-load `session_id`. Tile URL template is session-qualified. Added sessioned tile + tile-progress endpoints; legacy endpoints resolve to the latest session.

**#12 threat_corridors state shape mismatch** — RESOLVED (D-411, I-6)
`threat-corridor-editor` writes `{ routes: ThreatCorridor[], protected_point: {...} }`. Canonical schema is a flat `ThreatCorridor[]`. Simulation-runner pre-flight always reads the corridors indicator as true (non-null object). Backend receives an object where it expects an array.
_Fix:_ `_writeState` now emits a flat `ThreatCorridor[]` with `protected_point` denormalised onto each entry. `_readCanonical` accepts both shapes. `kill-chain-analyser` reads array directly with a defensive legacy fallback.

---

## Sonnet — medium, clear scope

All 16 Sonnet-tier items resolved in I-7 (2026-04-28). Fixes recorded in
`.forge/defect-register.yaml` as D-429 through D-443 and in
`.forge/gate-proofs/I-7.yaml`. Commit: d71245f.

**#3 optimiser manifest missing `placements` in `writes[]`** — RESOLVED (I-7)
`applyBtn` calls `api.state.set('placements', merged)` but manifest only declares `writes: ["optimiser_results"]`. The real state Proxy will throw at runtime — Apply button is broken in the live shell.
_Fix:_ Added `"placements"` to `writes[]` in `optimiser/manifest.json`.

**#4 optimiser POSTs terrain as an object** — RESOLVED (I-7)
Sends `terrain: latestTerrain` (full state object). `OptimiserRequest.terrain` is `str`. Every optimiser POST fails with a 422.
_Fix:_ Changed to `terrain: latestTerrain?.dem_path ?? null` in `_runOptimiser()`.

**#6 report-configurator wrong field names in report_config state** — RESOLVED (I-7)
`_currentConfig()` writes `{sanitisation_level, sections, logo}`. Canonical schema is `{sanitise_level, include_modules, logo_path}`. Any consumer reading standard names gets `undefined`.
_Fix:_ `_currentConfig()` now returns canonical names. `_updateForm()` accepts both for backward compat.

**#13 Silent sensor skip produces misleading coverage figure** — RESOLVED (I-7)
When a sensor name doesn't match the library, it is skipped with only a log warning. Response claims success with 0% coverage and no indication sensors were omitted.
_Fix:_ Added SSE progress event with warning message and `sensor_skip_count` in final result.

**#14 Zones never loaded in API simulate pipeline** — RESOLVED (I-7)
`compute_coverage_stats` receives `site.zones` but `load_dem` doesn't populate it — a separate `load_zones` call is needed. Per-zone coverage statistics are always `{}`.
_Fix:_ Added `_parse_ui_zones()` helper with CRS reprojection; called in both simulate and optimise pipelines.

**#15 CHM CRS mismatch not reprojected** — RESOLVED (I-7)
When CHM CRS differs from DEM CRS, code warns and continues without reprojection. The DSM path reprojecs correctly — inconsistent, potentially producing misaligned canopy heights in viewshed calculations.
_Fix:_ CHM CRS mismatch now triggers `_reproject_array()` to match DEM CRS/transform/shape.

**#16 scenario-comparison attaches global document listeners** — RESOLVED (I-7)
Swipe-divider drag registers `mousemove`/`mouseup` on `document` directly, violating module isolation. Any unmount failure leaves them permanently installed.
_Fix:_ Document listeners now attached only in `_onDividerMouseDown` and self-cleaned in `_onDocumentMouseUp`.

**#18 map_screenshot silently dropped by backend** — RESOLVED (I-7)
`report-configurator` includes `map_screenshot` in the POST body. `ReportRequest` has no such field; Pydantic silently ignores it. Captured map view never appears in the PDF.
_Fix:_ Added `map_screenshot: str | None = None` field to `ReportData`; passed from `request.map_screenshot`.

**#19 budget-tracker double-renders on every placement change** — RESOLVED (I-7)
Subscribes to both `placement:added`/`removed` bus events AND `watch('placements')`. State is set before the bus event fires, so both trigger per user action — two renders for one change.
_Fix:_ Removed bus subscriptions; `watch('placements', ...)` alone drives re-renders. Manifest `subscribes: []`.

**#21 find_saturation_threshold ignores priority_rule** — RESOLVED (I-7)
`priority_rule` is accepted in the model and documented but hardcoded to `CLOSEST_TO_ASSET` in the threshold sweep regardless of what the user configured.
_Fix:_ Added `priority_rule` parameter to `find_saturation_threshold()`; CLI passes `scenario.priority_rule`.

**#22 _raster_to_geojson simplifies before reprojecting** — RESOLVED (I-7)
For a projected CRS, simplification tolerance becomes ~9×10⁻¹⁰ m (effectively disabled). Correct order is reproject to WGS84 first, then simplify.
_Fix:_ Reproject to WGS84 first, then `simplify(_SIMPLIFY_TOLERANCE)` in degrees.

**#23 Thread-unsafe sensor/effector cache** — RESOLVED (I-7)
`_get_sensor_defs`/`_get_effector_defs` check-and-set the global without a lock. Two concurrent requests can both see the cache as empty and both invoke `load_sensors`.
_Fix:_ Added `threading.Lock` for each cache; check-and-set now atomic.

**#27 optimiser objective field has no backend handler** — RESOLVED (I-7)
`optimiser/index.js` sends `objective: currentObjective` in the POST body. `OptimiserRequest` has no `objective` field. All three UI objective options produce the same run — the selector has no effect.
_Fix:_ Added `objective` field to `OptimiserRequest` and `greedy_place_sensors()`; forwarded through call chain.

**#28 Kill-chain PDF always uses effector_defs[0]** — RESOLVED (I-7)
`render_kill_chain_chart` is called with `sim_results.effector_defs[0]`. Multi-effector scenarios only visualise the first effector with no warning.
_Fix:_ Uses `max(effector_defs, key=lambda e: e.defeat_probability)` with warning when multiple effectors present.

**#29 Two Terrarium encoding implementations with different B-channel arithmetic** — RESOLVED (I-7)
`viewer/export.py` and `app.py` each implement Terrarium tile encoding independently with subtly different fractional-part handling, producing inconsistent B-channel values.
_Fix:_ Unified to `_encode_terrarium()` in export.py with precise floor-based formula and `[0, 65535.999]` clamp. `app.py` imports and uses this shared helper.

**#30 protected_point missing cross-field validator** — RESOLVED (I-7)
`threat_profiles` non-empty + `protected_point = None` passes Pydantic validation but crashes in `find_worst_corridors` when the point is destructured.
_Fix:_ Added explicit `if protected_point is None: raise ValueError(...)` guard in `find_worst_corridors()` (model-level validator rejected — would break existing tests that create ScenarioConfig with threat_profiles but no protected_point; see D-443).

---

## Haiku — mechanical / trivial

All 11 Haiku-tier items resolved in I-8 (2026-04-29). Fixes recorded in
`.forge/defect-register.yaml` (D-444 through D-454).
`.forge/gate-proofs/I-8.yaml`. Commit: bae5a97.

**#10 mercantile and Pillow missing from pyproject.toml** — RESOLVED (D-444, I-8)
Both are imported at runtime in `app.py` for terrain tile generation but appear in no dependency group. Fresh install crashes with `ModuleNotFoundError`.

**#11 Dockerfile installs `.[dev]` not `.[dev,interface]`** — RESOLVED (D-445, I-8)
FastAPI and uvicorn are in the `interface` extra. The Docker image cannot start the API server as built.

**#17 scenario-comparison over-exports** — RESOLVED (D-446, I-8)
`index.js` exports `_parseScenarioJsText`, `_parseScenarioFile`, `_validateScenarioBPayload`, etc. alongside `init`. Architecture requires `index.js` exports only `{ init }`.

**#20 optimiser zone-gating too strict** — RESOLVED (D-447, I-8)
`prerequisites: ["terrain", "zones"]` prevents access to the optimiser until zones are defined. The backend doesn't require zones — they only affect scoring weights.

**#24 _test-module in production index.json** — RESOLVED (D-448, I-8)
The test stub is the first entry in `modules/index.json` and appears as a nav bar entry in every deployment.

**#25 scenario-comparison reads scenario_b_sim_results without declaring it in reads[]** — RESOLVED (D-436, I-7)
The manifest `reads: ["terrain", "sim_results"]` but the module calls `api.state.watch('scenario_b_sim_results', ...)`. Missing declaration makes the manifest contract misleading.

**#26 coverage-viewer dead placements declaration in manifest** — RESOLVED (D-449, I-8)
`reads: [..., "placements"]` but the module never calls `get('placements')` or `watch('placements')`. Dead manifest declaration.

**#31 SiteModel.resolution missing > 0 validator** — RESOLVED (D-450, I-8)
Zero or negative resolution passes Pydantic and reaches engine code where it is used as a divisor.

**#32 SanitiseConfig.coordinate_precision missing ge=0 bound** — RESOLVED (D-451, I-8)
Negative precision causes `round(v, -N)` — all coordinates become multiples of 10^N, producing geometrically invalid GeoJSON.

**#33 PlacementWeights missing extra="forbid"** — RESOLVED (D-452, I-8)
Unknown weight keys (e.g. typo `crital_asset`) are silently discarded. No validation error, no feedback to the caller.

**#34 Empty no-op bus subscriptions** — RESOLVED (D-453, I-8)
`gap-analysis` subscribes to `simulation:complete` with an empty body; `kill-chain-analyser` watches `terrain` with a no-op. Both generate unnecessary cleanup entries. Remove subscriptions and update manifests.

**#35 optimiser sensor_library_filter sends null instead of []** — RESOLVED (D-454, I-8)
When `constraints.allowed_sensor_ids` is absent, the POST sends `null`. Backend expects `list[str]` and may 422 or return "no sensors found".
