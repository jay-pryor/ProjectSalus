/**
 * test-budget-tracker.js — Unit tests for the Budget Tracker module.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-budget-tracker.js
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
    style: {
      cssText: '', cursor: '', display: '', transform: '',
      width: '', background: '', color: '',
    },
    dataset: {},
    textContent: '',
    innerHTML: '',
    id: '',
    title: '',
    disabled: false,
    type: '',
    value: '',

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
    click() { this._clicked = true; this._fire('click'); },
    /** Simulate an event on this element. */
    _fire(event, data = {}) {
      for (const h of (this._listeners[event] ?? [])) h({ ...data, target: el });
    },
  };
  return el;
}

// Track the last created <a> element for CSV download assertions
let lastAnchor = null;

globalThis.document = {
  createElement: (tag) => {
    const el = makeMockElement(tag);
    if (tag === 'a') lastAnchor = el;
    return el;
  },
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

// Mock Blob — captures content for test assertions
globalThis.Blob = class MockBlob {
  constructor(parts, opts) {
    this._content = parts.join('');
    this._type = opts?.type ?? '';
    globalThis._lastBlob = this;
  }
};
globalThis._lastBlob = null;

// Mock URL for createObjectURL / revokeObjectURL
globalThis.URL = {
  createObjectURL: (_blob) => 'blob:mock:test',
  revokeObjectURL: () => {},
};

// Dynamic import AFTER globalThis.document is set
const { init } = await import('../modules/budget-tracker/index.js');

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({
  placements = null,
  sensorLib = null,
  effectorLib = null,
} = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const busListeners = {};
  const busUnsubs = {};
  const stateWatchers = {};
  const stateData = {
    placements,
    sensor_library: sensorLib,
    effector_library: effectorLib,
    constraints: null,
  };

  const api = {
    // Test-only access
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

    _fireBus(event, data = {}) {
      for (const cb of (busListeners[event] ?? [])) cb(data);
    },

    moduleId: 'budget-tracker',

    state: {
      get(key) { return stateData[key] ?? null; },
      set(key, val) { stateData[key] = val; },
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
        const unsub = () => {
          const arr = busListeners[event];
          const i = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
        if (!busUnsubs[event]) busUnsubs[event] = [];
        busUnsubs[event].push(unsub);
        return unsub;
      },
    },

    panel: {
      mount(el) { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// DOM traversal helpers
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
  const results = findAll(root, el => el['data-testid'] === testId);
  return results[0] ?? null;
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const SAMPLE_SENSORS = {
  Radar: [
    { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000, confidence: 'measured' },
    { name: 'Radar Beta', type: 'Radar', cost_aud: 200000, confidence: 'estimated' },
  ],
};

const SAMPLE_EFFECTORS = {
  RF: [
    { name: 'Jammer X', type: 'RF', cost_aud: 50000, confidence: 'estimated' },
  ],
};

// Two sensors + one effector
const SAMPLE_PLACEMENTS = [
  { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
  { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
  { sensor_name: 'Jammer X', definition: { name: 'Jammer X', type: 'RF', cost_aud: 50000 } },
];

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  for (const field of ['id', 'label', 'reads', 'writes', 'prerequisites',
                        'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, field), `missing field: ${field}`);
  }
});

test('manifest id is budget-tracker', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  assert.equal(m.id, 'budget-tracker');
});

test('manifest reads placements, sensor_library, effector_library', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.reads.includes('placements'), 'reads must include placements');
  assert.ok(m.reads.includes('sensor_library'), 'reads must include sensor_library');
  assert.ok(m.reads.includes('effector_library'), 'reads must include effector_library');
});

test('manifest writes is ["constraints"]', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.writes, ['constraints']);
});

test('manifest does not subscribe to placement bus events (uses watch instead)', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(!m.subscribes.includes('placement:added'), 'subscribes must not include placement:added — use watch');
  assert.ok(!m.subscribes.includes('placement:removed'), 'subscribes must not include placement:removed — use watch');
});

test('manifest emits constraint:updated', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/budget-tracker/manifest.json'),
    'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.emits.includes('constraint:updated'), 'emits must include constraint:updated');
});

// ---------------------------------------------------------------------------
// Init / setup tests
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init writes initial constraints to state', () => {
  const api = makeApi();
  init(api);
  const c = api._stateData.constraints;
  assert.ok(c !== null, 'constraints must not be null after init');
  assert.ok(Object.prototype.hasOwnProperty.call(c, 'max_cost_aud'));
  assert.ok(Object.prototype.hasOwnProperty.call(c, 'allowed_sensor_ids'));
  assert.ok(Object.prototype.hasOwnProperty.call(c, 'max_sensors'));
  assert.ok(Object.prototype.hasOwnProperty.call(c, 'max_effectors'));
});

