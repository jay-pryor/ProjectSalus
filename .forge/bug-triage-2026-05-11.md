# Bug Triage — 2026-05-11

Ad-hoc bug sweep across the repo (six parallel review agents: two silent-failure hunters,
module-architecture reviewer, two general-purpose logic/security hunters, type-design
analyzer). Findings here are NOT yet in `.forge/defect-register.yaml` — they need to be
folded into the formal Forge workflow (logged before fixing, gate-proof on fix).

Triage routes each finding to **Opus** (complex reasoning, architectural decisions,
algorithmic semantics, security policy) or **Sonnet** (well-scoped mechanical fixes
where the patch shape is obvious from the description). Severity uses the project
convention: critical / high / medium / low.

---

## Counts

| Severity | Opus | Sonnet | Total |
|----------|------|--------|-------|
| critical | 2    | 0      | 2     |
| high     | 7    | 5      | 12    |
| medium   | 7    | 28     | 35    |
| low      | 0    | 27     | 27    |
| **total**| **16** | **60** | **76** |

(Several lower-value findings — pure style, theoretical edge cases that the agents
self-withdrew, and items already covered by deferred defects — were dropped.)

---

## OPUS TRACK — architectural / algorithmic / policy

These need judgment calls or multi-file reasoning. Hand to Opus.

### O-1 [CRITICAL] Module panels and map layers never re-mount on second activation
- **File:** `src/salus/viewer/interface/mode-manager.js:93-106` + every `modules/*/index.js`
- **Symptom:** `init()` runs once per session (guarded by `initialised.add(moduleId)`). Re-activating any module after first deactivation leaves the panel empty and the map layers gone. Affects 13 modules.
- **Why Opus:** Two viable architectures (split init/mount, or make init idempotent and adjust every module). Decision touches 13 modules + tests + the mode-manager contract. Needs end-to-end reasoning about what state survives a deactivate/activate cycle.

### O-2 [CRITICAL] `optimiser:apply` silently dropped — placements never merged
- **File:** `src/salus/viewer/interface/modules/optimiser/index.js:520` (emitter) + `placement-editor/index.js` (subscriber)
- **Symptom:** The Apply button emits `optimiser:apply` while placement-editor is, by mode-manager design, NOT active — so its bus subscription is already torn down. The modal closes, ghost markers vanish, user believes Apply succeeded; `placements` state is unchanged. Same pattern affects `placement:pending` from library-browser, gap-analysis, coverage-viewer.
- **Why Opus:** Three possible fixes (eager-init all modules, persistent bus subscriptions across unmount, move merge logic out of placement-editor) each have different implications for the isolation contract. D-5159 already deferred the "errored init" sub-case; this is the broader pattern.

### O-3 [HIGH] `compute_viewshed_through_canopy` perimeter cells silently stay transmission=0
- **File:** `src/salus/engine/viewshed.py:219, 233-271`
- **Symptom:** `transmission` initialised to zeros; canopy ray-march sweeps `max(360, 4*max(rows,cols))` angles and only updates cells the rounded ray steps through. Cells that the binary viewshed (`compute_viewshed`) marks visible but that fall between integer-rounded ray paths silently stay 0.0 ("fully blocked"), distinct from terrain-blocked. Coverage layers shrink at the perimeter without warning.
- **Why Opus:** Algorithm-level fix — needs reasoning about whether to initialise `transmission = binary.astype(float32)` and *reduce* along rays, or rebuild the ray pattern to guarantee coverage of every binary-visible cell. Either choice changes the canopy attenuation semantics; tests must be updated accordingly.

### O-4 [HIGH] `compute_viewshed_through_canopy` carries `t_ray` across terrain-blocked cells
- **File:** `src/salus/engine/viewshed.py:250-251`
- **Symptom:** When the ray hits a terrain-blocked cell, `continue` skips it but does **not** reset `t_ray`. A second visible cell beyond the occluder receives a transmission value contaminated by canopy along an irrelevant geometric path.
- **Why Opus:** Same algorithm as O-3; coherent fix needs paired reasoning. Reset on `binary[ri,ci] == False` is the obvious patch but the broader question (re-init transmission?) ties them together.

