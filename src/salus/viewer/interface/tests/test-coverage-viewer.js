/**
 * test-coverage-viewer.js — Unit tests for the Coverage Viewer module (S14.9).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-coverage-viewer.js
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
    style: { cssText: '', display: '', visibility: '', position: '', left: '', top: '',
             cursor: '', width: '', background: '', color: '' },
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
    parentElement: null,
    _clicked: false,

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
    get firstChild()  { return this._children[0] ?? null; },
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

const { init } = await import('../modules/coverage-viewer/index.js');

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

function makeApi({ sim_results = null, zones = null, terrain = null } = {}) {
  const mounted   = [];
  const unmountCbs = [];
  const emitted   = [];
  const busListeners  = {};
  const stateWatchers = {};
  const stateData = { sim_results, zones, terrain, placements: null };

  // Track source data and layer visibility
  const sources     = {};   // id → current GeoJSON data
  const layers      = {};   // id → spec
  const paintProps  = {};   // id → { prop → value }
  const layoutProps = {};   // id → { prop → value }
  const mapListeners = {};  // [event, layerId?] → handler[]

  const api = {
    _mounted: mounted,
    _unmountCbs: unmountCbs,
    _emitted: emitted,
    _sources: sources,
    _layers: layers,
    _paintProps: paintProps,
    _layoutProps: layoutProps,
    _mapListeners: mapListeners,
    _stateData: stateData,
    _stateWatchers: stateWatchers,
    _busListeners: busListeners,

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
    _fireMapEvent(event, layerId, eventData) {
      const key = layerId ? `${event}::${layerId}` : event;
      for (const h of (mapListeners[key] ?? [])) h(eventData);
    },

    moduleId: 'coverage-viewer',

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
      addSource(id, spec)   { sources[id]  = { data: spec.data, _spec: spec }; },
      removeSource(id)       { delete sources[id]; },
      getSource(id)          {
        if (!sources[id]) return null;
        return {
          setData(d) { sources[id].data = d; },
        };
      },
      addLayer(spec)         { layers[spec.id] = spec; },
      removeLayer(id)        { delete layers[id]; },
      getLayer(id)           { return layers[id] ?? null; },
      setLayoutProperty(id, prop, val) {
        if (!layoutProps[id]) layoutProps[id] = {};
        layoutProps[id][prop] = val;
      },
      setPaintProperty(id, prop, val) {
        if (!paintProps[id]) paintProps[id] = {};
        paintProps[id][prop] = val;
      },
      on(event, layerIdOrHandler, handler) {
        let key;
        if (typeof layerIdOrHandler === 'string') {
          key = `${event}::${layerIdOrHandler}`;
        } else {
          key = event;
          handler = layerIdOrHandler;
        }
        if (!mapListeners[key]) mapListeners[key] = [];
        mapListeners[key].push(handler);
      },
      off(event, layerIdOrHandler, handler) {
        let key;
        if (typeof layerIdOrHandler === 'string') {
          key = `${event}::${layerIdOrHandler}`;
        } else {
          key = event;
          handler = layerIdOrHandler;
        }
        const arr = mapListeners[key] ?? [];
        const h   = typeof handler === 'function' ? handler : layerIdOrHandler;
        const i   = arr.indexOf(h);
        if (i !== -1) arr.splice(i, 1);
      },
      getCanvas() {
        const canvas = makeMockElement('canvas');
        canvas.parentElement = makeMockElement('div');
        return canvas;
      },
      flyTo() {},
      fitBounds() {},
      project(lngLat) { return { x: 0, y: 0 }; },
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
// Fixtures
// ---------------------------------------------------------------------------

const ZONES = {
  priority: [
    {
      label: 'HQ Zone',
      min_coverage_pct: 80,
      geometry: {
        type: 'Polygon',
        coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
      },
    },
    {
      label: 'North Perimeter',
      min_coverage_pct: 70,
      geometry: {
        type: 'Polygon',
        coordinates: [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
      },
    },
  ],
  exclusion: [],
};

const SIM_RESULTS_EMPTY_LAYERS = {
  total_coverage_pct: 82.5,
  per_zone_coverage_pct: { 'HQ Zone': 74, 'North Perimeter': 78 },
  layers: {},
  sensor_placements: { type: 'FeatureCollection', features: [] },
  stats: { coverage_pct: 82.5 },
};

const SIM_RESULTS_WITH_LAYERS = {
  total_coverage_pct: 82.5,
  per_zone_coverage_pct: { 'HQ Zone': 85, 'North Perimeter': 78 },
  layers: {
    Radar: { type: 'FeatureCollection', features: [
      { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]] }, properties: {} },
    ]},
    gaps: { type: 'FeatureCollection', features: [
      { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2], [0.1, 0.1]]] }, properties: {} },
    ]},
  },
  sensor_placements: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [138.6, -34.9] },
        properties: {
          sensor_name: 'Radar-1',
          sensor_type: 'Radar',
          bearing_deg: 45,
          azimuth_coverage_deg: 120,
        },
      },
    ],
  },
};

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                    'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest reads terrain, sim_results, zones', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const k of ['terrain', 'sim_results', 'zones']) {
    assert.ok(m.reads.includes(k), `reads must include ${k}`);
  }
  assert.ok(!m.reads.includes('placements'), 'reads must not include placements (dead declaration removed)');
});

test('manifest has correct prerequisites', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.prerequisites.includes('terrain'),    'must prerequisite terrain');
  assert.ok(m.prerequisites.includes('sim_results'), 'must prerequisite sim_results');
});

test('manifest subscribes to simulation:complete', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.subscribes.includes('simulation:complete'), 'must subscribe simulation:complete');
});

test('manifest emits placement:pending', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.emits.includes('placement:pending'), 'must emit placement:pending');
});

test('manifest layer_id_prefix is coverage-viewer', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/coverage-viewer/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.equal(m.layer_id_prefix, 'coverage-viewer');
});

// ---------------------------------------------------------------------------
// Panel DOM tests
// ---------------------------------------------------------------------------

test('panel mounts to api.panel', () => {
  const api = makeApi();
  init(api);
  assert.equal(api._mounted.length, 1);
  assert.equal(api._mounted[0]['data-testid'], 'coverage-viewer-panel');
});

test('panel has layer control section with 7 toggle rows', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const section = findByTestId(panel, 'layer-control-section');
  assert.ok(section, 'layer-control-section present');

  const expectedKeys = ['Radar', 'RF', 'EO_IR', 'Acoustic', 'composite', 'gaps', 'effectors'];
  for (const k of expectedKeys) {
    const cb = findByTestId(panel, `toggle-${k}`);
    assert.ok(cb, `toggle-${k} present`);
    assert.ok(cb.checked, `toggle-${k} starts checked`);
  }
});

test('panel has zone compliance toggle', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const zoneCb = findByTestId(panel, 'toggle-zone-compliance');
  assert.ok(zoneCb, 'zone compliance toggle present');
  assert.ok(zoneCb.checked, 'zone compliance toggle starts checked');
});

test('panel has stats section with composite coverage display', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const stats = findByTestId(panel, 'stats-section');
  assert.ok(stats, 'stats-section present');
  const pctEl = findByTestId(panel, 'composite-coverage-pct');
  assert.ok(pctEl, 'composite-coverage-pct present');
});

test('panel has legend section', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const legend = findByTestId(panel, 'legend-section');
  assert.ok(legend, 'legend-section present');
});

// ---------------------------------------------------------------------------
// Map layer setup tests
// ---------------------------------------------------------------------------

test('adds a fill and outline layer for each of 7 display layer types', () => {
  const api = makeApi();
  init(api);
  const expectedKeys = ['Radar', 'RF', 'EO_IR', 'Acoustic', 'composite', 'gaps', 'effectors'];
  for (const k of expectedKeys) {
    assert.ok(api._layers[`coverage-viewer:${k}-fill`],    `${k}-fill layer present`);
    assert.ok(api._layers[`coverage-viewer:${k}-outline`], `${k}-outline layer present`);
  }
});

test('adds bearing-lines layer and zone-compliance-outline layer', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._layers['coverage-viewer:bearing-lines'],          'bearing-lines layer present');
  assert.ok(api._layers['coverage-viewer:zone-compliance-outline'], 'zone-compliance-outline layer present');
});

test('adds GeoJSON source for each display layer', () => {
  const api = makeApi();
  init(api);
  const expectedKeys = ['Radar', 'RF', 'EO_IR', 'Acoustic', 'composite', 'gaps', 'effectors'];
  for (const k of expectedKeys) {
    assert.ok(api._sources[`coverage-viewer:${k}-source`], `${k}-source present`);
  }
  assert.ok(api._sources['coverage-viewer:bearing-lines-source'],   'bearing-lines-source present');
  assert.ok(api._sources['coverage-viewer:zone-compliance-source'], 'zone-compliance-source present');
});

// ---------------------------------------------------------------------------
// Reactive update tests
// ---------------------------------------------------------------------------

test('sim_results state watch triggers layer source update', () => {
  const api = makeApi();
  init(api);

  api._triggerWatch('sim_results', SIM_RESULTS_WITH_LAYERS);

  const radarSrc = api._sources['coverage-viewer:Radar-source'];
  assert.ok(radarSrc, 'Radar source exists');
  assert.ok(radarSrc.data?.features?.length > 0, 'Radar source has features after update');
});

test('gaps layer source gets gap_index injected on rebuild', () => {
  const api = makeApi();
  init(api);

  api._triggerWatch('sim_results', SIM_RESULTS_WITH_LAYERS);

  const gapsSrc = api._sources['coverage-viewer:gaps-source'];
  assert.ok(gapsSrc, 'gaps source exists');
  const features = gapsSrc.data?.features ?? [];
  assert.ok(features.length > 0, 'has gap features');
  assert.equal(features[0].properties.gap_index, 0, 'first gap has gap_index 0');
});

test('bearing-lines source updated with directional sensor lines on rebuild', () => {
  const api = makeApi();
  init(api);

  api._triggerWatch('sim_results', SIM_RESULTS_WITH_LAYERS);

  const blSrc = api._sources['coverage-viewer:bearing-lines-source'];
  assert.ok(blSrc, 'bearing-lines source exists');
  // Sensor has azimuth_coverage_deg=120, so 2 bearing lines should be added
  assert.equal(blSrc.data?.features?.length, 2, 'two bearing extremity lines for one directional sensor');
});

test('stats section shows composite coverage after sim_results update', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('sim_results', SIM_RESULTS_EMPTY_LAYERS);

  const pctEl = findByTestId(panel, 'composite-coverage-pct');
  assert.ok(pctEl.textContent.includes('82.5'), 'coverage pct shows 82.5%');
});

test('stats section shows coverage from stats.coverage_pct fallback format', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('sim_results', {
    stats: { coverage_pct: 77.3 },
    layers: {},
    sensor_placements: { type: 'FeatureCollection', features: [] },
  });

  const pctEl = findByTestId(panel, 'composite-coverage-pct');
  assert.ok(pctEl.textContent.includes('77.3'), 'coverage pct shows 77.3% from stats.coverage_pct');
});

// ---------------------------------------------------------------------------
// S14.9-5: Zone compliance layer test
// ---------------------------------------------------------------------------

test('zone compliance layer shows fail status for zone at 74% vs 80% requirement', () => {
  const simResults = {
    total_coverage_pct: 74,
    per_zone_coverage_pct: { 'HQ Zone': 74 },
    layers: {},
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };

  const zones = {
    priority: [
      {
        label: 'HQ Zone',
        min_coverage_pct: 80,
        geometry: {
          type: 'Polygon',
          coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
      },
    ],
    exclusion: [],
  };

  const api = makeApi({ sim_results: simResults, zones });
  init(api);

  const zcSrc = api._sources['coverage-viewer:zone-compliance-source'];
  assert.ok(zcSrc, 'zone-compliance-source exists');
  const features = zcSrc.data?.features ?? [];
  assert.equal(features.length, 1, 'one zone feature in compliance layer');
  assert.equal(
    features[0].properties.compliance_status,
    'fail',
    'zone at 74% vs 80% requirement has status "fail"',
  );
  assert.equal(features[0].properties.zone_name, 'HQ Zone');
  assert.equal(features[0].properties.required_pct, 80);
  assert.equal(features[0].properties.actual_pct, 74);
});

test('zone compliance layer shows pass status for zone above requirement', () => {
  const simResults = {
    total_coverage_pct: 90,
    per_zone_coverage_pct: { 'HQ Zone': 85 },
    layers: {},
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };
  const zones = {
    priority: [{
      label: 'HQ Zone', min_coverage_pct: 80,
      geometry: { type: 'Polygon', coordinates: [[[0,0],[1,0],[1,1],[0,1],[0,0]]] },
    }],
    exclusion: [],
  };
  const api = makeApi({ sim_results: simResults, zones });
  init(api);

  const features = api._sources['coverage-viewer:zone-compliance-source']?.data?.features ?? [];
  assert.equal(features[0].properties.compliance_status, 'pass');
});

test('zone compliance layer shows marginal status for zone within 5pp of requirement', () => {
  const simResults = {
    total_coverage_pct: 76,
    per_zone_coverage_pct: { 'HQ Zone': 76 },
    layers: {},
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };
  const zones = {
    priority: [{
      label: 'HQ Zone', min_coverage_pct: 80,
      geometry: { type: 'Polygon', coordinates: [[[0,0],[1,0],[1,1],[0,1],[0,0]]] },
    }],
    exclusion: [],
  };
  const api = makeApi({ sim_results: simResults, zones });
  init(api);

  const features = api._sources['coverage-viewer:zone-compliance-source']?.data?.features ?? [];
  assert.equal(features[0].properties.compliance_status, 'marginal');
});

test('zone compliance layer updates when zones state changes', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_EMPTY_LAYERS });
  init(api);

  api._triggerWatch('zones', ZONES);

  const zcSrc = api._sources['coverage-viewer:zone-compliance-source'];
  const features = zcSrc?.data?.features ?? [];
  // HQ Zone at 74% vs 80% → fail
  const hq = features.find(f => f.properties.zone_name === 'HQ Zone');
  assert.ok(hq, 'HQ Zone feature present after zones update');
  assert.equal(hq.properties.compliance_status, 'fail');
});

test('zone compliance table row shows fail icon for failing zone', () => {
  const simResults = {
    total_coverage_pct: 74,
    per_zone_coverage_pct: { 'HQ Zone': 74 },
    layers: {},
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };
  const zones = {
    priority: [{
      label: 'HQ Zone', min_coverage_pct: 80,
      geometry: { type: 'Polygon', coordinates: [[[0,0],[1,0],[1,1],[0,1],[0,0]]] },
    }],
    exclusion: [],
  };
  const api = makeApi({ sim_results: simResults, zones });
  init(api);
  const panel = api._mounted[0];

  const statusCell = findByTestId(panel, 'zone-status-HQ Zone');
  assert.ok(statusCell, 'zone-status cell present');
  assert.equal(statusCell.textContent, '\u2717', 'fail icon shown for failing zone');
});

// ---------------------------------------------------------------------------
// Visibility toggle tests
// ---------------------------------------------------------------------------

test('unchecking a layer toggle calls setLayoutProperty to hide fill and outline', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  const cb = findByTestId(panel, 'toggle-Radar');
  assert.ok(cb, 'Radar toggle exists');
  cb.checked = false;
  cb._fire('change');

  assert.equal(api._layoutProps['coverage-viewer:Radar-fill']?.visibility,    'none');
  assert.equal(api._layoutProps['coverage-viewer:Radar-outline']?.visibility, 'none');
});

test('re-checking a layer toggle restores visibility', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  const cb = findByTestId(panel, 'toggle-composite');
  cb.checked = false;
  cb._fire('change');
  cb.checked = true;
  cb._fire('change');

  assert.equal(api._layoutProps['coverage-viewer:composite-fill']?.visibility, 'visible');
});

test('unchecking zone compliance toggle hides zone-compliance-outline layer', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  const cb = findByTestId(panel, 'toggle-zone-compliance');
  cb.checked = false;
  cb._fire('change');

  assert.equal(
    api._layoutProps['coverage-viewer:zone-compliance-outline']?.visibility,
    'none',
  );
});

// ---------------------------------------------------------------------------
// Gap click / highlight tests (S14.9-4)
// ---------------------------------------------------------------------------

test('clicking gaps-fill layer highlights the clicked gap via setPaintProperty', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  const e = {
    features: [{ properties: { gap_index: 0 } }],
    point: { x: 100, y: 200 },
  };
  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', e);

  const opacityProp = api._paintProps['coverage-viewer:gaps-fill']?.['fill-opacity'];
  assert.ok(opacityProp !== undefined, 'fill-opacity was set after gap click');
  // Should be an expression (array) when a specific gap is highlighted
  assert.ok(Array.isArray(opacityProp), 'fill-opacity set to data expression for highlight');
});

test('clicking general map (no gap) resets gap highlight paint property', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  // First click a gap to select it
  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{ properties: { gap_index: 0 } }],
    point: { x: 50, y: 50 },
  });
  // Then fire general map click to dismiss (no layer ID)
  api._fireMapEvent('click', null, {});

  const opacityProp = api._paintProps['coverage-viewer:gaps-fill']?.['fill-opacity'];
  // After dismissal, opacity should be a plain number (default), not an expression
  assert.ok(!Array.isArray(opacityProp), 'fill-opacity reset to default number after dismiss');
});

test('gap click with suggestion emits placement:pending', () => {
  const simResults = {
    total_coverage_pct: 50,
    layers: {
      gaps: {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: { type: 'Polygon', coordinates: [[[0,0],[1,0],[1,1],[0,1],[0,0]]] },
          properties: {
            gap_index: 0,
            suggestion: { lat: 0.5, lng: 0.5, definition: { type: 'Radar', name: 'R-1' } },
          },
        }],
      },
    },
    sensor_placements: { type: 'FeatureCollection', features: [] },
  };
  const api = makeApi({ sim_results: simResults });
  init(api);

  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{
      properties: {
        gap_index: 0,
        suggestion: { lat: 0.5, lng: 0.5, definition: { type: 'Radar', name: 'R-1' } },
      },
    }],
    point: { x: 10, y: 10 },
  });

  const pendingEvt = api._emitted.find(e => e.event === 'placement:pending');
  assert.ok(pendingEvt, 'placement:pending emitted on gap click with suggestion');
  assert.equal(pendingEvt.data.lat, 0.5);
  assert.equal(pendingEvt.data.lng, 0.5);
});

test('gap click without suggestion does not emit placement:pending', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{ properties: { gap_index: 0 } }],
    point: { x: 10, y: 10 },
  });

  const pendingEvt = api._emitted.find(e => e.event === 'placement:pending');
  assert.ok(!pendingEvt, 'placement:pending NOT emitted when no suggestion');
});

// ---------------------------------------------------------------------------
// S14.9-4: Inspect popup DOM content tests
// ---------------------------------------------------------------------------

test('gap click creates inspect popup div in map container', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  let capturedPopup = null;
  const origGetCanvas = api.map.getCanvas;
  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = origGetCanvas.call(api.map);
    c.parentElement = container;
    return c;
  };

  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{ properties: { gap_index: 0, area_m2: 5000, coverage_pct: 12.5 } }],
    point: { x: 50, y: 80 },
  });

  const popup = findByTestId(container, 'gap-inspect-popup');
  assert.ok(popup, 'gap-inspect-popup created in map container on gap click');
});

test('inspect popup contains gap area and coverage pct from feature properties', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = makeMockElement('canvas');
    c.parentElement = container;
    return c;
  };

  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{
      properties: {
        gap_index: 2,
        area_m2: 8500,
        coverage_pct: 22.0,
        covered_by: 'Radar',
        missing_types: 'RF, EO_IR',
      },
    }],
    point: { x: 60, y: 70 },
  });

  const popup = findByTestId(container, 'gap-inspect-popup');
  assert.ok(popup, 'popup present');

  // Gap title should reference gap index
  const allText = findAll(popup, el => el.textContent !== '').map(el => el.textContent).join(' ');
  assert.ok(allText.includes('2'), 'popup references gap index 2');

  // Area rendered
  const areaRows = findAll(popup, el => el.textContent?.includes('8,500') || el.textContent?.includes('8500'));
  assert.ok(areaRows.length > 0, 'popup contains gap area value');
});

test('second gap click replaces previous inspect popup', () => {
  const api = makeApi({ sim_results: SIM_RESULTS_WITH_LAYERS });
  init(api);

  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = makeMockElement('canvas');
    c.parentElement = container;
    return c;
  };

  // First gap click
  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{ properties: { gap_index: 0 } }],
    point: { x: 10, y: 10 },
  });
  assert.equal(
    findAll(container, el => el['data-testid'] === 'gap-inspect-popup').length, 1,
    'one popup after first click',
  );

  // Second gap click
  api._fireMapEvent('click', 'coverage-viewer:gaps-fill', {
    features: [{ properties: { gap_index: 1 } }],
    point: { x: 20, y: 20 },
  });
  assert.equal(
    findAll(container, el => el['data-testid'] === 'gap-inspect-popup').length, 1,
    'still only one popup after second click (previous removed)',
  );
});

// ---------------------------------------------------------------------------
// S14.9-5: Zone hover tooltip DOM tests
// ---------------------------------------------------------------------------

test('mouseenter on zone-compliance-outline creates tooltip in map container', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_EMPTY_LAYERS,
    zones: ZONES,
  });
  init(api);

  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = makeMockElement('canvas');
    c.parentElement = container;
    return c;
  };

  api._fireMapEvent('mouseenter', 'coverage-viewer:zone-compliance-outline', {
    features: [{
      properties: {
        zone_name: 'HQ Zone',
        required_pct: 80,
        actual_pct: 74,
        compliance_status: 'fail',
      },
    }],
    point: { x: 200, y: 150 },
  });

  const tooltip = findByTestId(container, 'zone-compliance-tooltip');
  assert.ok(tooltip, 'zone-compliance-tooltip created on mouseenter');
});

test('zone tooltip displays zone name, required pct, actual pct, and status', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_EMPTY_LAYERS,
    zones: ZONES,
  });
  init(api);

  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = makeMockElement('canvas');
    c.parentElement = container;
    return c;
  };

  api._fireMapEvent('mouseenter', 'coverage-viewer:zone-compliance-outline', {
    features: [{
      properties: {
        zone_name: 'HQ Zone',
        required_pct: 80,
        actual_pct: 74,
        compliance_status: 'fail',
      },
    }],
    point: { x: 100, y: 120 },
  });

  const tooltip   = findByTestId(container, 'zone-compliance-tooltip');
  const nameEl    = findByTestId(tooltip,   'zone-tip-name');
  const statusEl  = findByTestId(tooltip,   'zone-tip-status');

  assert.ok(nameEl,   'zone-tip-name present');
  assert.equal(nameEl.textContent, 'HQ Zone', 'tooltip shows zone name');

  assert.ok(statusEl, 'zone-tip-status present');
  assert.ok(
    statusEl.textContent.toLowerCase().includes('fail'),
    'tooltip shows fail status',
  );

  // Required and actual pcts should appear somewhere in the tooltip
  const allText = findAll(tooltip, el => el.textContent !== '')
    .map(el => el.textContent).join(' ');
  assert.ok(allText.includes('80'), 'tooltip shows required pct 80');
  assert.ok(allText.includes('74'), 'tooltip shows actual pct 74');
});

test('mouseleave on zone-compliance-outline removes tooltip', () => {
  const api = makeApi({
    sim_results: SIM_RESULTS_EMPTY_LAYERS,
    zones: ZONES,
  });
  init(api);

  const container = makeMockElement('div');
  api.map.getCanvas = () => {
    const c = makeMockElement('canvas');
    c.parentElement = container;
    return c;
  };

  // Show tooltip
  api._fireMapEvent('mouseenter', 'coverage-viewer:zone-compliance-outline', {
    features: [{ properties: { zone_name: 'HQ Zone', required_pct: 80, actual_pct: 74, compliance_status: 'fail' } }],
    point: { x: 50, y: 60 },
  });
  assert.ok(findByTestId(container, 'zone-compliance-tooltip'), 'tooltip shown');

  // Hide tooltip
  api._fireMapEvent('mouseleave', 'coverage-viewer:zone-compliance-outline', {});
  assert.ok(!findByTestId(container, 'zone-compliance-tooltip'), 'tooltip removed on mouseleave');
});

// ---------------------------------------------------------------------------
// Bus subscription tests
// ---------------------------------------------------------------------------

test('subscribes to simulation:complete bus event', () => {
  const api = makeApi();
  init(api);
  assert.ok(api._busListeners['simulation:complete']?.length > 0,
    'simulation:complete listener registered');
});

// ---------------------------------------------------------------------------
// Cleanup tests
// ---------------------------------------------------------------------------

test('onUnmount removes all layers and sources', () => {
  const api = makeApi();
  init(api);

  // Verify layers exist
  assert.ok(api._layers['coverage-viewer:Radar-fill'], 'Radar-fill exists before unmount');

  api._runUnmount();

  // All coverage layers should be removed
  const expectedKeys = ['Radar', 'RF', 'EO_IR', 'Acoustic', 'composite', 'gaps', 'effectors'];
  for (const k of expectedKeys) {
    assert.ok(!api._layers[`coverage-viewer:${k}-fill`],    `${k}-fill removed on unmount`);
    assert.ok(!api._layers[`coverage-viewer:${k}-outline`], `${k}-outline removed on unmount`);
    assert.ok(!api._sources[`coverage-viewer:${k}-source`], `${k}-source removed on unmount`);
  }
  assert.ok(!api._layers['coverage-viewer:bearing-lines'],           'bearing-lines removed');
  assert.ok(!api._sources['coverage-viewer:bearing-lines-source'],   'bearing-lines-source removed');
  assert.ok(!api._layers['coverage-viewer:zone-compliance-outline'],  'zone-compliance-outline removed');
  assert.ok(!api._sources['coverage-viewer:zone-compliance-source'], 'zone-compliance-source removed');
});

test('onUnmount unsubscribes all state watches and bus listeners', () => {
  const api = makeApi();
  init(api);

  assert.ok(api._stateWatchers['sim_results']?.length > 0, 'sim_results watcher registered');
  assert.ok(api._stateWatchers['zones']?.length > 0,       'zones watcher registered');

  api._runUnmount();

  assert.equal(api._stateWatchers['sim_results']?.length ?? 0, 0, 'sim_results watcher cleaned');
  assert.equal(api._stateWatchers['zones']?.length ?? 0,       0, 'zones watcher cleaned');
  assert.equal(api._busListeners['simulation:complete']?.length ?? 0, 0,
    'simulation:complete listener cleaned');
});