test('init writes max_cost_aud null when no budget entered', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._stateData.constraints.max_cost_aud, null);
});

test('init registers watch on placements', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    (api._stateWatchers['placements'] ?? []).length > 0,
    'must watch placements'
  );
});

test('init registers watch on sensor_library', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    (api._stateWatchers['sensor_library'] ?? []).length > 0,
    'must watch sensor_library'
  );
});

test('init registers watch on effector_library', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    (api._stateWatchers['effector_library'] ?? []).length > 0,
    'must watch effector_library'
  );
});

test('init does not subscribe to placement:added bus event (uses watch instead)', () => {
  const api = makeApi();
  init(api);
  assert.equal(
    (api._busListeners['placement:added'] ?? []).length,
    0,
    'must not subscribe to placement:added — placements state watch handles re-render'
  );
});

test('init does not subscribe to placement:removed bus event (uses watch instead)', () => {
  const api = makeApi();
  init(api);
  assert.equal(
    (api._busListeners['placement:removed'] ?? []).length,
    0,
    'must not subscribe to placement:removed — placements state watch handles re-render'
  );
});

test('init emits constraint:updated', () => {
  const api = makeApi();
  init(api);
  const events = api._emitted.filter(e => e.event === 'constraint:updated');
  assert.ok(events.length >= 1, 'must emit constraint:updated on init');
});

// ---------------------------------------------------------------------------
// Cost calculation tests
// ---------------------------------------------------------------------------

test('cost calculated from placements and library lookup', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const costEl = findByTestId(panel, 'cost-label');
  // 2 × 100000 + 1 × 50000 = 250000
  assert.ok(costEl.textContent.includes('250'), 'cost label must show 250,000');
});

test('over-budget warning shown when total exceeds budget', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '100000'; // total is 250000, well over budget
  budgetInput._fire('input');
  const warning = findByTestId(panel, 'over-budget-warning');
  assert.equal(warning.style.display, 'block');
});

test('over-budget warning hidden when within budget', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '500000'; // total is 250000, under budget
  budgetInput._fire('input');
  const warning = findByTestId(panel, 'over-budget-warning');
  assert.equal(warning.style.display, 'none');
});

test('progress bar background is red when over budget', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '100000';
  budgetInput._fire('input');
  const fill = findByTestId(panel, 'budget-progress-fill');
  assert.equal(fill.style.background, '#ef4444');
});

test('progress bar background is green when within budget', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '500000';
  budgetInput._fire('input');
  const fill = findByTestId(panel, 'budget-progress-fill');
  assert.equal(fill.style.background, '#22c55e');
});

// ---------------------------------------------------------------------------
// Budget input → constraints tests
// ---------------------------------------------------------------------------

test('budget input change updates constraints.max_cost_aud', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '2000000';
  budgetInput._fire('input');
  assert.equal(api._stateData.constraints.max_cost_aud, 2000000);
});

test('budget input cleared sets max_cost_aud to null', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const budgetInput = findByTestId(panel, 'budget-input');
  budgetInput.value = '';
  budgetInput._fire('input');
  assert.equal(api._stateData.constraints.max_cost_aud, null);
});

// ---------------------------------------------------------------------------
// Reactive watch update tests
// ---------------------------------------------------------------------------