### O-5 [HIGH] PDF report renders blank sections silently — broad-except in render helpers
- **File:** `src/salus/report/pdf.py:639-641, 660, 706, 744`
- **Symptom:** `_render_to_b64`, `_render_gap_map_to_b64`, `_render_kill_chain_chart_to_b64`, `_render_saturation_chart_to_b64` all wrap rendering in `except Exception → log warning → return None`. The PDF then renders with `None` substituted for the missing image, the section is skipped, and `render_pdf` returns Path. For a defence proposal output this is the textbook "looks complete, isn't" failure mode.
- **Why Opus:** Policy question: which sections are critical? (Coverage map probably must-have; kill-chain chart maybe optional.) Need to design a `ReportData.section_failures: list[str]` channel and decide raise-vs-stamp-on-PDF per section.

### O-6 [HIGH] Boundary load failure silently inflates coverage percentage
- **File:** `src/salus/cli.py:534-536, 2148-2154, 2328-2329`
- **Symptom:** Three CLI commands (`simulate`, `report`, `viewer`) catch boundary-load exceptions and fall back to `bitmask = np.ones(...)` (full DEM as boundary). The coverage-stats denominator silently grows from the intended boundary area to the entire DEM — a 45% coverage scenario reports as 78%. Only viewer command echoes a warning to stdout; report and simulate just log it.
- **Why Opus:** Defence-proposal integrity issue. Policy decision: abort with non-zero exit, or render with an unmissable "DENOMINATOR-CHANGED" stamp in the PDF/viewer. Touches three CLI commands plus the stats payload contract.

### O-7 [HIGH] `salus interface --host` accepts `0.0.0.0` with no warning; API has no auth
- **File:** `src/salus/cli.py:2398-2403, 2439-2477` + `src/salus/interface_api/app.py:8` (docstring contract)
- **Symptom:** `app.py` docstring declares "localhost-only service: CORS restricted, no authentication required." CLI lets operator bind to any address. CORS is irrelevant for non-browser callers. `POST /api/terrain/load` accepts 500 MB uploads; `POST /api/simulate` triggers GB-scale NumPy work — all unauthenticated to any network peer once the operator types `--host 0.0.0.0`.
- **Why Opus:** Security policy decision (refuse non-localhost by default? require `--allow-public`? add token auth?). Affects the operational story for remote deployments.

### O-8 [HIGH] Sanitiser does not redact `sensor_library` / `effector_library` in packaged viewer
- **File:** `src/salus/viewer/sanitise.py:69-140` + `src/salus/viewer/export.py:763, 805`
- **Symptom:** `_range_band` and `_RANGE_BANDS` exist (lines 36, 148) and the module docstring promises "exact range values replaced with band categories at REDACTED level." But no caller invokes the helper, and `sanitise_for_export` does not touch the embedded `sensor_library`/`effector_library` payloads that `_load_sensor_library` reads from the full sensor YAML (including `max_range_m`, vendor fields). A REDACTED customer-delivered viewer ships the full proprietary sensor DB.
- **Why Opus:** Contract design — decide what "redacted" means (per-placement override stripped? sensor-model ranges banded? whole library swapped for a public-fields whitelist?). Touches the customer-delivery story.

### O-9 [HIGH] `validateScenarioPayload` only checks key names — values written to state without escaping
- **File:** `src/salus/viewer/interface/shell.js:162-181` + `applyScenarioPayload`
- **Symptom:** Load Scenario validates only that JSON keys are a subset of `SCENARIO_KEYS`, then writes every value into state. A crafted `.salus.json` with HTML/JS payload in sensor `name` fields reaches downstream renderers that the existing CSP/CORS controls don't cover (Load Scenario bypasses the fetch path).
- **Why Opus:** Schema design decision — JSON-schema validation per key, vs centralised HTML-escape on render. Affects the entire scenario-load contract.

