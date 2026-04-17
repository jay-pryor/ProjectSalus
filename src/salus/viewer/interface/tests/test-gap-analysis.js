/**
 * test-gap-analysis.js — Unit tests for the Gap Analysis module (S14.9).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-gap-analysis.js
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
    style: { cssText: '', display: '' },
    dataset: {},
    textContent: '',
    id: '',
    disabled: false,
    type: '',
    value: '',
    checked: false,
    min: '',
    max: '',
    placeholder: '',
    parentElement: null,

    appendChild(child) {
      this._children.push(child);
      if (typeof child === 'object' && child !== null) child.parentElement = this;
      return child;
    },
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
    click()                   { this._fire('click'); },
    _fire(event, data = {})   {
      const evt = { ...data, target: this, stopPropagation() {}, preventDefault() {} };
      for (const h of (this._listeners[event] ?? [])) h(evt);
    },
  };
  return el;
}

globalThis.document = { createElement: (tag) => makeMockElement(tag) };

// ---------------------------------------------------------------------------
// Dynamic import AFTER globalThis.document is set
// ---------------------------------------------------------------------------

const { init } = await import('../modules/gap-analysis/index.js');

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

// ---------------------------------------------------------------------------
// Mock API factory
// ---------------------------------------------------------------------------

function makeApi({ sim_results = null, zones = null, sensor_library = null, terrain = null } = {}) {
  const mounted    = [];
  const unmountCbs = [];
  const emitted    = [];
  const busListeners  = {};
  const stateWatchers = {};
  const stateData = { sim_results, zones, sensor_library, terrain };

  let flyToCalls = [];

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _flyToCalls: flyToCalls,
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
    _fireBus(event, data) {
      for (const cb of (busListeners[event] ?? [])) cb(data);
    },

    moduleId: 'gap-analysis',

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
          const i   = arr.indexOf(cb);
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
          const i   = arr.indexOf(cb);
          if (i !== -1) arr.splice(i, 1);
        };
      },
    },

    map: {
      addSource()   {},
      removeSource(){},
      getSource()   { return null; },
      addLayer()    {},
      removeLayer() {},
      getLayer()    { return null; },
      setLayoutProperty() {},
      setPaintProperty()  {},
      on()          {},
      off()         {},
      getCanvas()   { return { parentElement: null }; },
      flyTo(opts)   { flyToCalls.push(opts); },
      fitBounds()   {},
    },

    panel: {
      mount(el) { mounted.push(el); },
      onUnmount(cb) { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// Zone polygon centred around [0.5, 0.5] (lng, lat)
const ZONE_POLYGON = {
  type: 'Polygon',
  coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
};

const ZONES_WITH_PRIORITY = {
  priority: [
    { label: 'HQ', min_coverage_pct: 90, geometry: ZONE_POLYGON },
  ],
  exclusion: [],
};

// Three gaps: two inside the zone polygon, one outside
const SIM_RESULTS_THREE_GAPS = {
  total_coverage_pct: 55,
  layers: {
    gaps: {
      type: 'FeatureCollection',
      features: [
        // Gap 0 — small, outside zone
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[5, 5], [5.01, 5], [5.01, 5.01], [5, 5.01], [5, 5]]],
          },
          properties: {},
        },
        // Gap 1 — large, inside zone (centroid ~[0.5, 0.5])
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9], [0.1, 0.1]]],
          },
          properties: {},
        },
        // Gap 2 — medium, outside zone
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[3, 3], [3.05, 3], [3.05, 3.05], [3, 3.05], [3, 3]]],
          },
          properties: {},
        },
      ],
    },
  },
  sensor_placements: { type: 'FeatureCollection', features: [] },
};

const SIM_RESULTS_WITH_SUGGESTION = {
  total_coverage_pct: 50,
  layers: {
    gaps: {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
        properties: {},
      }],
    },
  },
  gap_suggestions: [
    { lat: 0.5, lng: 0.5, definition: { type: 'Radar', name: 'Radar-2' } },
  ],
  sensor_placements: { type: 'FeatureCollection', features: [] },
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest id is gap-analysis', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  assert.equal(JSON.parse(raw).id, 'gap-analysis');
});

test('manifest reads terrain, sim_results, zones, sensor_library', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const k of ['terrain', 'sim_results', 'zones', 'sensor_library']) {
    assert.ok(m.reads.includes(k), `reads must include ${k}`);
  }
});

test('manifest prerequisites are terrain and sim_results', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.prerequisites.includes('terrain'),     'must prerequisite terrain');
  assert.ok(m.prerequisites.includes('sim_results'), 'must prerequisite sim_results');
});

test('manifest emits placement:pending', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.emits.includes('placement:pending'), 'must emit placement:pending');
});

test('manifest subscribes to simulation:complete', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/gap-analysis/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.subscribes.includes('simulation:complete'), 'must subscribe simulation:complete');
});

// ---------------------------------------------------------------------------
// Panel DOM tests
// ---------------------------------------------------------------------------

test('panel mounts to api.panel', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
  assert.equal(api._mounted[0]['data-testid'], 'gap-analysis-panel');
});

test('panel shows empty message when no sim_results', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const empty = findByTestId(panel, 'gap-list-empty');
  assert.ok(empty, 'empty-message shown when no sim_results');
});

test('panel shows empty message when sim_results has no gaps', () => {
  const api = makeApi({ sim_results: { layers: {}, sensor_placements: { type: 'FeatureCollection', features: [] } } });
  init(api);
  const panel = api._mounted[0];
  const empty = findByTestId(panel, 'gap-list-empty');
  assert.ok(empty, 'empty-message shown when gaps layer is empty');
});

// ---------------------------------------------------------------------------
// Gap list ranking tests
// ---------------------------------------------------------------------------

test('gap inside high-priority zone (min_coverage >= 90) gets Critical badge', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS, zones: ZONES_WITH_PRIORITY });
  init(api);
  const panel = api._mounted[0];

  // Gap 1 is inside the zone (centroid ~[0.5, 0.5])
  const badge = findByTestId(panel, 'gap-severity-1');
  assert.ok(badge, 'severity badge for gap 1 exists');
  assert.equal(badge.textContent, 'Critical', 'gap inside 90% zone is Critical');
});

test('gap outside any zone gets Medium badge', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS, zones: ZONES_WITH_PRIORITY });
  init(api);
  const panel = api._mounted[0];

  // Gap 0 is outside the zone
  const badge = findByTestId(panel, 'gap-severity-0');
  assert.ok(badge, 'severity badge for gap 0 exists');
  assert.equal(badge.textContent, 'Medium', 'gap outside zones is Medium');
});

test('critical gap appears first in sorted list', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS, zones: ZONES_WITH_PRIORITY });
  init(api);
  const panel = api._mounted[0];
  const list  = findByTestId(panel, 'gap-list');

  // First card should contain a Critical badge
  const firstCard = list._children[0];
  assert.ok(firstCard, 'first card exists');
  const badges = findAll(firstCard, el => el.textContent === 'Critical');
  assert.ok(badges.length > 0, 'first card contains Critical badge (sorted to top)');
});

test('gap cards each have a Fly to button', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS });
  init(api);
  const panel = api._mounted[0];

  // Should be 3 gaps
  for (let i = 0; i < 3; i++) {
    const btn = findByTestId(panel, `fly-to-btn-${i}`);
    assert.ok(btn, `fly-to-btn-${i} present`);
  }
});

test('clicking fly-to button calls api.map.flyTo', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS });
  init(api);
  const panel = api._mounted[0];

  const btn = findByTestId(panel, 'fly-to-btn-0');
  assert.ok(btn, 'fly-to-btn-0 exists');
  btn._fire('click');

  assert.equal(api._flyToCalls.length, 1, 'flyTo called once');
  assert.ok(api._flyToCalls[0].center, 'flyTo options include center');
});

test('each gap card shows area in m²', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS });
  init(api);
  const panel = api._mounted[0];

  for (let i = 0; i < 3; i++) {
    const areaEl = findByTestId(panel, `gap-area-${i}`);
    assert.ok(areaEl, `gap-area-${i} present`);
    assert.ok(areaEl.textContent.includes('m²'), `gap-area-${i} shows m² unit`);
  }
});

// ---------------------------------------------------------------------------
// Suggestion card tests
// ---------------------------------------------------------------------------

test('suggestion card shown when sim_results has gap_suggestions', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_SUGGESTION });
  init(api);
  const panel = api._mounted[0];

  const sugCard = findByTestId(panel, 'gap-suggestion-0');
  assert.ok(sugCard, 'suggestion card shown for gap 0');
  const placeBtn = findByTestId(panel, 'place-btn-0');
  assert.ok(placeBtn, 'Place this button present');
});

test('Place this button emits placement:pending with lat/lng/definition', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_SUGGESTION });
  init(api);
  const panel = api._mounted[0];

  const placeBtn = findByTestId(panel, 'place-btn-0');
  placeBtn._fire('click');

  const evt = api._emitted.find(e => e.event === 'placement:pending');
  assert.ok(evt, 'placement:pending emitted');
  assert.equal(evt.data.lat,                 0.5);
  assert.equal(evt.data.lng,                 0.5);
  assert.equal(evt.data.definition?.type,    'Radar');
  assert.equal(evt.data.definition?.name,    'Radar-2');
});

test('gap inside a MultiPolygon zone gets correct severity (not silently Medium)', () => {
  // The centroid of the gap at ~[0.5, 0.5] should be inside the MultiPolygon sub-polygon
  const multiPolyZones = {
    priority: [{
      label: 'Multi Zone',
      min_coverage_pct: 90,
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],  // contains [0.5, 0.5]
          [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]],  // separate polygon
        ],
      },
    }],
    exclusion: [],
  };
  const simResults = {
    total_coverage_pct: 55,
    layers: {
      gaps: {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9], [0.1, 0.1]]] },
          properties: {},
        }],
      },
    },
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };
  const api = makeApi({ sim_results: simResults, zones: multiPolyZones });
  init(api);
  const panel = api._mounted[0];
  const badge = findByTestId(panel, 'gap-severity-0');
  assert.ok(badge, 'severity badge present');
  assert.equal(badge.textContent, 'Critical', 'gap inside MultiPolygon zone gets Critical (not silently Medium)');
});

test('no suggestion card when gap_suggestions absent', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS });
  init(api);
  const panel = api._mounted[0];

  const sugCard = findByTestId(panel, 'gap-suggestion-0');
  assert.ok(!sugCard, 'no suggestion card when gap_suggestions not in sim_results');
});

// ---------------------------------------------------------------------------
// Reactive update tests
// ---------------------------------------------------------------------------

test('gap list re-renders on sim_results state watch', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  // Initially no gaps
  assert.ok(findByTestId(panel, 'gap-list-empty'), 'starts empty');

  api._triggerWatch('sim_results', SIM_RESULTS_THREE_GAPS);

  // After update, empty message should be gone and cards present
  assert.ok(!findByTestId(panel, 'gap-list-empty'), 'empty message gone after sim_results update');
  assert.ok(findByTestId(panel, 'fly-to-btn-0'), 'gap card 0 present after update');
});

test('gap list re-renders on zones state watch', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_THREE_GAPS });
  init(api);
  const panel = api._mounted[0];

  // Without zones, all gaps are Medium
  const badgeBefore = findByTestId(panel, 'gap-severity-1');
  assert.equal(badgeBefore?.textContent, 'Medium', 'gap 1 is Medium before zones loaded');

  api._triggerWatch('zones', ZONES_WITH_PRIORITY);

  // After zones, gap 1 (inside zone) should be Critical
  const badgeAfter = findByTestId(panel, 'gap-severity-1');
  assert.equal(badgeAfter?.textContent, 'Critical', 'gap 1 is Critical after zones loaded');
});

// ---------------------------------------------------------------------------
// Bus subscription tests
// ---------------------------------------------------------------------------

test('subscribes to simulation:complete', () => {
  const api = makeApi();
  init(api);
  assert.ok(
    api._busListeners['simulation:complete']?.length > 0,
    'simulation:complete listener registered',
  );
});

// ---------------------------------------------------------------------------
// Cleanup tests
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes state watchers and bus listeners', () => {
  const api = makeApi();
  init(api);

  assert.ok(api._stateWatchers['sim_results']?.length > 0, 'sim_results watcher registered');
  assert.ok(api._stateWatchers['zones']?.length > 0,       'zones watcher registered');

  api._runUnmount();

  assert.equal(api._stateWatchers['sim_results']?.length ?? 0, 0, 'sim_results watcher cleaned');
  assert.equal(api._stateWatchers['zones']?.length ?? 0,       0, 'zones watcher cleaned');
  assert.equal(
    api._busListeners['simulation:complete']?.length ?? 0, 0,
    'simulation:complete listener cleaned',
  );
});
