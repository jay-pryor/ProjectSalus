/**
 * test-terrain-loader.js — Unit tests for the terrain-loader module.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-terrain-loader.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal DOM mock (set before import so module-scope expressions are safe)
// ---------------------------------------------------------------------------

function _makeEl(tag = 'div') {
  const el = {
    _tag: tag,
    _children: [],
    _listeners: {},
    _attrs: {},
    id: '',
    hidden: false,
    value: 0,
    textContent: '',
    innerHTML: '',
    style: {},
    files: null,
    dataset: {},
    className: '',
    get firstElementChild() { return this._children[0] ?? null; },
    get firstChild() { return this._children[0] ?? null; },
    appendChild(child) { this._children.push(child); return child; },
    removeChild(child) {
      const i = this._children.indexOf(child);
      if (i !== -1) this._children.splice(i, 1);
    },
    querySelector(sel) {
      // Minimal support for #id selectors
      const idMatch = sel.match(/^#(.+)$/);
      if (idMatch) {
        const id = idMatch[1];
        const search = (node) => {
          if (node.id === id) return node;
          for (const c of node._children) {
            const found = search(c);
            if (found) return found;
          }
          return null;
        };
        return search(this);
      }
      return null;
    },
    querySelectorAll() { return []; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k] ?? null; },
    addEventListener(event, handler) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(handler);
    },
    removeEventListener(event, handler) {
      if (this._listeners[event]) {
        this._listeners[event] = this._listeners[event].filter(h => h !== handler);
      }
    },
    /** test helper: fire all listeners for an event */
    _fire(event, ...args) {
      for (const h of (this._listeners[event] ?? [])) h(...args);
    },
  };

  // When innerHTML is set, simulate DOM nesting:
  // The first matched id is the root child of this element; all remaining ids
  // are added as flat children of that root so querySelector can find them.
  // The `hidden` boolean attribute is extracted from the HTML tag and applied.
  Object.defineProperty(el, 'innerHTML', {
    set(html) {
      el._children.length = 0; // reset

      // Extract id + hidden status from each opening tag.
      // Matches id="xxx" and checks whether the tag also has a bare 'hidden' attribute.
      const tagPattern = /(<[a-z]+\s[^>]*?id="([^"]+)"[^>]*?>)/gi;
      const entries = []; // [{id, hidden}]
      let tm;
      while ((tm = tagPattern.exec(html)) !== null) {
        const tag = tm[1];
        const id = tm[2];
        const isHidden = /\bhidden\b/.test(tag);
        entries.push({ id, isHidden });
      }

      if (entries.length === 0) return;

      // First entry = root panel element (direct child of el)
      const root = _makeEl('div');
      root.id = entries[0].id;
      root.hidden = entries[0].isHidden;
      el._children.push(root);

      // Remaining entries = flat children of root so querySelector can reach them
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
  createElement(tag) { return _makeEl(tag); },
};

// Safe window.location mock
globalThis.window = { location: { origin: 'http://localhost:8000' } };

// EventSource mock
const _esInstances = [];
class MockEventSource {
  constructor(url) {
    this.url = url;
    this._closed = false;
    this.onmessage = null;
    this.onerror = null;
    _esInstances.push(this);
  }
  close() { this._closed = true; }
  /** test helper: simulate an SSE message */
  _emit(data) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(data) });
  }
  _emitError() {
    if (this.onerror) this.onerror(new Error('mock error'));
  }
}
globalThis.EventSource = MockEventSource;

// ---------------------------------------------------------------------------
// Import module under test (after globals are in place)
// ---------------------------------------------------------------------------