### O-10 [MEDIUM] Unbounded thread spawn per `/api/simulate` request — trivial DoS
- **File:** `src/salus/interface_api/app.py:64-65, 1100-1126`
- **Symptom:** Each simulate request spawns `Thread(daemon=True)` with no pool/semaphore. Ten concurrent valid requests OOM-kill the process; combined with O-7 (`--host 0.0.0.0`), reachable from any peer.
- **Why Opus:** Concurrency design — asyncio Semaphore, thread pool with bounded queue, or per-session worker. Choice depends on session/auth model decisions from O-7.

### O-11 [MEDIUM] `state.js` synchronous re-entrancy unguarded
- **File:** `src/salus/viewer/interface/state.js:121-122` and `_notify`
- **Symptom:** `set()` synchronously calls `_notify`; a watcher can `set` again; nested calls run depth-first with no detection. Two modules listening to each other's keys can hang the tab silently. No live infinite loop today, but no guard either.
- **Why Opus:** Design choice — batch notifications (microtask), re-entrancy Set guard, or accept and document. Affects every module's watcher contract.

### O-12 [MEDIUM] PDF template syntax errors silently drop entire sections
- **File:** `src/salus/report/pdf.py:347`
- **Symptom:** `TemplateError` → warning log → section dropped. The PDF still renders, missing kill_chain / saturation / threat_analysis depending on which template broke. Caller has no programmatic signal.
- **Why Opus:** Same family as O-5 — needs section-criticality policy.

### O-13 [MEDIUM] `placement-editor` modal double-applies when used with Optimiser's Apply
- **File:** `src/salus/viewer/interface/modules/placement-editor/index.js:735-745`
- **Symptom:** placement-editor's `optimiser:complete` listener spawns its own modal with its own Apply button. The optimiser also has its own Apply. Both can fire in one session and double-merge placements. D-470 deferred this.
- **Why Opus:** UX architecture decision — which path owns Apply?

### O-14 [MEDIUM] Untrusted scenario YAML can resolve paths outside scenario directory
- **File:** `src/salus/ingest/scenario.py:111-118`
- **Symptom:** After D-179/D-180/D-181 (logged), `_PATH_FIELDS` still resolves `"../../../etc/passwd"` and returns the resolved path. The `interface_api/app.py::_validate_dem_path` adds containment, but the standalone CLI does not.
- **Why Opus:** Trust model — should scenario YAMLs from disk be trusted? Add containment in ingest, or only in the API boundary?

### O-15 [MEDIUM] `compute_viewshed_through_canopy` observer cell forced to 1.0 even when observer is under canopy
- **File:** `src/salus/engine/viewshed.py:269`
- **Symptom:** Observer's own cell transmission = 1.0 unconditionally. If `canopy_height_m[obs_row, obs_col] > observer_height`, the sensor is physically buried under tree canopy but the transmission map says "self-cell unobscured" — conceals operator misconfiguration.
- **Why Opus:** Modelling decision — flag, downgrade transmission, or refuse placement. Algorithm-coupled with O-3/O-4.

### O-16 [MEDIUM] Canopy attenuation conflates 2D cell traversal with 3D LOS path
- **File:** `src/salus/engine/viewshed.py:233-271`
- **Symptom:** `t_ray *= penetration**(ch/10.0)` for every visible canopy cell, regardless of where the 3D LOS ray passes vertically through the cell. A ray skimming the canopy top vs trunk-piercing get identical penalty. Likely a deliberate simplification — but undocumented and worth a steer-vs-fix decision.
- **Why Opus:** Modelling fidelity decision; if deliberate, document.

---

## SONNET TRACK — well-scoped mechanical fixes

Each is a one-to-few-line change with the patch shape clear from the symptom. Group fixes
into one task per area when feasible.

