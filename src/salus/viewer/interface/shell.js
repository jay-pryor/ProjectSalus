/**
 * shell.js — Host application entry point.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.2
 *
 * The shell is the only part of the system that:
 *   - holds direct references to shared resources (map, state, bus)
 *   - constructs the injected API for each module
 *   - drives the module lifecycle via the mode manager
 *
 * Modules receive only the injected api object. They never receive the
 * shell, the raw state, the raw bus, or the raw map instance.
 *
 * Startup sequence (S14.14-1):
 *   1. Show loading overlay
 *   2. Fetch sensor/effector libraries in parallel (before any module init)
 *   3. Hide loading overlay
 *   4. Discover and validate modules from modules/index.json
 *   5. Build per-module state and bus contracts
 *   6. Instantiate state, bus, and map
 *   7. Initialise ui state
 *   8. Write fetched libraries to state
 *   9. Build module registry (api + runUnmount per module)
 *  10. Start mode manager (builds nav bar, wires prereq gating)
 *  11. Append shell-level Save/Load buttons to nav bar
 *  12. Mount the coord-tools shell-owned subsystem (I-20)
 */

import { createState } from './state.js';
import { createBus } from './bus.js';
import { createMapProxy } from './map-proxy.js';
import { createModeManager } from './mode-manager.js';
import { createCoordTools, COORD_TOOLS_LAYER_PREFIX } from './coord-tools/index.js';
import {
  discoverModules,
  buildContracts,
  createModuleAPI,
} from './registry.js';

// Initial MapLibre style. Owns exactly one shell-level layer — an opaque
// background — so any module-added layer (e.g. hillshade) renders on top of
// solid colour rather than the page bleed-through that previously made
// terrain look semi-translucent (D-480, I-11).
//
// Exported as a factory so the shape can be asserted from tests without
// instantiating MapLibre.
export function initialMapStyle() {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': '#1a1a2e' },
      },
    ],
  };
}

// State keys that are persisted in a saved scenario file (excludes 'ui' which
// is ephemeral shell-owned state).
const SCENARIO_KEYS = [
  'terrain',
  'sensor_library',
  'effector_library',
  'placements',
  'zones',
  'threat_corridors',
  'constraints',
  'sim_results',
  'optimiser_results',
  'scenario_b_sim_results',
  'report_config',
];

// ---------------------------------------------------------------------------
// Library pre-load helpers (S14.14-1)
// ---------------------------------------------------------------------------

/**
 * Fetch a library URL and return the parsed object, or a fallback.
 *
 * On HTTP error or network failure: emits `shell:library-load-error` on bus
 * and returns `fallback`.
 * On unexpected response shape (array or non-object): same.
 *
 * @param {string} url
 * @param {object} bus - unrestricted shell bus (may be null before bus is created)
 * @param {object} fallback - value to return on any failure
 */
async function _fetchLibrary(url, bus, fallback) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      console.warn(`[shell] ${url} returned HTTP ${resp.status}`);
      if (bus) bus.emit('shell:library-load-error', { url, status: resp.status });
      return fallback;
    }
    const body = await resp.json();
    if (body && typeof body === 'object' && !Array.isArray(body)) return body;
    console.warn(
      `[shell] ${url} returned ${Array.isArray(body) ? 'array' : typeof body}; ` +
      `expected object grouped by type. Falling back.`
    );
    if (bus) bus.emit('shell:library-load-error', { url, status: 200, reason: 'unexpected-shape' });
    return fallback;
  } catch (err) {
    console.warn(`[shell] Failed to fetch ${url}: ${err.message}`);
    if (bus) bus.emit('shell:library-load-error', { url, error: err.message });
    return fallback;
  }
}

/**
 * Fetch sensor and effector libraries in parallel, with SALUS_DATA fallback.
 *
 * Fallback chain:
 *   1. Backend API (/api/sensors, /api/effectors)
 *   2. window.SALUS_DATA.sensor_library / effector_library (from viewer_data.js)
 *   3. Empty object {}
 *
 * @returns {Promise<{sensorLib: object, effectorLib: object}>}
 */