test('placements watch re-renders breakdown table', () => {
  const api = makeApi({ sensorLib: SAMPLE_SENSORS });
  init(api);
  const panel = api._mounted[0];
  const costBefore = findByTestId(panel, 'cost-label').textContent;

  api._triggerWatch('placements', [
    { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
  ]);
  const costAfter = findByTestId(panel, 'cost-label').textContent;
  assert.notEqual(costBefore, costAfter);
  assert.ok(costAfter.includes('100'), 'cost label should show 100,000');
});

test('sensor_library watch re-renders when library changes', () => {
  const api = makeApi({
    placements: [{ sensor_name: 'New Sensor', definition: { type: 'Radar' } }],
  });
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('sensor_library', {
    Radar: [{ name: 'New Sensor', type: 'Radar', cost_aud: 75000 }],
  });
  const costEl = findByTestId(panel, 'cost-label');
  assert.ok(costEl.textContent.includes('75'), 'cost should reflect updated library');
});

// ---------------------------------------------------------------------------
// Bus event tests
// ---------------------------------------------------------------------------

test('placement:added bus event triggers re-render', () => {
  const api = makeApi({
    placements: SAMPLE_PLACEMENTS,
    sensorLib: SAMPLE_SENSORS,
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];

  // Update mirror and fire bus event — bus handler calls _render() using updated mirror
  api._stateData.placements = [
    ...SAMPLE_PLACEMENTS,
    { sensor_name: 'Radar Beta', definition: { name: 'Radar Beta', type: 'Radar', cost_aud: 200000 } },
  ];
  api._triggerWatch('placements', api._stateData.placements);
  api._fireBus('placement:added', {});

  // Cost should now include Radar Beta: 2×100k + 1×50k + 1×200k = 450k
  const costEl = findByTestId(panel, 'cost-label');
  assert.ok(costEl.textContent.includes('450'), 'cost should reflect added placement');
});

test('placement:removed bus event does not throw', () => {
  const api = makeApi({ placements: SAMPLE_PLACEMENTS });
  init(api);
  assert.doesNotThrow(() => api._fireBus('placement:removed', {}));
});

test('constraint:updated emitted on budget input change', () => {
  const api = makeApi();
  init(api);
  const prevCount = api._emitted.filter(e => e.event === 'constraint:updated').length;
  const panel = api._mounted[0];
  findByTestId(panel, 'budget-input').value = '1000000';
  findByTestId(panel, 'budget-input')._fire('input');
  const newCount = api._emitted.filter(e => e.event === 'constraint:updated').length;
  assert.ok(newCount > prevCount, 'must emit constraint:updated on budget change');
});

// ---------------------------------------------------------------------------
// Max-sensor / max-effector constraint tests (S14.6-3)
// ---------------------------------------------------------------------------

test('max sensors input updates constraints.max_sensors', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const inp = findByTestId(panel, 'max-sensors-input');
  inp.value = '4';
  inp._fire('input');
  assert.equal(api._stateData.constraints.max_sensors, 4);
});

test('max effectors input updates constraints.max_effectors', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const inp = findByTestId(panel, 'max-effectors-input');
  inp.value = '2';
  inp._fire('input');
  assert.equal(api._stateData.constraints.max_effectors, 2);
});

test('max sensors input cleared sets max_sensors to null', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const inp = findByTestId(panel, 'max-sensors-input');
  inp.value = '3';
  inp._fire('input');
  inp.value = '';
  inp._fire('input');
  assert.equal(api._stateData.constraints.max_sensors, null);
});