### Engine — coordinate / numerical guards (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-1 | M | `src/salus/engine/viewshed.py:344-348` & `engine/trajectory.py:587-593` (`_xy_to_rc`, `_row_col`) | Replace `int(...)` with `math.floor(...)` — half-cell west/south of origin silently maps to (0,0) and passes the bounds guard. |
| S-2 | M | `src/salus/engine/saturation.py:312-316` | Regression: code now `raise ValueError(...)`; D-187 resolution claims it should `log warning + return zero-capacity SaturationResult`. Restore the resolved behaviour. |
| S-3 | M | `src/salus/engine/saturation.py:67-77` (`_sample_dem_elevation`) | Raise `ValueError` or return NaN instead of silently returning 0.0 for nodata DEM cells. |
| S-4 | M | `src/salus/engine/rf_propagation.py:425-430` | Add `math.isfinite(sensor_agl)` guard before computing `sensor_abs_h` (parity with `dispatcher.py:85` / `placement.py:344-354`). |
| S-5 | M | `src/salus/engine/coverage.py:144` (`compute_layer_coverage`) | After shape check, warn when `cov` is floating and contains non-finite cells (NaN silently buckets as uncovered). |
| S-6 | M | `src/salus/engine/comparison.py:192-202` (`compare_configs`) | Raise on NaN composite instead of `nan_to_num + warning` — match `build_gap_analysis` policy. |
| S-7 | M | `src/salus/engine/path_planner.py:341-365` | Fallback trajectory uses lowest altitude band; accept explicit `asset_z_agl` and pass to `_cell_centroid`. |
| S-8 | L | `src/salus/engine/kill_chain.py:71` | Distinguish `first_det_range is None` (never detected) from `== 0.0` (detected at impact); split log + add `detected_at_impact` field. |
| S-9 | L | `src/salus/engine/kill_chain.py:89, 95` | Asymmetric `>=` vs `>` for `engagement_feasible` and `second_engagement_possible`; pick one. |
| S-10 | L | `src/salus/engine/acoustic.py:87-91` | Warn when `effective_range` collapses to ≤ 0 because of extreme `ambient_noise_db`. |
| S-11 | L | `src/salus/engine/placement.py:156-157` (`generate_candidate_positions`) | Upper edge cells never sampled because of `step_m/2` offset start; use cell-centred sampling. |
| S-12 | L | `src/salus/engine/kill_chain.py:177-197` | Remove `_required_time = required_time` alias (maintenance trap). |

### Ingest / models / data contracts (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-13 | M | `src/salus/models/scenario.py:106` | Warn when `data.pop("trajectory", None)` discards a non-None value (silent YAML key drop). |
| S-14 | M | `src/salus/ingest/boundaries.py:282-289` (`_collect_polygons`) | Count features skipped for null geometry; warn if > 50% dropped. |
| S-15 | M | `src/salus/ingest/boundaries.py:20, 79` (`load_boundary`) | Return type declares `Polygon` but `_reproject_geometry` can yield `MultiPolygon`. Either widen the type and update callers, or re-extract largest polygon after reproject. |
| S-16 | L | `src/salus/models/scenario.py:199-204` (`_protected_point_finite`) | Warn when protected_point is `(0.0, 0.0)` (common YAML default sentinel). |
| S-17 | L | `src/salus/models/saturation.py:104-118` (`SaturationScenario.targets`) | Warn on duplicate `approach_vector` entries (likely YAML typo). |
| S-18 | L | `src/salus/models/threat.py:96` (`DroneTrajectory`) | Validator: warn on consecutive waypoints with zero spatial distance. |
| S-19 | L | `src/salus/models/site.py:42-44` (`_validate_resolution`) | Reject subnormal resolutions (`< 1e-6`). |
| S-20 | L | `src/salus/models/site.py:118-124` (`extent`) | model_validator: ensure `cols * resolution` is finite. |
| S-21 | L | `src/salus/ingest/sensors.py:20-51` (`_load_yaml_records`) | Cast or narrow `dict[Any, Any]` after YAML load — declared return `list[dict[str, Any]]` is a lie. |
| S-22 | L | `src/salus/ingest/boundaries.py:144-151` | Whitespace-only zone names produce confusing error chain; strip and re-check before passing to Zone(). |

