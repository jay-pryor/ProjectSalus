/**
 * test-library-browser.js — Unit tests for the Library Browser module.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-library-browser.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------
// Mock DOM — must be installed before dynamic import of the module
// ---------------------------------------------------------------------------

function makeMockElement(tag = 'div') {
  const el = {
    _tag: tag,
    _children: [],
    _listeners: {},
    style: { cssText: '', cursor: '', display: '', transform: '' },
    dataset: {},
    textContent: '',
    innerHTML: '',
    id: '',
    title: '',
    disabled: false,
    draggable: false,

    appendChild(child)  { this._children.push(child); return child; },
    append(...children) { for (const c of children) this.appendChild(c); },
    removeChild(child) {
      const i = this._children.indexOf(child);
      if (i !== -1) this._children.splice(i, 1);
    },
    addEventListener(event, handler) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(handler);
    },
    removeEventListener(event, handler) {
      const arr = this._listeners[event] ?? [];
      const i = arr.indexOf(handler);
      if (i !== -1) arr.splice(i, 1);
    },
    setAttribute(name, value) { this[name] = value; },
    getAttribute(name)        { return this[name] ?? null; },
    get firstChild() { return this._children[0] ?? null; },
    /** Simulate an event on this element. */
    _fire(event, data = {}) {
      for (const h of (this._listeners[event] ?? [])) h({ ...data, target: el });
    },
  };
  return el;
}

globalThis.document = {
  createElement: (tag) => makeMockElement(tag),
  _listeners: {},
  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  },
  removeEventListener(event, handler) {
    const arr = this._listeners[event] ?? [];
    const i = arr.indexOf(handler);
    if (i !== -1) arr.splice(i, 1);
  },
  /** Simulate a document-level event (e.g. keydown). */
  _fire(event, data = {}) {
    for (const h of (this._listeners[event] ?? [])) h(data);
  },
};