// SPEC-REQUIRED TEST: set max_sensors=3, add 4 sensor placements, check indicator shows warning
test('sensor indicator shows warning when placement count exceeds max_sensors', () => {
  const fourSensorPlacements = [
    { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
    { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
    { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
    { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
  ];
  const api = makeApi({
    placements: fourSensorPlacements,
    sensorLib: SAMPLE_SENSORS,
  });
  init(api);
  const panel = api._mounted[0];

  // Set max_sensors to 3
  const maxInp = findByTestId(panel, 'max-sensors-input');
  maxInp.value = '3';
  maxInp._fire('input');

  const indicator = findByTestId(panel, 'sensor-limit-indicator');
  assert.equal(indicator.style.color, '#ef4444', 'indicator must be red when over limit');
  assert.ok(indicator.textContent.includes('\u26a0'), 'indicator must show warning symbol');
});

test('sensor indicator shows check when within max_sensors', () => {
  const api = makeApi({
    placements: [
      { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
      { sensor_name: 'Radar Alpha', definition: { name: 'Radar Alpha', type: 'Radar', cost_aud: 100000 } },
    ],
    sensorLib: SAMPLE_SENSORS,
  });
  init(api);
  const panel = api._mounted[0];
  const maxInp = findByTestId(panel, 'max-sensors-input');
  maxInp.value = '4';
  maxInp._fire('input');
  const indicator = findByTestId(panel, 'sensor-limit-indicator');
  assert.equal(indicator.style.color, '#22c55e', 'indicator must be green when within limit');
  assert.ok(indicator.textContent.includes('\u2713'), 'indicator must show check symbol');
});

test('effector indicator shows warning when effector count exceeds max_effectors', () => {
  const api = makeApi({
    placements: [
      { sensor_name: 'Jammer X', definition: { name: 'Jammer X', type: 'RF', cost_aud: 50000 } },
      { sensor_name: 'Jammer X', definition: { name: 'Jammer X', type: 'RF', cost_aud: 50000 } },
    ],
    effectorLib: SAMPLE_EFFECTORS,
  });
  init(api);
  const panel = api._mounted[0];
  const maxInp = findByTestId(panel, 'max-effectors-input');
  maxInp.value = '1';
  maxInp._fire('input');
  const indicator = findByTestId(panel, 'effector-limit-indicator');
  assert.equal(indicator.style.color, '#ef4444', 'effector indicator must be red when over limit');
});

test('max sensors/effectors emit constraint:updated on change', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const prevCount = api._emitted.filter(e => e.event === 'constraint:updated').length;
  const inp = findByTestId(panel, 'max-sensors-input');
  inp.value = '5';
  inp._fire('input');
  const newCount = api._emitted.filter(e => e.event === 'constraint:updated').length;
  assert.ok(newCount > prevCount, 'must emit constraint:updated when max_sensors changes');
});

// ---------------------------------------------------------------------------
// CSV export tests
// ---------------------------------------------------------------------------

test('CSV export produces correct header row', () => {
  const api = makeApi({ placements: SAMPLE_PLACEMENTS, sensorLib: SAMPLE_SENSORS, effectorLib: SAMPLE_EFFECTORS });
  init(api);
  const panel = api._mounted[0];
  globalThis._lastBlob = null;
  findByTestId(panel, 'csv-export-btn')._fire('click');
  assert.ok(globalThis._lastBlob, 'Blob must be created on CSV export');
  const csv = globalThis._lastBlob._content;
  assert.ok(csv.startsWith('Sensor Name,Type,Quantity,Unit Cost (AUD),Line Total (AUD)'),
    'CSV must start with correct header');
});

test('CSV export data rows include name, type, qty, unit cost, line total', () => {
  const api = makeApi({ placements: SAMPLE_PLACEMENTS, sensorLib: SAMPLE_SENSORS, effectorLib: SAMPLE_EFFECTORS });
  init(api);
  const panel = api._mounted[0];
  globalThis._lastBlob = null;
  findByTestId(panel, 'csv-export-btn')._fire('click');
  const csv = globalThis._lastBlob._content;
  // Radar Alpha appears twice → qty=2, line total=200000
  assert.ok(csv.includes('Radar Alpha'), 'CSV must include Radar Alpha');
  assert.ok(csv.includes('2'), 'CSV must show quantity 2 for Radar Alpha');
  assert.ok(csv.includes('200000'), 'CSV must show line total 200000');
});

test('CSV export grand total row is last line', () => {
  const api = makeApi({ placements: SAMPLE_PLACEMENTS, sensorLib: SAMPLE_SENSORS, effectorLib: SAMPLE_EFFECTORS });
  init(api);
  const panel = api._mounted[0];
  globalThis._lastBlob = null;
  findByTestId(panel, 'csv-export-btn')._fire('click');
  const csv = globalThis._lastBlob._content;
  const lines = csv.trim().split('\n');
  const lastLine = lines[lines.length - 1];
  // Grand total: 2×100000 + 1×50000 = 250000
  assert.ok(lastLine.includes('250000'), `grand total row must contain 250000, got: ${lastLine}`);
});

test('CSV download anchor filename matches salus-bom-YYYY-MM-DD.csv', () => {
  const api = makeApi({ placements: SAMPLE_PLACEMENTS, sensorLib: SAMPLE_SENSORS });
  init(api);
  const panel = api._mounted[0];
  lastAnchor = null;
  findByTestId(panel, 'csv-export-btn')._fire('click');
  assert.ok(lastAnchor, 'download anchor must be created');
  assert.ok(
    /^salus-bom-\d{4}-\d{2}-\d{2}\.csv$/.test(lastAnchor.download),
    `download filename must match pattern, got: ${lastAnchor.download}`
  );
});

// ---------------------------------------------------------------------------
// Cleanup / onUnmount tests
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);
  const watchersBefore = [
    (api._stateWatchers['placements'] ?? []).length,
    (api._stateWatchers['sensor_library'] ?? []).length,
    (api._stateWatchers['effector_library'] ?? []).length,
  ];
  assert.ok(watchersBefore.every(n => n > 0), 'watchers must be registered before unmount');
  api._runUnmount();
  assert.equal((api._stateWatchers['placements'] ?? []).length, 0, 'placements watcher must be removed');
  assert.equal((api._stateWatchers['sensor_library'] ?? []).length, 0, 'sensor_library watcher must be removed');
  assert.equal((api._stateWatchers['effector_library'] ?? []).length, 0, 'effector_library watcher must be removed');
});

test('onUnmount registers no bus listeners (placement changes handled via watch)', () => {
  const api = makeApi();
  init(api);
  assert.equal((api._busListeners['placement:added'] ?? []).length, 0, 'must have no placement:added bus listener');
  assert.equal((api._busListeners['placement:removed'] ?? []).length, 0, 'must have no placement:removed bus listener');
  api._runUnmount();
  assert.equal((api._busListeners['placement:added'] ?? []).length, 0, 'still no placement:added listener after unmount');
  assert.equal((api._busListeners['placement:removed'] ?? []).length, 0, 'still no placement:removed listener after unmount');
});

test('placement:added no longer fires after unmount', () => {
  const api = makeApi({ placements: [] });
  init(api);
  api._runUnmount();
  // firing bus after unmount should not throw and should have no effect
  assert.doesNotThrow(() => api._fireBus('placement:added', {}));
  assert.equal((api._busListeners['placement:added'] ?? []).length, 0);
});
