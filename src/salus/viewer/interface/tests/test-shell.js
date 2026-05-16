/**
 * test-shell.js — Unit tests for shell startup, library pre-load, and
 * scenario save/load (S14.14-1, S14.14-2, S14.14-3).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-shell.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  fetchLibraries,
  initialMapStyle,
  saveScenario,
  validateScenarioPayload,
  applyScenarioPayload,
  hasActivePlacements,
  mountShellNavButtons,
} from '../shell.js';
import { createState } from '../state.js';
import { createBus } from '../bus.js';
import { VALID_STATE_KEYS } from '../state-schema.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal state store with no module contracts (shell bypass only). */
function makeState() {
  return createState(new Map());
}

/** Build a minimal bus with no event contracts. */
function makeBus() {
  return createBus(new Map());
}

/**
 * Stub globalThis.fetch for the duration of fn(), then restore.
 * `responses` is a Map<url, {ok, status, body}>.
 */
async function withFetch(responses, fn) {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const r = responses.get(url) ?? { ok: false, status: 404 };
    return {
      ok: r.ok,
      status: r.status,
      json: async () => r.body,
    };
  };
  try {
    return await fn();
  } finally {
    globalThis.fetch = original;
  }
}

/** Minimal DOM stub for tests that exercise nav button mounting. */
function makeDomStub(opts = {}) {
  const elements = new Map(Object.entries(opts));
  const appended = [];
  return {
    getElementById: (id) => elements.get(id) ?? null,
    createElement: (tag) => ({
      tag,
      className: '',
      textContent: '',
      title: '',
      href: '',
      download: '',
      style: {},
      _listeners: {},
      _children: [],
      appendChild: function(c) { this._children.push(c); },
      addEventListener: function(ev, cb) { this._listeners[ev] = cb; },
      click: function() { (this._listeners['click'] ?? (() => {}))(); },
    }),
    body: {
      appendChild: (el) => appended.push(el),
      removeChild: () => {},
    },
    _appended: appended,
  };
}

// ---------------------------------------------------------------------------
// S14.14-1: Library pre-load
// ---------------------------------------------------------------------------

test('fetchLibraries(): returns sensor and effector libraries from API', async () => {
  const sensors = { radar: [{ name: 'Test Radar' }] };
  const effectors = { jammer: [{ name: 'Test Jammer' }] };

  const responses = new Map([
    ['/api/sensors', { ok: true, status: 200, body: sensors }],
    ['/api/effectors', { ok: true, status: 200, body: effectors }],
  ]);

  const { sensorLib, effectorLib } = await withFetch(responses, fetchLibraries);

  assert.deepEqual(sensorLib, sensors);
  assert.deepEqual(effectorLib, effectors);
});

test('fetchLibraries(): falls back to SALUS_DATA when API returns 404', async () => {
  const original = globalThis.SALUS_DATA;
  globalThis.SALUS_DATA = {
    sensor_library: { rf: [{ name: 'RfOne' }] },
    effector_library: { jammer: [{ name: 'DroneCannon' }] },
  };

  const responses = new Map([
    ['/api/sensors', { ok: false, status: 404 }],
    ['/api/effectors', { ok: false, status: 404 }],
  ]);

  try {
    const { sensorLib, effectorLib } = await withFetch(responses, fetchLibraries);
    assert.deepEqual(sensorLib, globalThis.SALUS_DATA.sensor_library);
    assert.deepEqual(effectorLib, globalThis.SALUS_DATA.effector_library);
  } finally {
    globalThis.SALUS_DATA = original;
  }
});

test('fetchLibraries(): falls back to {} when API fails and no SALUS_DATA', async () => {
  const originalFetch = globalThis.fetch;
  const originalData = globalThis.SALUS_DATA;
  delete globalThis.SALUS_DATA;

  globalThis.fetch = async () => { throw new Error('network error'); };

  try {
    const { sensorLib, effectorLib } = await fetchLibraries();
    assert.deepEqual(sensorLib, {});
    assert.deepEqual(effectorLib, {});
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.SALUS_DATA = originalData;
  }
});

