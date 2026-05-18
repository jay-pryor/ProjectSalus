/**
 * test-coord-tools.js — Unit tests for the coord-tools shell-owned subsystem.
 *
 * Covers the I-20 infrastructure (toolbar shell, `coord_tools` state key) and
 * the I-21 behaviour (local-frame conversion maths, origin defaulting, the
 * pick-mode reset, the live X/Y/Z readout and its "—" degradation paths).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-coord-tools.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  createCoordTools,
  COORD_TOOLS_LAYER_PREFIX,
  lngLatToLocalXY,
} from '../coord-tools/index.js';
import { createMapProxy, LayerPrefixViolation } from '../map-proxy.js';
import { createState } from '../state.js';
import { VALID_STATE_KEYS } from '../state-schema.js';

// ---------------------------------------------------------------------------
// Minimal DOM stub — only what coord-tools/index.js touches.
// ---------------------------------------------------------------------------

function makeElement(tag) {
  return {
    tag,
    className: '',
    textContent: '',
    title: '',
    disabled: false,
    dataset: {},
    children: [],
    parentNode: null,
    _listeners: {},
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) this.children.splice(i, 1);
      child.parentNode = null;
      return child;
    },
    addEventListener(type, cb) {
      if (!this._listeners[type]) this._listeners[type] = [];
      this._listeners[type].push(cb);
    },
    removeEventListener(type, cb) {
      const a = this._listeners[type];
      if (a) {
        const i = a.indexOf(cb);
        if (i !== -1) a.splice(i, 1);
      }
    },
    _fire(type, arg) {
      for (const cb of (this._listeners[type] || []).slice()) cb(arg);
    },
  };
}

function makeDoc() {
  return { createElement: (tag) => makeElement(tag) };
}

// ---------------------------------------------------------------------------
// Mock MapLibre map — records calls, emits events, configurable elevation.
// ---------------------------------------------------------------------------

function makeMockMap(opts = {}) {
  const handlers = {};
  const calls = [];
  const sources = {};
  const layers = {};
  const canvas = { style: { cursor: '' } };
  let elevation = opts.elevation !== undefined ? opts.elevation : null;
  return {
    _calls: calls,
    _canvas: canvas,
    on(type, handler) {
      if (!handlers[type]) handlers[type] = [];
      handlers[type].push(handler);
      calls.push(['on', type]);
    },
    off(type, handler) {
      const a = handlers[type];
      if (a) {
        const i = a.indexOf(handler);
        if (i !== -1) a.splice(i, 1);
      }
      calls.push(['off', type]);
    },
    _emit(type, event) {
      for (const h of (handlers[type] || []).slice()) h(event);
    },
    _handlerCount(type) {
      return (handlers[type] || []).length;
    },
    addSource(id, spec) {
      sources[id] = spec;
      calls.push(['addSource', id]);
    },
    removeSource(id) {
      delete sources[id];
      calls.push(['removeSource', id]);
    },
    getSource(id) {
      return sources[id];
    },
    addLayer(spec) {
      layers[spec.id] = spec;
      calls.push(['addLayer', spec.id]);
    },
    removeLayer(id) {
      delete layers[id];
      calls.push(['removeLayer', id]);
    },
    getLayer(id) {
      return layers[id];
    },
    getCanvas() {
      return canvas;
    },
    queryTerrainElevation() {
      if (opts.elevationThrows) {
        throw new Error('terrain renderer mid-teardown');
      }
      return elevation;
    },
    _setElevation(v) {
      elevation = v;
    },
  };
}

/** A coord-tools state handle backed by a tiny in-memory store. */
function makeStateHandle(opts = {}) {
  let coordTools = {
    origin_lnglat: null,
    grid_enabled: false,
    grid_spacing_m: null,
    measure: null,
  };
  let terrain = opts.terrain !== undefined ? opts.terrain : null;
  const terrainWatchers = [];
  return {
    get: () => coordTools,
    set: (value) => { coordTools = value; },
    getTerrain: () => terrain,
    watchTerrain: (cb) => {
      terrainWatchers.push(cb);
      return () => {
        const i = terrainWatchers.indexOf(cb);
        if (i !== -1) terrainWatchers.splice(i, 1);
      };
    },
    _setTerrain: (t) => {
      const old = terrain;
      terrain = t;
      for (const cb of terrainWatchers.slice()) cb(t, old);
    },
    _coordTools: () => coordTools,
    _terrainWatcherCount: () => terrainWatchers.length,
  };
}

