/**
 * test-optimiser.js — Unit tests for the Optimiser module (S14.11).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-optimiser.js
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
      cssText: '', display: '', width: '', background: '', color: '',
      cursor: '', transform: '',
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

    appendChild(child)   { this._children.push(child); return child; },
    append(...children)  { for (const c of children) this.appendChild(c); },
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
    click() { this._clicked = true; this._fire('click'); },
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
};

// ---------------------------------------------------------------------------
// SSE stream mock helpers
// ---------------------------------------------------------------------------

function makeSseStream(sseText) {
  const encoder = new TextEncoder();
  const chunks = [encoder.encode(sseText)];
  let idx = 0;
  return {
    getReader() {
      return {
        read: async () => {
          if (idx < chunks.length) return { done: false, value: chunks[idx++] };
          return { done: true, value: undefined };
        },
        releaseLock() {},
      };
    },
  };
}

function makeSseText(events) {
  return events
    .map(({ type, data }) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('');
}

// Default mock fetch — immediately completes with empty stream
function makeMockFetch(sseEvents = [], status = 200) {
  let lastCall = null;
  const fn = async (url, opts) => {
    lastCall = { url, opts };
    fn._lastCall = lastCall;
    if (status >= 400) {
      return { ok: false, status, body: makeSseStream('') };
    }
    return { ok: true, status, body: makeSseStream(makeSseText(sseEvents)) };
  };
  fn._lastCall = null;
  return fn;
}

// Mock AbortController that tracks abort() calls
class MockAbortController {
  constructor() {
    this.signal = { aborted: false };
    this._abortCalled = false;
  }
  abort() {
    this._abortCalled = true;
    this.signal.aborted = true;
  }
}

// ---------------------------------------------------------------------------
// Dynamic import AFTER globalThis.document is set
// ---------------------------------------------------------------------------

const { init } = await import('../modules/optimiser/index.js');

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({
  terrain = null,
  zones = null,
  constraints = null,
  sensorLib = null,
  effectorLib = null,
  threatCorridors = null,
  placements = null,
  optimiserResults = null,
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
    zones,
    constraints,
    sensor_library: sensorLib,
    effector_library: effectorLib,
    threat_corridors: threatCorridors,
    placements,
    optimiser_results: optimiserResults,
  };

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _busListeners: busListeners,
    _stateWatchers: stateWatchers,
    _stateData: stateData,
    _sources: sources,
    _layers: layers,

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

    moduleId: 'optimiser',

    state: {
      get(key) { return stateData[key] ?? null; },
      set(key, val) {
        stateData[key] = val;
        // Fire watchers synchronously — matches real state layer behaviour
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
      addLayer(spec)   { layers[spec.id] = spec; },
      removeLayer(id)  { delete layers[id]; },
      getLayer(id)     { return layers[id] ?? null; },
      on()  {},
      off() {},
      getCanvas() { return makeMockElement('canvas'); },
    },

    panel: {
      mount(el) { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// DOM helpers
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

// Settle all micro-tasks / promises
function tick(ms = 30) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

// Canonical zones shape — {priority: PriorityZone[], exclusion: ExclusionZone[]}
// matching what zone-editor writes since I-6 (D-410).
const SAMPLE_ZONES = {
  priority: [{
    id: 'z1',
    label: 'Zone A',
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
    min_coverage_pct: 80,
  }],
  exclusion: [],
};
const SAMPLE_CONSTRAINTS = { max_cost_aud: 500000, max_sensors: 4, max_effectors: 2, allowed_sensor_ids: null };
const SAMPLE_PLACEMENTS = [
  { sensor_name: 'Radar Alpha', lat: -34.9, lng: 138.6 },
];
const SAMPLE_PROPOSED = [
  { sensor_name: 'Radar Beta', lat: -34.8, lng: 138.5 },
  { sensor_name: 'Radar Gamma', lat: -34.7, lng: 138.4 },
];
const SAMPLE_RESULTS = {
  proposed_placements: SAMPLE_PROPOSED,
  score: 0.876,
  coverage_pct: 87.6,
  total_cost_aud: 400000,
  satisfied_constraints: ['budget', 'max_sensors'],
  violated_constraints: [],
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest reads all required state keys', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const key of ['terrain', 'zones', 'constraints', 'sensor_library',
                      'effector_library', 'threat_corridors', 'placements']) {
    assert.ok(m.reads.includes(key), `reads must include ${key}`);
  }
});

test('manifest writes optimiser_results only (single-writer rule, D-435)', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.writes.includes('optimiser_results'), 'writes must include optimiser_results');
  assert.ok(
    !m.writes.includes('placements'),
    'placements must NOT be in optimiser writes — placement-editor is the sole writer; ' +
      'optimiser delegates via the optimiser:apply event (D-435)'
  );
});

test('manifest prerequisites are terrain only (zones removed — optional for backend)', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.prerequisites.includes('terrain'), 'prerequisites must include terrain');
  assert.ok(!m.prerequisites.includes('zones'), 'zones must not be a prerequisite (zones only affect scoring weights, not required by backend)');
});

test('manifest subscribes to zone:added, zone:removed, constraint:updated', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const ev of ['zone:added', 'zone:removed', 'constraint:updated']) {
    assert.ok(m.subscribes.includes(ev), `subscribes must include ${ev}`);
  }
});

test('manifest emits optimiser:started, optimiser:complete, optimiser:failed, optimiser:apply', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/optimiser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const ev of [
    'optimiser:started',
    'optimiser:complete',
    'optimiser:failed',
    'optimiser:apply', // D-435: delegate placements writes to placement-editor
  ]) {
    assert.ok(m.emits.includes(ev), `emits must include ${ev}`);
  }
  assert.ok(
    !m.emits.includes('placement:added'),
    'placement:added must NOT be in optimiser emits — placement-editor emits these ' +
      'after handling optimiser:apply (D-435)'
  );
});

// ---------------------------------------------------------------------------
// Init / setup tests
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init adds ghost-sensors map source', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._sources['optimiser:ghost-sensors'], 'ghost-sensors source must be added');
});

test('init adds ghost-sensors-circle map layer', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['optimiser:ghost-sensors-circle'], 'ghost-sensors-circle layer must be added');
});

test('init registers watches on all read state keys', () => {
  const api = makeApi();
  init(api);
  for (const key of ['terrain', 'zones', 'constraints', 'sensor_library',
                      'effector_library', 'threat_corridors', 'placements', 'optimiser_results']) {
    assert.ok(
      (api._stateWatchers[key] ?? []).length > 0,
      `must register watch on ${key}`
    );
  }
});

test('init subscribes to zone:added, zone:removed, constraint:updated bus events', () => {
  const api = makeApi();
  init(api);
  for (const ev of ['zone:added', 'zone:removed', 'constraint:updated']) {
    assert.ok(
      (api._busListeners[ev] ?? []).length > 0,
      `must subscribe to ${ev}`
    );
  }
});

// ---------------------------------------------------------------------------
// Constraint summary tests
// ---------------------------------------------------------------------------

test('constraint summary shows budget from constraints state', () => {
  const api = makeApi({ constraints: SAMPLE_CONSTRAINTS });
  init(api);
  const panel = api._mounted[0];
  const cells = findAll(panel, el => el.textContent.includes('500'));
  assert.ok(cells.length > 0, 'must show budget value containing 500');
});

test('constraint summary shows max_sensors from constraints state', () => {
  const api = makeApi({ constraints: SAMPLE_CONSTRAINTS });
  init(api);
  const panel = api._mounted[0];
  const cells = findAll(panel, el => el.textContent === '4');
  assert.ok(cells.length > 0, 'must show max_sensors value');
});

test('constraint summary updates when constraints watch fires', () => {
  const api = makeApi({ constraints: null });
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('constraints', { max_cost_aud: 1000000, max_sensors: 6, max_effectors: 3 });

  const cells = findAll(panel, el => el.textContent.includes('1,000,000') || el.textContent.includes('1000000'));
  assert.ok(cells.length > 0, 'budget cell must update after constraints watch fires');
});

// ---------------------------------------------------------------------------
// Parameters-changed notice tests
// ---------------------------------------------------------------------------

test('param notice shown on zone:added bus event', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const notice = findByTestId(panel, 'param-notice');
  assert.notEqual(notice.style.display, 'block', 'notice must be hidden initially');
  api._fireBus('zone:added', {});
  assert.equal(notice.style.display, 'block');
});

test('param notice shown on zone:removed bus event', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  api._fireBus('zone:removed', {});
  assert.equal(findByTestId(panel, 'param-notice').style.display, 'block');
});

test('param notice shown on constraint:updated bus event', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  api._fireBus('constraint:updated', {});
  assert.equal(findByTestId(panel, 'param-notice').style.display, 'block');
});

// ---------------------------------------------------------------------------
// Objective selector tests
// ---------------------------------------------------------------------------

test('panel contains three objective radio buttons', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const radios = findAll(panel, el => el._tag === 'input' && el.type === 'radio');
  assert.equal(radios.length, 3);
});

test('first objective radio is checked by default', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const radios = findAll(panel, el => el._tag === 'input' && el.type === 'radio');
  assert.ok(radios[0].checked, 'first objective must be selected by default');
});

// ---------------------------------------------------------------------------
// Run optimiser tests (async)
// ---------------------------------------------------------------------------

test('run button emits optimiser:started', async () => {
  globalThis.fetch = makeMockFetch([]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const started = api._emitted.filter(e => e.event === 'optimiser:started');
  assert.ok(started.length >= 1, 'must emit optimiser:started');
});

test('run button sends POST to /api/optimise', async () => {
  const mockFetch = makeMockFetch([]);
  globalThis.fetch = mockFetch;
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ zones: SAMPLE_ZONES, constraints: SAMPLE_CONSTRAINTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  assert.ok(mockFetch._lastCall, 'fetch must have been called');
  assert.equal(mockFetch._lastCall.url, '/api/optimise');
  assert.equal(mockFetch._lastCall.opts.method, 'POST');
});

test('run request body includes zones, constraints, and objective', async () => {
  const mockFetch = makeMockFetch([]);
  globalThis.fetch = mockFetch;
  globalThis.AbortController = MockAbortController;
  const api = makeApi({ zones: SAMPLE_ZONES, constraints: SAMPLE_CONSTRAINTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const body = JSON.parse(mockFetch._lastCall.opts.body);
  assert.deepEqual(body.zones, SAMPLE_ZONES);
  assert.deepEqual(body.constraints, SAMPLE_CONSTRAINTS);
  assert.ok(body.objective, 'body must include objective');
});

test('progress event updates progress log text', async () => {
  globalThis.fetch = makeMockFetch([
    { type: 'progress', data: { message: 'Placing sensor 1/4 — coverage now 32%' } },
  ]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const log = findByTestId(panel, 'progress-log');
  assert.ok(log.textContent.includes('Placing sensor 1/4'), `expected progress text, got: ${log.textContent}`);
});

test('cancel button calls abort on the controller', async () => {
  let capturedController = null;
  globalThis.AbortController = class {
    constructor() {
      this.signal = { aborted: false };
      capturedController = this;
    }
    abort() { this.signal.aborted = true; this._aborted = true; }
  };
  // Fetch that never resolves (blocks)
  globalThis.fetch = async () => new Promise(() => {});
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick(5);
  findByTestId(panel, 'cancel-btn')._fire('click');
  assert.ok(capturedController, 'AbortController must have been created');
  assert.ok(capturedController.signal.aborted, 'abort() must have been called');
});

// ---------------------------------------------------------------------------
// SSE complete event tests
// ---------------------------------------------------------------------------

test('complete SSE event writes optimiser_results to state', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'complete', data: SAMPLE_RESULTS }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  assert.ok(api._stateData.optimiser_results != null, 'optimiser_results must be written to state');
  assert.equal(api._stateData.optimiser_results.coverage_pct, 87.6);
});

test('complete SSE event emits optimiser:complete', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'complete', data: SAMPLE_RESULTS }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const ev = api._emitted.find(e => e.event === 'optimiser:complete');
  assert.ok(ev, 'must emit optimiser:complete');
  assert.equal(ev.data.score, SAMPLE_RESULTS.score);
});

test('complete SSE event shows results section', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'complete', data: SAMPLE_RESULTS }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const resultsSection = findByTestId(panel, 'results-section');
  assert.equal(resultsSection.style.display, 'block');
});

test('complete SSE event sets ghost markers from proposed_placements', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'complete', data: SAMPLE_RESULTS }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const ghost = api._sources['optimiser:ghost-sensors'];
  assert.ok(ghost._data.features.length === SAMPLE_PROPOSED.length,
    'ghost source must have one feature per proposed placement');
});

// ---------------------------------------------------------------------------
// SSE error event tests
// ---------------------------------------------------------------------------

test('error SSE event shows error in progress log', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'error', data: { message: 'No feasible placement' } }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const log = findByTestId(panel, 'progress-log');
  assert.ok(log.textContent.includes('No feasible placement') || log.textContent.includes('Error'),
    `expected error text, got: ${log.textContent}`);
});

test('error SSE event emits optimiser:failed', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'error', data: { message: 'Optimiser failed' } }]);
  globalThis.AbortController = MockAbortController;
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  const ev = api._emitted.find(e => e.event === 'optimiser:failed');
  assert.ok(ev, 'must emit optimiser:failed on error');
});

// ---------------------------------------------------------------------------
// Apply tests (S14.11-3)
// ---------------------------------------------------------------------------

test('apply emits optimiser:apply with proposed placements (D-435)', async () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    optimiserResults: SAMPLE_RESULTS,
  });
  init(api);
  const panel = api._mounted[0];
  // Results section should be visible since optimiser_results is set
  assert.equal(findByTestId(panel, 'results-section').style.display, 'block');
  findByTestId(panel, 'apply-btn')._fire('click');
  const ev = api._emitted.find(e => e.event === 'optimiser:apply');
  assert.ok(ev, 'apply must emit optimiser:apply (placement-editor performs the merge)');
  assert.deepEqual(ev.data?.proposed, SAMPLE_PROPOSED);
});

test('apply does NOT write placements directly (single-writer rule, D-435)', async () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    optimiserResults: SAMPLE_RESULTS,
  });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'apply-btn')._fire('click');
  // Optimiser must not touch the placements key — placement-editor owns it.
  assert.deepEqual(
    api._stateData.placements,
    SAMPLE_PLACEMENTS,
    'optimiser must not write placements directly; placement-editor handles optimiser:apply'
  );
});

test('apply does NOT emit placement:added directly (D-435)', async () => {
  const api = makeApi({ placements: [], optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'apply-btn')._fire('click');
  const addedEvents = api._emitted.filter(e => e.event === 'placement:added');
  assert.equal(
    addedEvents.length,
    0,
    'placement:added must be emitted by placement-editor (sole writer), not optimiser'
  );
});

test('apply clears ghost markers', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'apply-btn')._fire('click');
  const ghost = api._sources['optimiser:ghost-sensors'];
  assert.equal(ghost._data.features.length, 0, 'ghost markers must be cleared after apply');
});

test('apply nulls optimiser_results state', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'apply-btn')._fire('click');
  assert.equal(api._stateData.optimiser_results, null);
});

test('apply hides results section', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'apply-btn')._fire('click');
  assert.equal(findByTestId(panel, 'results-section').style.display, 'none');
});

// ---------------------------------------------------------------------------
// Discard tests (S14.11-3)
// ---------------------------------------------------------------------------

test('discard clears ghost markers', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  // Ghost markers set by _showResults on init (results already in state)
  findByTestId(panel, 'discard-btn')._fire('click');
  const ghost = api._sources['optimiser:ghost-sensors'];
  assert.equal(ghost._data.features.length, 0, 'ghost markers must be cleared after discard');
});

test('discard nulls optimiser_results state', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'discard-btn')._fire('click');
  assert.equal(api._stateData.optimiser_results, null);
});

// ---------------------------------------------------------------------------
// Stale flag tests (S14.11-4)
// ---------------------------------------------------------------------------

// SPEC-REQUIRED TEST: zone added after optimiser has run → stale notice appears
test('stale notice shown when zone:added fires and optimiser_results exist', async () => {
  // Simulate: optimiser ran, results in state, then zone added
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const staleNotice = findByTestId(panel, 'results-stale-notice');

  assert.notEqual(staleNotice.style.display, 'block', 'stale notice must be hidden initially');
  api._fireBus('zone:added', {});
  assert.equal(staleNotice.style.display, 'block', 'stale notice must appear after zone:added');
});

test('stale notice shown when constraint:updated fires and results exist', async () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const staleNotice = findByTestId(panel, 'results-stale-notice');
  api._fireBus('constraint:updated', {});
  assert.equal(staleNotice.style.display, 'block');
});

test('stale notice not shown when no results exist', async () => {
  const api = makeApi({ optimiserResults: null });
  init(api);
  const panel = api._mounted[0];
  api._fireBus('zone:added', {});
  const staleNotice = findByTestId(panel, 'results-stale-notice');
  assert.notEqual(staleNotice.style.display, 'block', 'stale notice must not appear without results');
});

// SPEC-REQUIRED TEST: re-run clears stale notice
test('stale notice clears when a new optimiser run completes', async () => {
  globalThis.fetch = makeMockFetch([{ type: 'complete', data: SAMPLE_RESULTS }]);
  globalThis.AbortController = MockAbortController;

  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const staleNotice = findByTestId(panel, 'results-stale-notice');

  // Make stale
  api._fireBus('zone:added', {});
  assert.equal(staleNotice.style.display, 'block', 'must be stale before re-run');

  // Re-run — immediately hides stale notice at run start
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  assert.equal(staleNotice.style.display, 'none', 'stale notice must be cleared after new run');
});

test('stale watch on zones state triggers stale notice when results exist', () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS, zones: SAMPLE_ZONES });
  init(api);
  const panel = api._mounted[0];
  const staleNotice = findByTestId(panel, 'results-stale-notice');
  api._triggerWatch('zones', {
    priority: SAMPLE_ZONES.priority,
    exclusion: [{
      id: 'z2',
      label: 'Exclusion B',
      geometry: { type: 'Polygon', coordinates: [[[2, 2], [3, 2], [3, 3], [2, 2]]] },
      reason: 'test',
    }],
  });
  assert.equal(staleNotice.style.display, 'block');
});

// ---------------------------------------------------------------------------
// Results display tests
// ---------------------------------------------------------------------------

test('results section shows coverage percentage', () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const covCell = findByTestId(panel, 'results-coverage');
  assert.ok(covCell.textContent.includes('87.6'), `expected 87.6%, got: ${covCell.textContent}`);
});

test('results section shows total cost', () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const costCell = findByTestId(panel, 'results-cost');
  assert.ok(costCell.textContent.includes('400'), `expected 400,000, got: ${costCell.textContent}`);
});

test('results section shows satisfied constraints', () => {
  const api = makeApi({ optimiserResults: SAMPLE_RESULTS });
  init(api);
  const panel = api._mounted[0];
  const satEl = findByTestId(panel, 'results-satisfied');
  assert.ok(satEl.textContent.includes('budget'), `expected 'budget' in satisfied, got: ${satEl.textContent}`);
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
      `watcher for ${key} must be removed after unmount`
    );
  }
});

test('onUnmount unsubscribes all bus listeners', () => {
  const api = makeApi();
  init(api);
  api._runUnmount();
  for (const ev of ['zone:added', 'zone:removed', 'constraint:updated']) {
    assert.equal((api._busListeners[ev] ?? []).length, 0, `${ev} listener must be removed`);
  }
});

test('onUnmount removes ghost-sensors map layer and source', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['optimiser:ghost-sensors-circle'], 'layer must exist before unmount');
  assert.ok(api._sources['optimiser:ghost-sensors'], 'source must exist before unmount');
  api._runUnmount();
  assert.equal(api._layers['optimiser:ghost-sensors-circle'], undefined, 'layer must be removed');
  assert.equal(api._sources['optimiser:ghost-sensors'], undefined, 'source must be removed');
});
