/**
 * test-scenario-comparison.js — Unit tests for the Scenario Comparison module (S14.12).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-scenario-comparison.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------
// Mock DOM
// ---------------------------------------------------------------------------

function makeMockElement(tag = 'div') {
  const el = {
    _tag: tag,
    _children: [],
    _listeners: {},
    style: {
      cssText: '', display: '', left: '', background: '',
      cursor: '', transform: '', width: '',
    },
    dataset: {},
    textContent: '',
    innerHTML: '',
    id: '',
    title: '',
    disabled: false,
    type: '',
    value: '',
    name: '',
    checked: false,
    files: null,

    appendChild(child)  { this._children.push(child); child._parent = this; return child; },
    append(...children) { for (const c of children) this.appendChild(c); },
    removeChild(child)  {
      const i = this._children.indexOf(child);
      if (i !== -1) { this._children.splice(i, 1); child._parent = null; }
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
    getBoundingClientRect() {
      return { left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500, x: 0, y: 0 };
    },
    get firstChild() { return this._children[0] ?? null; },
    get parentElement() { return this._parent ?? null; },
    click() { this._clicked = true; this._fire('click'); },
    _fire(event, data = {}) {
      for (const h of (this._listeners[event] ?? [])) h({ ...data, target: el });
    },
    get nodeType() { return 1; },
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
  _fire(event, data = {}) {
    for (const h of (this._listeners[event] ?? [])) h(data);
  },
};

// ---------------------------------------------------------------------------
// Import module (after document mock is set up)
// ---------------------------------------------------------------------------

const mod = await import('../modules/scenario-comparison/index.js');
const {
  init,
  _parseScenarioJsText,
  _parseScenarioFile,
  _validateScenarioBPayload,
  _featureCentroidLng,
} = mod;

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({
  terrain = null,
  simResults = null,
  scenarioB = null,
} = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const busListeners = {};
  const stateWatchers = {};
  const sources = {};
  const layers = {};
  const stateData = {
    terrain,
    sim_results: simResults,
    scenario_b_sim_results: scenarioB,
  };

  const canvas = makeMockElement('canvas');
  const canvasParent = makeMockElement('div');
  canvasParent.appendChild(canvas);

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _busListeners: busListeners,
    _stateWatchers: stateWatchers,
    _stateData: stateData,
    _sources: sources,
    _layers: layers,
    _canvas: canvas,
    _canvasParent: canvasParent,

    _runUnmount() {
      const cbs = [...unmountCbs];
      unmountCbs.length = 0;
      for (const cb of cbs) cb();
    },
    _triggerWatch(key, value) {
      stateData[key] = value;
      for (const cb of (stateWatchers[key] ?? [])) cb(value);
    },
    _fireBus(event, data = {}) {
      for (const cb of (busListeners[event] ?? [])) cb(data);
    },

    moduleId: 'scenario-comparison',

    state: {
      get(key) { return stateData[key] ?? null; },
      set(key, val) {
        stateData[key] = val;
        for (const cb of (stateWatchers[key] ?? [])) cb(val);
      },
      watch(key, cb) {
        if (!stateWatchers[key]) stateWatchers[key] = [];
        stateWatchers[key].push(cb);
        return () => {
          const arr = stateWatchers[key];
          const i = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
      },
    },

    bus: {
      emit(event, data) { emitted.push({ event, data }); },
      on(event, cb) {
        if (!busListeners[event]) busListeners[event] = [];
        busListeners[event].push(cb);
        return () => {
          const arr = busListeners[event];
          const i = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
      },
    },

    map: {
      addSource(id, spec) {
        sources[id] = {
          ...spec,
          _data: spec.data,
          setData(d) { this._data = d; },
        };
      },
      removeSource(id) { delete sources[id]; },
      getSource(id)    { return sources[id] ?? null; },
      addLayer(spec)   { layers[spec.id] = { ...spec, _visibility: spec?.layout?.visibility ?? 'visible' }; },
      removeLayer(id)  { delete layers[id]; },
      getLayer(id)     { return layers[id] ?? null; },
      setLayoutProperty(layerId, name, value) {
        const lyr = layers[layerId];
        if (!lyr) return;
        if (!lyr.layout) lyr.layout = {};
        lyr.layout[name] = value;
        if (name === 'visibility') lyr._visibility = value;
      },
      setPaintProperty() {},
      on()  {},
      off() {},
      getCanvas() { return canvas; },
      unproject([px, _py]) {
        // Map px 0..1000 to longitude 130..140 for predictable tests
        return { lng: 130 + (px / 1000) * 10, lat: 0 };
      },
      project() { return { x: 0, y: 0 }; },
      flyTo() {},
      fitBounds() {},
      queryRenderedFeatures() { return []; },
    },

    panel: {
      mount(el) { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Helpers
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

function findByTestId(root, testId) {
  return findAll(root, el => el['data-testid'] === testId)[0] ?? null;
}

function tick(ms = 10) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Mock File with .text() method
function makeFile(text, name) {
  return {
    name,
    type: name.endsWith('.json') ? 'application/json' : 'application/javascript',
    size: text.length,
    text: async () => text,
  };
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const SAMPLE_COMPOSITE_A = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[[133.0, -25.0], [134.0, -25.0], [134.0, -24.0], [133.0, -24.0], [133.0, -25.0]]],
    },
    properties: {},
  }],
};

const SAMPLE_COMPOSITE_B = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[[133.5, -25.0], [134.5, -25.0], [134.5, -24.0], [133.5, -24.0], [133.5, -25.0]]],
    },
    properties: {},
  }],
};

const SAMPLE_SENSORS_FC = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [133.5, -24.5] },
    properties: { name: 'Radar Alpha' },
  }],
};

const SAMPLE_SIM_RESULTS_A = {
  scenario_name: 'scenario_a',
  generated_at: '2026-04-17T00:00:00Z',
  stats: {
    total_coverage_pct: 72.5,
    total_cost_aud: 500000,
    largest_contiguous_gap_m2: 12500,
  },
  total_coverage_pct: 72.5,
  largest_contiguous_gap_m2: 12500,
  layers: { composite: SAMPLE_COMPOSITE_A },
  sensor_placements: SAMPLE_SENSORS_FC,
  corridor_results: [{ threat_name: 'T1', coverage_pct: 60.0 }, { threat_name: 'T2', coverage_pct: 45.0 }],
  kill_chain_results: [{ margin_s: 4.2 }, { margin_s: -1.1 }],
};

const SAMPLE_SCENARIO_B = {
  scenario_name: 'scenario_b',
  generated_at: '2026-03-01T00:00:00Z',
  stats: {
    total_coverage_pct: 88.0,
    total_cost_aud: 800000,
    largest_contiguous_gap_m2: 5000,
  },
  total_coverage_pct: 88.0,
  largest_contiguous_gap_m2: 5000,
  layers: { composite: SAMPLE_COMPOSITE_B },
  sensor_placements: SAMPLE_SENSORS_FC,
  corridor_results: [{ threat_name: 'T1', coverage_pct: 70.0 }],
  kill_chain_results: [{ margin_s: 6.1 }],
};

// Mock fetch — captures last call and returns configurable response
function makeMockFetch(diffResponse = null, status = 200) {
  const fn = async (url, opts) => {
    fn._lastCall = { url, opts };
    if (status >= 400) {
      return { ok: false, status, json: async () => ({}) };
    }
    return {
      ok: true,
      status,
      json: async () => diffResponse ?? {
        a_only: { type: 'FeatureCollection', features: [] },
        b_only: { type: 'FeatureCollection', features: [] },
        both:   { type: 'FeatureCollection', features: [] },
      },
    };
  };
  fn._lastCall = null;
  return fn;
}

class MockAbortController {
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; this._aborted = true; }
}

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                   'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest reads terrain and sim_results', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.reads.includes('terrain'));
  assert.ok(m.reads.includes('sim_results'));
});

test('manifest writes scenario_b_sim_results (sole writer)', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.writes.includes('scenario_b_sim_results'));
  assert.equal(m.writes.length, 1, 'writes must contain exactly scenario_b_sim_results');
});

test('manifest prerequisites are terrain and sim_results', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.prerequisites.includes('terrain'));
  assert.ok(m.prerequisites.includes('sim_results'));
});

test('manifest emits comparison:loaded', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.emits.includes('comparison:loaded'));
});

test('manifest subscribes is empty', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/scenario-comparison/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.subscribes, []);
});

// ---------------------------------------------------------------------------
// Parse / validation tests
// ---------------------------------------------------------------------------

test('_parseScenarioJsText extracts payload from SALUS_DATA assignment', () => {
  const text = 'window.SALUS_DATA={"a":1,"b":[2,3]};\n';
  const parsed = _parseScenarioJsText(text);
  assert.deepEqual(parsed, { a: 1, b: [2, 3] });
});

test('_parseScenarioJsText rejects non-matching content', () => {
  assert.throws(() => _parseScenarioJsText('window.FOO = {"x":1};'));
});

test('_parseScenarioFile handles .json files', () => {
  const parsed = _parseScenarioFile('{"layers":{"composite":{"type":"FeatureCollection","features":[]}}}', 'x.json');
  assert.ok(parsed.layers);
});

test('_parseScenarioFile handles .js files', () => {
  const text = 'window.SALUS_DATA={"layers":{"composite":{"type":"FeatureCollection","features":[]}}};';
  const parsed = _parseScenarioFile(text, 'viewer_data.js');
  assert.ok(parsed.layers);
});

test('_validateScenarioBPayload accepts valid payload', () => {
  const v = _validateScenarioBPayload(SAMPLE_SCENARIO_B);
  assert.equal(v.ok, true);
});

test('_validateScenarioBPayload rejects null', () => {
  assert.equal(_validateScenarioBPayload(null).ok, false);
});

test('_validateScenarioBPayload rejects missing layers', () => {
  const v = _validateScenarioBPayload({ stats: {} });
  assert.equal(v.ok, false);
});

test('_validateScenarioBPayload rejects missing layers.composite', () => {
  const v = _validateScenarioBPayload({ layers: {} });
  assert.equal(v.ok, false);
});

// ---------------------------------------------------------------------------
// Centroid helper
// ---------------------------------------------------------------------------

test('_featureCentroidLng averages polygon ring longitudes', () => {
  const centroid = _featureCentroidLng(SAMPLE_COMPOSITE_A.features[0]);
  assert.ok(Math.abs(centroid - 133.6) < 0.5, `centroid ~133.5, got ${centroid}`);
});

test('_featureCentroidLng returns null for no geometry', () => {
  assert.equal(_featureCentroidLng({}), null);
});

// ---------------------------------------------------------------------------
// Init / mount
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init adds all expected map sources', () => {
  const api = makeApi();
  init(api);
  for (const src of [
    'scenario-comparison:a-only-src',
    'scenario-comparison:b-only-src',
    'scenario-comparison:both-src',
    'scenario-comparison:a-composite-src',
    'scenario-comparison:b-composite-src',
    'scenario-comparison:a-sensors-src',
    'scenario-comparison:b-sensors-src',
  ]) {
    assert.ok(api._sources[src], `missing source: ${src}`);
  }
});

test('init adds all expected map layers', () => {
  const api = makeApi();
  init(api);
  for (const lyr of [
    'scenario-comparison:a-only-fill',
    'scenario-comparison:b-only-fill',
    'scenario-comparison:both-fill',
    'scenario-comparison:a-composite-fill',
    'scenario-comparison:b-composite-fill',
    'scenario-comparison:a-sensors-circle',
    'scenario-comparison:b-sensors-circle',
  ]) {
    assert.ok(api._layers[lyr], `missing layer: ${lyr}`);
  }
});

test('init registers watch on sim_results', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._stateWatchers.sim_results ?? []).length > 0);
});

test('init registers watch on scenario_b_sim_results', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._stateWatchers.scenario_b_sim_results ?? []).length > 0);
});

test('diff layers hidden until scenario B is loaded', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  for (const lyr of [
    'scenario-comparison:a-only-fill',
    'scenario-comparison:b-only-fill',
    'scenario-comparison:both-fill',
  ]) {
    assert.equal(api._layers[lyr].layout.visibility, 'none',
      `${lyr} must be hidden when no scenario B`);
  }
});

// ---------------------------------------------------------------------------
// File loading tests (S14.12-1)
// ---------------------------------------------------------------------------

test('loading a valid viewer_data.js writes scenario_b_sim_results', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  const fileInput = findByTestId(panel, 'file-input');
  const jsText = `window.SALUS_DATA=${JSON.stringify(SAMPLE_SCENARIO_B)};\n`;
  const file = makeFile(jsText, 'viewer_data.js');
  fileInput.files = [file];
  fileInput._fire('change', { target: fileInput });
  await tick(30);
  assert.ok(api._stateData.scenario_b_sim_results != null,
    'scenario_b_sim_results must be set after successful file load');
  assert.equal(api._stateData.scenario_b_sim_results.stats.total_coverage_pct, 88.0);
});

test('loading emits comparison:loaded event', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  const fileInput = findByTestId(panel, 'file-input');
  const file = makeFile(JSON.stringify(SAMPLE_SCENARIO_B), 'scenario_b.json');
  fileInput.files = [file];
  fileInput._fire('change', { target: fileInput });
  await tick(30);
  const ev = api._emitted.find(e => e.event === 'comparison:loaded');
  assert.ok(ev, 'must emit comparison:loaded');
  assert.equal(ev.data.filename, 'scenario_b.json');
  assert.ok(ev.data.timestamp, 'timestamp must be set');
});

test('loaded indicator shows filename after successful load', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  const fileInput = findByTestId(panel, 'file-input');
  const file = makeFile(JSON.stringify(SAMPLE_SCENARIO_B), 'b.json');
  fileInput.files = [file];
  fileInput._fire('change', { target: fileInput });
  await tick(30);
  const indicator = findByTestId(panel, 'loaded-indicator');
  assert.equal(indicator.style.display, 'block');
  assert.ok(indicator.textContent.includes('b.json'), `expected filename, got: ${indicator.textContent}`);
});

test('invalid JSON surfaces parse error and does NOT write state', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  const fileInput = findByTestId(panel, 'file-input');
  const file = makeFile('this is not { valid JSON', 'bad.json');
  fileInput.files = [file];
  fileInput._fire('change', { target: fileInput });
  await tick(30);
  const errEl = findByTestId(panel, 'load-error');
  assert.equal(errEl.style.display, 'block');
  assert.equal(api._stateData.scenario_b_sim_results, null);
});

test('payload missing layers.composite surfaces validation error', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  const fileInput = findByTestId(panel, 'file-input');
  const file = makeFile(JSON.stringify({ stats: { total_coverage_pct: 50 } }), 'partial.json');
  fileInput.files = [file];
  fileInput._fire('change', { target: fileInput });
  await tick(30);
  const errEl = findByTestId(panel, 'load-error');
  assert.equal(errEl.style.display, 'block');
  assert.equal(api._stateData.scenario_b_sim_results, null);
});

// ---------------------------------------------------------------------------
// Summary table tests (S14.12-1)
// ---------------------------------------------------------------------------

test('summary table hidden before scenario B loads', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'summary-section').style.display, 'none');
});

test('summary table visible after scenario B loads', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'summary-section').style.display, 'block');
});

test('summary table shows A coverage and B coverage', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  assert.ok(findByTestId(panel, 'summary-a-coverage').textContent.includes('72.5'));
  assert.ok(findByTestId(panel, 'summary-b-coverage').textContent.includes('88.0'));
});

test('summary table shows A cost and B cost', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  assert.ok(findByTestId(panel, 'summary-a-cost').textContent.includes('500'));
  assert.ok(findByTestId(panel, 'summary-b-cost').textContent.includes('800'));
});

test('summary table shows worst corridor coverage for both scenarios', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  // A has corridors 60, 45 → worst = 45
  assert.ok(findByTestId(panel, 'summary-a-worstcorr').textContent.includes('45'));
  assert.ok(findByTestId(panel, 'summary-b-worstcorr').textContent.includes('70'));
});

test('summary table shows kill-chain margin best/worst', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  const aKc = findByTestId(panel, 'summary-a-killchain').textContent;
  assert.ok(aKc.includes('4.2') && aKc.includes('-1.1'),
    `expected 4.2 and -1.1 in A kill-chain, got: ${aKc}`);
});

test('summary table updates when scenario_b_sim_results watch fires', () => {
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  const panel = api._mounted[0];
  // Before load
  assert.equal(findByTestId(panel, 'summary-section').style.display, 'none');
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  // After load
  assert.equal(findByTestId(panel, 'summary-section').style.display, 'block');
  assert.ok(findByTestId(panel, 'summary-b-coverage').textContent.includes('88.0'));
});

// ---------------------------------------------------------------------------
// Diff fetch tests (S14.12-2)
// ---------------------------------------------------------------------------

test('loading scenario B triggers POST /api/compare in overlay mode', async () => {
  const mockFetch = makeMockFetch();
  globalThis.fetch = mockFetch;
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  assert.ok(mockFetch._lastCall, 'fetch must have been called');
  assert.equal(mockFetch._lastCall.url, '/api/compare');
  assert.equal(mockFetch._lastCall.opts.method, 'POST');
});

test('compare request body includes a_composite and b_composite', async () => {
  const mockFetch = makeMockFetch();
  globalThis.fetch = mockFetch;
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  const body = JSON.parse(mockFetch._lastCall.opts.body);
  assert.ok(body.a_composite, 'body must include a_composite');
  assert.ok(body.b_composite, 'body must include b_composite');
  assert.equal(body.a_composite.features.length, 1);
});

test('diff response populates a-only / b-only / both sources', async () => {
  const diffResponse = {
    a_only: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: {} }] },
    b_only: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: {} }] },
    both:   { type: 'FeatureCollection', features: [] },
  };
  globalThis.fetch = makeMockFetch(diffResponse);
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  assert.equal(api._sources['scenario-comparison:a-only-src']._data.features.length, 1);
  assert.equal(api._sources['scenario-comparison:b-only-src']._data.features.length, 1);
  assert.equal(api._sources['scenario-comparison:both-src']._data.features.length, 0);
});

test('diff layers become visible in overlay mode when scenario B is loaded', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  assert.equal(api._layers['scenario-comparison:a-only-fill'].layout.visibility, 'visible');
  assert.equal(api._layers['scenario-comparison:b-only-fill'].layout.visibility, 'visible');
  assert.equal(api._layers['scenario-comparison:both-fill'].layout.visibility, 'visible');
});

test('toggling A-only hides only the A-only layer', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  await tick(30);
  const panel = api._mounted[0];
  const aToggle = findByTestId(panel, 'toggle-a-only');
  aToggle.checked = false;
  aToggle._fire('change');
  assert.equal(api._layers['scenario-comparison:a-only-fill'].layout.visibility, 'none');
  assert.equal(api._layers['scenario-comparison:b-only-fill'].layout.visibility, 'visible');
});

test('sensor layers become visible when scenario B is loaded', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  assert.equal(api._layers['scenario-comparison:a-sensors-circle'].layout.visibility, 'visible');
  assert.equal(api._layers['scenario-comparison:b-sensors-circle'].layout.visibility, 'visible');
});

test('scenario B sensor source populated from sensor_placements FC', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  const bSensorData = api._sources['scenario-comparison:b-sensors-src']._data;
  assert.equal(bSensorData.features.length, 1);
});

// ---------------------------------------------------------------------------
// Swipe mode tests (S14.12-3)
// ---------------------------------------------------------------------------

test('switching to swipe mode shows composite layers and summary', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  await tick(5);
  const panel = api._mounted[0];
  const swipeRadio = findByTestId(panel, 'mode-swipe');
  swipeRadio.checked = true;
  swipeRadio._fire('change');

  assert.equal(api._layers['scenario-comparison:a-composite-fill'].layout.visibility, 'visible');
  assert.equal(api._layers['scenario-comparison:b-composite-fill'].layout.visibility, 'visible');
  assert.equal(api._layers['scenario-comparison:a-only-fill'].layout.visibility, 'none');
  assert.equal(findByTestId(panel, 'swipe-summary').style.display, 'block');
});

test('switching to swipe mode creates the divider element', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  const swipeRadio = findByTestId(panel, 'mode-swipe');
  swipeRadio.checked = true;
  swipeRadio._fire('change');
  // Divider attached to canvas parent
  const divider = findByTestId(api._canvasParent, 'swipe-divider');
  assert.ok(divider, 'swipe divider element must be attached to canvas parent');
  assert.equal(divider.style.left, '50%', 'default x_fraction is 0.5');
});

test('switching back to overlay mode removes the divider', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  const swipeRadio = findByTestId(panel, 'mode-swipe');
  swipeRadio.checked = true;
  swipeRadio._fire('change');
  assert.ok(findByTestId(api._canvasParent, 'swipe-divider'));

  const overlayRadio = findByTestId(panel, 'mode-overlay');
  overlayRadio.checked = true;
  overlayRadio._fire('change');
  assert.equal(findByTestId(api._canvasParent, 'swipe-divider'), null);
});

test('swipe summary shows A, B, and delta values', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  const swipeRadio = findByTestId(panel, 'mode-swipe');
  swipeRadio.checked = true;
  swipeRadio._fire('change');
  const summary = findByTestId(panel, 'swipe-summary');
  assert.ok(summary.textContent.includes('72.5'), `expected A coverage in swipe summary: ${summary.textContent}`);
  assert.ok(summary.textContent.includes('88.0'), `expected B coverage in swipe summary: ${summary.textContent}`);
  assert.ok(summary.textContent.includes('+15.5') || summary.textContent.includes('15.5'),
    `expected delta in swipe summary: ${summary.textContent}`);
});

test('dragging the divider updates x_fraction via document mousemove', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  const swipeRadio = findByTestId(panel, 'mode-swipe');
  swipeRadio.checked = true;
  swipeRadio._fire('change');

  const divider = findByTestId(api._canvasParent, 'swipe-divider');
  // Simulate mousedown on divider
  divider._fire('mousedown', { clientX: 500, preventDefault: () => {} });
  // Simulate document mousemove with clientX at 700px (canvas width 1000 → frac 0.7)
  globalThis.document._fire('mousemove', { clientX: 700 });
  assert.equal(divider.style.left, '70%', `expected 70%, got ${divider.style.left}`);
  // Mouseup stops dragging
  globalThis.document._fire('mouseup', {});
});

test('swipe mode filters composite features by divider longitude', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  // Two A features: one clearly to left of divider, one clearly right
  const leftFeat = {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[131.0, -25], [131.5, -25], [131.5, -24], [131.0, -24], [131.0, -25]]] },
    properties: {},
  };
  const rightFeat = {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[138.0, -25], [138.5, -25], [138.5, -24], [138.0, -24], [138.0, -25]]] },
    properties: {},
  };
  const simA = {
    ...SAMPLE_SIM_RESULTS_A,
    layers: { composite: { type: 'FeatureCollection', features: [leftFeat, rightFeat] } },
  };
  const scenB = {
    ...SAMPLE_SCENARIO_B,
    layers: { composite: { type: 'FeatureCollection', features: [leftFeat, rightFeat] } },
  };
  const api = makeApi({ simResults: simA, scenarioB: scenB });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'mode-swipe').checked = true;
  findByTestId(panel, 'mode-swipe')._fire('change');

  // Default x_fraction = 0.5 → divider_lng = 135 (test unproject mapping)
  // Scenario A composite should include only leftFeat (lng ~131)
  // Scenario B composite should include only rightFeat (lng ~138)
  const aData = api._sources['scenario-comparison:a-composite-src']._data;
  const bData = api._sources['scenario-comparison:b-composite-src']._data;
  assert.equal(aData.features.length, 1, 'scenario A should show only features left of divider');
  assert.equal(bData.features.length, 1, 'scenario B should show only features right of divider');
});

// ---------------------------------------------------------------------------
// Mode switching
// ---------------------------------------------------------------------------

test('toggle section visible only in overlay mode', async () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'toggle-section').style.display, 'block');
  findByTestId(panel, 'mode-swipe').checked = true;
  findByTestId(panel, 'mode-swipe')._fire('change');
  assert.equal(findByTestId(panel, 'toggle-section').style.display, 'none');
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

test('compare endpoint failure surfaces error but does not throw', async () => {
  globalThis.fetch = makeMockFetch(null, 500);
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A });
  init(api);
  api._triggerWatch('scenario_b_sim_results', SAMPLE_SCENARIO_B);
  await tick(30);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'load-error').style.display, 'block');
  // scenario B state should still be set since the load itself succeeded
  assert.ok(api._stateData.scenario_b_sim_results != null);
});

// ---------------------------------------------------------------------------
// onUnmount cleanup tests
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);
  const keysBefore = Object.keys(api._stateWatchers).filter(
    k => (api._stateWatchers[k] ?? []).length > 0
  );
  assert.ok(keysBefore.length > 0, 'must have watchers before unmount');
  api._runUnmount();
  for (const key of keysBefore) {
    assert.equal(
      (api._stateWatchers[key] ?? []).length, 0,
      `watcher for ${key} must be removed`
    );
  }
});

test('onUnmount removes all map layers and sources', () => {
  const api = makeApi();
  init(api);
  // Pre-unmount: all layers and sources present
  for (const lyr of [
    'scenario-comparison:a-only-fill', 'scenario-comparison:b-only-fill',
    'scenario-comparison:both-fill', 'scenario-comparison:a-composite-fill',
    'scenario-comparison:b-composite-fill', 'scenario-comparison:a-sensors-circle',
    'scenario-comparison:b-sensors-circle',
  ]) {
    assert.ok(api._layers[lyr], `layer ${lyr} must exist before unmount`);
  }
  api._runUnmount();
  for (const lyr of [
    'scenario-comparison:a-only-fill', 'scenario-comparison:b-only-fill',
    'scenario-comparison:both-fill', 'scenario-comparison:a-composite-fill',
    'scenario-comparison:b-composite-fill', 'scenario-comparison:a-sensors-circle',
    'scenario-comparison:b-sensors-circle',
  ]) {
    assert.equal(api._layers[lyr], undefined, `layer ${lyr} must be removed`);
  }
});

test('onUnmount removes swipe divider if attached', () => {
  globalThis.fetch = makeMockFetch();
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ simResults: SAMPLE_SIM_RESULTS_A, scenarioB: SAMPLE_SCENARIO_B });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'mode-swipe').checked = true;
  findByTestId(panel, 'mode-swipe')._fire('change');
  assert.ok(findByTestId(api._canvasParent, 'swipe-divider'), 'divider attached before unmount');
  api._runUnmount();
  assert.equal(findByTestId(api._canvasParent, 'swipe-divider'), null, 'divider removed on unmount');
});

test('onUnmount removes document-level event listeners added by this init', () => {
  // Each test leaves a fresh shared globalThis.document, so compare deltas
  // rather than absolute counts (other tests also register listeners).
  const before = {
    mousemove: (globalThis.document._listeners.mousemove ?? []).length,
    mouseup:   (globalThis.document._listeners.mouseup   ?? []).length,
  };
  const api = makeApi();
  init(api);
  assert.equal(
    (globalThis.document._listeners.mousemove ?? []).length,
    before.mousemove + 1,
    'init adds one mousemove listener',
  );
  assert.equal(
    (globalThis.document._listeners.mouseup ?? []).length,
    before.mouseup + 1,
    'init adds one mouseup listener',
  );
  api._runUnmount();
  assert.equal(
    (globalThis.document._listeners.mousemove ?? []).length,
    before.mousemove,
    'unmount restores mousemove listener count',
  );
  assert.equal(
    (globalThis.document._listeners.mouseup ?? []).length,
    before.mouseup,
    'unmount restores mouseup listener count',
  );
});