/** Build a full test harness: toolbar element, doc, mock map, state, api. */
function makeHarness(opts = {}) {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const mockMap = makeMockMap(opts);
  const state = makeStateHandle(opts);
  const api = {
    map: createMapProxy(mockMap, 'coord-tools', { allowTerrainQuery: true }),
    state,
  };
  return { doc, toolbar, mockMap, state, api };
}

/** A MapLibre-shaped pointer event at a lng/lat. */
function pointerEvent(lng, lat) {
  return { lngLat: { lng, lat } };
}

/** Terrain metadata fixture with a centre at [133, -25] (central Australia). */
const TERRAIN = Object.freeze({
  centre_wgs84: [133, -25],
  bounds_wgs84: [132, -26, 134, -24],
  resolution_m: 1,
});

/** Pull the rendered tool buttons (those carrying data-tool) out of a root. */
function toolButtons(root) {
  return root.children.filter((c) => c.dataset && c.dataset.tool);
}

/** Find the readout element in a rendered root. */
function readoutOf(root) {
  return root.children.find((c) => c.dataset && c.dataset.role === 'readout');
}

/** Find the set-origin button in a rendered root. */
function originButtonOf(root) {
  return root.children.find((c) => c.dataset && c.dataset.tool === 'set-origin');
}

// ===========================================================================
// Toolbar shell (I-20, carried forward)
// ===========================================================================

test('createCoordTools mounts a .coord-tools root into the toolbar element', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  assert.equal(toolbar.children.length, 1);
  assert.equal(toolbar.children[0], root);
  assert.equal(root.className, 'coord-tools');
  assert.equal(root.parentNode, toolbar);
});

test('the toolbar renders a label and an X/Y/Z readout (dashes before terrain)', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  const label = root.children.find((c) => c.className === 'coord-tools-label');
  assert.ok(label, 'a .coord-tools-label must be rendered');
  assert.equal(label.textContent, 'Coordinate Tools');

  const readout = readoutOf(root);
  assert.ok(readout, 'a readout element must be rendered');
  assert.equal(readout.textContent, 'X: —  Y: —  Z: —');
});

test('the toolbar renders the set-origin, measure and grid controls', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  const tools = toolButtons(root).map((b) => b.dataset.tool);
  assert.deepEqual(tools.sort(), ['grid', 'measure', 'set-origin']);
});

test('measure and grid stay disabled stubs; set-origin is a live control', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  const byTool = Object.fromEntries(
    toolButtons(root).map((b) => [b.dataset.tool, b]),
  );
  assert.equal(byTool.measure.disabled, true, 'measure remains an I-22 stub');
  assert.equal(byTool.grid.disabled, true, 'grid remains an I-23 stub');
  assert.equal(byTool['set-origin'].disabled, false, 'set-origin is enabled in I-21');
  assert.equal(byTool['set-origin'].textContent, 'Set origin');
});

test('the toolbar is unaffected by module panel navigation', () => {
  // coord-tools is shell chrome in #coord-toolbar, not the #panel-slot the
  // mode manager swaps. Simulate a module switch and confirm it persists.
  const { doc, toolbar, api } = makeHarness();
  const panelSlot = makeElement('div');
  const { root } = createCoordTools(toolbar, api, doc);

  panelSlot.appendChild(makeElement('div')); // module A panel
  panelSlot.children.length = 0;             // mode-manager clears the slot
  panelSlot.appendChild(makeElement('div')); // module B panel

  assert.equal(toolbar.children.length, 1);
  assert.equal(toolbar.children[0], root);
  assert.equal(toolButtons(root).length, 3);
  // The controls keep their interactive state across navigation.
  const byTool = Object.fromEntries(
    toolButtons(root).map((b) => [b.dataset.tool, b]),
  );
  assert.equal(byTool['set-origin'].disabled, false);
  assert.equal(byTool.measure.disabled, true);
  assert.equal(byTool.grid.disabled, true);
});

// ===========================================================================
// Input validation
// ===========================================================================

