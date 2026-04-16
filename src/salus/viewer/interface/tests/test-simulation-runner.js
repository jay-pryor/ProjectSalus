/**
 * test-simulation-runner.js — Unit tests for the Simulation Runner module (S14.8).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-simulation-runner.js
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
      cssText: '', display: '', cursor: '', width: '', background: '',
      color: '', flex: '', scrollTop: 0, scrollHeight: 0,
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
    min: '',
    max: '',
    placeholder: '',
    accept: '',
    href: '',
    download: '',
    _clicked: false,

    appendChild(child)  { this._children.push(child); return child; },
    append(...children) { for (const c of children) this.appendChild(c); },
    removeChild(child) {
      const i = this._children.indexOf(child);
      if (i !== -1) this._children.splice(i, 1);
    },
    get firstChild() { return this._children[0] ?? null; },
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
    scrollIntoView()          {},
    click()                   { this._clicked = true; this._fire('click'); },
    _fire(event, data = {}) {
      const evt = { ...data, target: el, stopPropagation() {}, preventDefault() {} };
      for (const h of (this._listeners[event] ?? [])) h(evt);
    },
  };
  return el;
}

// ---------------------------------------------------------------------------
// Mock fetch + readable stream helpers
// ---------------------------------------------------------------------------

/**
 * Build a mock ReadableStream that yields SSE chunks.
 * chunks: string[] — each string is yielded as a separate chunk.
 */
function makeSseStream(chunks) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    getReader() {
      return {
        async read() {
          if (i >= chunks.length) return { done: true, value: undefined };
          const chunk = chunks[i++];
          return { done: false, value: encoder.encode(chunk) };
        },
        cancel() { return Promise.resolve(); },
      };
    },
  };
}

function sseEvent(type, data) {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
}

let _lastFetchUrl = null;
let _lastFetchOptions = null;
let _mockFetchResponse = null;

globalThis.fetch = async (url, opts) => {
  _lastFetchUrl = url;
  _lastFetchOptions = opts;
  if (_mockFetchResponse) return _mockFetchResponse;
  return { ok: false, status: 500, body: null };
};

// Mock AbortController
let _abortCalled = false;
const _originalAbortController = globalThis.AbortController;
// Use real AbortController if available, otherwise mock
if (typeof globalThis.AbortController === 'undefined') {
  globalThis.AbortController = class {
    constructor() {
      this.signal = { aborted: false };
      _abortCalled = false;
    }
    abort() {
      _abortCalled = true;
      this.signal.aborted = true;
    }
  };
}

// Mock TextEncoder
if (typeof globalThis.TextEncoder === 'undefined') {
  globalThis.TextEncoder = class {
    encode(str) {
      return Buffer.from(str, 'utf8');
    }
  };
}

// Mock TextDecoder
if (typeof globalThis.TextDecoder === 'undefined') {
  globalThis.TextDecoder = class {
    decode(value, opts) {
      if (!value) return '';
      return Buffer.from(value).toString('utf8');
    }
  };
}

// Mock setInterval / clearInterval
let _intervals = [];
const _originalSetInterval = globalThis.setInterval;
const _originalClearInterval = globalThis.clearInterval;

globalThis.setInterval = (fn, ms) => {
  const id = { fn, ms, _cancelled: false };
  _intervals.push(id);
  return id;
};
globalThis.clearInterval = (id) => {
  if (id) id._cancelled = true;
  _intervals = _intervals.filter(x => x !== id);
};

// Mock document
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
// Dynamic import AFTER globalThis.document is set
// ---------------------------------------------------------------------------

const { init } = await import('../modules/simulation-runner/index.js');

// ---------------------------------------------------------------------------
// Test helpers
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