test('fetchLibraries(): state is populated before any module init would run', async () => {
  // This test verifies that the return values are available to write to state
  // immediately — they must not require any async wait after being returned.
  const sensors = { radar: [{ name: 'Radar A' }] };
  const effectors = {};

  const responses = new Map([
    ['/api/sensors', { ok: true, status: 200, body: sensors }],
    ['/api/effectors', { ok: true, status: 200, body: effectors }],
  ]);

  const { sensorLib, effectorLib } = await withFetch(responses, fetchLibraries);

  // Simulate what shell.js does: write to state immediately after fetch
  const state = makeState();
  state.setState('sensor_library', sensorLib);
  state.setState('effector_library', effectorLib);

  // Both must be populated synchronously (no watchers needed)
  assert.deepEqual(state.getState('sensor_library'), sensors);
  assert.deepEqual(state.getState('effector_library'), effectors);
});

test('fetchLibraries(): SALUS_DATA sensor_library only — effector falls back to {}', async () => {
  const originalData = globalThis.SALUS_DATA;
  globalThis.SALUS_DATA = { sensor_library: { radar: [] } };

  const responses = new Map([
    ['/api/sensors', { ok: false, status: 503 }],
    ['/api/effectors', { ok: false, status: 503 }],
  ]);

  try {
    const { sensorLib, effectorLib } = await withFetch(responses, fetchLibraries);
    assert.deepEqual(sensorLib, { radar: [] });
    assert.deepEqual(effectorLib, {});
  } finally {
    globalThis.SALUS_DATA = originalData;
  }
});

// ---------------------------------------------------------------------------
// S14.14-2: Scenario save/load — validateScenarioPayload
// ---------------------------------------------------------------------------

test('validateScenarioPayload(): accepts object with valid keys only', () => {
  assert.equal(validateScenarioPayload({ placements: [], terrain: null }), true);
});

test('validateScenarioPayload(): accepts empty object', () => {
  assert.equal(validateScenarioPayload({}), true);
});

test('validateScenarioPayload(): rejects array', () => {
  assert.equal(validateScenarioPayload([]), false);
});

test('validateScenarioPayload(): rejects null', () => {
  assert.equal(validateScenarioPayload(null), false);
});

test('validateScenarioPayload(): rejects unknown key', () => {
  assert.equal(validateScenarioPayload({ unknown_key: 1 }), false);
});

test('validateScenarioPayload(): rejects ui key (not in SCENARIO_KEYS)', () => {
  assert.equal(validateScenarioPayload({ ui: { active_module_id: null } }), false);
});

// ---------------------------------------------------------------------------
// D-499 / I-15: deep structural validation against XSS and prototype pollution
// ---------------------------------------------------------------------------

test('validateScenarioPayload(): rejects __proto__ key at top level', () => {
  // JSON.parse('{"__proto__":{}}') puts __proto__ as an own key on the parsed
  // object — must be rejected before any downstream merge/assign operation.
  const parsed = JSON.parse('{"__proto__":{"polluted":true}}');
  assert.equal(validateScenarioPayload(parsed), false);
});

test('validateScenarioPayload(): rejects __proto__ key nested inside a value', () => {
  const parsed = JSON.parse('{"placements":[{"__proto__":{"polluted":true}}]}');
  assert.equal(validateScenarioPayload(parsed), false);
});

test('validateScenarioPayload(): rejects constructor key at any depth', () => {
  const parsed = JSON.parse('{"placements":[{"constructor":{"prototype":{}}}]}');
  assert.equal(validateScenarioPayload(parsed), false);
});

test('validateScenarioPayload(): rejects prototype key at any depth', () => {
  const parsed = JSON.parse('{"constraints":{"prototype":{}}}');
  assert.equal(validateScenarioPayload(parsed), false);
});

test('validateScenarioPayload(): rejects string containing an HTML tag opener', () => {
  assert.equal(
    validateScenarioPayload({
      placements: [{ sensor_name: '<script>alert(1)</script>' }],
    }),
    false,
  );
});

test('validateScenarioPayload(): rejects string containing an img onerror payload', () => {
  assert.equal(
    validateScenarioPayload({
      placements: [{ note: '<img src=x onerror=alert(1)>' }],
    }),
    false,
  );
});

test('validateScenarioPayload(): rejects javascript: URI in a string value', () => {
  assert.equal(
    validateScenarioPayload({
      placements: [{ url: 'javascript:alert(1)' }],
    }),
    false,
  );
});

