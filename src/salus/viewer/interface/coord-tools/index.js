/**
 * coord-tools/index.js — Coordinate-tools shell-owned subsystem.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.9 (Shell-Owned
 * Subsystems).
 *
 * The coordinate tools must be usable regardless of which module is active,
 * so they are NOT a navigable module — a module exists only while it is the
 * active panel. They are a shell-owned subsystem: the shell instantiates this
 * component once at startup, renders it into the permanent `#coord-toolbar`
 * chrome, and gives it its own scoped map proxy
 * (`createMapProxy(map, 'coord-tools', { allowTerrainQuery: true })`) so any
 * map layers it adds are prefix-enforced (`coord-tools:*`). It is not gated by
 * the mode manager and persists across module navigation.
 *
 * Tasks:
 *   - I-20 — toolbar shell + shell-owned subsystem skeleton (done).
 *   - I-21 — resettable origin point + live X/Y/Z cursor readout (done).
 *   - I-22 — two-point distance measurement (this file).
 *   - I-23 — toggleable coordinate grid overlay (Grid stub still disabled).
 *
 * I-21 — coordinate frame: a local tangent-plane frame anchored at the origin.
 * `X` is metres east, `Y` is metres north, both relative to the origin; `Z` is
 * the ground elevation sampled from the 3D terrain. This is a viewer-local
 * frame (sub-metre accurate within a few km — ample for a cUAS site), not the
 * DEM's projected CRS.
 */

/** Layer-ID prefix every map layer this subsystem owns must carry. */
export const COORD_TOOLS_LAYER_PREFIX = 'coord-tools';

/** Placeholder shown wherever a coordinate value is not available. */
const VALUE_PLACEHOLDER = '—'; // em dash

// --- Local tangent-plane conversion constants (I-21 design point 1) ---------

/** Mean Earth radius in metres — the `R` of the tangent-plane projection. */
const EARTH_RADIUS_M = 6_371_000;

/** Degrees-to-radians factor. */
const DEG_TO_RAD = Math.PI / 180;

// --- Origin indicator map layer ---------------------------------------------

/** Shared id of the origin GeoJSON source and its circle layer. */
const ORIGIN_ID = 'coord-tools:origin';

/** Paint for the origin circle — a bright cored target with a white ring. */
const ORIGIN_PAINT = Object.freeze({
  'circle-radius': 7,
  'circle-color': '#ff3b3b',
  'circle-opacity': 0.9,
  'circle-stroke-width': 2.5,
  'circle-stroke-color': '#ffffff',
});

// --- Measure tool map layers (I-22) -----------------------------------------

/**
 * Single GeoJSON source carrying both the line and the point features for the
 * measure tool. Two layers filter the same source by `$type`, matching the
 * pattern used by `threat-corridor-editor`. One source means a single setData
 * keeps the line and the markers atomically in sync.
 */
const MEASURE_SOURCE = 'coord-tools:measure-source';
const MEASURE_LINE_LAYER = 'coord-tools:measure-line';
const MEASURE_POINTS_LAYER = 'coord-tools:measure-points';

const MEASURE_LINE_PAINT = Object.freeze({
  'line-color': '#ffe066',
  'line-width': 2,
  'line-opacity': 0.95,
});

const MEASURE_POINT_PAINT = Object.freeze({
  'circle-radius': 5,
  'circle-color': '#ffe066',
  'circle-opacity': 0.95,
  'circle-stroke-width': 2,
  'circle-stroke-color': '#1a1a2e',
});

// --- Toolbar control labels -------------------------------------------------

const SET_ORIGIN_LABEL = 'Set origin';
const PICK_CANCEL_LABEL = 'Cancel';
const MEASURE_LABEL = 'Measure';
const MEASURE_CANCEL_LABEL = 'Cancel';
const CLEAR_LABEL = 'Clear';

/**
 * Disabled tool-control stubs — filled in by the named later task. `tool` is
 * the stable `data-tool` hook. (Set origin is a live control from I-21 and
 * Measure is a live control from I-22; both are built separately, below.)
 */
const TOOL_STUBS = [
  { tool: 'grid', label: 'Grid', task: 'I-23' },
];

// ---------------------------------------------------------------------------
// Local tangent-plane conversion (exported — pure, unit-tested directly)
// ---------------------------------------------------------------------------