function tick() {
  return new Promise(resolve => setTimeout(resolve, 20));
}

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({ terrain = null, placements = null, threat_corridors = null, zones = null } = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const busListeners = {};
  const stateWatchers = {};
  const stateData = { terrain, placements, threat_corridors, zones, sim_results: null };

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _busListeners: busListeners,
    _stateWatchers: stateWatchers,
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

    moduleId: 'simulation-runner',

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
      addSource()  {},
      removeSource(){},
      getSource()  { return null; },
      addLayer()   {},
      removeLayer(){},
      getLayer()   { return null; },
      getCanvas()  { return makeMockElement('canvas'); },
      on()         {},
      off()        {},
    },

    panel: {
      mount(el) { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const TERRAIN = { dem_path: '/data/site.tif', bounds: [-35, 138, -34, 139] };
const PLACEMENTS_FLAT = [
  { sensor_name: 'Radar-1', sensor_type: 'Radar', lat: -34.9, lng: 138.6, bearing_deg: 45 },
];
const PLACEMENTS_SCHEMA = {
  sensors: [{ sensor_name: 'Radar-1', sensor_type: 'Radar', lat: -34.9, lng: 138.6, bearing_deg: 45 }],
  effectors: [],
};
const THREAT_CORRIDORS = [{ waypoints: [], threat_profile: 'UAS-Small' }];
const ZONES = { priority: [{ label: 'HQ', min_coverage_pct: 80 }], exclusion: [] };

const SIM_RESULTS = {
  layers: {},
  sensor_placements: { type: 'FeatureCollection', features: [] },
  stats: {
    coverage_pct: 82.5,
    largest_gap_area_m2: 15000,
    worst_corridor_coverage_pct: 71.3,
  },
  corridor_results: [],
  kill_chain_results: [],
  saturation_result: null,
  sanitised: false,
  generated_at: '2026-04-16T09:00:00Z',
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest reads terrain, placements, threat_corridors, zones', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const k of ['terrain', 'placements', 'threat_corridors', 'zones']) {
    assert.ok(m.reads.includes(k), `reads must include ${k}`);
  }
});

test('manifest writes only sim_results', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.writes, ['sim_results']);
});

test('manifest prerequisites are terrain and placements', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.prerequisites.includes('terrain'));
  assert.ok(m.prerequisites.includes('placements'));
});

test('manifest emits all four simulation events', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const ev of ['simulation:started', 'simulation:progress',
                    'simulation:complete', 'simulation:failed']) {
    assert.ok(m.emits.includes(ev), `emits must include ${ev}`);
  }
});

test('manifest subscribes is empty', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/simulation-runner/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.subscribes, []);
});

// ---------------------------------------------------------------------------
// Init / setup tests
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init registers watch on terrain, placements, threat_corridors, zones', () => {
  const api = makeApi();
  init(api);
  for (const key of ['terrain', 'placements', 'threat_corridors', 'zones']) {
    assert.ok(
      (api._stateWatchers[key] ?? []).length > 0,
      `must register watch on ${key}`
    );
  }
});

test('init does not subscribe to any bus events', () => {
  const api = makeApi();
  init(api);
  // No bus.on() calls expected (subscribes: [])
  assert.equal(Object.keys(api._busListeners).length, 0);
});

// ---------------------------------------------------------------------------
// Pre-flight checklist tests
// ---------------------------------------------------------------------------

test('run button is disabled when terrain and placements are null', () => {
  const api = makeApi({ terrain: null, placements: null });
  init(api);
  const panel = api._mounted[0];
  const btn = findByTestId(panel, 'run-btn');
  assert.equal(btn.disabled, true);
});

test('run button is disabled when only terrain is set', () => {
  const api = makeApi({ terrain: TERRAIN, placements: null });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'run-btn').disabled, true);
});

test('run button is disabled when only placements are set', () => {
  const api = makeApi({ terrain: null, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'run-btn').disabled, true);
});

test('run button is enabled when terrain and placements are set', () => {
  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'run-btn').disabled, false);
});

test('run button enables when terrain watch fires', () => {
  const api = makeApi({ terrain: null, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'run-btn').disabled, true);
  api._triggerWatch('terrain', TERRAIN);
  assert.equal(findByTestId(panel, 'run-btn').disabled, false);
});

test('run button enables when placements watch fires', () => {
  const api = makeApi({ terrain: TERRAIN, placements: null });
  init(api);
  const panel = api._mounted[0];
  api._triggerWatch('placements', PLACEMENTS_FLAT);
  assert.equal(findByTestId(panel, 'run-btn').disabled, false);
});

test('run button disables again when placements cleared', () => {
  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'run-btn').disabled, false);
  api._triggerWatch('placements', []);
  assert.equal(findByTestId(panel, 'run-btn').disabled, true);
});