export async function fetchLibraries() {
  const salusData =
    typeof globalThis.SALUS_DATA === 'object' && globalThis.SALUS_DATA !== null
      ? globalThis.SALUS_DATA
      : null;

  const sensorFallback = salusData?.sensor_library ?? {};
  const effectorFallback = salusData?.effector_library ?? {};

  if (typeof fetch !== 'function') {
    console.warn('[shell] global fetch is not available — using fallback libraries.');
    return { sensorLib: sensorFallback, effectorLib: effectorFallback };
  }

  const [sensorLib, effectorLib] = await Promise.all([
    _fetchLibrary('/api/sensors', null, sensorFallback),
    _fetchLibrary('/api/effectors', null, effectorFallback),
  ]);
  return { sensorLib, effectorLib };
}

// ---------------------------------------------------------------------------
// Scenario save / load (S14.14-2)
// ---------------------------------------------------------------------------

/**
 * Serialise all non-ui state keys to a JSON blob and trigger a browser download.
 *
 * @param {object} state - full state store from createState()
 * @param {object} bus - unrestricted shell bus
 * @param {Document} doc - injectable document for testing
 */
export function saveScenario(state, bus, doc = globalThis.document) {
  const payload = {};
  for (const key of SCENARIO_KEYS) {
    payload[key] = state.getState(key);
  }
  const json = JSON.stringify(payload, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const date = new Date().toISOString().slice(0, 10);
  const a = doc.createElement('a');
  a.href = url;
  a.download = `scenario-${date}.salus.json`;
  doc.body.appendChild(a);
  a.click();
  doc.body.removeChild(a);
  URL.revokeObjectURL(url);

  bus.emit('scenario:saved', { timestamp: new Date().toISOString() });
}

// Deep-validation limits — defence-in-depth against pathological scenario
// payloads (D-499). A legitimate save file has a handful of top-level keys
// with shallow object trees; these caps are well above realistic content but
// well below anything an attacker would use to wedge the parser or render path.
const _MAX_SCENARIO_DEPTH = 32;
const _MAX_SCENARIO_STRING_LEN = 100_000;

// Keys that can pollute Object.prototype if assigned via dynamic key access.
// JSON.parse itself does not pollute the prototype, but downstream code that
// does e.g. `Object.assign(target, parsed)` or merges values can — reject at
// the trust boundary instead of trusting every downstream consumer.
const _FORBIDDEN_OBJECT_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

// Conservative HTML-tag-opener detection: "<" followed by a letter, "!", "/",
// or "?" covers element openers, closers, comments, and processing
// instructions. A scenario file legitimately contains paths, names, and
// numbers — never markup — so any opener is suspicious. Combined with a
// "javascript:" URI detector this raises the XSS bar against downstream
// renderers that may use innerHTML (D-499).
const _HTML_OPENER_RE = /<[!?/A-Za-z]/;
const _JS_URI_RE = /javascript\s*:/i;

function _isPlainObject(v) {
  return (
    v !== null &&
    typeof v === 'object' &&
    !Array.isArray(v) &&
    Object.getPrototypeOf(v) === Object.prototype
  );
}

function _isSafeScenarioValue(v, depth) {
  if (depth > _MAX_SCENARIO_DEPTH) return false;
  if (v === null) return true;
  if (typeof v === 'boolean') return true;
  if (typeof v === 'number') return Number.isFinite(v);
  if (typeof v === 'string') {
    if (v.length > _MAX_SCENARIO_STRING_LEN) return false;
    if (_HTML_OPENER_RE.test(v)) return false;
    if (_JS_URI_RE.test(v)) return false;
    return true;
  }
  if (Array.isArray(v)) {
    for (const item of v) {
      if (!_isSafeScenarioValue(item, depth + 1)) return false;
    }
    return true;
  }
  if (_isPlainObject(v)) {
    for (const k of Object.keys(v)) {
      if (_FORBIDDEN_OBJECT_KEYS.has(k)) return false;
      if (!_isSafeScenarioValue(v[k], depth + 1)) return false;
    }
    return true;
  }
  return false;
}

/**
 * Validate a parsed scenario object. Returns true only when:
 *   - the root is a plain object (not array, not null, not a class instance);
 *   - every top-level key is in SCENARIO_KEYS;
 *   - every value (recursively) is plain JSON (null / boolean / number /
 *     string / array / plain object) within depth and string-size limits;
 *   - no nested key is `__proto__` / `constructor` / `prototype`;
 *   - no string value contains an HTML-tag-opener pattern or a `javascript:`
 *     URI (defence-in-depth against XSS in downstream renderers — see D-499).
 *
 * @param {unknown} parsed
 * @returns {boolean}
 */
export function validateScenarioPayload(parsed) {
  if (!_isPlainObject(parsed)) return false;
  const validKeys = new Set(SCENARIO_KEYS);
  for (const k of Object.keys(parsed)) {
    if (!validKeys.has(k)) return false;
    if (!_isSafeScenarioValue(parsed[k], 1)) return false;
  }
  return true;
}

/**
 * Write a validated scenario payload to state via the shell bypass path.
 * Fires state watchers for every key written (including null clears).
 *
 * @param {object} payload - validated scenario object
 * @param {object} state - full state store from createState()
 * @param {object} bus - unrestricted shell bus
 */
export function applyScenarioPayload(payload, state, bus) {
  for (const key of SCENARIO_KEYS) {
    state.setState(key, payload[key] ?? null);
  }
  bus.emit('scenario:loaded', { timestamp: new Date().toISOString() });
}

/**
 * Check whether the current session has active placements (the key condition
 * for showing the overwrite confirmation modal).
 *
 * @param {object} state
 * @returns {boolean}
 */
export function hasActivePlacements(state) {
  const p = state.getState('placements');
  return Array.isArray(p) && p.length > 0;
}

// ---------------------------------------------------------------------------
// Shell-level nav bar buttons (S14.14-2)
// ---------------------------------------------------------------------------

/**
 * Append shell-owned Save Scenario and Load Scenario buttons to the nav bar.
 * These live below the mode-manager module buttons and the Back button.
 *
 * @param {HTMLElement} navContainer
 * @param {object} state
 * @param {object} bus
 * @param {Document} [doc]
 */
export function mountShellNavButtons(navContainer, state, bus, doc = globalThis.document) {
  const divider = doc.createElement('div');
  divider.className = 'shell-divider';
  navContainer.appendChild(divider);

  const saveBtn = doc.createElement('button');
  saveBtn.className = 'shell-action';
  saveBtn.textContent = '💾 Save Scenario';
  saveBtn.title = 'Download the current session as a .salus.json file';
  saveBtn.addEventListener('click', () => saveScenario(state, bus, doc));
  navContainer.appendChild(saveBtn);

  const fileInput = doc.getElementById('shell-load-file');
  const modal = doc.getElementById('load-confirm-modal');
  const confirmOk = doc.getElementById('load-confirm-ok');
  const confirmCancel = doc.getElementById('load-confirm-cancel');

  let _pendingPayload = null;

  function _doLoad(payload) {
    applyScenarioPayload(payload, state, bus);
    _pendingPayload = null;
  }

  if (!fileInput) {
    console.warn('[shell] #shell-load-file not found in DOM — Load Scenario button will be inert');
  } else {
    fileInput.addEventListener('change', () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      fileInput.value = '';
      const reader = new FileReader();
      reader.onerror = () => {
        console.error('[shell] Load scenario: file read failed', reader.error);
      };
      reader.onload = (e) => {
        let parsed;
        try {
          parsed = JSON.parse(e.target.result);
        } catch {
          console.error('[shell] Load scenario: invalid JSON');
          return;
        }
        if (!validateScenarioPayload(parsed)) {
          console.error('[shell] Load scenario: unrecognised payload shape');
          return;
        }
        if (hasActivePlacements(state) && modal) {
          _pendingPayload = parsed;
          modal.showModal();
        } else {
          _doLoad(parsed);
        }
      };
      reader.readAsText(file);
    });
  }

  if (confirmOk) {
    confirmOk.addEventListener('click', () => {
      if (_pendingPayload) _doLoad(_pendingPayload);
      if (modal) modal.close();
    });
  }

  if (confirmCancel) {
    confirmCancel.addEventListener('click', () => {
      _pendingPayload = null;
      if (modal) modal.close();
    });
  }

  const loadBtn = doc.createElement('button');
  loadBtn.className = 'shell-action';
  loadBtn.textContent = '📂 Load Scenario';
  loadBtn.title = 'Load a previously saved .salus.json file';
  loadBtn.addEventListener('click', () => fileInput?.click());
  navContainer.appendChild(loadBtn);
}