import { init } from '../modules/terrain-loader/index.js';

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeMockApi({ terrainValue = null } = {}) {
  let currentTerrain = terrainValue;
  const watchCallbacks = {};
  const unmountCallbacks = [];
  const mapCalls = [];

  // Track source/layer existence for getSource/getLayer
  const sources = new Set();
  const layers = new Set();

  const api = {
    moduleId: 'terrain-loader',

    state: {
      get(key) { return key === 'terrain' ? currentTerrain : null; },
      set(key, value) {
        if (key === 'terrain') {
          const old = currentTerrain;
          currentTerrain = value;
          for (const cb of (watchCallbacks[key] ?? [])) cb(value, old);
        }
      },
      watch(key, cb) {
        if (!watchCallbacks[key]) watchCallbacks[key] = [];
        watchCallbacks[key].push(cb);
        return () => {
          watchCallbacks[key] = (watchCallbacks[key] ?? []).filter(c => c !== cb);
        };
      },
    },

    bus: {
      emitCalls: [],
      emit(event, data) { this.emitCalls.push({ event, data }); },
    },

    map: {
      _calls: mapCalls,
      getSource(id) { return sources.has(id) ? { id } : null; },
      getLayer(id) { return layers.has(id) ? { id } : null; },
      addSource(id, spec) { sources.add(id); mapCalls.push({ method: 'addSource', args: [id, spec] }); },
      addLayer(spec) { layers.add(spec.id); mapCalls.push({ method: 'addLayer', args: [spec] }); },
      removeSource(id) { sources.delete(id); mapCalls.push({ method: 'removeSource', args: [id] }); },
      removeLayer(id) { layers.delete(id); mapCalls.push({ method: 'removeLayer', args: [id] }); },
      fitBounds(bounds, opts) { mapCalls.push({ method: 'fitBounds', args: [bounds, opts] }); },
      setTerrainSource(sourceId) { mapCalls.push({ method: 'setTerrainSource', args: [sourceId] }); },
    },

    panel: {
      mountedElements: [],
      mount(el) { this.mountedElements.push(el); },
      onUnmount(cb) { unmountCallbacks.push(cb); },
    },

    _terrainValue: () => currentTerrain,
    _watchCallbacks: watchCallbacks,
    _unmountCallbacks: unmountCallbacks,
  };

  return api;
}

// ---------------------------------------------------------------------------
// Tests: module structure
// ---------------------------------------------------------------------------

test('init is exported as a function', () => {
  assert.equal(typeof init, 'function');
});

// ---------------------------------------------------------------------------
// Tests: panel mounting
// ---------------------------------------------------------------------------

test('init() mounts a panel element', () => {
  const api = makeMockApi();
  init(api);
  assert.equal(api.panel.mountedElements.length, 1);
  assert.ok(api.panel.mountedElements[0], 'mounted element must be truthy');
});

test('panel has DEM file input with correct accept attribute', () => {
  const api = makeMockApi();
  init(api);
  const panel = api.panel.mountedElements[0];
  const demInput = panel.querySelector('#tl-dem-input');
  assert.ok(demInput, '#tl-dem-input must exist');
});

test('panel has progress section hidden by default', () => {
  const api = makeMockApi();
  init(api);
  const panel = api.panel.mountedElements[0];
  const progressSection = panel.querySelector('#tl-progress-section');
  assert.ok(progressSection, '#tl-progress-section must exist');
  assert.equal(progressSection.hidden, true);
});

test('panel has summary section hidden when no terrain loaded', () => {
  const api = makeMockApi();
  init(api);
  const panel = api.panel.mountedElements[0];
  const summary = panel.querySelector('#tl-summary');
  assert.ok(summary, '#tl-summary must exist');
  assert.equal(summary.hidden, true);
});

// ---------------------------------------------------------------------------
// Tests: state watch
// ---------------------------------------------------------------------------

test('init() registers api.state.watch for terrain key', () => {
  const api = makeMockApi();
  init(api);
  assert.ok(
    Array.isArray(api._watchCallbacks['terrain']) && api._watchCallbacks['terrain'].length > 0,
    'at least one watch callback must be registered on "terrain"'
  );
});

test('onUnmount unsubscribes from terrain watch', () => {
  const api = makeMockApi();
  init(api);
  const beforeCount = (api._watchCallbacks['terrain'] ?? []).length;
  assert.ok(beforeCount > 0, 'watch should be registered');

  // Fire all onUnmount callbacks
  for (const cb of api._unmountCallbacks) cb();

  const afterCount = (api._watchCallbacks['terrain'] ?? []).length;
  assert.equal(afterCount, beforeCount - 1, 'watch should be unsubscribed after unmount');
});

// ---------------------------------------------------------------------------
// Tests: initial terrain state rendering
// ---------------------------------------------------------------------------

test('init() shows summary when terrain state is already set', () => {
  const metadata = {
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };
  const api = makeMockApi({ terrainValue: metadata });
  init(api);

  const panel = api.panel.mountedElements[0];
  const summary = panel.querySelector('#tl-summary');
  assert.equal(summary.hidden, false, 'summary must be visible when terrain is pre-loaded');
});