### Engine — type design (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-23 | H | `src/salus/engine/path_planner.py:111-113` | `effective_bands = _DEFAULT_ALTITUDE_BANDS_M` shares module-level list by reference; wrap in `list(...)`. Callers can mutate the default for the rest of the process. |
| S-24 | M | `src/salus/interface_api/app.py:356-391` (`_get_sensor_defs`, `_get_effector_defs`) | Return type `list[X]` but cache annotation includes `None`; assert non-None or `return _sensor_cache or []`. |
| S-25 | M | `src/salus/report/maps.py:48, 71, 107` (`render_coverage_map`, `_hillshade`) | Bare `np.ndarray` then `~coverage`; annotate `npt.NDArray[np.bool_]` and add explicit dtype guard. |
| S-26 | M | `src/salus/viewer/export.py:99` (`ViewerData.sensor_placements`) | `Any` is a type lie — every downstream caller assumes a dict. Annotate `dict[str, Any]`. |
| S-27 | M | `src/salus/engine/threat_corridor.py:186, 225-229` (`find_worst_corridors`) | Either widen `protected_point: tuple[float, float]` to `... | None` to match the dead None guard, or drop the guard. |
| S-28 | L | `src/salus/engine/coverage.py:330` (`compute_coverage_stats`) | `zones: list` → `zones: list[Zone]`. |
| S-29 | L | `src/salus/models/site.py:23, 26, 30` | DEM/DSM/canopy_height_m as bare `np.ndarray`; add dtype-kind check `np.issubdtype(v.dtype, np.floating)` in validator. |
| S-30 | L | `src/salus/interface_api/app.py:450, 461` (`_parse_ui_zones`) | Return `list[Any]` → `list[Zone]`. |

### Report / charts / maps (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-31 | M | `src/salus/report/charts.py:170-175` (`render_kill_chain_chart`) | Non-finite margin produces a misleadingly "feasible-looking" bar; draw a red error indicator instead of bare `continue`. |
| S-32 | M | `src/salus/report/charts.py:480-516` (firing/reload loop) | Subnormal `reaction_time_s` could cause `t + reaction_s == t` infinite loop; cap iteration count. |
| S-33 | M | `src/salus/report/maps.py:1487-1499` (`cost_rgba` build) | NaN cells in `cost_2d` render as transparent — empty detection density; `np.clip` + NaN guard. |
| S-34 | L | `src/salus/report/maps.py:201-202, 221-222, 711-712, 849-850, 1018-1019, 1047-1048, 1187-1188, 1371-1372, 1407-1408, 1562-1563, 1599-1600` | All `except Exception: warnings.warn` for legend/scalebar/colorbar — add `_log.warning(...)` in parallel so non-interactive runs see it. |
| S-35 | L | `src/salus/report/charts.py:381` | `unengaged > 0` colour map; NaN cells silently coloured green ("engaged"). Filter or warn on non-integer values. |
| S-36 | L | `src/salus/report/maps.py:1287` | Degenerate detection-time normalisation (all identical) renders all-red lines indistinguishably from real high-threat; warn when range is zero. |