test('createCoordTools throws TypeError when toolbarEl is not a DOM element', () => {
  const { doc, api } = makeHarness();
  assert.throws(() => createCoordTools(null, api, doc), TypeError);
  assert.throws(() => createCoordTools({}, api, doc), TypeError);
});

test('createCoordTools throws when api is missing or not an object', () => {
  const { doc, toolbar } = makeHarness();
  assert.throws(() => createCoordTools(toolbar, null, doc), TypeError);
  assert.throws(() => createCoordTools(toolbar, 'nope', doc), TypeError);
});

test('createCoordTools throws when api.map lacks the allowTerrainQuery opt-in', () => {
  // D-604: a map handle without queryTerrainElevation is rejected at the cause.
  const { doc, toolbar, state } = makeHarness();
  assert.throws(() => createCoordTools(toolbar, { state }, doc), TypeError);
  assert.throws(
    () => createCoordTools(toolbar, { map: {}, state }, doc),
    TypeError,
  );
});

test('createCoordTools throws when api.state is missing a required method', () => {
  // D-605: get/set/getTerrain/watchTerrain must all be functions.
  const { doc, toolbar, api } = makeHarness();
  const goodMap = api.map;
  assert.throws(() => createCoordTools(toolbar, { map: goodMap }, doc), TypeError);
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: {} }, doc),
    TypeError,
  );
  assert.throws(
    () =>
      createCoordTools(
        toolbar,
        { map: goodMap, state: { get: () => null, set: () => {} } },
        doc,
      ),
    TypeError,
  );
});

// ===========================================================================
// Local tangent-plane conversion maths (I-21 design point 1)
// ===========================================================================

test('lngLatToLocalXY: cursor at the origin yields {0, 0}', () => {
  const { x, y } = lngLatToLocalXY([133, -25], [133, -25]);
  assert.equal(x, 0);
  assert.equal(y, 0);
});

test('lngLatToLocalXY: one degree east at the equator is ~111195 m east', () => {
  const { x, y } = lngLatToLocalXY([1, 0], [0, 0]);
  // (pi/180) * 6_371_000 = 111194.926...
  assert.ok(Math.abs(x - 111194.93) < 0.1, `x was ${x}`);
  assert.ok(Math.abs(y) < 1e-6, `y was ${y}`);
});

test('lngLatToLocalXY: one degree north is ~111195 m north regardless of longitude', () => {
  const { x, y } = lngLatToLocalXY([10, 1], [10, 0]);
  assert.ok(Math.abs(y - 111194.93) < 0.1, `y was ${y}`);
  assert.ok(Math.abs(x) < 1e-6, `x was ${x}`);
});

test('lngLatToLocalXY: longitude metres are scaled by cos(latitude)', () => {
  // At 60°N a degree of longitude spans half the equatorial distance.
  const { x } = lngLatToLocalXY([1, 60], [0, 60]);
  assert.ok(Math.abs(x - 111194.93 * Math.cos(60 * (Math.PI / 180))) < 0.1, `x was ${x}`);
  assert.ok(Math.abs(x - 55597.46) < 0.1, `x was ${x}`);
});

test('lngLatToLocalXY: west/south of the origin yields negative X/Y', () => {
  const { x, y } = lngLatToLocalXY([132, -26], [133, -25]);
  assert.ok(x < 0, `expected negative x, got ${x}`);
  assert.ok(y < 0, `expected negative y, got ${y}`);
});

// ===========================================================================
// Origin defaulting from terrain (AC 1)
// ===========================================================================

test('origin defaults to the terrain centre when terrain is already loaded', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  createCoordTools(toolbar, api, doc);

  assert.deepEqual(state._coordTools().origin_lnglat, [133, -25]);
  // The origin indicator source + layer were added with the prefixed id.
  assert.ok(mockMap._calls.some((c) => c[0] === 'addSource' && c[1] === 'coord-tools:origin'));
  assert.ok(mockMap._calls.some((c) => c[0] === 'addLayer' && c[1] === 'coord-tools:origin'));
});

test('origin defaults to the terrain centre when terrain loads after mount', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness();
  createCoordTools(toolbar, api, doc);
  assert.equal(state._coordTools().origin_lnglat, null);

  state._setTerrain(TERRAIN); // terrain-loader writes terrain state

  assert.deepEqual(state._coordTools().origin_lnglat, [133, -25]);
  assert.ok(mockMap._calls.some((c) => c[0] === 'addLayer' && c[1] === 'coord-tools:origin'));
});

