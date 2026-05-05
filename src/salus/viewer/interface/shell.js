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
 */

import { createState } from './state.js';
import { createBus } from './bus.js';
import { createMapProxy } from './map-proxy.js';
import { createModeManager } from './mode-manager.js';
import {
  discoverModules,
  buildContracts,
  createModuleAPI,
} from './registry.js';

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

/**
 * Validate a parsed scenario object: must be a plain object whose keys are
 * a subset of SCENARIO_KEYS.
 *
 * @param {unknown} parsed
 * @returns {boolean}
 */
export function validateScenarioPayload(parsed) {
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return false;
  const validKeys = new Set(SCENARIO_KEYS);
  return Object.keys(parsed).every(k => validKeys.has(k));
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
    style: {
      version: 8,
      sources: {},
      layers: [],
    },
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