// ---------------------------------------------------------------------------
// Main startup
// ---------------------------------------------------------------------------

async function main() {
  const doc = globalThis.document;

  // -------------------------------------------------------------------
  // 1. Show loading overlay
  // -------------------------------------------------------------------
  const loadingOverlay = doc?.getElementById('loading-overlay');

  // -------------------------------------------------------------------
  // 2. Fetch sensor/effector libraries BEFORE module discovery
  // -------------------------------------------------------------------
  const { sensorLib, effectorLib } = await fetchLibraries();

  // -------------------------------------------------------------------
  // 3. Hide loading overlay
  // -------------------------------------------------------------------
  if (loadingOverlay) loadingOverlay.classList.add('hidden');

  // -------------------------------------------------------------------
  // 4. Discover and validate modules
  // -------------------------------------------------------------------
  const validManifests = await discoverModules('.');

  // -------------------------------------------------------------------
  // 5. Build contract maps
  // -------------------------------------------------------------------
  const { stateContracts, busContracts } = buildContracts(validManifests);

  // -------------------------------------------------------------------
  // 6. Instantiate shared resources
  // -------------------------------------------------------------------
  const state = createState(stateContracts);
  const bus = createBus(busContracts);

  // MapLibreGL is loaded via <script> tag in index.html; maplibregl is global.
  const map = new maplibregl.Map({  // eslint-disable-line no-undef
    container: 'map',
    style: initialMapStyle(),
    center: [133.7751, -25.2744], // Geographic centre of Australia
    zoom: 4,
  });

  // -------------------------------------------------------------------
  // 7. Initialise shell-owned state
  // -------------------------------------------------------------------
  state.setState('ui', {
    active_module_id: null,
    nav_history: [],
  });

  // coord-tools subsystem state (I-20). Shell-owned, like 'ui' — no module
  // declares it. The skeleton object's sub-fields are populated by I-21–I-23
  // (origin, grid, measurement). In-session only — excluded from SCENARIO_KEYS.
  state.setState('coord_tools', {
    origin_lnglat: null,
    grid_enabled: false,
    grid_spacing_m: null,
    measure: null,
  });

  // -------------------------------------------------------------------
  // 8. Write fetched libraries to state (shell bypass — no contract check)
  //
  // Libraries are pre-fetched (step 2) and written here — after state is
  // created — so they are available the moment any module calls
  // api.state.get('sensor_library') or api.state.get('effector_library').
  // If the fetch failed, the SALUS_DATA fallback or empty {} is used
  // (see fetchLibraries()).  bus.emit is not available at fetch time;
  // emit library-load-error here if the library is still empty and
  // SALUS_DATA was not present either.
  // -------------------------------------------------------------------
  state.setState('sensor_library', sensorLib);
  state.setState('effector_library', effectorLib);

  // Emit library-load-error for empty libraries now that bus exists (D-461).
  // Previously _fetchLibrary emitted this but bus=null at pre-fetch time.
  if (Object.keys(sensorLib).length === 0) {
    bus.emit('shell:library-load-error', { url: '/api/sensors', reason: 'empty-after-fallback' });
  }
  if (Object.keys(effectorLib).length === 0) {
    bus.emit('shell:library-load-error', { url: '/api/effectors', reason: 'empty-after-fallback' });
  }

  // -------------------------------------------------------------------
  // 9. Build module registry
  // -------------------------------------------------------------------
  const panelSlot = doc.getElementById('panel-slot');
  const navContainer = doc.getElementById('nav-bar');

  const moduleRegistry = validManifests.map((manifest) => {
    const prefix = manifest.layer_id_prefix ?? manifest.id;
    const mapProxy = createMapProxy(map, prefix, {
      allowTerrainSource: manifest.id === 'terrain-loader',
    });
    const scopedBus = bus.createScopedBus(manifest.id);
    const { api, runUnmount } = createModuleAPI(
      manifest.id,
      manifest,
      state,
      scopedBus,
      mapProxy,
      panelSlot
    );

    return {
      manifest,
      api,
      runUnmount,
      loadModule: () => import(`./modules/${manifest.id}/index.js`),
    };
  });

  // -------------------------------------------------------------------
  // 10. Start mode manager
  // -------------------------------------------------------------------
  const modeManager = createModeManager(navContainer, panelSlot, state, bus, moduleRegistry);
  modeManager.init();

  // -------------------------------------------------------------------
  // 11. Append shell-level Save/Load buttons (S14.14-2)
  // -------------------------------------------------------------------
  mountShellNavButtons(navContainer, state, bus, doc);

  // -------------------------------------------------------------------
  // 12. Mount the coord-tools shell-owned subsystem (I-20)
  //
  // coord-tools is shell chrome, not a navigable module: it persists across
  // module navigation and is not gated by the mode manager. It receives its
  // own `coord-tools`-prefixed scoped map proxy (with the queryTerrainElevation
  // opt-in for the I-21 Z readout) so any layers it adds are prefix-enforced,
  // and a narrow state handle: read/write of the shell-owned `coord_tools` key
  // plus read-only observation of `terrain` (so the origin can default to the
  // terrain centre on load) — all via the shell bypass path.
  // -------------------------------------------------------------------
  const coordToolbar = doc.getElementById('coord-toolbar');
  if (coordToolbar) {
    const coordMapProxy = createMapProxy(map, COORD_TOOLS_LAYER_PREFIX, {
      allowTerrainQuery: true,
    });
    createCoordTools(
      coordToolbar,
      {
        map: coordMapProxy,
        state: {
          get: () => state.getState('coord_tools'),
          set: (value) => state.setState('coord_tools', value),
          getTerrain: () => state.getState('terrain'),
          watchTerrain: (callback) => state.watch('terrain', callback),
        },
      },
      doc
    );
  } else {
    console.warn('[shell] #coord-toolbar not found in DOM — coord-tools subsystem not mounted');
  }

  // Expose a narrow shell handle for debugging and programmatic navigation.
  // emitScenario is restricted to the two scenario lifecycle events to prevent
  // external callers from emitting arbitrary events into the raw bus (D-462).
  const _ALLOWED_SCENARIO_EVENTS = new Set(['scenario:loaded', 'scenario:saved']);
  window._salusShell = {
    emitScenario: (event, data) => {
      if (!_ALLOWED_SCENARIO_EVENTS.has(event)) {
        throw new Error(`[shell] emitScenario: '${event}' is not an allowed scenario event`);
      }
      bus.emit(event, data);
    },
    onScenario: (event, cb) => {
      if (!_ALLOWED_SCENARIO_EVENTS.has(event)) {
        throw new Error(`[shell] onScenario: '${event}' is not an allowed scenario event`);
      }
      return bus.on(event, cb);
    },
    activateModule: (moduleId) => modeManager.activateModule(moduleId),
  };
}

main().catch((err) => {
  console.error('[shell] Startup failed:', err);
});