test('terrain check icon is green check when terrain set', () => {
  const api = makeApi({ terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const icon = findByTestId(panel, 'check-terrain-icon');
  assert.equal(icon.textContent, '\u2713');
  assert.equal(icon.style.color, '#4ade80');
});

test('terrain check icon is red cross when terrain null', () => {
  const api = makeApi({ terrain: null });
  init(api);
  const panel = api._mounted[0];
  const icon = findByTestId(panel, 'check-terrain-icon');
  assert.equal(icon.textContent, '\u2717');
  assert.equal(icon.style.color, '#f87171');
});

test('corridors check icon is neutral dash when corridors null (optional)', () => {
  const api = makeApi({ threat_corridors: null });
  init(api);
  const panel = api._mounted[0];
  const icon = findByTestId(panel, 'check-corridors-icon');
  assert.equal(icon.textContent, '\u2013');
  assert.equal(icon.style.color, '#666');
});

test('corridors check icon is green when corridors set', () => {
  const api = makeApi({ threat_corridors: THREAT_CORRIDORS });
  init(api);
  const panel = api._mounted[0];
  const icon = findByTestId(panel, 'check-corridors-icon');
  assert.equal(icon.textContent, '\u2713');
});

test('checklist updates in real time via watch', () => {
  const api = makeApi({ terrain: null, placements: null });
  init(api);
  const panel = api._mounted[0];
  api._triggerWatch('terrain', TERRAIN);
  const terrainIcon = findByTestId(panel, 'check-terrain-icon');
  assert.equal(terrainIcon.textContent, '\u2713');
});

test('cancel button is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const cancelBtn = findByTestId(panel, 'cancel-btn');
  assert.equal(cancelBtn.style.display, 'none');
});

test('progress section is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const ps = findByTestId(panel, 'progress-section');
  assert.equal(ps.style.display, 'none');
});

test('results section is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const rs = findByTestId(panel, 'results-section');
  assert.equal(rs.style.display, 'none');
});

test('stale banner is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sb = findByTestId(panel, 'stale-banner');
  assert.equal(sb.style.display, 'none');
});

// ---------------------------------------------------------------------------
// Run simulation — fetch body serialisation tests
// ---------------------------------------------------------------------------

test('run button click POSTs to /api/simulate with correct body shape', async () => {
  _lastFetchUrl = null;
  _lastFetchOptions = null;

  const stream = makeSseStream([
    sseEvent('complete', SIM_RESULTS),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_SCHEMA });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  assert.equal(_lastFetchUrl, '/api/simulate');
  assert.equal(_lastFetchOptions.method, 'POST');

  const body = JSON.parse(_lastFetchOptions.body);
  assert.ok('site_dem_path' in body, 'body must have site_dem_path');
  assert.ok('sensor_placements' in body, 'body must have sensor_placements');
  assert.ok('effector_placements' in body, 'body must have effector_placements');
  assert.ok('threat_corridors' in body, 'body must have threat_corridors');
  assert.ok('zones' in body, 'body must have zones');
});

test('serialisation maps terrain.dem_path to site_dem_path', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_SCHEMA });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.equal(body.site_dem_path, TERRAIN.dem_path);
});

test('serialisation maps placements.sensors to sensor_placements (schema format)', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_SCHEMA });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.equal(body.sensor_placements.length, 1);
  assert.equal(body.sensor_placements[0].sensor_name, 'Radar-1');
});

test('serialisation handles flat array placements (S14.5 format)', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  // Flat array → sensor_placements
  assert.equal(body.sensor_placements.length, 1);
  assert.deepEqual(body.effector_placements, []);
});

// ---------------------------------------------------------------------------
// Run simulation — UI state during run
// ---------------------------------------------------------------------------

test('run button click shows cancel button and progress section', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  // Capture state before stream resolves — inspect synchronous side-effects first
  const prom = new Promise(resolve => {
    const orig = api.bus.emit.bind(api.bus);
    api.bus.emit = (event, data) => {
      orig(event, data);
      if (event === 'simulation:started') resolve();
    };
  });

  findByTestId(panel, 'run-btn')._fire('click');
  await prom;

  assert.equal(findByTestId(panel, 'cancel-btn').style.display, 'block');
  assert.equal(findByTestId(panel, 'progress-section').style.display, 'block');
});

test('run button click emits simulation:started', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:started');
  assert.ok(ev, 'must emit simulation:started');
});

// ---------------------------------------------------------------------------
// SSE event dispatch tests
// ---------------------------------------------------------------------------