// Dynamic import AFTER globalThis.document is set so the module code sees the mock.
const { init } = await import('../modules/library-browser/index.js');

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({
  sensors = null,
  effectors = null,
  unprojectResult = { lng: 10, lat: 20 },
} = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const stateWatchers = {};
  const mapListeners = {};
  const sources = {};
  const layers = {};
  const canvas = makeMockElement('canvas');

  const stateData = {
    sensor_library: sensors,
    effector_library: effectors,
  };

  const api = {
    // Test-only access
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _stateWatchers: stateWatchers,
    _mapListeners: mapListeners,
    _sources: sources,
    _layers: layers,
    _canvas: canvas,
    _stateData: stateData,

    _runUnmount() {
      const cbs = [...unmountCbs];
      unmountCbs.length = 0;
      for (const cb of cbs) cb();
    },

    _triggerWatch(key, value) {
      stateData[key] = value;
      for (const cb of (stateWatchers[key] ?? [])) cb(value);
    },

    _triggerMapEvent(event, data) {
      for (const h of (mapListeners[event] ?? [])) h(data);
    },

    moduleId: 'library-browser',

    state: {
      get(key) { return stateData[key] ?? null; },
      watch(key, cb) {
        if (!stateWatchers[key]) stateWatchers[key] = [];
        stateWatchers[key].push(cb);
        return () => {
          const arr = stateWatchers[key];
          const i = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
      },
      set() { throw new Error('library-browser must not call state.set'); },
    },

    bus: {
      emit(event, data) { emitted.push({ event, data }); },
      on()  { throw new Error('library-browser must not call bus.on'); },
    },

    map: {
      addSource(id, spec) {
        sources[id] = { ...spec, _data: spec.data, setData(d) { this._data = d; } };
      },
      removeSource(id) { delete sources[id]; },
      getSource(id)    { return sources[id] ?? null; },
      addLayer(spec)   { layers[spec.id] = spec; },
      removeLayer(id)  { delete layers[id]; },
      getLayer(id)     { return layers[id] ?? null; },
      on(event, handler) {
        if (!mapListeners[event]) mapListeners[event] = [];
        mapListeners[event].push(handler);
      },
      off(event, handler) {
        const arr = mapListeners[event] ?? [];
        const i = arr.indexOf(handler);
        if (i !== -1) arr.splice(i, 1);
      },
      getCanvas()        { return canvas; },
      unproject(_point)  { return unprojectResult; },
    },

    panel: {
      mount(el)       { mounted.push(el); },
      onUnmount(cb)   { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// DOM tree traversal helpers
// ---------------------------------------------------------------------------

function findAll(root, predicate) {
  const results = [];
  function walk(el) {
    if (!el || typeof el !== 'object') return;
    if (predicate(el)) results.push(el);
    for (const child of (el._children ?? [])) walk(child);
  }
  walk(root);
  return results;
}

function findDragHandles(panel) {
  return findAll(panel, el => el.draggable === 'true' || el.draggable === true);
}

function findPlaceButtons(panel) {
  return findAll(panel, el => el._tag === 'button' && el.textContent === 'Place');
}

// ---------------------------------------------------------------------------
// Sample library data
// ---------------------------------------------------------------------------

const SAMPLE_SENSORS = {
  Radar: [
    {
      name: 'Radar Alpha',
      type: 'Radar',
      max_range_m: 5000,
      azimuth_coverage_deg: 360,
      cost_aud: 100000,
      confidence: 'measured',
    },
  ],
};

const SAMPLE_EFFECTORS = {
  RF: [
    {
      name: 'Jammer Beta',
      type: 'RF',
      max_range_m: 1000,
      azimuth_coverage_deg: 180,
      cost_aud: 50000,
      confidence: 'estimated',
    },
  ],
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.join(__dirname, '../modules/library-browser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'emits', 'subscribes', 'prerequisites', 'layer_id_prefix']) {
    assert.ok(f in m, `manifest missing field: '${f}'`);
  }
});

test('manifest reads sensor_library and effector_library', async () => {
  const raw = await readFile(
    path.join(__dirname, '../modules/library-browser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.reads.includes('sensor_library'),   'reads must include sensor_library');
  assert.ok(m.reads.includes('effector_library'), 'reads must include effector_library');
});

test('manifest has no writes', async () => {
  const raw = await readFile(
    path.join(__dirname, '../modules/library-browser/manifest.json'), 'utf8'
  );
  assert.deepEqual(JSON.parse(raw).writes, []);
});

test('manifest emits placement:pending', async () => {
  const raw = await readFile(
    path.join(__dirname, '../modules/library-browser/manifest.json'), 'utf8'
  );
  assert.ok(JSON.parse(raw).emits.includes('placement:pending'));
});

test('manifest has no prerequisites', async () => {
  const raw = await readFile(
    path.join(__dirname, '../modules/library-browser/manifest.json'), 'utf8'
  );
  assert.deepEqual(JSON.parse(raw).prerequisites, []);
});

// ---------------------------------------------------------------------------
// init() — basic setup
// ---------------------------------------------------------------------------

test('init() mounts a panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1, 'panel.mount should be called once');
  assert.ok(api._mounted[0], 'mounted element should be truthy');
});

test('init() adds library-browser:drag-ghost source', () => {
  const api = makeApi();
  init(api);
  assert.ok('library-browser:drag-ghost' in api._sources, 'ghost source should be added');
});

test('init() adds library-browser:drag-ghost-circle layer', () => {
  const api = makeApi();
  init(api);
  assert.ok('library-browser:drag-ghost-circle' in api._layers, 'ghost layer should be added');
});

test('init() registers dragover and drop listeners on map', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._mapListeners['dragover'] ?? []).length > 0, 'dragover listener should be registered');
  assert.ok((api._mapListeners['drop']     ?? []).length > 0, 'drop listener should be registered');
});

test('init() watches sensor_library and effector_library', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._stateWatchers['sensor_library']   ?? []).length > 0, 'sensor_library watch should be registered');
  assert.ok((api._stateWatchers['effector_library'] ?? []).length > 0, 'effector_library watch should be registered');
});

