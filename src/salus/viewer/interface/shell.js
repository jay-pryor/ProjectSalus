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