test('progress SSE event appends to log and updates progress fill', async () => {
  // Stream with only a progress event — stream ends without complete/error to avoid fill being overridden
  const stream = makeSseStream([
    sseEvent('progress', { message: 'Computing viewsheds', pct: 40 }),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  const logEl = findByTestId(panel, 'progress-log');
  const logText = logEl._children.map(c => c.textContent).join('\n');
  assert.ok(logText.includes('Computing viewsheds'), 'log must include progress message');
  assert.equal(findByTestId(panel, 'progress-fill').style.width, '40%');
});

test('progress SSE event emits simulation:progress', async () => {
  const stream = makeSseStream([
    sseEvent('progress', { message: 'Running', pct: 50 }),
    sseEvent('complete', SIM_RESULTS),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:progress');
  assert.ok(ev, 'must emit simulation:progress');
  assert.equal(ev.data.pct, 50);
  assert.equal(ev.data.message, 'Running');
});

test('complete SSE event writes sim_results to state', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  assert.deepEqual(api._stateData.sim_results, SIM_RESULTS);
});

test('complete SSE event emits simulation:complete with coverage_pct', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:complete');
  assert.ok(ev, 'must emit simulation:complete');
  assert.equal(ev.data.coverage_pct, SIM_RESULTS.stats.coverage_pct);
});

test('complete SSE event shows results section with stats', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'results-section').style.display, 'block');
  const coverage = findByTestId(panel, 'results-coverage');
  assert.ok(coverage.textContent.includes('82.5'), 'must show coverage_pct');
  const gapArea = findByTestId(panel, 'results-gap-area');
  assert.ok(gapArea.textContent.includes('15'), 'must show largest gap area');
  const corridorCov = findByTestId(panel, 'results-corridor-cov');
  assert.ok(corridorCov.textContent.includes('71.3'), 'must show worst corridor coverage');
});

test('complete SSE event hides cancel button', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'cancel-btn').style.display, 'none');
});

test('error SSE event emits simulation:failed and hides cancel button', async () => {
  const stream = makeSseStream([
    sseEvent('error', { message: 'DEM file not found' }),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:failed');
  assert.ok(ev, 'must emit simulation:failed');
  assert.equal(ev.data.error, 'DEM file not found');
  assert.equal(findByTestId(panel, 'cancel-btn').style.display, 'none');
});

test('error SSE event appends error to log', async () => {
  const stream = makeSseStream([
    sseEvent('error', { message: 'DEM file not found' }),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  const logEl = findByTestId(panel, 'progress-log');
  const logText = logEl._children.map(c => c.textContent).join('\n');
  assert.ok(logText.includes('DEM file not found'), 'error must appear in log');
});

test('HTTP error response emits simulation:failed', async () => {
  _mockFetchResponse = { ok: false, status: 503, body: null };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:failed');
  assert.ok(ev, 'must emit simulation:failed on HTTP error');
  assert.ok(ev.data.error.includes('503'), 'error must reference HTTP status');
});

// ---------------------------------------------------------------------------
// Cancellation tests
// ---------------------------------------------------------------------------

test('cancel button click aborts the fetch', async () => {
  // Use a stream that blocks on second read — resolved externally by rejecting with AbortError
  let rejectSecondRead;
  const blockingStream = {
    getReader() {
      let count = 0;
      return {
        read() {
          count++;
          if (count === 1) {
            return Promise.resolve({
              done: false,
              value: new TextEncoder().encode(sseEvent('progress', { message: 'Running', pct: 10 })),
            });
          }
          // Block until we trigger AbortError
          return new Promise((_, reject) => { rejectSecondRead = reject; });
        },
        cancel() { return Promise.resolve(); },
      };
    },
  };
  _mockFetchResponse = { ok: true, status: 200, body: blockingStream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick(); // let first read complete; simulation is now blocked on second read

  findByTestId(panel, 'cancel-btn')._fire('click');
  // Reject the blocked read with AbortError (mimics browser behaviour when fetch is aborted)
  if (rejectSecondRead) {
    rejectSecondRead(Object.assign(new Error('The user aborted a request.'), { name: 'AbortError' }));
  }
  await tick();
  await tick();

  // After cancel: cancel button should be hidden
  assert.equal(findByTestId(panel, 'cancel-btn').style.display, 'none');
});



test('cancel shows "Simulation cancelled" in log', async () => {
  const encoder = new TextEncoder();
  let called = false;
  const blockingStream = {
    getReader() {
      return {
        async read() {
          if (called) {
            // Return an AbortError on second read to simulate cancellation
            throw Object.assign(new Error('The user aborted a request.'), { name: 'AbortError' });
          }
          called = true;
          return {
            done: false,
            value: encoder.encode(sseEvent('progress', { message: 'Working', pct: 5 })),
          };
        },
        cancel() { return Promise.resolve(); },
      };
    },
  };
  _mockFetchResponse = { ok: true, status: 200, body: blockingStream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  findByTestId(panel, 'cancel-btn')._fire('click');
  await tick();
  await tick();

  const logEl = findByTestId(panel, 'progress-log');
  const logText = logEl._children.map(c => c.textContent).join('\n');
  assert.ok(logText.includes('cancelled'), 'log must contain "cancelled"');
});

// ---------------------------------------------------------------------------
// Stale banner tests
// ---------------------------------------------------------------------------

test('stale banner appears when placements changes after successful simulation', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  // Simulation complete — now change placements
  api._triggerWatch('placements', [
    ...PLACEMENTS_FLAT,
    { sensor_name: 'New-1', sensor_type: 'RF', lat: -35.0, lng: 139.0, bearing_deg: 0 },
  ]);

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'block');
});

test('stale banner appears when threat_corridors changes after successful simulation', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  api._triggerWatch('threat_corridors', THREAT_CORRIDORS);

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'block');
});

test('stale banner appears when terrain changes after successful simulation', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  api._triggerWatch('terrain', { dem_path: '/data/new.tif' });

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'block');
});

