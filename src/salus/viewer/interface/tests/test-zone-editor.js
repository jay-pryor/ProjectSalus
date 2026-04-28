/**
 * test-zone-editor.js — Unit tests for the Zone Editor module (S14.7-3, S14.7-4).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-zone-editor.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal DOM mock
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

const { init } = await import('../modules/zone-editor/index.js');

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({ initState = null } = {}) {
  const stateData = { zones: initState };
  const watchCallbacks = {};
  const unmountCallbacks = [];
  const emitted = [];
  const sources = {};
  const layers = {};
  const mapListeners = {};
  const canvas = _makeEl('canvas');
  canvas.style = { cursor: '' };

  const api = {
    moduleId: 'zone-editor',

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
      getSource(id) { return sources[id] ?? null; },
      getLayer(id)  { return layers[id] ?? null; },
      addSource(id, spec) {
        sources[id] = { ...spec, _data: spec.data ?? null, setData(d) { this._data = d; } };
      },
      addLayer(spec)  { layers[spec.id] = spec; },
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
      queryRenderedFeatures(_point, _opts) { return []; },
    },

    panel: {
      mounted: [],
      unmountCbs: [],
      mount(el)     { this.mounted.push(el); },
      onUnmount(cb) { this.unmountCbs.push(cb); },
    },

    _stateData: stateData,
    _emitted: emitted,
    _sources: sources,
    _layers: layers,
    _mapListeners: mapListeners,
    _canvas: canvas,

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

function getPanel(api) {
  return api.panel.mounted[0];
}

/** Helper: simulate drawing a triangle and firing dblclick.
 *
 * Browsers fire click then dblclick in sequence.  Our _onDrawDblClick fix pops
 * the duplicate tail vertex added by the preceding click event (D-343).  To
 * end up with 3 confirmed vertices we therefore send 4 click events + dblclick:
 * 3 real vertex clicks + 1 click that precedes the dblclick (gets popped).
 */
function _drawTriangle(api, panel) {
  panel.querySelector('#ze-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 300, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 200, y: 250 } });
  api._triggerMapEvent('click', { point: { x: 200, y: 250 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
}

// ---------------------------------------------------------------------------
// Tests: module structure
// ---------------------------------------------------------------------------

test('init is exported as a function', () => {
  assert.equal(typeof init, 'function');
});

test('module exports only { init }', async () => {
  const mod = await import('../modules/zone-editor/index.js');
  assert.deepEqual(Object.keys(mod), ['init']);
});

// ---------------------------------------------------------------------------
// Tests: panel mounting
// ---------------------------------------------------------------------------

test('init() mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api.panel.mounted.length, 1);
});

test('panel has draw button', () => {
  const api = makeApi();
  init(api);
  assert.ok(getPanel(api).querySelector('#ze-draw-btn'), '#ze-draw-btn must exist');
});

test('panel has zone type selector', () => {
  const api = makeApi();
  init(api);
  assert.ok(getPanel(api).querySelector('#ze-zone-type'), '#ze-zone-type must exist');
});

test('form is hidden by default', () => {
  const api = makeApi();
  init(api);
  const form = getPanel(api).querySelector('#ze-form');
  assert.ok(form, '#ze-form must exist');
  assert.equal(form.hidden, true);
});

test('threshold-error element is hidden by default', () => {
  const api = makeApi();
  init(api);
  const el = getPanel(api).querySelector('#ze-threshold-error');
  assert.ok(el, '#ze-threshold-error must exist');
  assert.equal(el.hidden, true);
});

// ---------------------------------------------------------------------------
// Tests: draw mode
// ---------------------------------------------------------------------------

test('clicking draw button sets cursor to crosshair', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#ze-draw-btn')._fire('click');
  assert.equal(api._canvas.style.cursor, 'crosshair');
});

test('3 clicks update working-source with polygon preview', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#ze-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 300, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 200, y: 250 } });
  const src = api._sources['zone-editor:working-source'];
  assert.ok(src, 'working-source must exist');
  assert.ok(src._data.features.length > 0, 'working-source must have features');
});

test('dblclick with ≥3 vertices shows confirmation form', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);
  assert.equal(panel.querySelector('#ze-form').hidden, false, 'form must show after dblclick');
});

