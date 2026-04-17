/**
 * test-saturation-analyser.js — Unit tests for the Saturation Analyser module (S14.10).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-saturation-analyser.js
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
      cssText: '', display: '', cursor: '', width: '', background: '', color: '',
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

    appendChild(child)   { this._children.push(child); return child; },
    append(...children)  { for (const c of children) this.appendChild(c); },
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
// Dynamic import
// ---------------------------------------------------------------------------

const { init } = await import('../modules/saturation-analyser/index.js');

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

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({ sim_results = null, terrain = null } = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const busListeners = {};
  const stateWatchers = {};
  const stateData = { sim_results, terrain };

  const mapSources = {};
  const mapLayers = {};
  const sourceData = {};

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _busListeners: busListeners,
    _stateWatchers: stateWatchers,
    _stateData: stateData,
    _mapSources: mapSources,
    _mapLayers: mapLayers,
    _sourceData: sourceData,

    _runUnmount() {
      const cbs = [...unmountCbs];
      unmountCbs.length = 0;
      for (const cb of cbs) cb();
    },
    _triggerWatch(key, value) {
      stateData[key] = value;
      for (const cb of (stateWatchers[key] ?? [])) cb(value);
    },
    _triggerBus(event, data) {
      for (const cb of (busListeners[event] ?? [])) cb(data);
    },

    moduleId: 'saturation-analyser',

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
      addSource(id, spec) { mapSources[id] = { spec, data: spec.data }; },
      removeSource(id)    { delete mapSources[id]; },
      getSource(id)       {
        if (!mapSources[id]) return null;
        return {
          setData(d) { sourceData[id] = d; mapSources[id].data = d; },
        };
      },
      addLayer(spec)      { mapLayers[spec.id] = spec; },
      removeLayer(id)     { delete mapLayers[id]; },
      getLayer(id)        { return mapLayers[id] ?? null; },
      fitBounds()         {},
      flyTo()             {},
      on()                {},
      off()               {},
      setLayoutProperty() {},
      setPaintProperty()  {},
    },

    panel: {
      mount(el)     { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const TERRAIN = { bounds_wgs84: [138.5, -35.1, 139.0, -34.7] };

const SAT_RESULT = {
  simultaneous_engagement_capacity: 5,
  saturation_threshold_n: 6,
  unengaged_count_at_threshold: 1,
  per_effector_utilisation: {
    'Jammer-NW': 0.85,
    'Jammer-NE': 0.72,
    'Spoofer-C': 0.60,
  },
};

const SIM_RESULTS = {
  total_coverage_pct: 72.5,
  kill_chain_results: [],
  saturation_result: SAT_RESULT,
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest id is saturation-analyser', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.equal(m.id, 'saturation-analyser');
});

test('manifest reads terrain and sim_results', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.ok(m.reads.includes('terrain'));
  assert.ok(m.reads.includes('sim_results'));
});

test('manifest writes is empty', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.deepEqual(m.writes, []);
});

test('manifest emits is empty', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.deepEqual(m.emits, []);
});

test('manifest subscribes to simulation:complete', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.ok(m.subscribes.includes('simulation:complete'));
});

test('manifest layer_id_prefix is saturation-analyser', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/saturation-analyser/manifest.json'), 'utf8'
  ));
  assert.equal(m.layer_id_prefix, 'saturation-analyser');
});

// ---------------------------------------------------------------------------
// Init / setup tests
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init registers watch on sim_results and terrain', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._stateWatchers['sim_results'] ?? []).length > 0, 'must watch sim_results');
  assert.ok((api._stateWatchers['terrain'] ?? []).length > 0, 'must watch terrain');
});

test('init subscribes to simulation:complete bus event', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._busListeners['simulation:complete'] ?? []).length > 0);
});

test('init adds map sources for approach-vectors and overwhelmed-effectors', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapSources['saturation-analyser:approach-vectors-source']);
  assert.ok(api._mapSources['saturation-analyser:overwhelmed-effectors-source']);
});

test('init adds map layers for approach-vectors-line and overwhelmed-effectors-circle', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapLayers['saturation-analyser:approach-vectors-line']);
  assert.ok(api._mapLayers['saturation-analyser:overwhelmed-effectors-circle']);
});

// ---------------------------------------------------------------------------
// No-data state
// ---------------------------------------------------------------------------

test('no-data notice is shown when saturation_result is null', () => {
  const api = makeApi({ sim_results: null });
  init(api);
  const panel = api._mounted[0];
  const notice = findByTestId(panel, 'no-data-notice');
  assert.equal(notice.style.display, 'block');
});

test('slider section is hidden when no saturation data', () => {
  const api = makeApi({ sim_results: null });
  init(api);
  const panel = api._mounted[0];
  const section = findByTestId(panel, 'slider-section');
  assert.equal(section.style.display, 'none');
});

// ---------------------------------------------------------------------------
// Slider tests
// ---------------------------------------------------------------------------

test('slider is initially set to 1', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const slider = findByTestId(panel, 'threat-count-slider');
  assert.equal(slider.value, '1');
});

test('slider value display shows initial value 1', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const display = findByTestId(panel, 'slider-value');
  assert.equal(display.textContent, '1');
});

test('slider input event updates slider value display', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const slider = findByTestId(panel, 'threat-count-slider');
  const display = findByTestId(panel, 'slider-value');

  slider.value = '8';
  slider._fire('input');

  assert.equal(display.textContent, '8');
});

test('simulation:complete resets slider to 1', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const slider = findByTestId(panel, 'threat-count-slider');

  // Advance slider
  slider.value = '10';
  slider._fire('input');
  assert.equal(slider.value, '10');

  // simulation:complete should reset it
  api._triggerBus('simulation:complete', {});
  assert.equal(slider.value, '1');
});

// ---------------------------------------------------------------------------
// Threshold and capacity display
// ---------------------------------------------------------------------------

test('saturation threshold is displayed correctly', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const thresholdEl = findByTestId(panel, 'threshold-value');
  assert.ok(thresholdEl && thresholdEl.textContent.includes('6'), 'must show threshold of 6 targets');
});

test('engagement capacity is displayed correctly', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const capacityEl = findByTestId(panel, 'capacity-value');
  assert.ok(capacityEl && capacityEl.textContent.includes('5'), 'must show capacity of 5');
});

test('unengaged badge shows 0 when N <= capacity', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const badge = findByTestId(panel, 'unengaged-badge');
  assert.equal(badge.textContent, '0');
});

test('unengaged badge shows correct count when N > capacity', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const slider = findByTestId(panel, 'threat-count-slider');
  const badge = findByTestId(panel, 'unengaged-badge');

  slider.value = '8';  // 8 threats, capacity 5 → 3 unengaged
  slider._fire('input');

  assert.equal(badge.textContent, '3');
});

// ---------------------------------------------------------------------------
// Chart rendering
// ---------------------------------------------------------------------------

test('utilisation chart has SVG when saturation data available', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const chart = findByTestId(panel, 'utilisation-chart');
  assert.ok(chart && chart.innerHTML.includes('<svg'), 'utilisation chart must contain SVG');
});

test('targets chart has SVG when saturation data available', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];
  const chart = findByTestId(panel, 'targets-chart');
  assert.ok(chart && chart.innerHTML.includes('<svg'), 'targets chart must contain SVG');
});

// ---------------------------------------------------------------------------
// Reactive updates
// ---------------------------------------------------------------------------

test('sim_results watch renders saturation data', () => {
  const api = makeApi({ sim_results: null, terrain: TERRAIN });
  init(api);
  const panel = api._mounted[0];

  // Initially no data
  assert.equal(findByTestId(panel, 'no-data-notice').style.display, 'block');

  // Set sim_results with saturation data
  api._triggerWatch('sim_results', SIM_RESULTS);
  assert.equal(findByTestId(panel, 'no-data-notice').style.display, 'none');
});

test('terrain watch updates map layers without crashing', () => {
  const api = makeApi({ sim_results: SIM_RESULTS, terrain: null });
  init(api);
  api._triggerWatch('terrain', TERRAIN);
  assert.ok(true, 'terrain watch must not throw');
});

// ---------------------------------------------------------------------------
// onUnmount cleanup
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);
  for (const key of ['sim_results', 'terrain']) {
    assert.ok((api._stateWatchers[key] ?? []).length > 0, `${key} watcher must be registered`);
  }
  api._runUnmount();
  for (const key of ['sim_results', 'terrain']) {
    assert.equal((api._stateWatchers[key] ?? []).length, 0, `${key} watcher must be removed`);
  }
});

test('onUnmount removes all map layers', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapLayers['saturation-analyser:approach-vectors-line']);
  assert.ok(api._mapLayers['saturation-analyser:overwhelmed-effectors-circle']);

  api._runUnmount();

  assert.ok(!api._mapLayers['saturation-analyser:approach-vectors-line']);
  assert.ok(!api._mapLayers['saturation-analyser:overwhelmed-effectors-circle']);
});

test('onUnmount removes all map sources', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapSources['saturation-analyser:approach-vectors-source']);
  assert.ok(api._mapSources['saturation-analyser:overwhelmed-effectors-source']);

  api._runUnmount();

  assert.ok(!api._mapSources['saturation-analyser:approach-vectors-source']);
  assert.ok(!api._mapSources['saturation-analyser:overwhelmed-effectors-source']);
});

test('onUnmount unsubscribes from simulation:complete', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._busListeners['simulation:complete'] ?? []).length > 0);
  api._runUnmount();
  assert.equal((api._busListeners['simulation:complete'] ?? []).length, 0);
});