test('a terrain payload without a valid centre does not set an origin', () => {
  const { doc, toolbar, api, state } = makeHarness();
  createCoordTools(toolbar, api, doc);

  state._setTerrain({ centre_wgs84: null });
  assert.equal(state._coordTools().origin_lnglat, null);

  state._setTerrain({ centre_wgs84: [133] }); // wrong length
  assert.equal(state._coordTools().origin_lnglat, null);
});

// ===========================================================================
// Pick mode — "Set origin" reset (AC 4)
// ===========================================================================

test('clicking "Set origin" enters pick mode and sets the crosshair cursor', () => {
  const { doc, toolbar, api, mockMap } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = originButtonOf(root);

  btn._fire('click');

  assert.equal(btn.dataset.active, 'true');
  assert.equal(btn.textContent, 'Cancel');
  assert.equal(mockMap._canvas.style.cursor, 'crosshair');
});

test('a map click in pick mode moves the origin and exits pick mode', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = originButtonOf(root);

  btn._fire('click');                       // enter pick mode
  mockMap._emit('click', pointerEvent(134, -24)); // pick a new origin

  assert.deepEqual(state._coordTools().origin_lnglat, [134, -24]);
  assert.equal(btn.dataset.active, 'false', 'pick mode exits after the pick');
  assert.equal(btn.textContent, 'Set origin');
  assert.equal(mockMap._canvas.style.cursor, '', 'cursor restored after the pick');
});

test('clicking "Set origin" twice cancels pick mode without changing the origin', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = originButtonOf(root);
  const originBefore = state._coordTools().origin_lnglat;

  btn._fire('click'); // enter
  btn._fire('click'); // cancel

  assert.equal(btn.dataset.active, 'false');
  assert.equal(mockMap._canvas.style.cursor, '');
  assert.deepEqual(state._coordTools().origin_lnglat, originBefore);
});

test('a map click when not in pick mode does not change the origin', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  createCoordTools(toolbar, api, doc);
  const originBefore = state._coordTools().origin_lnglat;

  // a map click without ever entering pick mode is a no-op for the origin
  mockMap._emit('click', pointerEvent(140, -20));

  assert.deepEqual(state._coordTools().origin_lnglat, originBefore);
});

// ===========================================================================
// Live readout + "—" degradation (AC 2, 3, 5)
// ===========================================================================

test('before terrain loads the readout shows "—" and does not error', () => {
  const { doc, toolbar, api, mockMap } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  assert.doesNotThrow(() => mockMap._emit('mousemove', pointerEvent(135, -26)));
  assert.equal(readoutOf(root).textContent, 'X: —  Y: —  Z: —');
});

test('with an origin the readout shows live X/Y and the terrain Z', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(210.4);
  const { root } = createCoordTools(toolbar, api, doc);

  // cursor one degree east + one degree north of the [133,-25] origin
  mockMap._emit('mousemove', pointerEvent(134, -24));

  const text = readoutOf(root).textContent;
  // X ≈ 111195·cos(25°) ≈ 100776 m; Y ≈ 111195 m; Z rounds to 210 m.
  const m = text.match(/^X: (-?\d+) m {2}Y: (-?\d+) m {2}Z: (-?\d+) m$/);
  assert.ok(m, `readout did not match expected shape: "${text}"`);
  assert.ok(Math.abs(Number(m[1]) - 100776) < 5, `X was ${m[1]}`);
  assert.ok(Math.abs(Number(m[2]) - 111195) < 5, `Y was ${m[2]}`);
  assert.equal(m[3], '210');
  assert.ok(state); // origin came from terrain
});

test('Z shows "—" where terrain elevation is unavailable, X/Y still show', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(null); // queryTerrainElevation off-tile / no terrain
  const { root } = createCoordTools(toolbar, api, doc);

  mockMap._emit('mousemove', pointerEvent(134, -24));

  const text = readoutOf(root).textContent;
  assert.match(text, /^X: -?\d+ m {2}Y: -?\d+ m {2}Z: —$/, `readout was "${text}"`);
});