test('stale banner appears when zones changes after successful simulation', async () => {
  const stream = makeSseStream([sseEvent('complete', SIM_RESULTS)]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  api._triggerWatch('zones', ZONES);

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'block');
});

test('stream ending without complete event emits simulation:failed and resets UI', async () => {
  // Stream with only a progress event and done=true — no complete event
  const stream = makeSseStream([
    sseEvent('progress', { message: 'Working', pct: 30 }),
  ]);
  _mockFetchResponse = { ok: true, status: 200, body: stream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'simulation:failed');
  assert.ok(ev, 'must emit simulation:failed when stream ends without complete');
  assert.ok(ev.data.error.toLowerCase().includes('stream'), 'error must mention stream');
  assert.equal(findByTestId(panel, 'cancel-btn').style.display, 'none', 'cancel button must be hidden');
  assert.equal(findByTestId(panel, 'run-btn').disabled, false, 'run button must be re-enabled');
});

test('stale banner does not appear before first simulation completes', () => {
  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  // Change placements without running simulation first
  api._triggerWatch('placements', [...PLACEMENTS_FLAT]);

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'none');
});

test('stale banner clears on next successful completion', async () => {
  // First run
  _mockFetchResponse = { ok: true, status: 200, body: makeSseStream([sseEvent('complete', SIM_RESULTS)]) };
  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'run-btn')._fire('click');
  await tick();
  api._triggerWatch('placements', [...PLACEMENTS_FLAT]); // trigger stale
  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'block');

  // Second run clears stale
  _mockFetchResponse = { ok: true, status: 200, body: makeSseStream([sseEvent('complete', SIM_RESULTS)]) };
  findByTestId(panel, 'run-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'stale-banner').style.display, 'none');
});

// ---------------------------------------------------------------------------
// onUnmount cleanup tests
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);
  for (const key of ['terrain', 'placements', 'threat_corridors', 'zones']) {
    assert.ok((api._stateWatchers[key] ?? []).length > 0, `${key} watcher must be registered`);
  }
  api._runUnmount();
  for (const key of ['terrain', 'placements', 'threat_corridors', 'zones']) {
    assert.equal((api._stateWatchers[key] ?? []).length, 0, `${key} watcher must be removed`);
  }
});

test('onUnmount clears elapsed timer interval when simulation is in progress', async () => {
  _intervals = []; // reset interval tracking

  // Blocking stream — simulation stays running so the timer is active during unmount
  let rejectRead;
  const blockingStream = {
    getReader() {
      let count = 0;
      return {
        read() {
          count++;
          if (count === 1) {
            return Promise.resolve({
              done: false,
              value: new TextEncoder().encode(sseEvent('progress', { message: 'Running', pct: 10 })),
            });
          }
          return new Promise((_, reject) => { rejectRead = reject; });
        },
        cancel() { return Promise.resolve(); },
      };
    },
  };
  _mockFetchResponse = { ok: true, status: 200, body: blockingStream };

  const api = makeApi({ terrain: TERRAIN, placements: PLACEMENTS_FLAT });
  init(api);

  findByTestId(api._mounted[0], 'run-btn')._fire('click');
  await tick(); // simulation running, timer interval created

  const activeIntervals = _intervals.length;
  assert.ok(activeIntervals > 0, 'timer interval must exist while simulation is running');

  api._runUnmount(); // onUnmount calls _stopTimer() → clearInterval
  if (rejectRead) rejectRead(Object.assign(new Error('Aborted'), { name: 'AbortError' }));

  // After unmount, the timer interval must have been cleared
  assert.equal(_intervals.length, 0, 'timer interval must be cleared on unmount');
});
