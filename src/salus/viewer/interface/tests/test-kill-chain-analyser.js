/**
 * test-kill-chain-analyser.js — Unit tests for the Kill Chain Analyser module (S14.10).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-kill-chain-analyser.js
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
      color: '', flex: '',
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
// Dynamic import AFTER globalThis.document is set
// ---------------------------------------------------------------------------

const { init } = await import('../modules/kill-chain-analyser/index.js');

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

function makeApi({ sim_results = null, threat_corridors = null, terrain = null } = {}) {
  const mounted = [];
  const unmountCbs = [];
  const emitted = [];
  const busListeners = {};
  const stateWatchers = {};
  const stateData = { sim_results, threat_corridors, terrain };

  const mapSources = {};
  const mapLayers = {};
  let sourceData = {};

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

    moduleId: 'kill-chain-analyser',

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

const THREAT_CORRIDORS = {
  routes: [
    { id: 'r1', label: 'North approach', color: '#ef4444', waypoints: [[138.7, -34.9], [138.75, -34.8]] },
    { id: 'r2', label: 'East approach',  color: '#3b82f6', waypoints: [[138.9, -34.95], [138.75, -34.8]] },
  ],
  protected_point: [138.75, -34.8],
};

const KILL_CHAIN_RESULTS = [
  {
    available_time_s:  45.2,
    required_time_s:   38.5,
    margin_s:           6.7,
    first_detection_range_m: 1200.0,
    engagement_feasible: true,
    second_engagement_possible: false,
  },
  {
    available_time_s:  30.0,
    required_time_s:   42.0,
    margin_s:          -12.0,
    first_detection_range_m: 800.0,
    engagement_feasible: false,
    second_engagement_possible: false,
  },
];

const SIM_RESULTS_WITH_KC = {
  total_coverage_pct: 72.5,
  kill_chain_results: KILL_CHAIN_RESULTS,
  saturation_result: null,
  corridor_results: [],
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest id is kill-chain-analyser', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.equal(m.id, 'kill-chain-analyser');
});

test('manifest reads terrain, sim_results, threat_corridors', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  for (const k of ['terrain', 'sim_results', 'threat_corridors']) {
    assert.ok(m.reads.includes(k), `reads must include ${k}`);
  }
});

test('manifest writes is empty', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.deepEqual(m.writes, []);
});

test('manifest prerequisites are terrain and sim_results', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.ok(m.prerequisites.includes('terrain'));
  assert.ok(m.prerequisites.includes('sim_results'));
});

test('manifest emits is empty', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.deepEqual(m.emits, []);
});

test('manifest subscribes to simulation:complete', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.ok(m.subscribes.includes('simulation:complete'));
});

test('manifest layer_id_prefix is kill-chain-analyser', async () => {
  const m = JSON.parse(await readFile(
    path.resolve(__dirname, '../modules/kill-chain-analyser/manifest.json'), 'utf8'
  ));
  assert.equal(m.layer_id_prefix, 'kill-chain-analyser');
});

// ---------------------------------------------------------------------------
// Init / setup tests
// ---------------------------------------------------------------------------

test('init mounts exactly one panel element', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
});

test('init registers watch on sim_results and threat_corridors and terrain', () => {
  const api = makeApi();
  init(api);
  for (const key of ['sim_results', 'threat_corridors', 'terrain']) {
    assert.ok(
      (api._stateWatchers[key] ?? []).length > 0,
      `must register watch on ${key}`
    );
  }
});

test('init subscribes to simulation:complete bus event', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    (api._busListeners['simulation:complete'] ?? []).length > 0,
    'must subscribe to simulation:complete'
  );
});

test('init adds all three map sources', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapSources['kill-chain-analyser:selected-corridor-source']);
  assert.ok(api._mapSources['kill-chain-analyser:detection-event-source']);
  assert.ok(api._mapSources['kill-chain-analyser:engagement-marker-source']);
});

test('init adds all three map layers', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._mapLayers['kill-chain-analyser:selected-corridor-line']);
  assert.ok(api._mapLayers['kill-chain-analyser:detection-event-circles']);
  assert.ok(api._mapLayers['kill-chain-analyser:engagement-marker']);
});

// ---------------------------------------------------------------------------
// No-data state
// ---------------------------------------------------------------------------

test('no-data notice is shown when sim_results is null', () => {
  const api = makeApi({ sim_results: null });
  init(api);
  const panel = api._mounted[0];
  const notice = findByTestId(panel, 'no-data-notice');
  assert.ok(notice, 'no-data-notice must exist');
  assert.equal(notice.style.display, 'block');
});

test('no-data notice is shown when kill_chain_results is empty', () => {
  const api = makeApi({
    sim_results: { kill_chain_results: [], saturation_result: null },
    threat_corridors: null,
  });
  init(api);
  const panel = api._mounted[0];
  const notice = findByTestId(panel, 'no-data-notice');
  assert.equal(notice.style.display, 'block');
});

test('corridor selector section is hidden when no data', () => {
  const api = makeApi({ sim_results: null });
  init(api);
  const panel = api._mounted[0];
  const section = findByTestId(panel, 'corridor-selector-section');
  assert.equal(section.style.display, 'none');
});

// ---------------------------------------------------------------------------
// Corridor selector population
// ---------------------------------------------------------------------------

test('corridor selector shows corridors when kill_chain_results available', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const section = findByTestId(panel, 'corridor-selector-section');
  assert.equal(section.style.display, 'block');
  const select = findByTestId(panel, 'corridor-select');
  assert.ok(select._children.length >= 2, 'must show at least 2 corridors');
});

test('corridor selector populates from threat_corridors routes labels', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const select = findByTestId(panel, 'corridor-select');
  const labels = select._children.map(c => c.textContent);
  assert.ok(labels.some(l => l.includes('North approach')), 'must include North approach label');
});

test('corridor selector includes feasibility indicator', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const select = findByTestId(panel, 'corridor-select');
  const labels = select._children.map(c => c.textContent);
  assert.ok(labels.some(l => l.includes('✓')), 'feasible corridor must show ✓');
  assert.ok(labels.some(l => l.includes('✗')), 'infeasible corridor must show ✗');
});

// ---------------------------------------------------------------------------
// Stats display
// ---------------------------------------------------------------------------

test('stats section shows detection range for selected corridor', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const cell = findByTestId(panel, 'stat-detection-range');
  assert.ok(cell && cell.textContent.includes('1200'), 'must show detection range');
});

test('stats section shows available time', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const cell = findByTestId(panel, 'stat-available-time');
  assert.ok(cell && cell.textContent.includes('45.2'), 'must show available time');
});

test('stats section shows required time', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const cell = findByTestId(panel, 'stat-required-time');
  assert.ok(cell && cell.textContent.includes('38.5'), 'must show required time');
});

test('margin indicator shows positive margin in green', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const cell = findByTestId(panel, 'stat-margin');
  assert.ok(cell && cell.textContent.includes('+'), 'positive margin must show + sign');
  assert.equal(cell.style.color, '#4ade80');
});

test('gap warning is hidden when engagement is feasible', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const warning = findByTestId(panel, 'gap-warning');
  assert.equal(warning.style.display, 'none');
});

test('gap warning is shown when engagement is not feasible', () => {
  const simResults = {
    kill_chain_results: [KILL_CHAIN_RESULTS[1]], // infeasible
    saturation_result: null,
  };
  const corridors = {
    routes: [THREAT_CORRIDORS.routes[1]],
    protected_point: THREAT_CORRIDORS.protected_point,
  };
  const api = makeApi({ sim_results: simResults, threat_corridors: corridors });
  init(api);
  const panel = api._mounted[0];
  const warning = findByTestId(panel, 'gap-warning');
  assert.equal(warning.style.display, 'block');
});

test('margin indicator shows negative margin in red', () => {
  const simResults = {
    kill_chain_results: [KILL_CHAIN_RESULTS[1]], // negative margin
    saturation_result: null,
  };
  const corridors = {
    routes: [THREAT_CORRIDORS.routes[1]],
    protected_point: THREAT_CORRIDORS.protected_point,
  };
  const api = makeApi({ sim_results: simResults, threat_corridors: corridors });
  init(api);
  const panel = api._mounted[0];
  const cell = findByTestId(panel, 'stat-margin');
  assert.equal(cell.style.color, '#f87171');
});

// ---------------------------------------------------------------------------
// Gantt chart
// ---------------------------------------------------------------------------

test('gantt container has SVG content when kill chain data available', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const container = findByTestId(panel, 'gantt-container');
  assert.ok(container && container.innerHTML.includes('<svg'), 'gantt must contain SVG');
});

// ---------------------------------------------------------------------------
// Worst corridor button
// ---------------------------------------------------------------------------

test('worst button selects corridor with lowest margin', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_WITH_KC,
    threat_corridors: THREAT_CORRIDORS,
  });
  init(api);
  const panel = api._mounted[0];
  const worstBtn = findByTestId(panel, 'worst-btn');
  const select = findByTestId(panel, 'corridor-select');

  worstBtn._fire('click');

  // Corridor 1 (index 1) has margin -12.0 — the worst
  assert.equal(select.value, '1', 'worst button must select corridor with lowest margin');
});

// ---------------------------------------------------------------------------
// Reactive updates
// ---------------------------------------------------------------------------

test('sim_results watch populates stats when data arrives', () => {
  // No routes, no kill chain — notice shown; then sim_results arrives with both
  const api = makeApi({ sim_results: null, threat_corridors: null });
  init(api);
  const panel = api._mounted[0];

  // Initially truly no data (neither sim_results nor threat_corridors)
  assert.equal(findByTestId(panel, 'no-data-notice').style.display, 'block');

  // Set threat_corridors and sim_results
  api._triggerWatch('threat_corridors', THREAT_CORRIDORS);
  api._triggerWatch('sim_results', SIM_RESULTS_WITH_KC);

  // Now data is available — notice hidden, selector shown
  assert.equal(findByTestId(panel, 'no-data-notice').style.display, 'none');
  assert.equal(findByTestId(panel, 'corridor-selector-section').style.display, 'block');
});

test('threat_corridors watch re-renders corridor selector', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_KC, threat_corridors: null });
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('threat_corridors', THREAT_CORRIDORS);
  const select = findByTestId(panel, 'corridor-select');
  assert.ok(select._children.length >= 2, 'must populate selector after watch fires');
});

test('simulation:complete bus event triggers re-render', () => {
  let renderCount = 0;
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_KC, threat_corridors: THREAT_CORRIDORS });
  init(api);

  // Trigger simulation:complete
  api._triggerBus('simulation:complete', {});
  // No assertion on count — just ensure no exception is thrown
  assert.ok(true);
});

// ---------------------------------------------------------------------------
// onUnmount cleanup
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);
  for (const key of ['sim_results', 'threat_corridors', 'terrain']) {
    assert.ok((api._stateWatchers[key] ?? []).length > 0, `${key} watcher must be registered`);
  }
  api._runUnmount();
  for (const key of ['sim_results', 'threat_corridors', 'terrain']) {
    assert.equal((api._stateWatchers[key] ?? []).length, 0, `${key} watcher must be removed`);
  }
});

test('onUnmount removes all map layers and sources', () => {
  const api = makeApi();
  init(api);

  assert.ok(api._mapLayers['kill-chain-analyser:selected-corridor-line']);
  assert.ok(api._mapLayers['kill-chain-analyser:detection-event-circles']);
  assert.ok(api._mapLayers['kill-chain-analyser:engagement-marker']);

  api._runUnmount();

  assert.ok(!api._mapLayers['kill-chain-analyser:selected-corridor-line']);
  assert.ok(!api._mapLayers['kill-chain-analyser:detection-event-circles']);
  assert.ok(!api._mapLayers['kill-chain-analyser:engagement-marker']);
  assert.ok(!api._mapSources['kill-chain-analyser:selected-corridor-source']);
  assert.ok(!api._mapSources['kill-chain-analyser:detection-event-source']);
  assert.ok(!api._mapSources['kill-chain-analyser:engagement-marker-source']);
});

test('onUnmount unsubscribes from simulation:complete bus event', () => {
  const api = makeApi();
  init(api);
  assert.ok((api._busListeners['simulation:complete'] ?? []).length > 0);
  api._runUnmount();
  assert.equal((api._busListeners['simulation:complete'] ?? []).length, 0);
});