test('dblclick with only 2 real vertices does NOT show form', () => {
  // User draws 2 real vertices then double-clicks: browser sends click1, click2,
  // click3 (from dblclick), dblclick.  After pop → [v1, v2] → 2 < 3 → no form.
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  panel.querySelector('#ze-draw-btn')._fire('click');
  api._triggerMapEvent('click', { point: { x: 100, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 300, y: 100 } });
  api._triggerMapEvent('click', { point: { x: 300, y: 100 } }); // click preceding dblclick
  api._triggerMapEvent('dblclick', {});
  assert.equal(panel.querySelector('#ze-form').hidden, true, 'form must stay hidden with only 2 real vertices');
});

// ---------------------------------------------------------------------------
// S14.7-4 test: adding a zone writes the correct state
// ---------------------------------------------------------------------------

test('(S14.7-4) adding a priority zone writes correct state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const nameInput   = panel.querySelector('#ze-zone-name');
  const typeSelect  = panel.querySelector('#ze-zone-type');
  const threshInput = panel.querySelector('#ze-threshold');
  nameInput.value   = 'North Perimeter';
  typeSelect.value  = 'priority';
  threshInput.value = '80';

  panel.querySelector('#ze-confirm-btn')._fire('click');

  const state = api._stateData.zones;
  assert.ok(state, 'zones state must be set');
  assert.equal(state.priority.length, 1, 'must have exactly 1 priority zone');
  assert.equal(state.exclusion.length, 0, 'must have no exclusion zones');
  const z = state.priority[0];
  assert.equal(z.label, 'North Perimeter', 'zone label must match');
  assert.equal(z.min_coverage_pct, 80, 'min_coverage_pct must be 80');
  assert.equal(z.geometry.type, 'Polygon', 'geometry type must be Polygon');
  // Outer ring is closed (3 unique vertices + 1 closing duplicate).
  assert.equal(z.geometry.coordinates[0].length, 4, 'closed ring must have 4 positions');
});

test('(S14.7-4) adding an exclusion zone writes correct state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const nameInput  = panel.querySelector('#ze-zone-name');
  const typeSelect = panel.querySelector('#ze-zone-type');
  const reasonInput = panel.querySelector('#ze-reason');
  nameInput.value  = 'Comms Mast';
  typeSelect.value = 'exclusion';
  // Force drawType to 'exclusion' by re-triggering the draw after type change
  // (drawType is captured when draw mode starts — test sets it here via internal state)
  // Since the form was opened with the last drawType, we patch it via the test:
  // We re-draw with exclusion type selected
  panel.querySelector('#ze-cancel-btn')._fire('click');
  panel.querySelector('#ze-zone-type').value = 'exclusion';
  _drawTriangle(api, panel);
  panel.querySelector('#ze-zone-name').value = 'Comms Mast';
  if (reasonInput) reasonInput.value = 'Communications mast footprint';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  const state = api._stateData.zones;
  assert.ok(state, 'zones state must be set');
  assert.equal(state.exclusion.length, 1, 'must have 1 exclusion zone');
  assert.equal(state.priority.length, 0, 'must have no priority zones');
  const z = state.exclusion[0];
  assert.equal(z.label, 'Comms Mast', 'exclusion label must match');
  assert.equal(z.geometry.type, 'Polygon', 'exclusion geometry type must be Polygon');
  assert.equal(z.reason, 'Communications mast footprint', 'exclusion zones carry reason');
});

test('confirming a zone emits zone:added', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);
  panel.querySelector('#ze-zone-name').value = 'Test Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  const evt = api._emitted.find(e => e.event === 'zone:added');
  assert.ok(evt, 'zone:added must be emitted');
  assert.equal(evt.data.name, 'Test Zone');
});

// ---------------------------------------------------------------------------
// S14.7-4 test: removing a zone emits zone:removed
// ---------------------------------------------------------------------------