/**
 * Convert a lng/lat to local tangent-plane X/Y metres relative to an origin.
 *
 *   X = (lng − lng0)·(π/180)·R·cos(lat0)   metres east
 *   Y = (lat − lat0)·(π/180)·R             metres north
 *
 * @param {[number, number]} lngLat - cursor [lng, lat] in degrees
 * @param {[number, number]} originLngLat - origin [lng, lat] in degrees
 * @returns {{x: number, y: number}} metres east / north of the origin
 */
export function lngLatToLocalXY(lngLat, originLngLat) {
  const [lng, lat] = lngLat;
  const [lng0, lat0] = originLngLat;
  const x =
    (lng - lng0) * DEG_TO_RAD * EARTH_RADIUS_M * Math.cos(lat0 * DEG_TO_RAD);
  const y = (lat - lat0) * DEG_TO_RAD * EARTH_RADIUS_M;
  return { x, y };
}

/**
 * I-22 — compute the local-frame deltas and totals for a two-point measurement.
 *
 * Both endpoints are projected to the local tangent plane anchored at the
 * coord-tools origin, then ΔX/ΔY are the eastward/northward component
 * distances and ΔZ the ground-elevation difference. The headline total is the
 * 3D slant `√(ΔX²+ΔY²+ΔZ²)`; the 2D horizontal `√(ΔX²+ΔY²)` is always shown.
 *
 * When either endpoint's elevation is unavailable (off-tile, no terrain
 * loaded, or the query threw) `hasZ` is false; `dz` and `slant3d` are then
 * null and the headline falls back to `hyp2d`, labelled as 2D by the caller.
 *
 * @param {[number, number]} a            - first endpoint [lng, lat]
 * @param {[number, number]} b            - second endpoint [lng, lat]
 * @param {[number, number]} originLngLat - the coord-tools origin [lng, lat]
 * @param {number | null}    zA           - ground elevation at `a` in metres
 * @param {number | null}    zB           - ground elevation at `b` in metres
 * @returns {{
 *   dx: number, dy: number, dz: number | null,
 *   hyp2d: number, slant3d: number | null, hasZ: boolean
 * }}
 */
export function measurePair(a, b, originLngLat, zA, zB) {
  const pa = lngLatToLocalXY(a, originLngLat);
  const pb = lngLatToLocalXY(b, originLngLat);
  const dx = pb.x - pa.x;
  const dy = pb.y - pa.y;
  const hyp2d = Math.hypot(dx, dy);
  const hasZ = Number.isFinite(zA) && Number.isFinite(zB);
  const dz = hasZ ? zB - zA : null;
  const slant3d = hasZ ? Math.hypot(dx, dy, dz) : null;
  return { dx, dy, dz, hyp2d, slant3d, hasZ };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** True when `terrain` carries a usable [lon, lat] centre. */
function _hasCentre(terrain) {
  return (
    terrain != null &&
    Array.isArray(terrain.centre_wgs84) &&
    terrain.centre_wgs84.length === 2 &&
    terrain.centre_wgs84.every((n) => typeof n === 'number' && Number.isFinite(n))
  );
}

/** True when both lng and lat are finite numbers (D-607 / D-608). */
function _isFiniteLngLat(lng, lat) {
  return Number.isFinite(lng) && Number.isFinite(lat);
}

/** Format a metre value for the readout (rounded integer + unit). */
function _formatMetres(value) {
  return `${Math.round(value)} m`;
}

// One-time latch so the requestAnimationFrame-fallback warning (D-609) is
// emitted at most once per process rather than once per subsystem instance.
let _rafFallbackWarned = false;

// One-time latch for the drawmode underflow warning, same shape.
let _drawModeUnderflowWarned = false;

/** Build the origin-point GeoJSON Feature for a [lng, lat]. */
function _originFeature(lngLat) {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lngLat[0], lngLat[1]] },
    properties: {},
  };
}

// ---------------------------------------------------------------------------
// Subsystem factory
// ---------------------------------------------------------------------------