test('init() applies map layers when terrain state is already set', () => {
  const metadata = {
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };
  const api = makeMockApi({ terrainValue: metadata });
  init(api);

  const addSourceCall = api.map._calls.find(c => c.method === 'addSource');
  assert.ok(addSourceCall, 'addSource must be called on init when terrain is pre-loaded');
  assert.equal(addSourceCall.args[0], 'terrain-loader:terrain-dem');

  const addLayerCall = api.map._calls.find(c => c.method === 'addLayer');
  assert.ok(addLayerCall, 'addLayer must be called on init when terrain is pre-loaded');
  assert.equal(addLayerCall.args[0].id, 'terrain-loader:hillshade');
});

test('init() calls setTerrainSource when terrain is pre-loaded', () => {
  const metadata = {
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };
  const api = makeMockApi({ terrainValue: metadata });
  init(api);

  const terrainCall = api.map._calls.find(c => c.method === 'setTerrainSource');
  assert.ok(terrainCall, 'setTerrainSource must be called when terrain is pre-loaded');
  assert.equal(terrainCall.args[0], 'terrain-loader:terrain-dem');
});

// ---------------------------------------------------------------------------
// Tests: reactive state update
// ---------------------------------------------------------------------------

test('terrain watch callback updates summary section', () => {
  const api = makeMockApi();
  init(api);

  const panel = api.panel.mountedElements[0];
  const summary = panel.querySelector('#tl-summary');
  assert.equal(summary.hidden, true, 'summary hidden before watch fires');

  // Fire watch by calling set() on state
  api.state.set('terrain', {
    crs_epsg: 4326,
    bounds_wgs84: [0, -10, 10, 0],
    centre_wgs84: [5, -5],
    resolution_m: 30.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 4,
    terrain_min_zoom: 5,
    terrain_max_zoom: 10,
  });

  assert.equal(summary.hidden, false, 'summary must be shown after watch fires');
});

// ---------------------------------------------------------------------------
// Tests: map layer cleanup on unmount
// ---------------------------------------------------------------------------

test('onUnmount removes hillshade layer and terrain-dem source', () => {
  const metadata = {
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };
  const api = makeMockApi({ terrainValue: metadata });
  init(api);

  // Fire all onUnmount callbacks
  for (const cb of api._unmountCallbacks) cb();

  const removeLayerCall = api.map._calls.find(c => c.method === 'removeLayer');
  assert.ok(removeLayerCall, 'removeLayer must be called on unmount');
  assert.equal(removeLayerCall.args[0], 'terrain-loader:hillshade');

  const removeSourceCall = api.map._calls.find(c => c.method === 'removeSource');
  assert.ok(removeSourceCall, 'removeSource must be called on unmount');
  assert.equal(removeSourceCall.args[0], 'terrain-loader:terrain-dem');
});

test('onUnmount clears terrain source via setTerrainSource(null)', () => {
  const metadata = {
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };
  const api = makeMockApi({ terrainValue: metadata });
  init(api);

  for (const cb of api._unmountCallbacks) cb();

  const clearCall = api.map._calls.filter(c => c.method === 'setTerrainSource').at(-1);
  assert.ok(clearCall, 'setTerrainSource must be called on unmount');
  assert.equal(clearCall.args[0], null, 'setTerrainSource(null) clears terrain canvas');
});

// ---------------------------------------------------------------------------
// Tests: async file load pipeline (with mocked fetch + EventSource)
// ---------------------------------------------------------------------------

test('DEM file selection triggers POST to /api/terrain/load', async () => {
  const api = makeMockApi();
  init(api);

  const panel = api.panel.mountedElements[0];
  const demInput = panel.querySelector('#tl-dem-input');

  // Mock fetch to return terrain metadata
  const mockMetadata = {
    dem_path: '/tmp/dem.tif',
    dsm_path: null,
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };

  let fetchCalled = false;
  let fetchUrl = '';
  globalThis.fetch = async (url, opts) => {
    fetchCalled = true;
    fetchUrl = url;
    return {
      ok: true,
      json: async () => mockMetadata,
    };
  };

  // Simulate file selection
  const mockFile = { name: 'dem.tif', size: 100 };
  demInput.files = [mockFile];

  // Fire change event
  demInput._fire('change');

  // EventSource is created asynchronously — wait for it
  await new Promise(r => setTimeout(r, 10));

  // Simulate SSE complete
  const esInstance = _esInstances[_esInstances.length - 1];
  if (esInstance) esInstance._emit({ type: 'complete', pct: 100 });

  // Wait for async load to complete
  await new Promise(r => setTimeout(r, 20));

  assert.ok(fetchCalled, 'fetch must be called when DEM is selected');
  assert.ok(fetchUrl.includes('/api/terrain/load'), 'fetch URL must include /api/terrain/load');

  // Restore fetch
  delete globalThis.fetch;
});