test('validateScenarioPayload(): rejects javascript: URI with whitespace', () => {
  // The matcher must tolerate whitespace before the colon, e.g.
  // "javascript :" or "JAVASCRIPT  :" — both bypass naive substring checks.
  assert.equal(
    validateScenarioPayload({
      placements: [{ url: 'JAVASCRIPT  :alert(1)' }],
    }),
    false,
  );
});

test('validateScenarioPayload(): rejects string exceeding max length', () => {
  const huge = 'a'.repeat(100_001);
  assert.equal(
    validateScenarioPayload({ placements: [{ note: huge }] }),
    false,
  );
});

test('validateScenarioPayload(): rejects object nested beyond max depth', () => {
  // Build a chain of 40 nested {a:{...}} objects under a known key.
  let nested = { leaf: 1 };
  for (let i = 0; i < 40; i += 1) {
    nested = { a: nested };
  }
  assert.equal(
    validateScenarioPayload({ constraints: nested }),
    false,
  );
});

test('validateScenarioPayload(): accepts nested object within depth limit', () => {
  // 5 levels of nesting — well under the cap.
  const nested = { a: { b: { c: { d: { e: 'safe' } } } } };
  assert.equal(
    validateScenarioPayload({ constraints: nested }),
    true,
  );
});

test('validateScenarioPayload(): rejects NaN number value', () => {
  // NaN cannot survive JSON.parse, but defence-in-depth: synthetic input
  // produced by buggy downstream code must not pass.
  assert.equal(
    validateScenarioPayload({ placements: [{ lat: NaN }] }),
    false,
  );
});

test('validateScenarioPayload(): rejects Infinity number value', () => {
  assert.equal(
    validateScenarioPayload({ placements: [{ lat: Infinity }] }),
    false,
  );
});

test('validateScenarioPayload(): accepts realistic scenario payload unchanged', () => {
  // Realistic save-file shape — must still be accepted post-tightening.
  const payload = {
    terrain: { dem_path: '/data/site.tif' },
    placements: [
      { id: 'p1', lat: -33.8688, lon: 151.2093, sensor_name: 'Sensor-1' },
    ],
    zones: [],
    threat_corridors: [{ bearing_deg: 45, start_distance_m: 1000 }],
    constraints: { budget_aud: 250000 },
    sim_results: null,
    report_config: { include_kill_chain: true },
  };
  assert.equal(validateScenarioPayload(payload), true);
});

test('validateScenarioPayload(): rejects unsafe content inside sensor_library entry', () => {
  // sensor_library is a SCENARIO_KEY because it round-trips through save/load,
  // so it must still be subject to deep validation.
  assert.equal(
    validateScenarioPayload({
      sensor_library: {
        Radar: [{ name: '<script>alert(1)</script>', type: 'Radar' }],
      },
    }),
    false,
  );
});

test('validateScenarioPayload(): accepts a realistic sensor_library payload', () => {
  // Positive round-trip case — a sanitised library shape must pass so that
  // save-then-load preserves library content.
  assert.equal(
    validateScenarioPayload({
      sensor_library: {
        Radar: [
          { name: 'Radar-1', type: 'Radar', range_band: 'medium', azimuth_coverage_deg: 120 },
        ],
        EO_IR: [
          { name: 'EO_IR-1', type: 'EO_IR', range_band: 'long', azimuth_coverage_deg: 360 },
        ],
      },
      effector_library: {
        Jammer: [{ name: 'Jammer-1', type: 'Jammer', range_band: 'long', requires_los: false }],
      },
    }),
    true,
  );
});

// ---------------------------------------------------------------------------
// S14.14-2: Scenario save/load — applyScenarioPayload
// ---------------------------------------------------------------------------

test('applyScenarioPayload(): writes all payload keys to state', () => {
  const state = makeState();
  const bus = makeBus();
  const payload = {
    placements: [{ id: 'p1' }],
    terrain: { dem_path: '/tmp/test.tif' },
  };

  applyScenarioPayload(payload, state, bus);

  assert.deepEqual(state.getState('placements'), [{ id: 'p1' }]);
  assert.deepEqual(state.getState('terrain'), { dem_path: '/tmp/test.tif' });
});

