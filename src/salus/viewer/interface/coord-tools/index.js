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
 *   - I-21 — resettable origin point + live X/Y/Z cursor readout (this file).
 *   - I-22 — two-point distance measurement (Measure stub still disabled).
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

// --- Toolbar control labels -------------------------------------------------

const SET_ORIGIN_LABEL = 'Set origin';
const PICK_CANCEL_LABEL = 'Cancel';

/**
 * Disabled tool-control stubs — filled in by the named later task. `tool` is
 * the stable `data-tool` hook. (Set origin is a live control from I-21 and is
 * built separately, below.)
 */
const TOOL_STUBS = [
  { tool: 'measure', label: 'Measure', task: 'I-22' },
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
 *   state: {get: Function, set: Function, getTerrain: Function, watchTerrain: Function}
 * }} api - the shell-built handle. `map` is a `coord-tools`-prefixed scoped map
 *   proxy (with `queryTerrainElevation`). `state` reads/writes the shell-owned
 *   `coord_tools` key (`get`/`set`) and gives read-only observation of the
 *   `terrain` key (`getTerrain`/`watchTerrain`) so the origin can default to
 *   the terrain centre.
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

  // Measure / Grid — disabled until I-22 / I-23 wire them up.
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
  let savedCursor = null;      // canvas cursor saved on entering pick mode
  let latestMoveEvent = null;  // most recent mousemove event (for the readout)
  let rafPending = false;      // true while a readout frame is scheduled
  let disposed = false;        // true after dispose() — guards a late frame

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
    if (!pickMode) return; // the readout-only click path is a no-op
    _exitPickMode();
    if (event != null && event.lngLat != null) {
      _setOrigin([event.lngLat.lng, event.lngLat.lat]);
    }
  }

  function handleOriginButtonClick() {
    // Toggle: a click enters pick mode; a second click cancels it without
    // changing the origin (the cancellable path of design point 3).
    if (pickMode) _exitPickMode();
    else _enterPickMode();
  }

  originBtn.addEventListener('click', handleOriginButtonClick);
  api.map.on('mousemove', handleMouseMove);
  api.map.on('click', handleMapClick);

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
   * Tear down the subsystem: remove every map listener, the terrain watch and
   * the `coord-tools:origin` layer/source, restore the cursor if a pick was in
   * progress, and remove the toolbar DOM.
   */
  function dispose() {
    disposed = true;
    api.map.off('mousemove', handleMouseMove);
    api.map.off('click', handleMapClick);
    originBtn.removeEventListener('click', handleOriginButtonClick);
    if (typeof unwatchTerrain === 'function') unwatchTerrain();
    if (pickMode) _exitPickMode();
    _removeOriginIndicator();
    if (root.parentNode != null) {
      root.parentNode.removeChild(root);
    }
  }

  return { root, dispose };
}
