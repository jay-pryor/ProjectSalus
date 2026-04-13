/**
 * mode-manager.js — Navigation bar, prerequisite gating, and panel lifecycle.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.5
 *
 * Responsibilities:
 *   - Build the nav bar from the module registry at init() time.
 *   - Gate each button: enabled only when all prerequisites[] keys are non-null.
 *   - On module activation: run onUnmount callbacks, lazy-init the module if
 *     first visit, mount its panel, update state.ui.
 *   - Maintain nav history and a Back button.
 *
 * The mode manager is shell code: it calls state.setState/getState (bypassing
 * the module proxy) to own the `ui` state key.
 *
 * @param {HTMLElement} navContainer - element to append nav buttons to
 * @param {HTMLElement} panelSlot - panel slot element (unused directly here; panel
 *   mounting is delegated to api.panel.mount which the module calls from its init)
 * @param {object} state - full state store from createState()
 * @param {object} bus - unrestricted shell bus from createBus()
 * @param {Array} moduleRegistry - [{manifest, api, runUnmount, loadModule}]
 * @param {Document} [_doc] - injectable document for testing (default: global document)
 */
export function createModeManager(navContainer, panelSlot, state, bus, moduleRegistry, _doc = globalThis.document) {
  let activeModuleId = null;
  const navHistory = [];

  // moduleId → true once init(api) has been called successfully
  const initialised = new Set();

  // ---------------------------------------------------------------------------
  // Prerequisite check
  // ---------------------------------------------------------------------------

  function allPrereqsMet(manifest) {
    return (manifest.prerequisites ?? []).every(key => state.getState(key) !== null);
  }

  function missingPrereqs(manifest) {
    return (manifest.prerequisites ?? []).filter(key => state.getState(key) === null);
  }

  function updateButtonState(manifest, btn) {
    const met = allPrereqsMet(manifest);
    btn.disabled = !met;
    btn.title = met ? '' : `Requires: ${missingPrereqs(manifest).join(', ')}`;
  }

  // ---------------------------------------------------------------------------
  // Module activation
  // ---------------------------------------------------------------------------

  /**
   * Activate a module by ID.
   * - Unmounts the current module (runUnmount protected with try/catch).
   * - Lazy-loads module code on first activation (init called exactly once).
   * - Errors from loadModule() and init() are caught and logged; the module
   *   is removed from initialised so it can be retried on next click.
   *
   * @param {string} moduleId
   * @returns {Promise<void>}
   */
  async function activateModule(moduleId) {
    if (moduleId === activeModuleId) return;

    // Unmount the current module — never let a cleanup error block activation
    if (activeModuleId !== null) {
      const current = moduleRegistry.find(m => m.manifest.id === activeModuleId);
      if (current) {
        try {
          current.runUnmount();
        } catch (err) {
          console.error(`[mode-manager] runUnmount error for '${activeModuleId}':`, err);
        }
        navHistory.push(activeModuleId);
      }
    }

    activeModuleId = moduleId;

    // Update ui state (shell-owned, bypass proxy)
    const prevUi = state.getState('ui') ?? {};
    state.setState('ui', {
      ...prevUi,
      active_module_id: moduleId,
      nav_history: [...navHistory],
    });

    const entry = moduleRegistry.find(m => m.manifest.id === moduleId);
    if (!entry) return;

    // Lazy init: call module.init(api) exactly once on success
    if (!initialised.has(moduleId)) {
      try {
        const mod = await entry.loadModule();
        if (!mod || typeof mod.init !== 'function') {
          throw new Error(`Module '${moduleId}' index.js must export { init(api) }`);
        }
        mod.init(entry.api);
        // Only mark as initialised on success so a failed load can be retried
        initialised.add(moduleId);
      } catch (err) {
        console.error(`[mode-manager] Failed to activate module '${moduleId}':`, err);
        // Do not add to initialised — allow retry on next click
      }
    }
  }

  // ---------------------------------------------------------------------------
  // init(): build the nav bar
  // ---------------------------------------------------------------------------

  function init() {
    for (const entry of moduleRegistry) {
      const { manifest } = entry;

      const btn = _doc.createElement('button');
      btn.dataset.moduleId = manifest.id;

      // Render icon + label
      if (manifest.icon) {
        const iconSpan = _doc.createElement('span');
        iconSpan.className = 'nav-icon';
        iconSpan.setAttribute('aria-hidden', 'true');
        iconSpan.textContent = manifest.icon;
        btn.appendChild(iconSpan);
        const labelSpan = _doc.createElement('span');
        labelSpan.textContent = ` ${manifest.label}`;
        btn.appendChild(labelSpan);
      } else {
        btn.textContent = manifest.label;
      }

      updateButtonState(manifest, btn);

      // Watch every prerequisite key; update button when any changes
      for (const key of manifest.prerequisites ?? []) {
        state.watch(key, () => updateButtonState(manifest, btn));
      }

      btn.addEventListener('click', () => {
        if (!btn.disabled) {
          activateModule(manifest.id).catch(err =>
            console.error(`[mode-manager] Unhandled activation error for '${manifest.id}':`, err)
          );
        }
      });

      navContainer.appendChild(btn);
    }

    // Back button
    const backBtn = _doc.createElement('button');
    backBtn.id = 'nav-back';
    backBtn.textContent = 'Back';
    backBtn.disabled = navHistory.length === 0;

    backBtn.addEventListener('click', () => {
      if (navHistory.length > 0) {
        const prev = navHistory.pop();
        // Temporarily clear activeModuleId so activateModule re-runs for prev
        activeModuleId = null;
        activateModule(prev).catch(err =>
          console.error(`[mode-manager] Back navigation error:`, err)
        );
        backBtn.disabled = navHistory.length === 0;
      }
    });

    // Keep back button in sync with nav history in state
    state.watch('ui', (ui) => {
      backBtn.disabled = !ui || !Array.isArray(ui.nav_history) || ui.nav_history.length === 0;
    });

    navContainer.appendChild(backBtn);
  }

  // ---------------------------------------------------------------------------
  // Public interface
  // ---------------------------------------------------------------------------

  return {
    /** Build nav bar and wire prerequisite watchers. Call once at startup. */
    init,

    /**
     * Activate a module by ID. Errors are caught and logged internally.
     * Returns a Promise for tests that need to await activation completion.
     *
     * @param {string} moduleId
     * @returns {Promise<void>}
     */
    activateModule,

    /** For testing: inspect currently active module ID. */
    get activeModuleId() {
      return activeModuleId;
    },
  };
}