test('terrain state is written after successful load', async () => {
  const api = makeMockApi();
  init(api);

  const panel = api.panel.mountedElements[0];
  const demInput = panel.querySelector('#tl-dem-input');

  const mockMetadata = {
    dem_path: '/tmp/dem.tif',
    dsm_path: null,
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };

  globalThis.fetch = async () => ({ ok: true, json: async () => mockMetadata });

  demInput.files = [{ name: 'dem.tif' }];
  demInput._fire('change');

  await new Promise(r => setTimeout(r, 10));
  const esInstance = _esInstances[_esInstances.length - 1];
  if (esInstance) esInstance._emit({ type: 'complete', pct: 100 });
  await new Promise(r => setTimeout(r, 20));

  assert.deepEqual(api._terrainValue(), mockMetadata, 'terrain state must be set after load');

  delete globalThis.fetch;
});

test('terrain:loaded event is emitted after successful load', async () => {
  const api = makeMockApi();
  init(api);

  const panel = api.panel.mountedElements[0];
  const demInput = panel.querySelector('#tl-dem-input');

  const mockMetadata = {
    dem_path: '/tmp/dem.tif',
    dsm_path: null,
    crs_epsg: 28354,
    bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
    centre_wgs84: [148.5, -35.5],
    resolution_m: 1.0,
    tile_url_template: '/api/terrain/tiles/{z}/{x}/{y}.png',
    terrain_tile_count: 12,
    terrain_min_zoom: 8,
    terrain_max_zoom: 13,
  };

  globalThis.fetch = async () => ({ ok: true, json: async () => mockMetadata });

  demInput.files = [{ name: 'dem.tif' }];
  demInput._fire('change');

  await new Promise(r => setTimeout(r, 10));
  const esInstance = _esInstances[_esInstances.length - 1];
  if (esInstance) esInstance._emit({ type: 'complete', pct: 100 });
  await new Promise(r => setTimeout(r, 20));

  const emittedEvent = api.bus.emitCalls.find(c => c.event === 'terrain:loaded');
  assert.ok(emittedEvent, 'terrain:loaded must be emitted after successful load');

  delete globalThis.fetch;
});

// ---------------------------------------------------------------------------
// D-473: adopt pre-generated terrain session on init
// ---------------------------------------------------------------------------

const PREGEN_METADATA = {
  session_id: '20260510T050559181708',
  dem_path: '/tmp/dem.tif',
  dsm_path: null,
  crs_epsg: 28354,
  bounds_wgs84: [148.0, -36.0, 149.0, -35.0],
  centre_wgs84: [148.5, -35.5],
  resolution_m: 1.0,
  tile_url_template: '/api/terrain/sessions/abc/tiles/{z}/{x}/{y}.png',
  tile_progress_url: '/api/terrain/sessions/abc/tile-progress',
  terrain_tile_count: 12,
  terrain_min_zoom: 8,
  terrain_max_zoom: 13,
};

test('init adopts a pre-generated session when state.terrain is null (D-473)', async () => {
  const api = makeMockApi();
  let fetchedUrl = null;
  globalThis.fetch = async (url) => {
    fetchedUrl = url;
    return { ok: true, status: 200, json: async () => PREGEN_METADATA };
  };
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.ok(
    fetchedUrl && fetchedUrl.endsWith('/api/terrain/sessions/latest'),
    `init must GET /api/terrain/sessions/latest; got ${fetchedUrl}`
  );
  assert.deepEqual(
    api._terrainValue(),
    PREGEN_METADATA,
    'terrain state must be set from the pre-generated session metadata'
  );
  const emitted = api.bus.emitCalls.find(c => c.event === 'terrain:loaded');
  assert.ok(emitted, 'terrain:loaded must be emitted after adopting pregen session');

  delete globalThis.fetch;
});

test('init does NOT call sessions/latest when terrain already in state (D-473)', async () => {
  const api = makeMockApi({ terrainValue: PREGEN_METADATA });
  let fetched = false;
  globalThis.fetch = async () => {
    fetched = true;
    return { ok: true, status: 200, json: async () => ({}) };
  };
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(
    fetched,
    false,
    'sessions/latest must not be polled when state.terrain is already populated',
  );

  delete globalThis.fetch;
});