// ---------------------------------------------------------------------------
// onUnmount cleanup
// ---------------------------------------------------------------------------

test('onUnmount removes dragover and drop map listeners', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();
  assert.equal((api._mapListeners['dragover'] ?? []).length, 0, 'dragover listener should be removed');
  assert.equal((api._mapListeners['drop']     ?? []).length, 0, 'drop listener should be removed');
});

test('onUnmount unsubscribes state watchers', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();
  assert.equal((api._stateWatchers['sensor_library']   ?? []).length, 0, 'sensor_library watcher should be removed');
  assert.equal((api._stateWatchers['effector_library'] ?? []).length, 0, 'effector_library watcher should be removed');
});

test('onUnmount removes ghost layer and source', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();
  assert.ok(!('library-browser:drag-ghost-circle' in api._layers),  'ghost layer should be removed');
  assert.ok(!('library-browser:drag-ghost'        in api._sources), 'ghost source should be removed');
});

// ---------------------------------------------------------------------------
// Library rendering
// ---------------------------------------------------------------------------

test('panel is mounted even when both libraries are null', () => {
  const api = makeApi({ sensors: null, effectors: null });
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('sensor_library watch triggers panel rebuild', () => {
  const api = makeApi({ sensors: null, effectors: null });
  init(api);
  const before = api._mounted.length;
  api._triggerWatch('sensor_library', SAMPLE_SENSORS);
  assert.equal(api._mounted.length, before + 1, 'panel should be re-mounted after sensor watch fires');
});

test('effector_library watch triggers panel rebuild', () => {
  const api = makeApi({ sensors: null, effectors: null });
  init(api);
  const before = api._mounted.length;
  api._triggerWatch('effector_library', SAMPLE_EFFECTORS);
  assert.equal(api._mounted.length, before + 1, 'panel should be re-mounted after effector watch fires');
});

test('panel contains drag handles when library has items', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS, effectors: SAMPLE_EFFECTORS });
  init(api);
  const panel = api._mounted[api._mounted.length - 1];
  const handles = findDragHandles(panel);
  assert.ok(handles.length >= 2, 'should have one drag handle per library item');
});

test('panel contains Place buttons when library has items', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS, effectors: SAMPLE_EFFECTORS });
  init(api);
  const panel = api._mounted[api._mounted.length - 1];
  const btns = findPlaceButtons(panel);
  assert.ok(btns.length >= 2, 'should have one Place button per library item');
});

// ---------------------------------------------------------------------------
// Drag-and-drop
// ---------------------------------------------------------------------------

test('map drop after dragstart emits placement:pending', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  const handles = findDragHandles(panel);
  assert.ok(handles.length > 0, 'need a drag handle');

  const mockDT = { _data: {}, setData(k, v) { this._data[k] = v; }, effectAllowed: '' };
  handles[0]._fire('dragstart', { dataTransfer: mockDT });

  api._triggerMapEvent('drop', { preventDefault() {}, offsetX: 100, offsetY: 200 });

  assert.equal(api._emitted.length, 1, 'placement:pending should be emitted');
  assert.equal(api._emitted[0].event, 'placement:pending');
  assert.ok('lat'        in api._emitted[0].data, 'emission must include lat');
  assert.ok('lng'        in api._emitted[0].data, 'emission must include lng');
  assert.ok('definition' in api._emitted[0].data, 'emission must include definition');
  assert.equal(api._emitted[0].data.definition.name, 'Radar Alpha');
});

test('definition stored in dataTransfer on dragstart', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  const handles = findDragHandles(panel);

  const mockDT = { _data: {}, setData(k, v) { this._data[k] = v; }, effectAllowed: '' };
  handles[0]._fire('dragstart', { dataTransfer: mockDT });

  assert.ok('application/json' in mockDT._data, 'definition should be stored in dataTransfer');
  const stored = JSON.parse(mockDT._data['application/json']);
  assert.equal(stored.name, 'Radar Alpha');
});