test('(S14.7-4) removing a zone emits zone:removed', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);

  // Add a zone
  _drawTriangle(api, panel);
  panel.querySelector('#ze-zone-name').value = 'Delta Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  // Find and click trash button
  const zoneList = panel.querySelector('#ze-zone-list');
  let trashBtn = null;
  for (const row of (zoneList._children ?? [])) {
    for (const child of (row._children ?? [])) {
      if (child.textContent === '🗑') { trashBtn = child; break; }
    }
    if (trashBtn) break;
  }
  assert.ok(trashBtn, 'trash button must be present in zone list');
  trashBtn._fire('click');

  const evt = api._emitted.find(e => e.event === 'zone:removed');
  assert.ok(evt, 'zone:removed must be emitted');
  assert.equal(evt.data.name, 'Delta Zone');
});

test('removing a zone removes it from state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);

  _drawTriangle(api, panel);
  panel.querySelector('#ze-zone-name').value = 'Echo Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  const zoneList = panel.querySelector('#ze-zone-list');
  let trashBtn = null;
  for (const row of (zoneList._children ?? [])) {
    for (const child of (row._children ?? [])) {
      if (child.textContent === '🗑') { trashBtn = child; break; }
    }
    if (trashBtn) break;
  }
  trashBtn._fire('click');

  const state = api._stateData.zones;
  assert.equal(state.priority.length, 0, 'priority must be empty after removal');
  assert.equal(state.exclusion.length, 0, 'exclusion must be empty after removal');
});

// ---------------------------------------------------------------------------
// S14.7-4 test: invalid threshold value is rejected with a visible error
// ---------------------------------------------------------------------------

test('(S14.7-4) non-numeric threshold shows error and does NOT write state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const typeSelect  = panel.querySelector('#ze-zone-type');
  const threshInput = panel.querySelector('#ze-threshold');
  const threshError = panel.querySelector('#ze-threshold-error');
  typeSelect.value  = 'priority';
  threshInput.value = 'abc';

  // The form was opened with the type from before draw started.
  // We ensure threshold validation runs by confirming:
  panel.querySelector('#ze-zone-name').value = 'Bad Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  // Error must be shown (note: error visibility depends on the current drawType
  // being 'priority'. Since draw started with whatever value ze-zone-type had,
  // which defaults to 'priority', this should fire the validator.)
  assert.equal(threshError.hidden, false, 'threshold error must be visible for invalid input');
  // State must NOT have been written (or zones must be empty)
  const state = api._stateData.zones;
  assert.ok(!state || ((state.priority?.length ?? 0) + (state.exclusion?.length ?? 0) === 0), 'state must not be written when threshold is invalid');
});

test('(S14.7-4) out-of-range threshold (>100) shows error', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const threshInput = panel.querySelector('#ze-threshold');
  const threshError = panel.querySelector('#ze-threshold-error');
  threshInput.value = '150';

  panel.querySelector('#ze-zone-name').value = 'Over Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  assert.equal(threshError.hidden, false, 'error must show for threshold > 100');
  const state = api._stateData.zones;
  assert.ok(!state || ((state.priority?.length ?? 0) + (state.exclusion?.length ?? 0) === 0), 'state must not be written for out-of-range threshold');
});

test('(S14.7-4) negative threshold shows error', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const threshInput = panel.querySelector('#ze-threshold');
  const threshError = panel.querySelector('#ze-threshold-error');
  threshInput.value = '-5';

  panel.querySelector('#ze-confirm-btn')._fire('click');

  assert.equal(threshError.hidden, false, 'error must show for threshold < 0');
});

test('(S14.7-4) valid threshold clears error and writes state', () => {
  const api = makeApi();
  init(api);
  const panel = getPanel(api);
  _drawTriangle(api, panel);

  const threshInput = panel.querySelector('#ze-threshold');
  const threshError = panel.querySelector('#ze-threshold-error');
  threshInput.value = '75';
  panel.querySelector('#ze-zone-name').value = 'Valid Zone';
  panel.querySelector('#ze-confirm-btn')._fire('click');

  assert.equal(threshError.hidden, true, 'error must be hidden for valid threshold');
  const state = api._stateData.zones;
  assert.ok(state && state.priority.length === 1, 'priority state must be written for valid threshold');
  assert.equal(state.priority[0].min_coverage_pct, 75);
});