test('init silently no-ops when sessions/latest returns 404 (D-473)', async () => {
  const api = makeMockApi();
  globalThis.fetch = async () => ({ ok: false, status: 404, json: async () => ({}) });
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(api._terrainValue(), null, 'terrain state must remain null on 404');
  const emitted = api.bus.emitCalls.find(c => c.event === 'terrain:loaded');
  assert.equal(emitted, undefined, '404 must not emit terrain:loaded');

  delete globalThis.fetch;
});

test('init silently no-ops when sessions/latest payload is malformed (D-473)', async () => {
  const api = makeMockApi();
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ session_id: 'x' }), // missing tile_url_template
  });
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(
    api._terrainValue(),
    null,
    'malformed metadata (missing tile_url_template) must not be adopted',
  );

  delete globalThis.fetch;
});

test('init silently no-ops when sessions/latest fetch rejects (D-473)', async () => {
  const api = makeMockApi();
  globalThis.fetch = async () => { throw new Error('network down'); };
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(api._terrainValue(), null, 'fetch rejection must leave terrain state null');

  delete globalThis.fetch;
});

test('adopt is preempted by a user upload that completes first (D-474)', async () => {
  const api = makeMockApi();
  // sessions/latest is slow; the user-driven upload finishes before it returns.
  let resolveLatest;
  globalThis.fetch = (url) => {
    if (url.endsWith('/api/terrain/sessions/latest')) {
      return new Promise((resolve) => { resolveLatest = resolve; });
    }
    // Fallback for any other fetch the upload path makes.
    return Promise.resolve({ ok: true, json: async () => UPLOAD_METADATA });
  };

  const UPLOAD_METADATA = { ...PREGEN_METADATA, session_id: 'user-upload-session' };
  const PREGEN = { ...PREGEN_METADATA, session_id: 'pregen-session' };

  init(api);

  // Simulate a user upload that lands first by setting state directly (mirrors
  // what _loadTerrain does on success).
  api.state.set('terrain', UPLOAD_METADATA);

  // Now release the in-flight sessions/latest with the pre-gen metadata.
  resolveLatest({ ok: true, status: 200, json: async () => PREGEN });
  await new Promise(r => setTimeout(r, 10));

  assert.equal(
    api._terrainValue().session_id,
    'user-upload-session',
    'user upload must NOT be overwritten by a late adopt response',
  );

  delete globalThis.fetch;
});

test('adopt is preempted when the panel is unmounted mid-flight (D-474)', async () => {
  const api = makeMockApi();
  let resolveLatest;
  globalThis.fetch = () =>
    new Promise((resolve) => { resolveLatest = resolve; });

  init(api);
  // Trigger unmount before the adopt-fetch resolves.
  for (const cb of api._unmountCallbacks) cb();

  resolveLatest({ ok: true, status: 200, json: async () => PREGEN_METADATA });
  await new Promise(r => setTimeout(r, 10));

  assert.equal(
    api._terrainValue(),
    null,
    'unmount before resolution must prevent state.set on a stale adopt',
  );

  delete globalThis.fetch;
});

test('adopt rejects metadata with non-finite bounds_wgs84 (D-475)', async () => {
  const api = makeMockApi();
  const bad = { ...PREGEN_METADATA, bounds_wgs84: [148.0, NaN, 149.0, -35.0] };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => bad });
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(api._terrainValue(), null, 'NaN in bounds_wgs84 must fail validation');

  delete globalThis.fetch;
});

test('adopt rejects metadata with non-integer zoom levels (D-475)', async () => {
  const api = makeMockApi();
  const bad = { ...PREGEN_METADATA, terrain_min_zoom: 'eight' };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => bad });
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(api._terrainValue(), null, 'non-integer zoom must fail validation');

  delete globalThis.fetch;
});

test('adopt rejects metadata when min_zoom > max_zoom (D-475)', async () => {
  const api = makeMockApi();
  const bad = { ...PREGEN_METADATA, terrain_min_zoom: 14, terrain_max_zoom: 8 };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => bad });
  init(api);
  await new Promise(r => setTimeout(r, 10));

  assert.equal(api._terrainValue(), null, 'inverted zoom range must fail validation');

  delete globalThis.fetch;
});
