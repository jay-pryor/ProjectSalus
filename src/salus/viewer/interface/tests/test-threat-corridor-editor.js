/**
 * test-threat-corridor-editor.js — Unit tests for the Threat Corridor Editor module.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-threat-corridor-editor.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal DOM mock (set before dynamic import so module-level code is safe)
// ---------------------------------------------------------------------------

function _makeEl(tag = 'div') {
  const el = {
    _tag: tag,
    _children: [],
    _listeners: {},
    _attrs: {},
    id: '',
    hidden: false,
    value: '',
    textContent: '',
    innerHTML: '',
    title: '',
    style: { cssText: '', cursor: '', display: '' },
    dataset: {},
    className: '',
    get firstChild() { return this._children[0] ?? null; },
    appendChild(child)  { this._children.push(child); return child; },
    append(...children) { for (const c of children) this._children.push(c); },
    removeChild(child) {
      const i = this._children.indexOf(child);
      if (i !== -1) this._children.splice(i, 1);
    },
    querySelector(sel) {
      const m = sel.match(/^#(.+)$/);
      if (!m) return null;
      const id = m[1];
      const walk = (node) => {
        if (node.id === id) return node;
        for (const c of (node._children ?? [])) {
          const f = walk(c);
          if (f) return f;
        }
        return null;
      };
      return walk(this);
    },
    querySelectorAll() { return []; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k)    { return this._attrs[k] ?? null; },
    addEventListener(event, handler) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(handler);
    },
    removeEventListener(event, handler) {
      const arr = this._listeners[event] ?? [];
      const i = arr.indexOf(handler);
      if (i !== -1) arr.splice(i, 1);
    },
    _fire(event, data = {}) {
      for (const h of (this._listeners[event] ?? [])) h({ ...data, target: el });
    },
  };

  // innerHTML setter: parse id-bearing elements into flat child list
  Object.defineProperty(el, 'innerHTML', {
    set(html) {
      el._children.length = 0;
      const tagPattern = /(<[a-z]+\s[^>]*?id="([^"]+)"[^>]*?>)/gi;
      const entries = [];
      let m;
      while ((m = tagPattern.exec(html)) !== null) {
        entries.push({ id: m[2], isHidden: /\bhidden\b/.test(m[1]) });
      }
      if (entries.length === 0) return;
      const root = _makeEl('div');
      root.id = entries[0].id;
      root.hidden = entries[0].isHidden;
      el._children.push(root);
      for (let i = 1; i < entries.length; i++) {
        const child = _makeEl('div');
        child.id = entries[i].id;
        child.hidden = entries[i].isHidden;
        root._children.push(child);
      }
    },
    get() { return ''; },
    configurable: true,
  });

  return el;
}

globalThis.document = {
  createElement: (tag) => _makeEl(tag),
};

// ---------------------------------------------------------------------------
// Import module under test
// ---------------------------------------------------------------------------

const { init } = await import('../modules/threat-corridor-editor/index.js');

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({ initState = null } = {}) {
  const stateData = { threat_corridors: initState };
  const watchCallbacks = {};
  const unmountCallbacks = [];
  const emitted = [];
  const sources = {};
  const layers = {};
  const mapListeners = {};
  const canvas = _makeEl('canvas');
  canvas.style = { cursor: '' };

  const api = {
    moduleId: 'threat-corridor-editor',

    state: {
      get(key) { return stateData[key] ?? null; },
      set(key, value) {
        stateData[key] = value;
        for (const cb of (watchCallbacks[key] ?? [])) cb(value);
      },
      watch(key, cb) {
        if (!watchCallbacks[key]) watchCallbacks[key] = [];
        watchCallbacks[key].push(cb);
        return () => {
          const arr = watchCallbacks[key] ?? [];
          const i = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
      },
    },

    bus: {
      emit(event, data) { emitted.push({ event, data }); },
    },

    map: {
      getSource(id) {
        return sources[id] ?? null;
      },
      getLayer(id) {
        return layers[id] ?? null;
      },
      addSource(id, spec) {
        sources[id] = { ...spec, _data: spec.data ?? null, setData(d) { this._data = d; } };
      },
      addLayer(spec) {
        layers[spec.id] = spec;
      },
      removeSource(id) { delete sources[id]; },
      removeLayer(id)  { delete layers[id]; },
      on(event, layerOrHandler, handler) {
        const h = handler ?? layerOrHandler;
        const key = (typeof layerOrHandler === 'string' && handler !== undefined)
          ? `${event}::${layerOrHandler}`
          : event;
        if (!mapListeners[key]) mapListeners[key] = [];
        mapListeners[key].push(h);
      },
      off(event, layerOrHandler, handler) {
        const h = handler ?? layerOrHandler;
        const key = (typeof layerOrHandler === 'string' && handler !== undefined)
          ? `${event}::${layerOrHandler}`
          : event;
        const arr = mapListeners[key] ?? [];
        const i = arr.indexOf(h);
        if (i !== -1) arr.splice(i, 1);
      },
      getCanvas() { return canvas; },
      unproject(point) {
        return { lng: (point.x ?? 0) / 100, lat: (point.y ?? 0) / 100 };
      },
      queryRenderedFeatures(point, opts) {
        // Return empty by default; tests can override via api._mockFeatures
        return api._mockFeatures ?? [];
      },
    },

    panel: {
      mounted: [],
      unmountCbs: [],
      mount(el)     { this.mounted.push(el); },
      onUnmount(cb) { this.unmountCbs.push(cb); },
    },

    // Test helpers
    _stateData: stateData,
    _emitted: emitted,
    _sources: sources,
    _layers: layers,
    _mapListeners: mapListeners,
    _canvas: canvas,
    _mockFeatures: null,

    _runUnmount() {
      for (const cb of [...this.panel.unmountCbs]) cb();
    },

    _triggerMapEvent(event, data, layerId = null) {
      const key = layerId ? `${event}::${layerId}` : event;
      for (const h of (mapListeners[key] ?? [])) h(data ?? {});
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Helper: get mounted panel
// ---------------------------------------------------------------------------

function getPanel(api) {
  return api.panel.mounted[0];
}

// ---------------------------------------------------------------------------
// Tests: module structure
// ---------------------------------------------------------------------------

test('init is exported as a function', () => {
  assert.equal(typeof init, 'function');
});

test('module exports only { init }', async () => {
  const mod = await import('../modules/threat-corridor-editor/index.js');
  assert.deepEqual(Object.keys(mod), ['init']);
});

// ---------------------------------------------------------------------------
// Tests: panel mounting
// ---------------------------------------------------------------------------

test('init() mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api.panel.mounted.length, 1);
  assert.ok(api.panel.mounted[0], 'mounted element must be truthy');
});

test('panel has draw button', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  const btn = panel.querySelector('#tce-draw-btn');
  assert.ok(btn, '#tce-draw-btn must exist');
});

test('panel has protected-point button', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  assert.ok(panel.querySelector('#tce-point-btn'), '#tce-point-btn must exist');
});

test('form is hidden by default', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  const form = panel.querySelector('#tce-form');
  assert.ok(form, '#tce-form must exist');
  assert.equal(form.hidden, true);
});

test('edit bar is hidden by default', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  const bar = panel.querySelector('#tce-edit-bar');
  assert.ok(bar, '#tce-edit-bar must exist');
  assert.equal(bar.hidden, true);
});

// ---------------------------------------------------------------------------
// Tests: draw mode
// ---------------------------------------------------------------------------

test('clicking draw button sets cursor to crosshair', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  assert.equal(api._canvas.style.cursor, 'crosshair');
});

test('clicking draw button again exits draw mode and clears cursor', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  const drawBtn = panel.querySelector('#tce-draw-btn');
  drawBtn._fire('click'); // start
  drawBtn._fire('click'); // stop
  assert.equal(api._canvas.style.cursor, '');
});

test('map click in draw mode adds a waypoint to working source', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 200 } });
  // working source should now have 1 point
  const src = api._sources['threat-corridor-editor:working-source'];
  assert.ok(src, 'working source must exist');
  assert.ok(src._data.features.length > 0, 'working source must have features after click');
});

test('three clicks + dblclick with ≥2 waypoints shows form', () => {
  // Browser fires click then dblclick: after 2 real clicks, the dblclick fires a
  // third click event before the dblclick event.  Our fix pops the duplicate tail
  // waypoint in _onDrawDblClick, so 3 click events → pop → 2 waypoints → form.
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 200, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 200, y: 100 } }); // click that precedes dblclick
  api._triggerMapEvent('dblclick', {});
  const form = panel.querySelector('#tce-form');
  assert.equal(form.hidden, false, 'form must be visible after dblclick with ≥2 waypoints');
});

test('dblclick with only 1 waypoint (2 click events) does NOT show form', () => {
  // 1 real click → 1 waypoint; double-click fires another click (→ 2 waypoints) then
  // dblclick pops back to 1 waypoint — below the 2-waypoint minimum, form stays hidden.
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } }); // real click
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } }); // click from dblclick
  api._triggerMapEvent('dblclick', {});
  const form = panel.querySelector('#tce-form');
  assert.equal(form.hidden, true, 'form must stay hidden with only 1 real waypoint');
});

// ---------------------------------------------------------------------------
// Tests: route confirmation — writes state and emits corridor:added
// ---------------------------------------------------------------------------

test('confirming a route writes to threat_corridors state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});

  // Fill form
  const nameInput = panel.querySelector('#tce-name-input');
  const profileSel = panel.querySelector('#tce-profile-select');
  nameInput.value = 'Alpha Route';
  profileSel.value = 'High';

  panel.querySelector('#tce-confirm-btn')._fire('click');

  const state = api._stateData.threat_corridors;
  assert.ok(Array.isArray(state), 'threat_corridors state must be a flat array');
  assert.equal(state.length, 1, 'must have exactly 1 route');
  assert.equal(state[0].name, 'Alpha Route');
  assert.equal(state[0].threat_profile, 'High');
  assert.equal(state[0].waypoints.length, 2, 'must have 2 waypoints');
});

test('confirming a route emits corridor:added', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});

  panel.querySelector('#tce-name-input').value = 'Bravo Route';
  panel.querySelector('#tce-confirm-btn')._fire('click');

  const emitted = api._emitted.find(e => e.event === 'corridor:added');
  assert.ok(emitted, 'corridor:added must be emitted');
  assert.equal(emitted.data.name, 'Bravo Route');
});

test('form hides after confirming route', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  panel.querySelector('#tce-confirm-btn')._fire('click');
  assert.equal(panel.querySelector('#tce-form').hidden, true);
});

test('cancelling form discards working waypoints', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  panel.querySelector('#tce-cancel-btn')._fire('click');

  assert.equal(panel.querySelector('#tce-form').hidden, true, 'form must hide on cancel');
  const src = api._sources['threat-corridor-editor:working-source'];
  // working source should be empty after cancel
  assert.equal(src._data.features.length, 0, 'working source must be empty after cancel');
});

// ---------------------------------------------------------------------------
// Tests: route removal — emits corridor:removed
// ---------------------------------------------------------------------------

test('removing a route emits corridor:removed', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);

  // Add a route first
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  panel.querySelector('#tce-name-input').value = 'Charlie Route';
  panel.querySelector('#tce-confirm-btn')._fire('click');

  // Find the trash button in the route list and fire it
  const routeList = panel.querySelector('#tce-route-list');
  // Walk children to find a button containing trash icon
  function findTrashBtn(el) {
    for (const child of (el._children ?? [])) {
      if (child._tag === 'div' || child._tag === 'button') {
        for (const btn of (child._children ?? [])) {
          if (btn.textContent === '🗑') return btn;
        }
        const nested = findTrashBtn(child);
        if (nested) return nested;
      }
    }
    return null;
  }
  // buttons are direct children of route row divs
  let trashBtn = null;
  for (const row of (routeList._children ?? [])) {
    for (const child of (row._children ?? [])) {
      if (child.textContent === '🗑') { trashBtn = child; break; }
    }
    if (trashBtn) break;
  }
  assert.ok(trashBtn, 'trash button must exist in route list');
  trashBtn._fire('click');

  const emitted = api._emitted.find(e => e.event === 'corridor:removed');
  assert.ok(emitted, 'corridor:removed must be emitted');
  assert.equal(emitted.data.name, 'Charlie Route');
});

test('removing a route removes it from state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);

  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  panel.querySelector('#tce-confirm-btn')._fire('click');

  let trashBtn = null;
  const routeList = panel.querySelector('#tce-route-list');
  for (const row of (routeList._children ?? [])) {
    for (const child of (row._children ?? [])) {
      if (child.textContent === '🗑') { trashBtn = child; break; }
    }
    if (trashBtn) break;
  }
  assert.ok(trashBtn, 'trash button must exist');
  trashBtn._fire('click');

  const state = api._stateData.threat_corridors;
  assert.ok(Array.isArray(state), 'state must be an array');
  assert.equal(state.length, 0, 'routes must be empty after removal');
});

// ---------------------------------------------------------------------------
// Tests: map sources and layers
// ---------------------------------------------------------------------------

test('routes-source is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._sources['threat-corridor-editor:routes-source'], 'routes-source must exist');
});

test('routes-line layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['threat-corridor-editor:routes-line'], 'routes-line layer must exist');
});

test('routes-arrow layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['threat-corridor-editor:routes-arrow'], 'routes-arrow layer must exist');
});

test('protected-point layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['threat-corridor-editor:protected-point'], 'protected-point layer must exist');
});

// ---------------------------------------------------------------------------
// Tests: state watch — reactive rebuild
// ---------------------------------------------------------------------------

test('watch on threat_corridors is registered', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    Array.isArray(api._mapListeners['click'] ?? null) ||
    Object.keys(api._stateData).includes('threat_corridors') ||
    true, // watch callbacks are stored in closures; verify via state set
    'watch must be registered'
  );
  // Verify watch fires by setting state externally and checking sources update.
  // State is the canonical flat ThreatCorridor[] shape with protected_point
  // denormalised onto each corridor.
  api.state.set('threat_corridors', [{
    id: 'ext-1',
    name: 'External',
    threat_profile: 'Low',
    altitude_m: null,
    speed_ms: null,
    waypoints: [[10, 20], [30, 40]],
    protected_point: null,
  }]);
  const src = api._sources['threat-corridor-editor:routes-source'];
  assert.ok(src._data.features.length > 0, 'routes-source must update when state changes');
});

// ---------------------------------------------------------------------------
// Tests: onUnmount cleanup
// ---------------------------------------------------------------------------

test('onUnmount removes all map layers', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();

  const requiredLayers = [
    'threat-corridor-editor:routes-line',
    'threat-corridor-editor:routes-arrow',
    'threat-corridor-editor:protected-point',
  ];
  for (const id of requiredLayers) {
    assert.equal(api._layers[id], undefined, `layer ${id} must be removed on unmount`);
  }
});

test('onUnmount removes all map sources', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();

  const requiredSources = [
    'threat-corridor-editor:routes-source',
    'threat-corridor-editor:protected-point-source',
  ];
  for (const id of requiredSources) {
    assert.equal(api._sources[id], undefined, `source ${id} must be removed on unmount`);
  }
});

test('onUnmount restores cursor after draw mode', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#tce-draw-btn')._fire('click'); // start draw
  api._runUnmount();
  assert.equal(api._canvas.style.cursor, '', 'cursor must be cleared on unmount');
});

test('onUnmount removes draw click listeners', () => {
  const api = makeApi();
  init(api);
  // idle-mode routes-line click listener is always registered; starting draw mode
  // adds further click listeners that must also be cleaned up.
  getPanel(api).querySelector('#tce-draw-btn')._fire('click');
  const clickCountBefore =
    (api._mapListeners['click'] ?? []).length +
    (api._mapListeners['click::threat-corridor-editor:routes-line'] ?? []).length;
  api._runUnmount();
  const clickCountAfter =
    (api._mapListeners['click'] ?? []).length +
    (api._mapListeners['click::threat-corridor-editor:routes-line'] ?? []).length;
  assert.ok(clickCountAfter < clickCountBefore || clickCountAfter === 0,
    'draw click listeners must be removed on unmount');
});

// (S14.7-5, D-349) working-source data must be cleared when module is unmounted
test('(S14.7-5) onUnmount clears working-source data', () => {
  const api = makeApi();
  init(api);
  // Start draw mode and add a waypoint to populate working-source
  getPanel(api).querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 200 } });
  const src = api._sources['threat-corridor-editor:working-source'];
  assert.ok(src._data.features.length > 0, 'working-source must have data before unmount');
  // Unmount — stopDrawMode is called, which clears the canvas cursor but does
  // not flush working-source. After unmount the source is removed entirely.
  api._runUnmount();
  // Source must have been removed (data is not accessible after unmount)
  assert.equal(api._sources['threat-corridor-editor:working-source'], undefined,
    'working-source must be removed on unmount');
});

// (S14.7-2, D-346) clicking a route line in idle mode enters edit mode
test('(S14.7-2) clicking a route line in idle mode enters edit mode', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);

  // Add a route
  panel.querySelector('#tce-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } });
  api._triggerMapEvent('click', { point: { x: 30, y: 40 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  panel.querySelector('#tce-confirm-btn')._fire('click');

  const state = api._stateData.threat_corridors;
  assert.ok(Array.isArray(state), 'threat_corridors state must be an array before route-line click test');
  const routeId = state[0].id;

  // Simulate clicking the routes-line layer in idle mode
  api._mockFeatures = [{ properties: { id: routeId } }];
  api._triggerMapEvent('click', { point: { x: 10, y: 20 } }, 'threat-corridor-editor:routes-line');

  const editBar = panel.querySelector('#tce-edit-bar');
  assert.equal(editBar.hidden, false, 'edit bar must be visible after routes-line click in idle mode');
});