test('applyScenarioPayload(): missing keys are cleared to null', () => {
  const state = makeState();
  const bus = makeBus();

  // Pre-populate a key
  state.setState('sim_results', { coverage_pct: 80 });

  // Load a payload that does not include sim_results
  applyScenarioPayload({ placements: [] }, state, bus);

  assert.equal(state.getState('sim_results'), null);
});

test('applyScenarioPayload(): emits scenario:loaded event', () => {
  const state = makeState();
  const bus = makeBus();
  const events = [];
  bus.on('scenario:loaded', (data) => events.push(data));

  applyScenarioPayload({}, state, bus);

  assert.equal(events.length, 1);
  assert.ok(events[0].timestamp);
});

test('save then load round-trip: state is preserved', () => {
  const state = makeState();
  const bus = makeBus();

  const placements = [{ id: 'p1', lat: -33.8, lon: 151.2 }];
  state.setState('placements', placements);
  state.setState('sim_results', { coverage_pct: 72 });

  // Capture what saveScenario would serialise
  const savedPayload = {};
  const SCENARIO_KEYS = [
    'terrain', 'sensor_library', 'effector_library', 'placements', 'zones',
    'threat_corridors', 'constraints', 'sim_results', 'optimiser_results',
    'scenario_b_sim_results', 'report_config',
  ];
  for (const key of SCENARIO_KEYS) {
    savedPayload[key] = state.getState(key);
  }

  // Load into fresh state
  const state2 = makeState();
  applyScenarioPayload(savedPayload, state2, bus);

  assert.deepEqual(state2.getState('placements'), placements);
  assert.deepEqual(state2.getState('sim_results'), { coverage_pct: 72 });
  assert.equal(state2.getState('terrain'), null);
});

// ---------------------------------------------------------------------------
// S14.14-2: hasActivePlacements
// ---------------------------------------------------------------------------

test('hasActivePlacements(): returns false when placements is null', () => {
  const state = makeState();
  assert.equal(hasActivePlacements(state), false);
});

test('hasActivePlacements(): returns false when placements is empty array', () => {
  const state = makeState();
  state.setState('placements', []);
  assert.equal(hasActivePlacements(state), false);
});

test('hasActivePlacements(): returns true when placements has entries', () => {
  const state = makeState();
  state.setState('placements', [{ id: 'p1' }]);
  assert.equal(hasActivePlacements(state), true);
});

// ---------------------------------------------------------------------------
// S14.14-3: Minimal deployment — shell functions in no-API environment
// ---------------------------------------------------------------------------

test('fetchLibraries(): no fetch + SALUS_DATA present — returns SALUS_DATA values', async () => {
  const originalFetch = globalThis.fetch;
  const originalData = globalThis.SALUS_DATA;

  delete globalThis.fetch;
  globalThis.SALUS_DATA = {
    sensor_library: { radar: [{ name: 'MinimalRadar' }] },
    effector_library: {},
  };

  try {
    const { sensorLib, effectorLib } = await fetchLibraries();
    assert.deepEqual(sensorLib, { radar: [{ name: 'MinimalRadar' }] });
    assert.deepEqual(effectorLib, {});
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.SALUS_DATA = originalData;
  }
});

test('fetchLibraries(): no fetch + no SALUS_DATA — returns empty objects without throwing', async () => {
  const originalFetch = globalThis.fetch;
  const originalData = globalThis.SALUS_DATA;

  delete globalThis.fetch;
  delete globalThis.SALUS_DATA;

  try {
    const { sensorLib, effectorLib } = await fetchLibraries();
    assert.deepEqual(sensorLib, {});
    assert.deepEqual(effectorLib, {});
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.SALUS_DATA = originalData;
  }
});

// ---------------------------------------------------------------------------
// I-11 / D-480: initial MapLibre style carries one opaque background layer
// ---------------------------------------------------------------------------

test('initialMapStyle(): exposes a single opaque background layer', () => {
  const style = initialMapStyle();
  assert.equal(style.version, 8);
  assert.deepEqual(style.sources, {});
  assert.equal(style.layers.length, 1);
  const layer = style.layers[0];
  assert.equal(layer.type, 'background');
  const color = layer.paint['background-color'];
  // Reject any transparent / undefined paint value — the whole point of the
  // layer is to be opaque so hillshade has solid colour to shade against.
  assert.ok(typeof color === 'string' && color.length > 0, 'background-color must be a non-empty string');
  assert.notEqual(color, 'transparent');
});