// ---------------------------------------------------------------------------
// Tests: map sources and layers
// ---------------------------------------------------------------------------

test('priority-fill layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['zone-editor:priority-fill'], 'priority-fill layer must exist');
});

test('priority-label layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['zone-editor:priority-label'], 'priority-label layer must exist');
});

test('exclusion-fill layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['zone-editor:exclusion-fill'], 'exclusion-fill layer must exist');
});

test('exclusion-outline layer is created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['zone-editor:exclusion-outline'], 'exclusion-outline layer must exist');
});

test('priority-source and exclusion-source are created on init', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._sources['zone-editor:priority-source'],  'priority-source must exist');
  assert.ok(api._sources['zone-editor:exclusion-source'], 'exclusion-source must exist');
});

// ---------------------------------------------------------------------------
// Tests: zones state watch — reactive rebuild (S14.7-3)
// ---------------------------------------------------------------------------

test('state watch on zones triggers source rebuild', () => {
  const api = makeApi();
  init(api);

  // Canonical zone state: {priority: PriorityZone[], exclusion: ExclusionZone[]}
  // PriorityZone fields: id, label, geometry (GeoJSON Polygon), min_coverage_pct
  api.state.set('zones', {
    priority: [{
      id: 'z1',
      label: 'Remote Zone',
      min_coverage_pct: 90,
      geometry: {
        type: 'Polygon',
        coordinates: [[[10, 20], [30, 20], [20, 40], [10, 20]]],
      },
    }],
    exclusion: [],
  });

  const pSrc = api._sources['zone-editor:priority-source'];
  assert.ok(pSrc._data.features.length > 0, 'priority-source must update when zones state changes');
});

test('exclusion zones update exclusion-source on state watch', () => {
  const api = makeApi();
  init(api);

  // Canonical ExclusionZone fields: id, label, geometry (GeoJSON Polygon), reason
  api.state.set('zones', {
    priority: [],
    exclusion: [{
      id: 'z2',
      label: 'No-Go Zone',
      reason: 'Building',
      geometry: {
        type: 'Polygon',
        coordinates: [[[5, 5], [15, 5], [10, 15], [5, 5]]],
      },
    }],
  });

  const eSrc = api._sources['zone-editor:exclusion-source'];
  assert.ok(eSrc._data.features.length > 0, 'exclusion-source must update for exclusion zones');
});

// ---------------------------------------------------------------------------
// Tests: onUnmount cleanup (S14.7-3)
// ---------------------------------------------------------------------------

test('onUnmount removes all required layers', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();

  const required = [
    'zone-editor:priority-fill',
    'zone-editor:priority-label',
    'zone-editor:exclusion-fill',
    'zone-editor:exclusion-outline',
  ];
  for (const id of required) {
    assert.equal(api._layers[id], undefined, `layer ${id} must be removed on unmount`);
  }
});

test('onUnmount removes all required sources', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();

  const required = [
    'zone-editor:priority-source',
    'zone-editor:exclusion-source',
    'zone-editor:working-source',
  ];
  for (const id of required) {
    assert.equal(api._sources[id], undefined, `source ${id} must be removed on unmount`);
  }
});

test('onUnmount restores cursor after draw mode', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#ze-draw-btn')._fire('click'); // activate draw mode
  api._runUnmount();
  assert.equal(api._canvas.style.cursor, '', 'cursor must be cleared on unmount');
});

test('onUnmount removes draw click listeners', () => {
  const api = makeApi();
  init(api);
  getPanel(api).querySelector('#ze-draw-btn')._fire('click');
  const before = (api._mapListeners['click'] ?? []).length;
  api._runUnmount();
  const after = (api._mapListeners['click'] ?? []).length;
  assert.ok(after < before || after === 0, 'draw click listeners must be removed on unmount');
});