### Viewer / export (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-37 | M | `src/salus/viewer/export.py:198` | `gaps_arr = ~sim_results.composite` fallback ignores boundary; call `compute_gaps(composite, full_bitmask)` for consistency with the PDF path. |
| S-38 | M | `src/salus/viewer/export.py:431-437` | Validate `fill_value` is finite and reasonable; warn on extreme. |
| S-39 | M | `src/salus/viewer/export.py:462-467` | `finally` block silently substitutes `fill_value` for NaN edge artefacts; log when NaN-fix count > 0. |
| S-40 | M | `src/salus/viewer/export.py:476-487` (`_encode_terrarium`) | `np.clip` to `[0, 65535.999]` silently flattens out-of-range elevations; warn when `np.any((elevation < -32768) | (elevation > 32767))`. |
| S-41 | M | `src/salus/viewer/export.py:828-835` (`_load_sensor_library`) | Missing `type:` key bucketed silently into "Unknown"; warn. |
| S-42 | M | `src/salus/viewer/sanitise.py:171-177` (`_round_coords_recursive`) | Passes non-list scalars through unmodified; warn on unexpected leaf shape. |
| S-43 | M | `src/salus/viewer/sanitise.py:205-212` (`_redact_stats`) | Crashes whole sanitiser when `per_layer_coverage_pct` is not a dict; add isinstance guard. |
| S-44 | L | `src/salus/viewer/sanitise.py:94` | `tuple(...)` of rounded `bounds_wgs84` doesn't guarantee 4-element arity. |
| S-45 | L | `src/salus/viewer/sanitise.py:147-153` (`_range_band`) | NaN value silently falls through to `return "long"`. (Note: function is currently unreferenced — see O-8.) |
| S-46 | L | `src/salus/viewer/export.py:551-554` (`_degrees_per_metre`) | Custom-CRS misclassified as geographic causes 111000× simplification error; defensive validation. (Function may also be dead — verify.) |
| S-47 | L | `src/salus/viewer/export.py:618-643` (`_compute_corridor_path_wgs84`) | Add `math.isfinite` guard around `transformer.transform` output (parity with `_build_sensor_geojson`). |

### CLI / API service (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-48 | M | `src/salus/interface_api/app.py:497-500` (`_parse_entry`) | Broad `except Exception` swallows zone-parse failures; return per-zone failure list to caller. |
| S-49 | M | `src/salus/interface_api/app.py:690-692, 802-804` | SSE error event packs only `str(exc)` — uninterpretable for the client. Include exception type and short traceback. |
| S-50 | M | `src/salus/interface_api/app.py:963-966` | Per-tile reproject failure logged at DEBUG only; elevate to WARNING or count and warn if >threshold. |
| S-51 | M | `src/salus/interface_api/app.py:1395-1400` | Unknown sensor-type key silently dropped from per-layer stats; surface skipped key count to caller. |
| S-52 | M | `src/salus/interface_api/app.py:1410-1418` (`_num`) | When every candidate key is non-numeric, silently returns default 0.0 → "0% coverage". Track whether any key parsed; warn if none did. |
| S-53 | M | `src/salus/cli.py:1700-1707` | Comparison DEM/composite shape-mismatch warning goes to `_log.warning` only; also `click.echo(err=True)`. |
| S-54 | M | `src/salus/cli.py:2442-2460` | `salus interface --scenario` swallows pre-load exception; CLI exits 0 with corrupt scenario. Make scenario-load failure fatal when `--scenario` was explicitly provided. |
| S-55 | M | `src/salus/interface_api/app.py:244, 1141-1143` (`OptimiserRequest.terrain`) | Empty string passes Pydantic, resolves to CWD which may pass the allowlist guard. Add `field_validator` rejecting empty string. |
| S-56 | M | `src/salus/interface_api/app.py:1730-1754` | `GET /api/terrain/sessions/latest` returns absolute `dem_path`/`dsm_path`; drop from response payload. |
| S-57 | M | `src/salus/interface_api/app.py:1283, 1561` | `HTTPException(detail=str(exc))` leaks raw exception strings (rasterio/shapely paths) to client; return generic detail, keep verbose in log. |
| S-58 | M | `src/salus/interface_api/app.py:1530, 1545` (`terrain_load`) | Size guard reads entire upload into memory before checking; stream with chunked read and threshold-check inline. |
| S-59 | M | `src/salus/cli.py:1895-1896` (`_gen_executive_summary`) | Bare `except Exception: return ""` with no log; add `_log.warning(...)`. |
| S-60 | L | `src/salus/interface_api/app.py:62, 368, 387` | Sensor/effector cache retries on every request after a persistent failure; rate-limit the warning or short-cache failure. |
| S-61 | L | `src/salus/interface_api/app.py:914-918` | DEM EPSG lookup failure logged at DEBUG only; elevate so misregistration cause is visible. |
| S-62 | L | `src/salus/interface_api/app.py:1854-1859` | StaticFiles mount exposes `tests/`, `package.json`, `deploy-minimal.sh`; restrict to client-facing files. |
| S-63 | L | `src/salus/interface_api/app.py:1485-1494` | `tmp_pdf.unlink` permission error masks the original render exception; wrap unlink in its own try. |
| S-64 | L | `src/salus/cli.py:1898-1904` (`_read_b64`) | Missing file and OSError indistinguishable; log warning on OSError. |
| S-65 | L | `src/salus/cli.py:2459-2460` | Interface pre-load failure uses `click.echo` to stdout (no `err=True`, no `_log`). |
| S-66 | L | `src/salus/cli.py:2469-2472` | `webbrowser.open` return value ignored; echo fallback URL when it returns False. |