test('a throw from queryTerrainElevation degrades Z to "—" without killing the readout', () => {
  // D-606: a terrain-query throw must not propagate out of the readout.
  const { doc, toolbar, api, mockMap } = makeHarness({
    terrain: TERRAIN,
    elevationThrows: true,
  });
  const { root } = createCoordTools(toolbar, api, doc);

  assert.doesNotThrow(() => mockMap._emit('mousemove', pointerEvent(134, -24)));
  const text = readoutOf(root).textContent;
  assert.match(text, /^X: -?\d+ m {2}Y: -?\d+ m {2}Z: —$/, `readout was "${text}"`);
});

test('a mousemove with a non-finite lng/lat shows "—", not "NaN m"', () => {
  // D-608: a malformed cursor position degrades to the placeholder.
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);

  mockMap._emit('mousemove', pointerEvent(NaN, -24));
  assert.equal(readoutOf(root).textContent, 'X: —  Y: —  Z: —');
});

test('a pick click with a non-finite lng/lat does not change the origin', () => {
  // D-607: a non-finite pick must not poison originLngLat or coord_tools.
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const originBefore = state._coordTools().origin_lnglat;

  originButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(NaN, undefined));

  assert.deepEqual(state._coordTools().origin_lnglat, originBefore);
});

test('_setOrigin still works when the coord_tools state starts null (D-610)', () => {
  // A null coord_tools (a shell wiring regression) must not crash the origin
  // write — the origin is still persisted.
  const { doc, toolbar, mockMap } = makeHarness();
  let coordTools = null;
  const state = {
    get: () => coordTools,
    set: (v) => { coordTools = v; },
    getTerrain: () => TERRAIN,
    watchTerrain: () => () => {},
  };
  const api = {
    map: createMapProxy(mockMap, 'coord-tools', { allowTerrainQuery: true }),
    state,
  };
  assert.doesNotThrow(() => createCoordTools(toolbar, api, doc));
  assert.deepEqual(coordTools.origin_lnglat, [133, -25]);
});

test('the readout recomputes against a new origin after a pick', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(100);
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = originButtonOf(root);

  // cursor at [134,-24]; with the [133,-25] origin X/Y are non-zero
  mockMap._emit('mousemove', pointerEvent(134, -24));
  assert.notEqual(readoutOf(root).textContent, 'X: 0 m  Y: 0 m  Z: 100 m');

  // move the origin onto the cursor — readout must recompute to ~0,0
  btn._fire('click');
  mockMap._emit('click', pointerEvent(134, -24));
  assert.equal(readoutOf(root).textContent, 'X: 0 m  Y: 0 m  Z: 100 m');
});

// ===========================================================================
// Animation-frame throttling (AC 6)
// ===========================================================================

test('the mousemove handler updates at most once per animation frame', () => {
  const frames = [];
  const original = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (cb) => {
    frames.push(cb);
    return frames.length;
  };
  try {
    const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
    mockMap._setElevation(50);
    const { root } = createCoordTools(toolbar, api, doc);

    mockMap._emit('mousemove', pointerEvent(133.1, -25));
    mockMap._emit('mousemove', pointerEvent(133.2, -25));
    mockMap._emit('mousemove', pointerEvent(133.3, -25));
    assert.equal(frames.length, 1, 'three moves must schedule only one frame');

    frames[0](); // run the frame — renders the latest event only
    const afterFirst = readoutOf(root).textContent;
    assert.match(afterFirst, /^X: \d+ m {2}Y: 0 m {2}Z: 50 m$/);

    mockMap._emit('mousemove', pointerEvent(133.4, -25));
    assert.equal(frames.length, 2, 'a move after the frame resolved schedules a new one');
  } finally {
    globalThis.requestAnimationFrame = original;
  }
});

// ===========================================================================
// Disposal (AC 6)
// ===========================================================================

test('dispose removes the mousemove and click map listeners', () => {
  const { doc, toolbar, api, mockMap } = makeHarness();
  const { dispose } = createCoordTools(toolbar, api, doc);

  assert.equal(mockMap._handlerCount('mousemove'), 1);
  assert.equal(mockMap._handlerCount('click'), 1);
  dispose();
  assert.equal(mockMap._handlerCount('mousemove'), 0);
  assert.equal(mockMap._handlerCount('click'), 0);
});

