/**
 * mode-manager.js — Navigation bar, prerequisite gating, and panel lifecycle.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.5
 *
 * Responsibilities:
 *   - Build the nav bar from the module registry at init() time.
 *   - Gate each button: enabled only when all prerequisites[] keys are non-null.
 *   - On module activation: run onUnmount callbacks on the outgoing module,
 *     call mod.init(api) on the incoming module (every activation), update
 *     state.ui.
 *   - Maintain nav history and a Back button.
 *   - Route handoff events (e.g. optimiser:apply) to receiver modules that
 *     are not currently active so their scoped subscriptions can fire.
 *
 * The mode manager is shell code: it calls state.setState/getState (bypassing
 * the module proxy) to own the `ui` state key, and it uses the raw
 * (unscoped) bus.
 */

/**
 * Handoff events whose semantics are "the receiver becomes active and processes
 * this payload." These are emitted by a module that, by design, the user is
 * currently sitting on (so the receiver is NOT active and has no live bus
 * subscription). The mode manager intercepts the event on the raw bus,
 * activates the receiver (which runs its init and registers its scoped
 * subscription), then re-emits so the receiver's handler fires.
 *
 * Listed by event name → receiver moduleId. Only events listed here trigger
 * the route; ordinary intra-active-module events flow through the scoped bus
 * unchanged.
 *
 * D-493: `optimiser:apply` is emitted from the Optimiser panel — placement-
 * editor (the sole writer of `placements`) is inactive at that moment, so
 * without routing the event is silently dropped.
 */
const _HANDOFF_EVENT_TARGETS = Object.freeze({
  'optimiser:apply': 'placement-editor',
});

/**
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

  // Handoff events currently being routed. Used as a per-event in-flight
  // guard that handles both re-entrancy (the router's own re-emit firing the
  // listener again) AND rapid duplicates (e.g. user double-clicks Apply,
  // emitting twice before the first activation has completed). Either case
  // is a no-op while the first route is still in flight.
  const _pendingHandoff = new Set();

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
   * - Calls mod.init(api) on the incoming module on every activation (D-492);
   *   ES module loading is browser-cached so this is cheap on repeat visits.
   * - Errors from loadModule() and init() are caught and logged so a failed
   *   activation can be retried by the user clicking the nav button again.
   *
   * @param {string} moduleId
   * @returns {Promise<boolean>} true if init succeeded, false on caught error
   *   (return value used by the handoff router to decide whether to re-emit).
   */
  async function activateModule(moduleId) {
    if (moduleId === activeModuleId) return true;

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
    if (!entry) return false;

    // D-492: call module.init(api) on every activation, not just the first.
    // Deactivation tears the module down completely — runUnmount removes the
    // panel DOM from the slot, removes map sources/layers, unsubscribes from
    // state.watch and bus.on. A previously-initialised module that the user
    // navigates back to has no live UI or subscriptions; init() must run
    // again to rebuild them.
    //
    // Module init() functions are required to be idempotent across an
    // unmount/mount cycle: every addSource/addLayer/watch/on must be paired
    // with a removal in onUnmount (Interface Module Standard §15, §9, §12).
    // The dynamic import inside loadModule() is cached by the browser's ES
    // module system, so re-calling it returns the same module record without
    // re-fetching.
    try {
      const mod = await entry.loadModule();
      if (!mod || typeof mod.init !== 'function') {
        throw new Error(`Module '${moduleId}' index.js must export { init(api) }`);
      }
      mod.init(entry.api);
      return true;
    } catch (err) {
      console.error(`[mode-manager] Failed to activate module '${moduleId}':`, err);
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Handoff event routing (D-493)
  // ---------------------------------------------------------------------------

  /**
   * Handle a handoff event observed on the raw bus.
   *
   * Cases handled:
   *   1. A route for this event is already in flight (re-entrancy from our
   *      own re-emit, or a rapid duplicate user click) — no-op.
   *   2. The target module is already active — its own scoped subscription
   *      fired through the normal bus dispatch; nothing extra to do.
   *   3. The target is inactive — activate it (its init registers the scoped
   *      subscription) and re-emit so the now-active handler receives it.
   *      If activation fails (init threw and was caught), the re-emit is
   *      skipped and a warning is logged — re-emitting onto a target with
   *      no live listener would silently drop the payload.
   *
   * @param {string} event - handoff event name (e.g. 'optimiser:apply')
   * @param {string} targetId - moduleId that owns the receiving logic
   * @param {*} payload
   * @returns {Promise<void>}
   */
  async function _routeHandoff(event, targetId, payload) {
    if (_pendingHandoff.has(event)) return; // re-entry or rapid duplicate
    if (activeModuleId === targetId) return; // native dispatch handled it

    _pendingHandoff.add(event);
    try {
      const ok = await activateModule(targetId);
      if (!ok) {
        console.warn(
          `[mode-manager] handoff '${event}' dropped: '${targetId}' failed to initialise`,
        );
        return;
      }
      bus.emit(event, payload);
    } catch (err) {
      console.error(
        `[mode-manager] handoff routing failed for '${event}' → '${targetId}':`,
        err,
      );
    } finally {
      _pendingHandoff.delete(event);
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
        // Tear down the current module before clearing activeModuleId.
        // activateModule's own unmount block is keyed off activeModuleId !==
        // null; clearing it without first running runUnmount would leak the
        // current module's map sources, layers, and bus subscriptions.
        // Back navigation does NOT push the current module onto navHistory
        // (the user is moving backwards through it, not deepening the stack).
        if (activeModuleId !== null) {
          const current = moduleRegistry.find(m => m.manifest.id === activeModuleId);
          if (current) {
            try {
              current.runUnmount();
            } catch (err) {
              console.error(`[mode-manager] runUnmount error during Back:`, err);
            }
          }
        }
        // Clear activeModuleId so activateModule's same-module guard does
        // not short-circuit, and so its unmount block does not run a second
        // time (already done above).
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

    // Wire handoff event routing on the raw bus (D-493).
    // These listeners persist for the page lifetime — no cleanup needed.
    for (const [event, targetId] of Object.entries(_HANDOFF_EVENT_TARGETS)) {
      bus.on(event, (payload) => {
        _routeHandoff(event, targetId, payload).catch(err =>
          console.error(`[mode-manager] Unhandled handoff error for '${event}':`, err)
        );
      });
    }
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