### JS interface modules (Sonnet)

| ID  | Sev | File:line | One-line fix |
|-----|-----|-----------|--------------|
| S-67 | H | `src/salus/viewer/interface/modules/zone-editor/index.js:862-867` | Watch `if (!val) return;` leaves stale zones drawn after scenario without `zones:` field; replace with `const safe = val ?? { priority: [], exclusion: [] };` and run rebuild. |
| S-68 | H | `src/salus/viewer/interface/modules/threat-corridor-editor/index.js:817-826` | Same pattern as S-67 with `threat_corridors`. |
| S-69 | H | `src/salus/viewer/interface/map-proxy.js:138-143` | `setLayoutProperty`/`setPaintProperty` skip `assertPrefix`; documented isolation invariant unenforced. |
| S-70 | M | `src/salus/viewer/interface/modules/simulation-runner/index.js:558-565` | Mid-flight abort suppresses both `complete` and `failed`; emit `simulation:failed` with `{error:'aborted'}` or define `simulation:cancelled`. |
| S-71 | M | `src/salus/viewer/interface/modules/placement-editor/index.js:534-540` | `selectedIndex` updated after `api.state.set('placements', ...)`; render uses stale index. Update index before set. |
| S-72 | L | `src/salus/viewer/interface/modules/saturation-analyser/index.js:453-458` | Slider snaps back to 1 on every `simulation:complete`; only reset when threshold/capacity actually changes. |
| S-73 | L | `src/salus/viewer/interface/modules/coverage-viewer/index.js:740-744` | `simulation:complete` bus handler is redundant with state watch; remove or accept event payload. |
| S-74 | L | `src/salus/viewer/interface/shell.js:362-367` | `library-load-error` fires when SALUS_DATA fallback delivered an empty library by design; check whether fetch actually failed. |
| S-75 | L | `src/salus/viewer/interface/shell.js:134-153` (`saveScenario`) | Blob URL leaked if `a.click()` throws; wrap in try/finally and revoke unconditionally. |

---

## Notes

- **Workflow:** When picking these up, log each to `.forge/defect-register.yaml` with the
  next D-NNN ID (highest existing is D-478) BEFORE fixing, per CLAUDE.md.
- **Verification:** Several findings (S-45 `_range_band` unused, S-46 `_degrees_per_metre`
  unused) should be `grep`-verified for live callers before deletion.
- **Algorithm coupling:** O-3, O-4, O-15, O-16 all touch `compute_viewshed_through_canopy`
  — handle as one canopy-attenuation overhaul rather than four separate patches.
- **Critical-pair coupling:** O-1 (panel re-mount) and O-2 (optimiser:apply) both stem
  from the same architectural assumption that modules re-init cleanly; design them
  together.
- **Security cluster:** O-7, O-8, O-9, O-10 together define the deployment threat model
  and should be decided as one policy pass before patching.
