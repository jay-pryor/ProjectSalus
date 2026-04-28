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
 * Startup sequence:
 *   1. Discover and validate modules from modules/index.json
 *   2. Build per-module state and bus contracts
 *   3. Instantiate state, bus, and map
 *   4. Initialise ui state
 *   5. Build module registry (api + runUnmount per module)
 *   6. Start mode manager (builds nav bar, wires prereq gating)
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

async function main() {
  // -------------------------------------------------------------------
  // 1. Discover and validate modules
  // -------------------------------------------------------------------
  const validManifests = await discoverModules('.');

  // -------------------------------------------------------------------
  // 2. Build contract maps
  // -------------------------------------------------------------------
  const { stateContracts, busContracts } = buildContracts(validManifests);

  // -------------------------------------------------------------------
  // 3. Instantiate shared resources
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
  // 4. Initialise shell-owned state
  // -------------------------------------------------------------------
  state.setState('ui', {
    active_module_id: null,
    nav_history: [],
  });

  // -------------------------------------------------------------------
  // 4b. Bootstrap sensor/effector libraries from the backend.
  //
  // No module writes sensor_library or effector_library — they originate
  // from the read-only bundled data directory on the server.  The shell
  // fetches them once at startup and exposes them via state.setState().
  //
  // If the backend is unreachable we fall back to empty dicts so library-
  // browser and budget-tracker render cleanly rather than crashing — but
  // we ALSO emit `shell:library-load-error` on the bus so a downstream
  // module (e.g. an error banner) can surface the failure to the user
  // rather than presenting empty dropdowns with no explanation (D-415).
  //
  // Test environments without `fetch` (e.g. Node test-runner module-level
  // unit tests that import the shell) short-circuit to empty libraries
  // instead of throwing (D-428).
  // -------------------------------------------------------------------
  async function _fetchLibrary(url) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) {
        console.warn(`[shell] ${url} returned HTTP ${resp.status}`);
        bus.emit('shell:library-load-error', { url, status: resp.status });
        return {};
      }
      const body = await resp.json();
      if (body && typeof body === 'object' && !Array.isArray(body)) return body;
      // A list response is a contract drift — log so the regression is
      // visible rather than silently producing empty libraries (D-419).
      console.warn(
        `[shell] ${url} returned ${Array.isArray(body) ? 'array' : typeof body}; ` +
        `expected object grouped by type. Falling back to empty library.`
      );
      bus.emit('shell:library-load-error', { url, status: 200, reason: 'unexpected-shape' });
      return {};
    } catch (err) {
      console.warn(`[shell] Failed to fetch ${url}: ${err.message}`);
      bus.emit('shell:library-load-error', { url, error: err.message });
      return {};
    }
  }

  let sensorLib = {};
  let effectorLib = {};
  if (typeof fetch === 'function') {
    [sensorLib, effectorLib] = await Promise.all([
      _fetchLibrary('/api/sensors'),
      _fetchLibrary('/api/effectors'),
    ]);
  } else {
    console.warn('[shell] global fetch is not available — libraries left empty.');
  }
  state.setState('sensor_library', sensorLib);
  state.setState('effector_library', effectorLib);

  // -------------------------------------------------------------------
  // 5. Build module registry
  // -------------------------------------------------------------------
  const panelSlot = document.getElementById('panel-slot');
  const navContainer = document.getElementById('nav-bar');

  const moduleRegistry = validManifests.map((manifest) => {
    const prefix = manifest.layer_id_prefix ?? manifest.id;
    const mapProxy = createMapProxy(map, prefix, {
      // terrain-loader is the only module permitted to call setTerrainSource().
      // All other modules receive a proxy without this method.
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
      // Lazy dynamic import — module code only executes on first activation
      loadModule: () => import(`./modules/${manifest.id}/index.js`),
    };
  });

  // -------------------------------------------------------------------
  // 6. Start mode manager
  // -------------------------------------------------------------------
  const modeManager = createModeManager(navContainer, panelSlot, state, bus, moduleRegistry);
  modeManager.init();

  // Expose a narrow shell handle for debugging and scenario load/save (the only
  // operations that legitimately need shell-level access from outside modules).
  // Does NOT expose raw state or raw bus — those bypass contract enforcement.
  window._salusShell = {
    /** Emit a scenario lifecycle event (shell-owned: scenario:loaded, scenario:saved). */
    emitScenario: (event, data) => bus.emit(event, data),
    /** Subscribe to scenario lifecycle events (shell-owned). */
    onScenario: (event, cb) => bus.on(event, cb),
    /** Activate a module by ID (for programmatic navigation). */
    activateModule: (moduleId) => modeManager.activateModule(moduleId),
  };
}

main().catch((err) => {
  console.error('[shell] Startup failed:', err);
});
