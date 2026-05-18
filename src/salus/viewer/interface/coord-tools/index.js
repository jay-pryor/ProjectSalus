/**
 * coord-tools/index.js — Coordinate-tools shell-owned subsystem (I-20).
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
 * map layers it later adds are prefix-enforced (`coord-tools:*`). It is not
 * gated by the mode manager and persists across module navigation.
 *
 * I-20 scope — infrastructure only. This renders the empty toolbar shell with
 * the tool controls stubbed and disabled. The user-facing behaviour, and the
 * use of `api.map` / `api.state`, is added by later tasks:
 *   - I-21 — resettable origin + live X/Y/Z cursor readout
 *   - I-22 — two-point distance measurement
 *   - I-23 — toggleable coordinate grid overlay
 */

/** Layer-ID prefix every map layer this subsystem owns must carry. */
export const COORD_TOOLS_LAYER_PREFIX = 'coord-tools';

/** Placeholder shown wherever a coordinate value is not yet available. */
const VALUE_PLACEHOLDER = '—'; // em dash

/**
 * Tool-control stubs rendered by I-20. Each is a disabled button until the
 * task named in `task` wires up its behaviour. `tool` is the stable
 * `data-tool` hook later tasks query for.
 */
const TOOL_STUBS = [
  { tool: 'set-origin', label: 'Set origin', task: 'I-21' },
  { tool: 'measure', label: 'Measure', task: 'I-22' },
  { tool: 'grid', label: 'Grid', task: 'I-23' },
];

/**
 * Instantiate the coord-tools subsystem and render its toolbar shell.
 *
 * @param {HTMLElement} toolbarEl - the permanent `#coord-toolbar` element the
 *   subsystem renders into (shell chrome — never the module panel slot).
 * @param {{map: object, state: {get: Function, set: Function}}} api - the
 *   shell-built handle: `map` is a `coord-tools`-prefixed scoped map proxy
 *   (with `queryTerrainElevation`); `state` reads/writes the shell-owned
 *   `coord_tools` state key. I-20 renders the shell only and does not yet
 *   read or write either — both are held for I-21–I-23.
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
  // proxy) must fail here, at the cause, not later in I-21 as a far-removed
  // "queryTerrainElevation is not a function" crash.
  if (api.map == null || typeof api.map.queryTerrainElevation !== 'function') {
    throw new TypeError(
      'createCoordTools(…, api, …): api.map must be a coord-tools map proxy ' +
      'created with { allowTerrainQuery: true }'
    );
  }
  // D-605: validate the state handle is the { get, set } shape the JSDoc
  // declares, so a malformed handle fails at construction, not on first use.
  if (
    api.state == null ||
    typeof api.state.get !== 'function' ||
    typeof api.state.set !== 'function'
  ) {
    throw new TypeError(
      'createCoordTools(…, api, …): api.state must provide get() and set()'
    );
  }

  const root = doc.createElement('div');
  root.className = 'coord-tools';

  // Subsystem label
  const label = doc.createElement('span');
  label.className = 'coord-tools-label';
  label.textContent = 'Coordinate Tools';
  root.appendChild(label);

  // Live X/Y/Z readout (I-21 populates it; I-20 shows placeholders only).
  const readout = doc.createElement('span');
  readout.className = 'coord-tools-readout';
  readout.dataset.role = 'readout';
  readout.textContent =
    `X: ${VALUE_PLACEHOLDER}  Y: ${VALUE_PLACEHOLDER}  Z: ${VALUE_PLACEHOLDER}`;
  root.appendChild(readout);

  // Tool-control stubs — disabled until the named task wires them up.
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

  /**
   * Tear down the subsystem. I-20 registers no listeners and adds no map
   * layers, so disposal only removes the toolbar DOM; I-21–I-23 extend this
   * to also remove their map/state listeners and `coord-tools:*` layers.
   */
  function dispose() {
    if (root.parentNode != null) {
      root.parentNode.removeChild(root);
    }
  }

  return { root, dispose };
}