/**
 * Instantiate the coord-tools subsystem and render its toolbar.
 *
 * @param {HTMLElement} toolbarEl - the permanent `#coord-toolbar` element the
 *   subsystem renders into (shell chrome — never the module panel slot).
 * @param {{
 *   map: object,
 *   state: {get: Function, set: Function, getTerrain: Function, watchTerrain: Function},
 *   bus: {on: Function}
 * }} api - the shell-built handle. `map` is a `coord-tools`-prefixed scoped map
 *   proxy (with `queryTerrainElevation`). `state` reads/writes the shell-owned
 *   `coord_tools` key (`get`/`set`) and gives read-only observation of the
 *   `terrain` key (`getTerrain`/`watchTerrain`) so the origin can default to
 *   the terrain centre. `bus.on` is a subscribe-only handle on the shell bus,
 *   used by I-22 to observe `drawmode:entered` / `drawmode:exited` and keep
 *   the Measure tool mutually exclusive with module draw modes.
 * @param {Document} [doc] - injectable document (for tests).
 * @returns {{root: HTMLElement, dispose: Function}}
 */
export function createCoordTools(toolbarEl, api, doc = globalThis.document) {
  if (
    toolbarEl == null ||
    typeof toolbarEl !== 'object' ||
    typeof toolbarEl.appendChild !== 'function'
  ) {
    throw new TypeError(
      'createCoordTools(toolbarEl, …): toolbarEl must be a DOM element'
    );
  }
  if (api == null || typeof api !== 'object') {
    throw new TypeError(
      'createCoordTools(…, api, …): api must provide { map, state }'
    );
  }
  // D-604: validate the map handle carries the allowTerrainQuery opt-in, not
  // just that it is present — a regressed shell wiring (flag dropped, wrong
  // proxy) must fail here, at the cause, not later as a far-removed
  // "queryTerrainElevation is not a function" crash.
  if (api.map == null || typeof api.map.queryTerrainElevation !== 'function') {
    throw new TypeError(
      'createCoordTools(…, api, …): api.map must be a coord-tools map proxy ' +
      'created with { allowTerrainQuery: true }'
    );
  }
  // D-605: validate the state handle is the shape the JSDoc declares, so a
  // malformed handle fails at construction, not on first use.
  if (
    api.state == null ||
    typeof api.state.get !== 'function' ||
    typeof api.state.set !== 'function' ||
    typeof api.state.getTerrain !== 'function' ||
    typeof api.state.watchTerrain !== 'function'
  ) {
    throw new TypeError(
      'createCoordTools(…, api, …): api.state must provide get(), set(), ' +
      'getTerrain() and watchTerrain()'
    );
  }
  // I-22: the Measure tool's mutex with module draw modes is driven by the
  // shell bus — fail at construction if the bus handle is missing rather than
  // a far-removed crash when the first drawmode event arrives.
  if (api.bus == null || typeof api.bus.on !== 'function') {
    throw new TypeError(
      'createCoordTools(…, api, …): api.bus must provide on(event, callback)'
    );
  }

  // Animation-frame scheduler — mousemove fires far faster than the display
  // refreshes, so readout updates are coalesced to one per frame. Captured
  // once; falls back to a synchronous call where requestAnimationFrame is
  // absent (e.g. a Node test environment that has not stubbed it). D-609: the
  // fallback disables the throttle, so its selection is logged (once) rather
  // than left a silent degradation.
  let raf;
  if (typeof globalThis.requestAnimationFrame === 'function') {
    raf = globalThis.requestAnimationFrame.bind(globalThis);
  } else {
    if (!_rafFallbackWarned) {
      console.warn(
        '[coord-tools] requestAnimationFrame unavailable — cursor readout ' +
        'updates run unthrottled'
      );
      _rafFallbackWarned = true;
    }
    raf = (cb) => {
      cb();
      return 0;
    };
  }

  // ----- Toolbar DOM -------------------------------------------------------

  const root = doc.createElement('div');
  root.className = 'coord-tools';

  const label = doc.createElement('span');
  label.className = 'coord-tools-label';
  label.textContent = 'Coordinate Tools';
  root.appendChild(label);

  // Live X/Y/Z readout.
  const readout = doc.createElement('span');
  readout.className = 'coord-tools-readout';
  readout.dataset.role = 'readout';
  root.appendChild(readout);

  // "Set origin" — a live control from I-21.
  const originBtn = doc.createElement('button');
  originBtn.className = 'coord-tools-btn';
  originBtn.dataset.tool = 'set-origin';
  originBtn.dataset.active = 'false';
  originBtn.textContent = SET_ORIGIN_LABEL;
  originBtn.title = 'Set the coordinate origin: click, then click a map point';
  root.appendChild(originBtn);

  // "Measure" — a live control from I-22. Two-click measurement; mutually
  // exclusive with module draw modes (via drawmode:entered/exited).
  const measureBtn = doc.createElement('button');
  measureBtn.className = 'coord-tools-btn';
  measureBtn.dataset.tool = 'measure';
  measureBtn.dataset.active = 'false';
  measureBtn.textContent = MEASURE_LABEL;
  measureBtn.title =
    'Measure: click to enter mode, then click two map points for ΔX/ΔY/ΔZ and total distance';
  root.appendChild(measureBtn);

  // Measure deltas / totals readout — only populated once two points are set.
  const measureReadout = doc.createElement('span');
  measureReadout.className = 'coord-tools-measure-readout';
  measureReadout.dataset.role = 'measure-readout';
  measureReadout.hidden = true;
  root.appendChild(measureReadout);

  // "Clear" — visible only when at least one measure point is on the map; a
  // click removes the points/line and resets without exiting measure mode.
  const clearBtn = doc.createElement('button');
  clearBtn.className = 'coord-tools-btn';
  clearBtn.dataset.tool = 'measure-clear';
  clearBtn.textContent = CLEAR_LABEL;
  clearBtn.title = 'Clear the current measurement';
  clearBtn.hidden = true;
  root.appendChild(clearBtn);

  // Grid — disabled until I-23 wires it up.
  for (const { tool, label: text, task } of TOOL_STUBS) {
    const btn = doc.createElement('button');
    btn.className = 'coord-tools-btn';
    btn.dataset.tool = tool;
    btn.textContent = text;
    btn.disabled = true;
    btn.title = `${text} — added in ${task}`;
    root.appendChild(btn);
  }

  toolbarEl.appendChild(root);

  // ----- Subsystem state ---------------------------------------------------

  let originLngLat = null;     // [lng, lat] | null — the coordinate origin
  let pickMode = false;        // true while awaiting an origin-pick map click
  let savedCursor = null;      // canvas cursor saved on entering pick/measure
  let latestMoveEvent = null;  // most recent mousemove event (for the readout)
  let rafPending = false;      // true while a readout frame is scheduled
  let disposed = false;        // true after dispose() — guards a late frame

  // I-22 — measure tool
  let measureMode = false;     // true while in two-click measure mode
  let measurePoints = [];      // collected [lng, lat] pairs (0..2)
  let drawModeDepth = 0;       // count of active module draw modes; AC 5 mutex

  // ----- Readout -----------------------------------------------------------

  function _writeReadout(xText, yText, zText) {
    readout.textContent = `X: ${xText}  Y: ${yText}  Z: ${zText}`;
  }

  /**
   * Render the readout from a mousemove event. Shows "—" for every field when
   * no origin is set yet (no terrain loaded), and "—" for Z alone where the
   * terrain elevation is unavailable (no terrain, or the point is off-tile).
   */
  function _renderReadout(moveEvent) {
    if (originLngLat == null || moveEvent == null || moveEvent.lngLat == null) {
      _writeReadout(VALUE_PLACEHOLDER, VALUE_PLACEHOLDER, VALUE_PLACEHOLDER);
      return;
    }
    const { lng, lat } = moveEvent.lngLat;
    // D-608: a malformed cursor position (non-finite lng/lat) is treated as
    // "unavailable" — the "—" placeholder — not rendered as a "NaN m" value.
    if (!_isFiniteLngLat(lng, lat)) {
      _writeReadout(VALUE_PLACEHOLDER, VALUE_PLACEHOLDER, VALUE_PLACEHOLDER);
      return;
    }
    const { x, y } = lngLatToLocalXY([lng, lat], originLngLat);

    // D-603: queryTerrainElevation returns null when no terrain is loaded or
    // the point is outside the loaded tiles — treated as "Z unavailable".
    // D-606: it can also throw mid-terrain-teardown — caught here so a failed
    // Z query degrades Z to "—" rather than killing the whole readout.
    let zText = VALUE_PLACEHOLDER;
    try {
      const z = api.map.queryTerrainElevation(moveEvent.lngLat);
      if (typeof z === 'number' && Number.isFinite(z)) {
        zText = _formatMetres(z);
      }
    } catch (err) {
      console.warn('[coord-tools] terrain elevation query failed:', err);
    }
    _writeReadout(_formatMetres(x), _formatMetres(y), zText);
  }

  _writeReadout(VALUE_PLACEHOLDER, VALUE_PLACEHOLDER, VALUE_PLACEHOLDER);

  // ----- Origin indicator map layer ----------------------------------------

  function _removeOriginIndicator() {
    try {
      if (api.map.getLayer(ORIGIN_ID)) api.map.removeLayer(ORIGIN_ID);
      if (api.map.getSource(ORIGIN_ID)) api.map.removeSource(ORIGIN_ID);
    } catch (err) {
      console.warn('[coord-tools] failed to remove origin indicator:', err);
    }
  }

  /**
   * Render (or move) the origin indicator. Remove-then-add keeps the call
   * idempotent and re-asserts the layer on top on every origin change.
   */
  function _renderOriginIndicator(lngLat) {
    try {
      _removeOriginIndicator();
      api.map.addSource(ORIGIN_ID, {
        type: 'geojson',
        data: _originFeature(lngLat),
      });
      api.map.addLayer({
        id: ORIGIN_ID,
        type: 'circle',
        source: ORIGIN_ID,
        paint: { ...ORIGIN_PAINT },
      });
    } catch (err) {
      console.warn('[coord-tools] failed to render origin indicator:', err);
    }
  }

  // ----- Origin ------------------------------------------------------------

  /**
   * Set the coordinate origin: update the local frame anchor, persist it to
   * `coord_tools.origin_lnglat`, re-render the indicator, and recompute the
   * readout against the last cursor position. A non-finite lng/lat is rejected
   * (D-607) so a bad origin can never poison the local frame or shared state.
   */
  function _setOrigin(lngLat) {
    const lng = lngLat[0];
    const lat = lngLat[1];
    if (!_isFiniteLngLat(lng, lat)) {
      console.warn('[coord-tools] ignoring origin with non-finite lng/lat:', lngLat);
      return;
    }
    originLngLat = [lng, lat];
    // D-610 / D-611: coord_tools is initialised by the shell (startup step 7)
    // as a plain object skeleton. Anything else here — null, or a non-object
    // (string/number/array) — means that wiring regressed: warn rather than
    // silently spreading a malformed value into the state write.
    const coordTools = api.state.get();
    const isSkeleton =
      coordTools != null &&
      typeof coordTools === 'object' &&
      !Array.isArray(coordTools);
    if (!isSkeleton) {
      console.warn(
        '[coord-tools] coord_tools state is not the expected shell skeleton ' +
        'object:', coordTools
      );
    }
    api.state.set({ ...(isSkeleton ? coordTools : {}), origin_lnglat: originLngLat });
    _renderOriginIndicator(originLngLat);
    if (latestMoveEvent != null) _renderReadout(latestMoveEvent);
  }

  // ----- Pick mode ---------------------------------------------------------

  function _enterPickMode() {
    // Pick-origin and measure are both single-handler click consumers in this
    // subsystem; never let both be active at once so a click is unambiguous.
    if (measureMode) _exitMeasureMode();
    pickMode = true;
    originBtn.dataset.active = 'true';
    originBtn.textContent = PICK_CANCEL_LABEL;
    const canvas = api.map.getCanvas();
    if (canvas != null && canvas.style != null) {
      savedCursor = canvas.style.cursor;
      canvas.style.cursor = 'crosshair';
    }
  }

  function _exitPickMode() {
    pickMode = false;
    originBtn.dataset.active = 'false';
    originBtn.textContent = SET_ORIGIN_LABEL;
    const canvas = api.map.getCanvas();
    if (canvas != null && canvas.style != null) {
      canvas.style.cursor = savedCursor != null ? savedCursor : '';
    }
    savedCursor = null;
  }

  // ----- Measure tool (I-22) -----------------------------------------------

  /**
   * Read the elevation at a lng/lat from the terrain. Mirrors the readout's
   * D-606 / D-603 guards: returns null when the proxy returns null/non-finite
   * or throws (mid-terrain teardown), so the caller can treat Z as unavailable
   * rather than crash the measurement render.
   */
  function _safeQueryElevation(lngLat) {
    try {
      const z = api.map.queryTerrainElevation({ lng: lngLat[0], lat: lngLat[1] });
      if (typeof z === 'number' && Number.isFinite(z)) return z;
    } catch (err) {
      console.warn('[coord-tools] measure: terrain elevation query failed:', err);
    }
    return null;
  }

  /** Build a FeatureCollection of the current measure points + line (if 2). */
  function _measureFeatureCollection() {
    const features = [];
    for (const [lng, lat] of measurePoints) {
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [lng, lat] },
        properties: {},
      });
    }
    if (measurePoints.length === 2) {
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: measurePoints.map((p) => [p[0], p[1]]),
        },
        properties: {},
      });
    }
    return { type: 'FeatureCollection', features };
  }

  function _removeMeasureLayers() {
    try {
      if (api.map.getLayer(MEASURE_LINE_LAYER)) api.map.removeLayer(MEASURE_LINE_LAYER);
      if (api.map.getLayer(MEASURE_POINTS_LAYER)) api.map.removeLayer(MEASURE_POINTS_LAYER);
      if (api.map.getSource(MEASURE_SOURCE)) api.map.removeSource(MEASURE_SOURCE);
    } catch (err) {
      console.warn('[coord-tools] failed to remove measure layers:', err);
    }
  }

  /**
   * Render (or update) the measure source + two `$type`-filtered layers. The
   * line layer filters to LineString, the points layer to Point — one source,
   * two layers, the convention used by `threat-corridor-editor`.
   *
   * D-614 / D-615: remove-then-add every time. The fast-path setData branch
   * (real MapLibre sources expose setData; the test mock does not) made the
   * production and test code paths diverge. More importantly, a partial
   * failure (addSource OK, addLayer throws) would leave the source orphaned
   * with no points layer, and the fast path would never restore it.
   * Remove-then-add is idempotent — each call starts from a known-clean state.
   */
  function _renderMeasureLayers() {
    try {
      _removeMeasureLayers();
      const data = _measureFeatureCollection();
      api.map.addSource(MEASURE_SOURCE, { type: 'geojson', data });
      api.map.addLayer({
        id: MEASURE_LINE_LAYER,
        type: 'line',
        source: MEASURE_SOURCE,
        filter: ['==', '$type', 'LineString'],
        paint: { ...MEASURE_LINE_PAINT },
      });
      api.map.addLayer({
        id: MEASURE_POINTS_LAYER,
        type: 'circle',
        source: MEASURE_SOURCE,
        filter: ['==', '$type', 'Point'],
        paint: { ...MEASURE_POINT_PAINT },
      });
    } catch (err) {
      console.warn('[coord-tools] failed to render measure layers:', err);
    }
  }

  /**
   * Persist the measurement (or its absence) to `coord_tools.measure`. Same
   * D-610 / D-611 guard as `_setOrigin`: only write when the shell-owned
   * skeleton is the expected object shape.
   */
  function _persistMeasure(value) {
    const coordTools = api.state.get();
    const isSkeleton =
      coordTools != null &&
      typeof coordTools === 'object' &&
      !Array.isArray(coordTools);
    if (!isSkeleton) {
      console.warn(
        '[coord-tools] coord_tools state is not the expected shell skeleton ' +
        'object:', coordTools
      );
    }
    api.state.set({ ...(isSkeleton ? coordTools : {}), measure: value });
  }

  /** Format the measure readout from a completed two-point measurement. */
  function _writeMeasureReadout(result) {
    const dxText = _formatMetres(result.dx);
    const dyText = _formatMetres(result.dy);
    if (result.hasZ) {
      // AC 2 — ΔX, ΔY, ΔZ, 3D slant headline, 2D horizontal also shown.
      measureReadout.textContent =
        `ΔX: ${dxText}  ΔY: ${dyText}  ΔZ: ${_formatMetres(result.dz)}  ` +
        `3D: ${_formatMetres(result.slant3d)}  2D: ${_formatMetres(result.hyp2d)}`;
    } else {
      // AC 3 — Z unavailable: ΔZ "—" and the headline is the 2D distance,
      // labelled as such.
      measureReadout.textContent =
        `ΔX: ${dxText}  ΔY: ${dyText}  ΔZ: ${VALUE_PLACEHOLDER}  ` +
        `2D: ${_formatMetres(result.hyp2d)}`;
    }
  }

  function _updateMeasureControls() {
    measureBtn.dataset.active = measureMode ? 'true' : 'false';
    measureBtn.textContent = measureMode ? MEASURE_CANCEL_LABEL : MEASURE_LABEL;
    // AC 5 — disabled while any module draw mode is active. D-612: origin-pick
    // is structurally the same kind of click-capturing single-handler mode, so
    // the same mutex applies to it — a module click must never simultaneously
    // place a sensor/waypoint/vertex AND move the coord-tools origin.
    measureBtn.disabled = drawModeDepth > 0;
    originBtn.disabled = drawModeDepth > 0;
    clearBtn.hidden = measurePoints.length === 0;
    measureReadout.hidden = measurePoints.length !== 2;
  }

  /**
   * Clear the measurement: remove the layers, drop the points, hide the
   * readout, and persist the cleared state. Used by both Clear (stays in
   * mode) and by mode exit (called from `_exitMeasureMode`).
   */
  function _clearMeasurement() {
    measurePoints = [];
    _removeMeasureLayers();
    measureReadout.textContent = '';
    _persistMeasure(null);
    _updateMeasureControls();
  }

  function _enterMeasureMode() {
    // Mutex within the subsystem — never have both pick and measure capturing
    // the same click. The cross-module mutex (AC 5) is handled separately.
    if (pickMode) _exitPickMode();
    // Start a fresh measurement on every entry.
    measurePoints = [];
    _removeMeasureLayers();
    measureReadout.textContent = '';
    _persistMeasure(null);
    measureMode = true;
    const canvas = api.map.getCanvas();
    if (canvas != null && canvas.style != null) {
      savedCursor = canvas.style.cursor;
      canvas.style.cursor = 'crosshair';
    }
    _updateMeasureControls();
  }

  function _exitMeasureMode() {
    if (!measureMode) return;
    measureMode = false;
    const canvas = api.map.getCanvas();
    if (canvas != null && canvas.style != null) {
      canvas.style.cursor = savedCursor != null ? savedCursor : '';
    }
    savedCursor = null;
    // AC 4 — exiting measure mode clears.
    _clearMeasurement();
  }

  /**
   * Append a measure point. The first click drops a marker; the second click
   * drops the line + second marker and renders the readout.
   */
  function _addMeasurePoint(event) {
    if (!measureMode) return; // defence-in-depth — caller (handleMapClick) already gates
    if (event == null || event.lngLat == null) return;
    const { lng, lat } = event.lngLat;
    if (!_isFiniteLngLat(lng, lat)) {
      console.warn('[coord-tools] measure: ignoring non-finite click:', event.lngLat);
      return;
    }
    if (measurePoints.length >= 2) return; // defensive — clear on entry, but be safe
    measurePoints.push([lng, lat]);
    _renderMeasureLayers();
    if (measurePoints.length === 2) {
      if (originLngLat == null) {
        // No origin yet — distances are not meaningful in the local frame.
        // Show placeholders; the measurement persists for visual reference.
        measureReadout.textContent =
          `ΔX: ${VALUE_PLACEHOLDER}  ΔY: ${VALUE_PLACEHOLDER}  ` +
          `ΔZ: ${VALUE_PLACEHOLDER}  2D: ${VALUE_PLACEHOLDER}`;
      } else {
        const [a, b] = measurePoints;
        const zA = _safeQueryElevation(a);
        const zB = _safeQueryElevation(b);
        const result = measurePair(a, b, originLngLat, zA, zB);
        _writeMeasureReadout(result);
      }
      _persistMeasure({ a: measurePoints[0], b: measurePoints[1] });
    } else {
      _persistMeasure({ a: measurePoints[0], b: null });
    }
    _updateMeasureControls();
  }

  // ----- Event handlers ----------------------------------------------------

  function handleMouseMove(event) {
    latestMoveEvent = event;
    if (rafPending) return; // a frame is already scheduled — coalesce
    rafPending = true;
    raf(() => {
      rafPending = false;
      if (disposed) return; // panel torn down before the frame ran
      if (latestMoveEvent != null) _renderReadout(latestMoveEvent);
    });
  }

  function handleMapClick(event) {
    if (pickMode) {
      _exitPickMode();
      if (event != null && event.lngLat != null) {
        _setOrigin([event.lngLat.lng, event.lngLat.lat]);
      }
      return;
    }
    if (measureMode) {
      _addMeasurePoint(event);
      return;
    }
    // Outside any capture mode, a map click is a no-op for coord-tools.
  }

  function handleOriginButtonClick() {
    // Toggle: a click enters pick mode; a second click cancels it without
    // changing the origin (the cancellable path of design point 3).
    if (pickMode) _exitPickMode();
    else _enterPickMode();
  }

  function handleMeasureButtonClick() {
    // Defensive — DOM `disabled` is the primary AC-5 enforcement, but a
    // direct `_fire('click')` in tests or a programmatic dispatch could still
    // trip this handler. Mirror the disabled gate here.
    if (measureBtn.disabled) return;
    if (measureMode) _exitMeasureMode();
    else _enterMeasureMode();
  }

  function handleClearButtonClick() {
    // AC 4 — Clear resets the measurement but stays in mode (so the user can
    // place a fresh pair without re-toggling Measure).
    _clearMeasurement();
  }

  function handleDrawModeEntered() {
    drawModeDepth += 1;
    // AC 5 — entering a module draw mode exits any active measure mode and
    // disables the Measure toggle until every draw mode exits. D-612: the
    // origin-pick is the structurally same kind of click-capturing mode, so
    // the same mutex applies — exit it too.
    if (measureMode) _exitMeasureMode();
    if (pickMode) _exitPickMode();
    _updateMeasureControls();
  }

  function handleDrawModeExited() {
    if (drawModeDepth === 0) {
      // An exited-without-entered means a module's mode lifecycle is broken;
      // clamping at 0 keeps the counter stable but the underflow itself is
      // worth surfacing once so the underlying bug can be fixed.
      if (!_drawModeUnderflowWarned) {
        console.warn(
          '[coord-tools] drawmode:exited received with no matching :entered'
        );
        _drawModeUnderflowWarned = true;
      }
      return;
    }
    drawModeDepth -= 1;
    _updateMeasureControls();
  }

  originBtn.addEventListener('click', handleOriginButtonClick);
  measureBtn.addEventListener('click', handleMeasureButtonClick);
  clearBtn.addEventListener('click', handleClearButtonClick);
  api.map.on('mousemove', handleMouseMove);
  api.map.on('click', handleMapClick);
  const unsubDrawEntered = api.bus.on('drawmode:entered', handleDrawModeEntered);
  const unsubDrawExited = api.bus.on('drawmode:exited', handleDrawModeExited);
  _updateMeasureControls();

  // ----- Origin defaulting from terrain ------------------------------------

  // Initial read — adopt an already-loaded terrain's centre (an approved
  // one-time read; future loads are handled reactively by the watch below).
  const initialTerrain = api.state.getTerrain();
  if (_hasCentre(initialTerrain)) {
    _setOrigin(initialTerrain.centre_wgs84);
  }

  // Reactive — when terrain (re)loads, default the origin to its centre.
  const unwatchTerrain = api.state.watchTerrain((terrain) => {
    if (_hasCentre(terrain)) _setOrigin(terrain.centre_wgs84);
  });

  // ----- Disposal ----------------------------------------------------------

  /**
   * Tear down the subsystem: remove every map listener, the terrain watch, the
   * shell-bus subscriptions, and the `coord-tools:origin` / `coord-tools:measure-*`
   * layers and source; restore the cursor if a pick or measure was in progress,
   * and remove the toolbar DOM.
   */
  function dispose() {
    disposed = true;
    api.map.off('mousemove', handleMouseMove);
    api.map.off('click', handleMapClick);
    originBtn.removeEventListener('click', handleOriginButtonClick);
    measureBtn.removeEventListener('click', handleMeasureButtonClick);
    clearBtn.removeEventListener('click', handleClearButtonClick);
    if (typeof unsubDrawEntered === 'function') unsubDrawEntered();
    if (typeof unsubDrawExited === 'function') unsubDrawExited();
    if (typeof unwatchTerrain === 'function') unwatchTerrain();
    if (pickMode) _exitPickMode();
    if (measureMode) _exitMeasureMode();
    _removeMeasureLayers();
    _removeOriginIndicator();
    if (root.parentNode != null) {
      root.parentNode.removeChild(root);
    }
  }

  return { root, dispose };
}