test('dispose removes the coord-tools:origin layer and source', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { dispose } = createCoordTools(toolbar, api, doc);
  assert.ok(api.map.getLayer('coord-tools:origin'), 'origin layer present after terrain load');

  dispose();
  assert.equal(api.map.getLayer('coord-tools:origin'), undefined);
  assert.equal(api.map.getSource('coord-tools:origin'), undefined);
  assert.ok(mockMap._calls.some((c) => c[0] === 'removeLayer' && c[1] === 'coord-tools:origin'));
});

test('dispose unsubscribes the terrain watch', () => {
  const { doc, toolbar, api, state } = makeHarness();
  const { dispose } = createCoordTools(toolbar, api, doc);
  assert.equal(state._terrainWatcherCount(), 1);

  dispose();
  assert.equal(state._terrainWatcherCount(), 0);
});

test('dispose restores the cursor when a pick was in progress', () => {
  const { doc, toolbar, api, mockMap } = makeHarness();
  const { root, dispose } = createCoordTools(toolbar, api, doc);

  originButtonOf(root)._fire('click'); // enter pick mode → crosshair cursor
  assert.equal(mockMap._canvas.style.cursor, 'crosshair');

  dispose();
  assert.equal(mockMap._canvas.style.cursor, '', 'cursor restored on disposal');
});

test('dispose removes the toolbar root and is idempotent', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root, dispose } = createCoordTools(toolbar, api, doc);

  dispose();
  assert.equal(toolbar.children.length, 0);
  assert.equal(root.parentNode, null);
  assert.doesNotThrow(() => dispose());
});

test('a mousemove queued before dispose does not render after dispose', () => {
  const frames = [];
  const original = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (cb) => {
    frames.push(cb);
    return frames.length;
  };
  try {
    const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
    const { root, dispose } = createCoordTools(toolbar, api, doc);

    mockMap._emit('mousemove', pointerEvent(134, -24)); // schedules a frame
    const before = readoutOf(root).textContent;
    dispose();
    frames[0](); // the frame fires after disposal — must be a no-op
    assert.equal(readoutOf(root).textContent, before);
  } finally {
    globalThis.requestAnimationFrame = original;
  }
});

// ===========================================================================
// Scoped map proxy + state key (I-20 infrastructure, carried forward)
// ===========================================================================

test('COORD_TOOLS_LAYER_PREFIX is the coord-tools prefix', () => {
  assert.equal(COORD_TOOLS_LAYER_PREFIX, 'coord-tools');
});

test('the subsystem map proxy enforces the coord-tools layer prefix', () => {
  const proxy = createMapProxy({ addSource() {}, addLayer() {} }, 'coord-tools', {
    allowTerrainQuery: true,
  });
  assert.doesNotThrow(() => proxy.addSource('coord-tools:grid', { type: 'geojson' }));
  assert.throws(
    () => proxy.addSource('grid', { type: 'geojson' }),
    (err) => err instanceof LayerPrefixViolation,
  );
});

test('coord_tools is a valid state key', () => {
  assert.ok(VALID_STATE_KEYS.has('coord_tools'));
});

test('the shell can read and write the coord_tools state key', () => {
  const state = createState(new Map());
  assert.equal(state.getState('coord_tools'), null);

  const value = {
    origin_lnglat: [133, -25],
    grid_enabled: false,
    grid_spacing_m: null,
    measure: null,
  };
  state.setState('coord_tools', value);
  assert.deepEqual(state.getState('coord_tools'), value);
});

test('no module declares coord_tools in its reads[] or writes[] contract', () => {
  const modulesDir = fileURLToPath(new URL('../modules/', import.meta.url));
  let checked = 0;
  for (const entry of readdirSync(modulesDir)) {
    const manifestPath = `${modulesDir}${entry}/manifest.json`;
    let raw;
    try {
      if (!statSync(`${modulesDir}${entry}`).isDirectory()) continue;
      raw = readFileSync(manifestPath, 'utf8');
    } catch {
      continue; // not a module directory / no manifest
    }
    const manifest = JSON.parse(raw);
    checked += 1;
    for (const key of manifest.reads ?? []) {
      assert.notEqual(key, 'coord_tools', `module '${entry}' must not read coord_tools`);
    }
    for (const key of manifest.writes ?? []) {
      assert.notEqual(key, 'coord_tools', `module '${entry}' must not write coord_tools`);
    }
  }
  assert.ok(checked > 0, 'expected at least one module manifest to be checked');
});