test('dragend clears ghost source data', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  const handles = findDragHandles(panel);

  const mockDT = { setData() {}, effectAllowed: '' };
  handles[0]._fire('dragstart', { dataTransfer: mockDT });
  handles[0]._fire('dragend', {});

  const ghostSrc = api._sources['library-browser:drag-ghost'];
  assert.ok(ghostSrc, 'ghost source should exist');
  assert.deepEqual(ghostSrc._data.features ?? [], [], 'ghost should be cleared after dragend');
});

test('map drop without prior dragstart does not emit', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  api._triggerMapEvent('drop', { preventDefault() {}, offsetX: 100, offsetY: 200 });

  assert.equal(api._emitted.length, 0, 'no emission expected without a prior dragstart');
});

// ---------------------------------------------------------------------------
// Click-to-place
// ---------------------------------------------------------------------------

test('Place button click sets cursor to crosshair', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  const btns = findPlaceButtons(panel);
  assert.ok(btns.length > 0, 'need a Place button');

  btns[0]._fire('click', {});
  assert.equal(api._canvas.style.cursor, 'crosshair', 'cursor should be set to crosshair');
});

test('Place button click registers a map click listener', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});

  assert.ok((api._mapListeners['click'] ?? []).length > 0, 'map click listener should be registered');
});

test('map click in click-to-place mode emits placement:pending with coordinates', () => {
  const api = makeApi({
    sensors: SAMPLE_SENSORS,
    unprojectResult: { lng: 145.5, lat: -34.2 },
  });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  api._triggerMapEvent('click', { point: { x: 50, y: 60 } });

  assert.equal(api._emitted.length, 1);
  assert.equal(api._emitted[0].event, 'placement:pending');
  assert.equal(api._emitted[0].data.lng, 145.5);
  assert.equal(api._emitted[0].data.lat, -34.2);
  assert.equal(api._emitted[0].data.definition.name, 'Radar Alpha');
});

test('map click listener is removed after click-to-place fires', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  api._triggerMapEvent('click', { point: { x: 50, y: 60 } });

  assert.equal((api._mapListeners['click'] ?? []).length, 0, 'click listener should be removed after placement');
});

test('map click listener is removed after click-to-place fires — cursor restored', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  api._triggerMapEvent('click', { point: { x: 50, y: 60 } });

  assert.equal(api._canvas.style.cursor, '', 'cursor should be restored after placement');
});

test('Escape key cancels click-to-place and restores cursor', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  assert.equal(api._canvas.style.cursor, 'crosshair', 'cursor should be crosshair after Place click');

  // D-315 fix: keydown listener is on the map canvas, not document
  api._canvas._fire('keydown', { key: 'Escape' });

  assert.equal(api._canvas.style.cursor, '', 'cursor should be restored after Escape');
  assert.equal((api._mapListeners['click'] ?? []).length, 0, 'click listener removed after Escape');
});

test('Escape key does not emit placement:pending', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  // D-315 fix: keydown listener is on the map canvas, not document
  api._canvas._fire('keydown', { key: 'Escape' });

  assert.equal(api._emitted.length, 0, 'Escape should not emit placement:pending');
});

test('onUnmount cancels active click-to-place mode and restores cursor', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});
  assert.equal(api._canvas.style.cursor, 'crosshair');

  api._runUnmount();

  assert.equal(api._canvas.style.cursor, '', 'cursor should be restored on unmount');
});

test('onUnmount removes keydown listener from map canvas', () => {
  const api = makeApi({ sensors: SAMPLE_SENSORS });
  init(api);

  const panel = api._mounted[api._mounted.length - 1];
  findPlaceButtons(panel)[0]._fire('click', {});

  // D-315 fix: keydown listener is on the map canvas, not document
  assert.ok(
    (api._canvas._listeners['keydown'] ?? []).length > 0,
    'keydown listener should be present on canvas during click-to-place'
  );

  api._runUnmount();

  assert.equal(
    (api._canvas._listeners['keydown'] ?? []).length, 0,
    'keydown listener should be removed from canvas on unmount'
  );
});
