/**
 * test-report-configurator.js — Unit tests for the Report Configurator module (S14.13).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-report-configurator.js
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
      color: '', flex: '', scrollTop: 0, scrollHeight: 0, src: '',
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
    src: '',
    files: null,
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
// Mock globals
// ---------------------------------------------------------------------------

let _lastCreatedAnchor = null;

globalThis.document = {
  createElement: (tag) => {
    const el = makeMockElement(tag);
    if (tag === 'a') _lastCreatedAnchor = el;
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

let _lastFetchUrl = null;
let _lastFetchOptions = null;
let _mockFetchResponse = null;

globalThis.fetch = async (url, opts) => {
  _lastFetchUrl = url;
  _lastFetchOptions = opts;
  if (_mockFetchResponse) return _mockFetchResponse;
  return { ok: false, status: 500, json: async () => ({}), blob: async () => ({}) };
};

let _createObjectUrlArg = null;
let _revokeObjectUrlArg = null;

globalThis.URL = {
  createObjectURL: (blob) => { _createObjectUrlArg = blob; return 'blob:mock://report-test'; },
  revokeObjectURL: (url)  => { _revokeObjectUrlArg = url; },
};

// ---------------------------------------------------------------------------
// Dynamic import AFTER globalThis.document is set
// ---------------------------------------------------------------------------

const { init } = await import('../modules/report-configurator/index.js');

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

function makeApi({
  sim_results      = { stats: { coverage_pct: 80 } },
  placements       = null,
  zones            = null,
  threat_corridors = null,
  report_config    = null,
} = {}) {
  const mounted      = [];
  const unmountCbs   = [];
  const emitted      = [];
  const busListeners = {};
  const stateWatchers = {};
  const stateData = { sim_results, placements, zones, threat_corridors, report_config };

  const api = {
    _mounted:        mounted,
    _unmountCbs:     unmountCbs,
    _emitted:        emitted,
    _busListeners:   busListeners,
    _stateWatchers:  stateWatchers,
    _stateData:      stateData,

    _runUnmount() {
      const cbs = [...unmountCbs];
      unmountCbs.length = 0;
      for (const cb of cbs) cb();
    },
    _triggerWatch(key, value) {
      stateData[key] = value;
      for (const cb of (stateWatchers[key] ?? [])) cb(value);
    },

    moduleId: 'report-configurator',

    state: {
      get(key)           { return stateData[key] ?? null; },
      set(key, val)      {
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
      addSource()   {},
      removeSource(){},
      getSource()   { return null; },
      addLayer()    {},
      removeLayer() {},
      getLayer()    { return null; },
      getCanvas()   {
        const canvas = makeMockElement('canvas');
        canvas.toDataURL = (_type) => 'data:image/png;base64,mockdata==';
        return canvas;
      },
      on()  {},
      off() {},
    },

    panel: {
      mount(el)      { mounted.push(el); },
      onUnmount(cb)  { unmountCbs.push(cb); },
    },
  };
  return api;
}

// ---------------------------------------------------------------------------
// Manifest tests
// ---------------------------------------------------------------------------

test('manifest has all required fields', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const f of ['id', 'label', 'reads', 'writes', 'prerequisites',
                   'emits', 'subscribes', 'layer_id_prefix', 'description']) {
    assert.ok(Object.prototype.hasOwnProperty.call(m, f), `missing field: ${f}`);
  }
});

test('manifest reads include sim_results, placements, zones, threat_corridors, report_config', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  for (const k of ['sim_results', 'placements', 'zones', 'threat_corridors', 'report_config']) {
    assert.ok(m.reads.includes(k), `reads must include ${k}`);
  }
});

test('manifest writes only report_config', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.writes, ['report_config']);
});

test('manifest prerequisites is ["sim_results"]', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.deepEqual(m.prerequisites, ['sim_results']);
});

test('manifest emits report:generated', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
  );
  const m = JSON.parse(raw);
  assert.ok(m.emits.includes('report:generated'), 'emits must include report:generated');
});

test('manifest subscribes is empty', async () => {
  const raw = await readFile(
    path.resolve(__dirname, '../modules/report-configurator/manifest.json'), 'utf8'
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

test('init registers watch on sim_results, placements, zones, threat_corridors, report_config', () => {
  const api = makeApi();
  init(api);
  for (const key of ['sim_results', 'placements', 'zones', 'threat_corridors', 'report_config']) {
    assert.ok(
      (api._stateWatchers[key] ?? []).length > 0,
      `must register watch on ${key}`
    );
  }
});

test('init does not subscribe to any bus events', () => {
  const api = makeApi();
  init(api);
  assert.equal(Object.keys(api._busListeners).length, 0);
});

test('panel contains client-name-input', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  assert.ok(findByTestId(panel, 'client-name-input'), 'client-name-input must be present');
});

test('panel contains logo-input with file type and image/* accept', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const input = findByTestId(panel, 'logo-input');
  assert.ok(input, 'logo-input must be present');
  assert.equal(input.type, 'file');
  assert.equal(input.accept, 'image/*');
});

test('panel contains sanitisation-select with four options', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  assert.ok(sel, 'sanitisation-select must be present');
  const opts = sel._children.filter(c => c._tag === 'option');
  assert.equal(opts.length, 4);
  const values = opts.map(o => o.value);
  for (const v of ['none', 'minimal', 'redacted', 'full']) {
    assert.ok(values.includes(v), `option ${v} must be present`);
  }
});

test('panel contains a checkbox for each of the 11 report sections', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  for (const section of [
    'executive_summary', 'site_overview', 'coverage_analysis', 'gap_analysis',
    'threat_analysis', 'kill_chain', 'saturation', 'comparison',
    'recommendations', 'assumptions', 'appendix',
  ]) {
    const cb = findByTestId(panel, `section-${section}`);
    assert.ok(cb, `checkbox section-${section} must be present`);
    assert.equal(cb.type, 'checkbox');
  }
});

test('panel contains capture-btn and generate-btn', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  assert.ok(findByTestId(panel, 'capture-btn'), 'capture-btn must be present');
  assert.ok(findByTestId(panel, 'generate-btn'), 'generate-btn must be present');
});

test('spinner is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'generate-spinner').style.display, 'none');
});

test('generate-status is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'generate-status').style.display, 'none');
});

// ---------------------------------------------------------------------------
// Sanitisation preview tests (S14.13-3 — core spec requirement)
// ---------------------------------------------------------------------------

test('sanitisation preview is hidden initially when level is none', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const preview = findByTestId(panel, 'sanitisation-preview');
  assert.ok(preview, 'sanitisation-preview element must exist');
  assert.equal(preview.style.display, 'none');
});

test('sanitisation preview shows when level set to Redacted', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'redacted';
  sel._fire('change');
  const preview = findByTestId(panel, 'sanitisation-preview');
  assert.equal(preview.style.display, 'block');
});

test('sanitisation preview shows rounded coordinates row when Redacted', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'redacted';
  sel._fire('change');

  const table = findByTestId(panel, 'preview-table');
  // Find all td textContent values from rows
  const allText = [];
  function collectText(el) {
    if (el._tag === 'td') allText.push(el.textContent);
    for (const child of (el._children ?? [])) collectText(child);
  }
  collectText(table);

  // Should include position_lat row
  assert.ok(allText.includes('position_lat'), 'preview must include position_lat field');
  assert.ok(allText.includes('51.2345'), 'preview must show original coordinate value');
  assert.ok(allText.includes('51.23'), 'preview must show rounded coordinate value');
});

test('sanitisation preview shows range band row when Redacted', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'redacted';
  sel._fire('change');

  const table = findByTestId(panel, 'preview-table');
  const allText = [];
  function collectText(el) {
    if (el._tag === 'td') allText.push(el.textContent);
    for (const child of (el._children ?? [])) collectText(child);
  }
  collectText(table);

  assert.ok(allText.includes('max_range_m'), 'preview must include max_range_m field');
  assert.ok(allText.some(t => t.includes('Long range')), "preview must show range band 'Long range'");
});

test('sanitisation preview shows path_wgs84 and available_time_s removed when Full', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'full';
  sel._fire('change');

  const table = findByTestId(panel, 'preview-table');
  const allText = [];
  function collectText(el) {
    if (el._tag === 'td') allText.push(el.textContent);
    for (const child of (el._children ?? [])) collectText(child);
  }
  collectText(table);

  assert.ok(allText.includes('path_wgs84'), 'full preview must include path_wgs84 field');
  assert.ok(allText.includes('available_time_s'), 'full preview must include available_time_s field');
});

test('sanitisation preview hides when level switched back to None', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');

  sel.value = 'redacted';
  sel._fire('change');
  assert.equal(findByTestId(panel, 'sanitisation-preview').style.display, 'block');

  sel.value = 'none';
  sel._fire('change');
  assert.equal(findByTestId(panel, 'sanitisation-preview').style.display, 'none');
});

test('sanitisation preview hides for Minimal level', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'minimal';
  sel._fire('change');
  assert.equal(findByTestId(panel, 'sanitisation-preview').style.display, 'none');
});

// ---------------------------------------------------------------------------
// Form → state tests
// ---------------------------------------------------------------------------

test('typing client name writes report_config to state', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const input = findByTestId(panel, 'client-name-input');
  input.value = 'ACME Defence';
  input._fire('input');
  const config = api._stateData.report_config;
  assert.ok(config, 'report_config must be written to state');
  assert.equal(config.client_name, 'ACME Defence');
});

test('changing sanitisation level writes sanitise_level to report_config state', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  sel.value = 'redacted';
  sel._fire('change');
  assert.equal(api._stateData.report_config.sanitise_level, 'redacted');
});

test('toggling a section checkbox writes include_modules to report_config state', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const cb = findByTestId(panel, 'section-kill_chain');
  cb.checked = false;
  cb._fire('change');
  const config = api._stateData.report_config;
  assert.equal(config.include_modules['Kill Chain'], false);
});

test('report_config state includes all 11 section keys in include_modules', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  // Trigger a config write
  findByTestId(panel, 'client-name-input')._fire('input');
  const include_modules = api._stateData.report_config.include_modules;
  for (const s of [
    'Executive Summary', 'Site Overview', 'Coverage Analysis', 'Gap Analysis',
    'Threat Analysis', 'Kill Chain', 'Saturation', 'Comparison',
    'Recommendations', 'Assumptions', 'Appendix',
  ]) {
    assert.ok(Object.prototype.hasOwnProperty.call(include_modules, s), `include_modules must contain '${s}'`);
  }
});

// ---------------------------------------------------------------------------
// State persistence tests (S14.13-3 — "reload" scenario)
// ---------------------------------------------------------------------------

test('client name is populated from report_config state on mount', () => {
  const savedConfig = {
    client_name: 'Preserved Corp',
    sanitisation_level: 'none',
    sections: {},
    logo: null,
  };
  const api = makeApi({ report_config: savedConfig });
  init(api);
  const panel = api._mounted[0];
  const input = findByTestId(panel, 'client-name-input');
  assert.equal(input.value, 'Preserved Corp');
});

test('sanitisation level is restored from report_config state on mount', () => {
  const savedConfig = {
    client_name: '',
    sanitisation_level: 'redacted',
    sections: {},
    logo: null,
  };
  const api = makeApi({ report_config: savedConfig });
  init(api);
  const panel = api._mounted[0];
  const sel = findByTestId(panel, 'sanitisation-select');
  assert.equal(sel.value, 'redacted');
  // Preview should be visible because level is Redacted
  assert.equal(findByTestId(panel, 'sanitisation-preview').style.display, 'block');
});

test('section checkboxes are restored from report_config state on mount', () => {
  const savedConfig = {
    client_name: '',
    sanitisation_level: 'none',
    sections: { 'Kill Chain': false, 'Saturation': false },
    logo: null,
  };
  const api = makeApi({ report_config: savedConfig });
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'section-kill_chain').checked, false);
  assert.equal(findByTestId(panel, 'section-saturation').checked, false);
  // Untouched sections remain true
  assert.equal(findByTestId(panel, 'section-appendix').checked, true);
});

test('watch report_config updates form when state changes externally', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  api._triggerWatch('report_config', {
    client_name: 'External Update',
    sanitisation_level: 'full',
    sections: {},
    logo: null,
  });

  const input = findByTestId(panel, 'client-name-input');
  assert.equal(input.value, 'External Update');
  const sel = findByTestId(panel, 'sanitisation-select');
  assert.equal(sel.value, 'full');
});

// ---------------------------------------------------------------------------
// Map capture tests
// ---------------------------------------------------------------------------

test('capture-btn click stores map canvas data URL', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'capture-btn')._fire('click');
  // After capture, thumbnail-wrap should be visible
  const wrap = findByTestId(panel, 'thumbnail-wrap');
  assert.equal(wrap.style.display, 'block');
});

test('capture-btn sets thumbnail src to data URL', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'capture-btn')._fire('click');
  const thumbnail = findByTestId(panel, 'map-thumbnail');
  assert.ok(thumbnail.src.startsWith('data:image/png'), 'thumbnail src must be a PNG data URL');
});

test('thumbnail-wrap is hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  assert.equal(findByTestId(panel, 'thumbnail-wrap').style.display, 'none');
});

// ---------------------------------------------------------------------------
// Report generation tests
// ---------------------------------------------------------------------------

test('generate-btn POSTs to /api/report', async () => {
  _lastFetchUrl = null;
  _mockFetchResponse = {
    ok: true, status: 200,
    blob: async () => ({}),
  };

  const api = makeApi();
  init(api);
  findByTestId(api._mounted[0], 'generate-btn')._fire('click');
  await tick();

  assert.equal(_lastFetchUrl, '/api/report');
  assert.equal(_lastFetchOptions.method, 'POST');
});

test('generate-btn POST body contains report_config, sim_results, placements, zones, threat_corridors, map_screenshot', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const simResults = { stats: { coverage_pct: 78 } };
  const api = makeApi({ sim_results: simResults });
  init(api);
  findByTestId(api._mounted[0], 'generate-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.ok('report_config'    in body, 'body must contain report_config');
  assert.ok('sim_results'      in body, 'body must contain sim_results');
  assert.ok('placements'       in body, 'body must contain placements');
  assert.ok('zones'            in body, 'body must contain zones');
  assert.ok('threat_corridors' in body, 'body must contain threat_corridors');
  assert.ok('map_screenshot'   in body, 'body must contain map_screenshot');
});

test('generate-btn POST body includes captured map view when available', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'capture-btn')._fire('click');    // capture first
  findByTestId(panel, 'generate-btn')._fire('click');   // then generate
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.ok(body.map_screenshot, 'map_screenshot must be populated after capture');
  assert.ok(body.map_screenshot.startsWith('data:image/png'), 'map_screenshot must be a PNG data URL');
});

test('generate emits report:generated with filename on success', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  findByTestId(api._mounted[0], 'generate-btn')._fire('click');
  await tick();

  const ev = api._emitted.find(e => e.event === 'report:generated');
  assert.ok(ev, 'must emit report:generated');
  assert.ok(ev.data.filename.startsWith('salus-report-'), 'filename must start with salus-report-');
  assert.ok(ev.data.filename.endsWith('.pdf'), 'filename must end with .pdf');
});

test('generate triggers blob download — anchor href set to object URL', async () => {
  _lastCreatedAnchor = null;
  _createObjectUrlArg = null;
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({ type: 'application/pdf' }) };

  const api = makeApi();
  init(api);
  findByTestId(api._mounted[0], 'generate-btn')._fire('click');
  await tick();

  assert.ok(_lastCreatedAnchor, 'an anchor element must have been created');
  assert.equal(_lastCreatedAnchor.href, 'blob:mock://report-test');
  assert.ok(_lastCreatedAnchor.download.startsWith('salus-report-'), 'download attr must start with salus-report-');
  assert.ok(_lastCreatedAnchor._clicked, 'anchor must have been clicked');
});

test('generate shows spinner while in flight', async () => {
  let resolveBlob;
  _mockFetchResponse = {
    ok: true, status: 200,
    blob: () => new Promise(resolve => { resolveBlob = resolve; }),
  };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'generate-spinner').style.display, 'block');

  // Resolve to unblock
  resolveBlob({});
  await tick();
});

test('generate shows error status on HTTP failure', async () => {
  _mockFetchResponse = { ok: false, status: 503, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  const status = findByTestId(panel, 'generate-status');
  assert.equal(status.style.display, 'block');
  assert.ok(status.textContent.includes('503'), 'error must mention HTTP status');
  assert.equal(status.style.color, '#f87171');
});

test('generate button is re-enabled after success', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'generate-btn').disabled, false);
});

test('generate button is re-enabled after failure', async () => {
  _mockFetchResponse = { ok: false, status: 503, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  assert.equal(findByTestId(panel, 'generate-btn').disabled, false);
});

// ---------------------------------------------------------------------------
// Local state mirrors — watch() updates
// ---------------------------------------------------------------------------

test('watch sim_results updates local mirror used in POST body', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const api = makeApi({ sim_results: { stats: { coverage_pct: 50 } } });
  init(api);
  const panel = api._mounted[0];

  const newSim = { stats: { coverage_pct: 95 } };
  api._triggerWatch('sim_results', newSim);

  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.deepEqual(body.sim_results, newSim);
});

test('watch placements updates local mirror used in POST body', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({}) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  const placements = [{ sensor_name: 'Radar-1' }];
  api._triggerWatch('placements', placements);

  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.deepEqual(body.placements, placements);
});

// ---------------------------------------------------------------------------
// Cleanup — onUnmount
// ---------------------------------------------------------------------------

test('onUnmount unsubscribes all state watchers', () => {
  const api = makeApi();
  init(api);

  for (const key of ['sim_results', 'placements', 'zones', 'threat_corridors', 'report_config']) {
    assert.ok((api._stateWatchers[key] ?? []).length > 0, `${key} watcher must be registered`);
  }

  api._runUnmount();

  for (const key of ['sim_results', 'placements', 'zones', 'threat_corridors', 'report_config']) {
    assert.equal((api._stateWatchers[key] ?? []).length, 0, `${key} watcher must be removed`);
  }
});

test('onUnmount can be called multiple times safely', () => {
  const api = makeApi();
  init(api);
  assert.doesNotThrow(() => {
    api._runUnmount();
    api._runUnmount();
  });
});

// ---------------------------------------------------------------------------
// D-376: Logo file read via FileReader
// ---------------------------------------------------------------------------

test('logo file change stores data URL in report_config.logo via FileReader', () => {
  let fileReaderInstance = null;
  globalThis.FileReader = class {
    readAsDataURL(_file) { fileReaderInstance = this; }
  };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const logoEl = findByTestId(panel, 'logo-input');
  logoEl.files = [{ name: 'logo.png', size: 1234 }];
  logoEl._fire('change');

  assert.ok(fileReaderInstance, 'FileReader must have been instantiated');
  fileReaderInstance.onload({ target: { result: 'data:image/png;base64,abc123' } });

  const config = api._stateData.report_config;
  assert.ok(config, 'report_config must be written to state after FileReader.onload');
  assert.equal(config.logo_path, 'data:image/png;base64,abc123', 'logo_path data URL must be written to state');

  delete globalThis.FileReader;
});

test('logo file change stores null when FileReader unavailable', () => {
  const orig = globalThis.FileReader;
  delete globalThis.FileReader;

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const logoEl = findByTestId(panel, 'logo-input');
  logoEl.files = [{ name: 'logo.png' }];
  logoEl._fire('change');

  const config = api._stateData.report_config;
  assert.ok(config, 'report_config must still be written to state');
  assert.equal(config.logo_path, null, 'logo_path must be null when FileReader is unavailable');

  if (orig) globalThis.FileReader = orig;
});

// ---------------------------------------------------------------------------
// D-377: Capture failure surfaced in UI
// ---------------------------------------------------------------------------

test('capture-status element is present and hidden initially', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  const captureStatus = findByTestId(panel, 'capture-status');
  assert.ok(captureStatus, 'capture-status must be present');
  assert.equal(captureStatus.style.display, 'none');
});

test('capture failure shows capture-status message', () => {
  const api = makeApi();
  api.map.getCanvas = () => { throw new Error('Canvas not available'); };
  init(api);
  const panel = api._mounted[0];

  findByTestId(panel, 'capture-btn')._fire('click');

  const captureStatus = findByTestId(panel, 'capture-status');
  assert.equal(captureStatus.style.display, 'block', 'capture-status must be visible on failure');
  assert.ok(
    captureStatus.textContent.toLowerCase().includes('capture') ||
    captureStatus.textContent.toLowerCase().includes('failed'),
    'capture-status must describe the failure'
  );
});

test('capture-status is hidden after a successful capture', () => {
  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  // First cause a failure to make status visible
  const origGetCanvas = api.map.getCanvas;
  api.map.getCanvas = () => { throw new Error('fail'); };
  findByTestId(panel, 'capture-btn')._fire('click');
  assert.equal(findByTestId(panel, 'capture-status').style.display, 'block');

  // Now restore and succeed
  api.map.getCanvas = origGetCanvas;
  findByTestId(panel, 'capture-btn')._fire('click');
  assert.equal(findByTestId(panel, 'capture-status').style.display, 'none');
});

// ---------------------------------------------------------------------------
// D-378: Zero-byte blob shows error rather than silent corrupt download
// ---------------------------------------------------------------------------

test('zero-byte blob response shows error status and does not emit report:generated', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({ size: 0 }) };
  _lastCreatedAnchor = null;

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];
  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  const status = findByTestId(panel, 'generate-status');
  assert.equal(status.style.display, 'block', 'error status must be shown for zero-byte blob');
  assert.equal(status.style.color, '#f87171', 'error must be red');

  const ev = api._emitted.find(e => e.event === 'report:generated');
  assert.ok(!ev, 'must not emit report:generated for zero-byte response');
});

// ---------------------------------------------------------------------------
// D-379: POST body uses latestReportConfig mirror, not api.state.get()
// ---------------------------------------------------------------------------

test('POST body uses report_config from watch mirror after external state update', async () => {
  _mockFetchResponse = { ok: true, status: 200, blob: async () => ({ size: 1024 }) };

  const api = makeApi();
  init(api);
  const panel = api._mounted[0];

  const externalConfig = {
    client_name: 'External Corp',
    sanitisation_level: 'redacted',
    sections: {},
    logo: null,
  };
  api._triggerWatch('report_config', externalConfig);

  findByTestId(panel, 'generate-btn')._fire('click');
  await tick();

  const body = JSON.parse(_lastFetchOptions.body);
  assert.deepEqual(body.report_config, externalConfig, 'POST must use the latest report_config from watch cache');
});
