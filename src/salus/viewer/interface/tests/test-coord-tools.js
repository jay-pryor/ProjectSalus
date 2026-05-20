/**
 * test-coord-tools.js — Unit tests for the coord-tools shell-owned subsystem.
 *
 * Covers the I-20 infrastructure (toolbar shell, `coord_tools` state key), the
 * I-21 behaviour (local-frame conversion maths, origin defaulting, the
 * pick-mode reset, the live X/Y/Z readout and its "—" degradation paths), the
 * I-22 measure tool (two-click measurement, ΔX/ΔY/ΔZ + 3D slant + 2D
 * fallback maths, clear path, disposal, and draw-mode mutual exclusion) and
 * the I-23 grid tool (spacing clamp, toggle add/remove, principal-axis
 * emphasis, origin-move regeneration, and terrain-driven enable gate).
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
  localXYToLngLat,
  measurePair,
  clampGridSpacing,
  GRID_SPACING_MIN_M,
  GRID_SPACING_MAX_M,
  GRID_SPACING_DEFAULT_M,
} from '../coord-tools/index.js';
import { createMapProxy, LayerPrefixViolation } from '../map-proxy.js';
import { createState } from '../state.js';
import { VALID_STATE_KEYS, VALID_EVENTS } from '../state-schema.js';

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

/**
 * Mock shell bus — subscribe + fire only. Coord-tools is given a subscribe-only
 * handle, so the test bus deliberately omits `emit` to mirror that surface.
 */
function makeMockBus() {
  const handlers = {};
  return {
    on(event, cb) {
      if (!handlers[event]) handlers[event] = [];
      handlers[event].push(cb);
      return () => {
        const a = handlers[event];
        if (a) {
          const i = a.indexOf(cb);
          if (i !== -1) a.splice(i, 1);
        }
      };
    },
    _fire(event, data) {
      for (const cb of (handlers[event] || []).slice()) cb(data);
    },
    _handlerCount(event) {
      return (handlers[event] || []).length;
    },
  };
}

/** Build a full test harness: toolbar element, doc, mock map, state, bus, api. */
function makeHarness(opts = {}) {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const mockMap = makeMockMap(opts);
  const state = makeStateHandle(opts);
  const bus = makeMockBus();
  const api = {
    map: createMapProxy(mockMap, 'coord-tools', { allowTerrainQuery: true }),
    state,
    bus,
  };
  return { doc, toolbar, mockMap, state, bus, api };
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

test('the toolbar renders the set-origin, measure, measure-clear, grid and grid-spacing controls', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  const tools = toolButtons(root).map((b) => b.dataset.tool);
  assert.deepEqual(
    tools.sort(),
    ['grid', 'grid-spacing', 'measure', 'measure-clear', 'set-origin'],
  );
});

test('all toolbar controls are live; grid + spacing start disabled until terrain loads', () => {
  const { doc, toolbar, api } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);

  const byTool = Object.fromEntries(
    toolButtons(root).map((b) => [b.dataset.tool, b]),
  );
  assert.equal(byTool['set-origin'].disabled, false, 'set-origin is enabled in I-21');
  assert.equal(byTool['set-origin'].textContent, 'Set origin');
  assert.equal(byTool.measure.disabled, false, 'measure is enabled in I-22');
  assert.equal(byTool.measure.textContent, 'Measure');
  // I-23: grid + spacing are live controls but disabled until terrain loads
  // (no footprint to clip the grid to — AC 5).
  assert.equal(byTool.grid.disabled, true, 'grid is disabled without terrain');
  assert.equal(byTool.grid.textContent, 'Grid');
  assert.equal(byTool['grid-spacing'].disabled, true, 'spacing input disabled without terrain');
  assert.equal(byTool['grid-spacing'].value, String(GRID_SPACING_DEFAULT_M));
});

test('grid + spacing become enabled once terrain loads', () => {
  const { doc, toolbar, api, state } = makeHarness();
  const { root } = createCoordTools(toolbar, api, doc);
  const byTool = Object.fromEntries(
    toolButtons(root).map((b) => [b.dataset.tool, b]),
  );
  assert.equal(byTool.grid.disabled, true);

  state._setTerrain(TERRAIN);

  assert.equal(byTool.grid.disabled, false, 'grid enabled when terrain present');
  assert.equal(byTool['grid-spacing'].disabled, false, 'spacing input enabled');
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
  assert.equal(toolButtons(root).length, 5);
  // The controls keep their interactive state across navigation.
  const byTool = Object.fromEntries(
    toolButtons(root).map((b) => [b.dataset.tool, b]),
  );
  assert.equal(byTool['set-origin'].disabled, false);
  assert.equal(byTool.measure.disabled, false);
  assert.equal(byTool.grid.disabled, true, 'grid disabled without terrain');
  assert.equal(byTool['grid-spacing'].disabled, true);
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
  const goodBus = api.bus;
  assert.throws(() => createCoordTools(toolbar, { map: goodMap, bus: goodBus }, doc), TypeError);
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: {}, bus: goodBus }, doc),
    TypeError,
  );
  assert.throws(
    () =>
      createCoordTools(
        toolbar,
        { map: goodMap, state: { get: () => null, set: () => {} }, bus: goodBus },
        doc,
      ),
    TypeError,
  );
});

test('createCoordTools throws when api.bus is missing on()', () => {
  // I-22: the Measure tool's mutex with module draw modes depends on the bus.
  const { doc, toolbar, api } = makeHarness();
  const goodMap = api.map;
  const goodState = api.state;
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: goodState }, doc),
    TypeError,
  );
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: goodState, bus: {} }, doc),
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
  const { doc, toolbar, mockMap, bus } = makeHarness();
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
    bus,
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

// ===========================================================================
// I-22 — measure tool helpers
// ===========================================================================

function measureButtonOf(root) {
  return root.children.find((c) => c.dataset && c.dataset.tool === 'measure');
}

function clearButtonOf(root) {
  return root.children.find((c) => c.dataset && c.dataset.tool === 'measure-clear');
}

function measureReadoutOf(root) {
  return root.children.find(
    (c) => c.dataset && c.dataset.role === 'measure-readout',
  );
}

// ===========================================================================
// I-22 — drawmode:* events are valid contract events
// ===========================================================================

test('drawmode:entered and drawmode:exited are valid bus events', () => {
  assert.ok(VALID_EVENTS.has('drawmode:entered'));
  assert.ok(VALID_EVENTS.has('drawmode:exited'));
});

// ===========================================================================
// I-22 — measurePair distance maths (AC 2, 3, 7)
// ===========================================================================

test('measurePair: identical endpoints yield zero deltas and a zero total', () => {
  const r = measurePair([133, -25], [133, -25], [133, -25], 100, 100);
  assert.equal(r.dx, 0);
  assert.equal(r.dy, 0);
  assert.equal(r.dz, 0);
  assert.equal(r.hyp2d, 0);
  assert.equal(r.slant3d, 0);
  assert.equal(r.hasZ, true);
});

test('measurePair: a one-degree NE move yields a known 3D slant when elevated', () => {
  // At lat0 = -25°, one degree east ≈ 111195·cos(25°) ≈ 100776 m; one degree
  // north ≈ 111195 m; with a 200 m climb the 3D slant is sqrt(dx²+dy²+dz²).
  const r = measurePair([133, -25], [134, -24], [133, -25], 100, 300);
  assert.ok(Math.abs(r.dx - 100776) < 5, `dx was ${r.dx}`);
  assert.ok(Math.abs(r.dy - 111195) < 5, `dy was ${r.dy}`);
  assert.equal(r.dz, 200);
  const expected2d = Math.hypot(r.dx, r.dy);
  const expected3d = Math.hypot(r.dx, r.dy, 200);
  assert.ok(Math.abs(r.hyp2d - expected2d) < 1e-6);
  assert.ok(Math.abs(r.slant3d - expected3d) < 1e-6);
  assert.ok(r.slant3d > r.hyp2d, '3D slant must exceed the 2D horizontal');
  assert.equal(r.hasZ, true);
});

test('measurePair: a missing endpoint elevation yields hasZ=false and null dz/slant3d', () => {
  const r = measurePair([133, -25], [134, -25], [133, -25], 100, null);
  assert.equal(r.hasZ, false);
  assert.equal(r.dz, null);
  assert.equal(r.slant3d, null);
  // The 2D horizontal is still computed.
  assert.ok(Number.isFinite(r.hyp2d) && r.hyp2d > 0);
});

test('measurePair: a non-finite elevation (NaN) is treated as unavailable', () => {
  const r = measurePair([133, -25], [134, -25], [133, -25], NaN, 50);
  assert.equal(r.hasZ, false);
  assert.equal(r.dz, null);
  assert.equal(r.slant3d, null);
});

// ===========================================================================
// I-22 — two-click flow + on-map layers (AC 1, 6, 7)
// ===========================================================================

test('Measure: clicking the toggle enters mode, sets crosshair, and clears any prior state', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  btn._fire('click');
  assert.equal(btn.dataset.active, 'true');
  assert.equal(btn.textContent, 'Cancel');
  assert.equal(mockMap._canvas.style.cursor, 'crosshair');
  assert.equal(measureReadoutOf(root).hidden, true, 'no measurement yet — readout hidden');
  assert.equal(clearButtonOf(root).hidden, true, 'no points yet — clear hidden');
});

test('Measure: a single click places one marker, the second click places line + second marker', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(150);
  const { root } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click'); // enter mode
  mockMap._emit('click', pointerEvent(133.1, -25.0));

  // After one click: a Point feature exists; no line yet.
  let src = api.map.getSource('coord-tools:measure-source');
  assert.ok(src, 'a coord-tools:measure-source must be added on the first click');
  assert.equal(src.data.features.length, 1);
  assert.equal(src.data.features[0].geometry.type, 'Point');
  assert.equal(clearButtonOf(root).hidden, false, 'Clear must be visible with a point');
  assert.equal(measureReadoutOf(root).hidden, true, 'readout is hidden until 2nd click');

  // Both prefix-correct layers exist immediately (one source, two $type layers).
  assert.ok(api.map.getLayer('coord-tools:measure-line'));
  assert.ok(api.map.getLayer('coord-tools:measure-points'));

  mockMap._emit('click', pointerEvent(133.2, -25.0));

  src = api.map.getSource('coord-tools:measure-source');
  const types = src.data.features.map((f) => f.geometry.type).sort();
  assert.deepEqual(types, ['LineString', 'Point', 'Point']);
  assert.equal(measureReadoutOf(root).hidden, false, 'readout is shown after 2nd click');
});

test('Measure: after two clicks the readout shows ΔX, ΔY, ΔZ, 3D slant and 2D horizontal', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(120); // both points share this elevation → ΔZ = 0
  const { root } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));        // origin point
  mockMap._emit('click', pointerEvent(133.001, -25));    // ~100 m east

  const text = measureReadoutOf(root).textContent;
  const m = text.match(
    /^ΔX: (-?\d+) m {2}ΔY: (-?\d+) m {2}ΔZ: (-?\d+) m {2}3D: (\d+) m {2}2D: (\d+) m$/,
  );
  assert.ok(m, `measure readout did not match the expected shape: "${text}"`);
  // 0.001° lng at -25° lat ≈ 100.78 m east; ΔY = 0; ΔZ = 0; 3D == 2D.
  assert.ok(Math.abs(Number(m[1]) - 101) < 2, `ΔX was ${m[1]}`);
  assert.equal(m[2], '0');
  assert.equal(m[3], '0');
  assert.equal(m[4], m[5], 'with ΔZ=0 the 3D slant equals the 2D horizontal');
});

// ===========================================================================
// I-22 — Z-unavailable fallback (AC 3, 7)
// ===========================================================================

test('Measure: when terrain elevation is unavailable, ΔZ shows "—" and the headline is 2D', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(null); // queryTerrainElevation returns null off-tile
  const { root } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  mockMap._emit('click', pointerEvent(133.001, -25));

  const text = measureReadoutOf(root).textContent;
  // No 3D segment; "ΔZ: —" present; 2D total present.
  assert.match(text, /ΔZ: —/, `readout was "${text}"`);
  assert.ok(!/3D:/.test(text), `3D label must not appear when Z is unavailable: "${text}"`);
  assert.match(text, /2D: \d+ m/, `2D total must appear when Z is unavailable: "${text}"`);
});

test('Measure: a queryTerrainElevation throw at an endpoint falls back to the 2D total', () => {
  // D-606 mirror for the measure path.
  const { doc, toolbar, api, mockMap } = makeHarness({
    terrain: TERRAIN,
    elevationThrows: true,
  });
  const { root } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click');
  assert.doesNotThrow(() => {
    mockMap._emit('click', pointerEvent(133, -25));
    mockMap._emit('click', pointerEvent(133.001, -25));
  });
  const text = measureReadoutOf(root).textContent;
  assert.match(text, /ΔZ: —/, `readout was "${text}"`);
  assert.match(text, /2D: \d+ m/, `2D total must remain: "${text}"`);
});

// ===========================================================================
// I-22 — clear + exit semantics (AC 4, 6, 7)
// ===========================================================================

test('Measure: Clear removes the layers, hides the readout, and stays in mode', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(50);
  const { root } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  mockMap._emit('click', pointerEvent(133.001, -25));
  assert.ok(api.map.getSource('coord-tools:measure-source'));

  clearButtonOf(root)._fire('click');

  // Layers + source gone; readout + clear hidden; still in measure mode.
  assert.equal(api.map.getSource('coord-tools:measure-source'), undefined);
  assert.equal(api.map.getLayer('coord-tools:measure-line'), undefined);
  assert.equal(api.map.getLayer('coord-tools:measure-points'), undefined);
  assert.equal(measureReadoutOf(root).hidden, true);
  assert.equal(clearButtonOf(root).hidden, true);
  assert.equal(measureButtonOf(root).dataset.active, 'true', 'still in measure mode');

  // A fresh pair after Clear renders again — confirms layers can be re-added.
  mockMap._emit('click', pointerEvent(133.002, -25));
  mockMap._emit('click', pointerEvent(133.003, -25));
  assert.ok(api.map.getSource('coord-tools:measure-source'));
});

test('Measure: toggling Measure off (Cancel) clears the layers and restores the cursor', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(50);
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  btn._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  mockMap._emit('click', pointerEvent(133.001, -25));
  assert.ok(api.map.getSource('coord-tools:measure-source'));

  btn._fire('click'); // exit measure mode

  assert.equal(btn.dataset.active, 'false');
  assert.equal(btn.textContent, 'Measure');
  assert.equal(mockMap._canvas.style.cursor, '', 'cursor restored on exit');
  assert.equal(api.map.getSource('coord-tools:measure-source'), undefined);
  assert.equal(measureReadoutOf(root).hidden, true);
  assert.equal(clearButtonOf(root).hidden, true);
});

test('Measure: coord_tools.measure is written on each click and cleared on exit', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(50);
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  assert.equal(state._coordTools().measure, null);

  btn._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  assert.deepEqual(state._coordTools().measure, { a: [133, -25], b: null });

  mockMap._emit('click', pointerEvent(133.001, -25));
  assert.deepEqual(state._coordTools().measure, { a: [133, -25], b: [133.001, -25] });

  btn._fire('click'); // exit
  assert.equal(state._coordTools().measure, null);
});

// ===========================================================================
// I-22 — pick / measure click mutex within the subsystem (AC 5)
// ===========================================================================

test('a single map click is consumed by Measure, not by the origin pick (and vice versa)', () => {
  const { doc, toolbar, api, state, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const originBefore = state._coordTools().origin_lnglat;

  // While in measure mode, a click must drop a measure point — not move the origin.
  measureButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(134, -24));
  assert.deepEqual(state._coordTools().origin_lnglat, originBefore, 'origin unchanged');
  assert.ok(api.map.getSource('coord-tools:measure-source'), 'measure point recorded');

  // Pressing the origin button while in measure mode exits measure mode.
  originButtonOf(root)._fire('click');
  assert.equal(measureButtonOf(root).dataset.active, 'false');
  assert.equal(api.map.getSource('coord-tools:measure-source'), undefined);

  // The next click is consumed by the origin pick, not by Measure.
  mockMap._emit('click', pointerEvent(135, -23));
  assert.deepEqual(state._coordTools().origin_lnglat, [135, -23]);
});

// ===========================================================================
// I-22 — module draw-mode mutex (AC 5, 7)
// ===========================================================================

test('a drawmode:entered while idle disables the Measure toggle', () => {
  const { doc, toolbar, api, bus } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);
  assert.equal(btn.disabled, false, 'enabled with no draw modes active');

  bus._fire('drawmode:entered', { mode: 'draw' });
  assert.equal(btn.disabled, true, 'disabled while a module draw mode is active');

  bus._fire('drawmode:exited', { mode: 'draw' });
  assert.equal(btn.disabled, false, 're-enabled when every draw mode exits');
});

test('a drawmode:entered also exits origin-pick mode and disables the Set origin button (D-612)', () => {
  // D-612: origin-pick is structurally the same kind of click-capturing
  // single-handler mode as Measure, so the same mutex applies — a module
  // click must never simultaneously move the coord-tools origin AND place a
  // sensor / waypoint / vertex.
  const { doc, toolbar, api, bus, state, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const originBtn = originButtonOf(root);
  const originBefore = state._coordTools().origin_lnglat;

  originBtn._fire('click'); // enter origin-pick mode
  assert.equal(originBtn.dataset.active, 'true');

  bus._fire('drawmode:entered', { mode: 'draw' });
  assert.equal(originBtn.dataset.active, 'false', 'origin-pick exited');
  assert.equal(originBtn.disabled, true, 'Set origin button disabled by the draw mode');

  // A click while a module draw mode is active must NOT move the origin.
  mockMap._emit('click', pointerEvent(135, -23));
  assert.deepEqual(state._coordTools().origin_lnglat, originBefore);

  bus._fire('drawmode:exited', { mode: 'draw' });
  assert.equal(originBtn.disabled, false, 'Set origin re-enabled when the draw mode exits');
});

test('drawmode:entered while measure is active exits measure and clears layers', () => {
  const { doc, toolbar, api, bus, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(80);
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  btn._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  assert.ok(api.map.getSource('coord-tools:measure-source'));

  bus._fire('drawmode:entered', { mode: 'draw' });
  assert.equal(btn.dataset.active, 'false', 'measure mode exited');
  assert.equal(btn.disabled, true, 'Measure now disabled');
  assert.equal(api.map.getSource('coord-tools:measure-source'), undefined);
});

test('overlapping draw modes balance via a depth counter — Measure stays disabled until the last exit', () => {
  const { doc, toolbar, api, bus } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  bus._fire('drawmode:entered', { mode: 'draw' });
  bus._fire('drawmode:entered', { mode: 'pick' });
  assert.equal(btn.disabled, true);

  bus._fire('drawmode:exited', { mode: 'pick' });
  assert.equal(btn.disabled, true, 'still one draw mode active');

  bus._fire('drawmode:exited', { mode: 'draw' });
  assert.equal(btn.disabled, false, 're-enabled when depth reaches zero');
});

test('a Measure click is a no-op when the button has been disabled by a draw mode', () => {
  // Defensive — a programmatic _fire('click') on a disabled button must not
  // re-enter measure mode (AC 5: a single click is never double-handled).
  const { doc, toolbar, api, bus } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = measureButtonOf(root);

  bus._fire('drawmode:entered', { mode: 'draw' });
  btn._fire('click');
  assert.equal(btn.dataset.active, 'false', 'must remain idle when disabled');
});

// ===========================================================================
// I-22 — disposal (AC 6)
// ===========================================================================

test('dispose removes the coord-tools:measure-* layers, source and bus subscriptions', () => {
  const { doc, toolbar, api, bus, mockMap } = makeHarness({ terrain: TERRAIN });
  mockMap._setElevation(50);
  const { root, dispose } = createCoordTools(toolbar, api, doc);

  measureButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(133, -25));
  mockMap._emit('click', pointerEvent(133.001, -25));
  assert.ok(api.map.getSource('coord-tools:measure-source'));
  assert.equal(bus._handlerCount('drawmode:entered'), 1);
  assert.equal(bus._handlerCount('drawmode:exited'), 1);

  dispose();

  assert.equal(api.map.getSource('coord-tools:measure-source'), undefined);
  assert.equal(api.map.getLayer('coord-tools:measure-line'), undefined);
  assert.equal(api.map.getLayer('coord-tools:measure-points'), undefined);
  assert.equal(bus._handlerCount('drawmode:entered'), 0, 'drawmode:entered unsubscribed');
  assert.equal(bus._handlerCount('drawmode:exited'), 0, 'drawmode:exited unsubscribed');
});

// ===========================================================================
// I-23 — grid tool helpers
// ===========================================================================

function gridButtonOf(root) {
  return root.children.find((c) => c.dataset && c.dataset.tool === 'grid');
}

function spacingInputOf(root) {
  return root.children.find(
    (c) => c.dataset && c.dataset.tool === 'grid-spacing',
  );
}

// ===========================================================================
// I-23 — pure maths: localXYToLngLat (inverse) and clampGridSpacing (AC 2, 7)
// ===========================================================================

test('localXYToLngLat: (0, 0) returns the origin lng/lat unchanged', () => {
  const [lng, lat] = localXYToLngLat({ x: 0, y: 0 }, [133, -25]);
  assert.equal(lng, 133);
  assert.equal(lat, -25);
});

test('localXYToLngLat round-trips through lngLatToLocalXY within 1e-9 deg', () => {
  const origin = [133, -25];
  const samples = [
    [133.001, -25],
    [134.0, -24.5],
    [132.5, -25.7],
    [0, 0],
  ];
  for (const sample of samples) {
    const xy = lngLatToLocalXY(sample, origin);
    const back = localXYToLngLat(xy, origin);
    assert.ok(Math.abs(back[0] - sample[0]) < 1e-9, `lng round-trip ${sample}: got ${back[0]}`);
    assert.ok(Math.abs(back[1] - sample[1]) < 1e-9, `lat round-trip ${sample}: got ${back[1]}`);
  }
});

test('clampGridSpacing: clamps below the min, above the max, and leaves in-range alone', () => {
  assert.equal(clampGridSpacing(5), GRID_SPACING_MIN_M, 'below min snaps to MIN');
  assert.equal(clampGridSpacing(10), GRID_SPACING_MIN_M);
  assert.equal(clampGridSpacing(100), 100);
  assert.equal(clampGridSpacing(5000), GRID_SPACING_MAX_M);
  assert.equal(clampGridSpacing(50000), GRID_SPACING_MAX_M, 'above max snaps to MAX');
});

test('clampGridSpacing: non-finite values fall back to the default', () => {
  assert.equal(clampGridSpacing(NaN), GRID_SPACING_DEFAULT_M);
  assert.equal(clampGridSpacing(Infinity), GRID_SPACING_DEFAULT_M);
  assert.equal(clampGridSpacing(-Infinity), GRID_SPACING_DEFAULT_M);
});

// ===========================================================================
// I-23 — toggle add/remove and prefix-correct layers (AC 1, 6, 7)
// ===========================================================================

test('Grid: clicking the toggle adds both coord-tools:grid* layers and sources', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = gridButtonOf(root);

  assert.equal(api.map.getSource('coord-tools:grid'), undefined);
  assert.equal(api.map.getSource('coord-tools:grid-axes'), undefined);

  btn._fire('click');

  assert.equal(btn.dataset.active, 'true');
  assert.ok(api.map.getSource('coord-tools:grid'), 'minor-grid source present');
  assert.ok(api.map.getSource('coord-tools:grid-axes'), 'axes source present');
  assert.ok(api.map.getLayer('coord-tools:grid'), 'minor-grid layer present');
  assert.ok(api.map.getLayer('coord-tools:grid-axes'), 'axes layer present');
  // Every layer id this subsystem touched is coord-tools-prefixed.
  for (const [op, id] of mockMap._calls) {
    if (op === 'addLayer' || op === 'addSource') {
      assert.match(id, /^coord-tools:/, `layer/source id "${id}" must carry the coord-tools prefix`);
    }
  }
});

test('Grid: clicking the toggle a second time removes the layers and sources', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = gridButtonOf(root);

  btn._fire('click'); // on
  assert.ok(api.map.getSource('coord-tools:grid'));

  btn._fire('click'); // off

  assert.equal(btn.dataset.active, 'false');
  assert.equal(api.map.getSource('coord-tools:grid'), undefined);
  assert.equal(api.map.getSource('coord-tools:grid-axes'), undefined);
  assert.equal(api.map.getLayer('coord-tools:grid'), undefined);
  assert.equal(api.map.getLayer('coord-tools:grid-axes'), undefined);
});

test('Grid: with the default spacing and a 2°×2° footprint, many minor lines are generated', () => {
  // The TERRAIN fixture spans [132,-26]→[134,-24] — ~111 km on a side at this
  // latitude. At a 100 m default spacing, the minor-grid line count is in the
  // thousands. Assert a lower bound so we know the generator did fire.
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');

  const minorSrc = api.map.getSource('coord-tools:grid');
  const axesSrc = api.map.getSource('coord-tools:grid-axes');
  assert.ok(minorSrc.data.features.length > 100, `expected many minor lines, got ${minorSrc.data.features.length}`);
  // Exactly two principal axes (X=0 and Y=0) when origin is inside the bounds.
  assert.equal(axesSrc.data.features.length, 2, 'axes layer must hold exactly the two principal lines');
});

// ===========================================================================
// I-23 — principal-axis emphasis (AC 3, 7)
// ===========================================================================

test('Grid: the X=0 and Y=0 axes through the origin land on the axes layer with distinct paint', () => {
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');

  // The axes source carries the two principal lines: one at lng=lng0, one at lat=lat0.
  const axesFeatures = api.map.getSource('coord-tools:grid-axes').data.features;
  const lng0 = 133;
  const lat0 = -25;
  const hasXAxis = axesFeatures.some((f) =>
    f.geometry.coordinates.every((c) => Math.abs(c[0] - lng0) < 1e-9)
  );
  const hasYAxis = axesFeatures.some((f) =>
    f.geometry.coordinates.every((c) => Math.abs(c[1] - lat0) < 1e-9)
  );
  assert.ok(hasXAxis, 'an axes line must run at constant lng=lng0 (the X=0 axis)');
  assert.ok(hasYAxis, 'an axes line must run at constant lat=lat0 (the Y=0 axis)');

  // The two layers must be visibly distinct: the recorded addLayer paint
  // dicts must differ on width and colour.
  const addLayerSpecs = mockMap._calls.filter((c) => c[0] === 'addLayer');
  assert.ok(addLayerSpecs.some((c) => c[1] === 'coord-tools:grid'));
  assert.ok(addLayerSpecs.some((c) => c[1] === 'coord-tools:grid-axes'));
  // The mock stores specs in mockMap as well — extract them.
  // mockMap stores the spec passed to addLayer keyed by id (sources[] is for sources;
  // layers[] holds the spec). We retrieve them via getLayer.
  const minorSpec = api.map.getLayer('coord-tools:grid');
  const axesSpec = api.map.getLayer('coord-tools:grid-axes');
  assert.ok(minorSpec, 'minor-grid layer present');
  assert.ok(axesSpec, 'axes layer present');
  assert.notEqual(
    minorSpec.paint['line-color'],
    axesSpec.paint['line-color'],
    'principal axes must use a different line-color from the minor grid',
  );
  assert.ok(
    axesSpec.paint['line-width'] > minorSpec.paint['line-width'],
    'principal axes must be drawn thicker than the minor grid',
  );
});

// ===========================================================================
// I-23 — D-616..D-621 regression tests
// ===========================================================================

test('Grid: an empty spacing input restores the current value rather than snapping to MIN (D-616)', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const spacing = spacingInputOf(root);

  spacing.value = '250';
  spacing._fire('change');
  assert.equal(spacing.value, '250');

  // Now clear the field and commit — must NOT collapse to MIN.
  spacing.value = '';
  spacing._fire('change');
  assert.equal(spacing.value, '250', 'empty input must not snap to MIN');
});

test('Grid: degenerate terrain bounds render an empty grid rather than zero-length lines (D-617)', () => {
  // east==west and north==south — a zero-area footprint must refuse to render.
  const DEGENERATE = Object.freeze({
    centre_wgs84: [133, -25],
    bounds_wgs84: [133, -25, 133, -25],
    resolution_m: 1,
  });
  const { doc, toolbar, api } = makeHarness({ terrain: DEGENERATE });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');

  const minorSrc = api.map.getSource('coord-tools:grid');
  const axesSrc = api.map.getSource('coord-tools:grid-axes');
  assert.equal(minorSrc.data.features.length, 0, 'no minor lines for a zero-area bounds');
  assert.equal(axesSrc.data.features.length, 0, 'no axes lines for a zero-area bounds');
});

test('Grid: inverted terrain bounds (east<west) render an empty grid (D-617)', () => {
  const INVERTED = Object.freeze({
    centre_wgs84: [133, -25],
    bounds_wgs84: [134, -24, 132, -26], // west, south, east, north all swapped
    resolution_m: 1,
  });
  const { doc, toolbar, api } = makeHarness({ terrain: INVERTED });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');

  const minorSrc = api.map.getSource('coord-tools:grid');
  assert.equal(minorSrc.data.features.length, 0, 'inverted bounds must not draw backwards lines');
});

test('Grid: a render failure rolls gridEnabled back to false and refreshes controls (D-618)', () => {
  // Force a render failure by reassigning the underlying mock's addLayer to
  // one that throws — the scoped map proxy delegates through to the mock.
  const { doc, toolbar, api, mockMap } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = gridButtonOf(root);

  const originalAddLayer = mockMap.addLayer;
  mockMap.addLayer = () => { throw new Error('boom'); };
  try {
    btn._fire('click'); // attempt to enable — should fail and roll back
  } finally {
    mockMap.addLayer = originalAddLayer;
  }
  assert.equal(btn.dataset.active, 'false', 'Grid button must show inactive after a failed render');
  assert.equal(api.map.getSource('coord-tools:grid'), undefined, 'no orphan source after failed render');
  assert.equal(api.map.getSource('coord-tools:grid-axes'), undefined);
});

test('Grid: terrain reload with new bounds renders against the NEW bounds (D-619)', () => {
  const { doc, toolbar, api, state } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');
  const linesBefore = api.map.getSource('coord-tools:grid').data.features.length;

  // Load a much SMALLER terrain footprint — line count must drop accordingly,
  // proving the regenerated grid used the new bounds rather than the old.
  const SMALL = Object.freeze({
    centre_wgs84: [133, -25],
    bounds_wgs84: [132.95, -25.05, 133.05, -24.95],
    resolution_m: 1,
  });
  state._setTerrain(SMALL);

  const linesAfter = api.map.getSource('coord-tools:grid').data.features.length;
  assert.ok(linesAfter < linesBefore, `smaller bounds → fewer minor lines (before=${linesBefore}, after=${linesAfter})`);
});

test('Grid: a typed spacing value is flushed when the grid is toggled before the input blurs (D-621)', () => {
  const { doc, toolbar, api, state } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = gridButtonOf(root);
  const spacing = spacingInputOf(root);

  // User types a new spacing then clicks the toggle WITHOUT firing 'change'.
  spacing.value = '500';
  btn._fire('click'); // enable the grid; toggle must commit pending spacing first

  assert.equal(state._coordTools().grid_spacing_m, 500, 'pending typed value must be flushed on toggle');
  assert.equal(spacing.value, '500');
});

// ===========================================================================
// I-23 — origin move regenerates the grid (AC 4, 7)
// ===========================================================================

test('Grid: moving the origin regenerates the grid against the new frame', () => {
  const { doc, toolbar, api, mockMap, state } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');

  const lngBefore = api.map.getSource('coord-tools:grid-axes').data.features.find(
    (f) => f.geometry.coordinates.every((c) => Math.abs(c[0] - c[0]) < 1e-9 && f.properties.axis === 'x'),
  );
  const xAxisLng = lngBefore.geometry.coordinates[0][0];
  assert.equal(xAxisLng, 133, 'X=0 axis initially at lng0=133');

  // Move origin via the pick mode. The next map click is consumed by the pick.
  originButtonOf(root)._fire('click');
  mockMap._emit('click', pointerEvent(133.5, -24.5));
  assert.deepEqual(state._coordTools().origin_lnglat, [133.5, -24.5]);

  // The X=0 axis is now at lng=133.5 — proving the grid re-rendered.
  const axesAfter = api.map.getSource('coord-tools:grid-axes').data.features;
  const xAxisAfter = axesAfter.find((f) => f.properties.axis === 'x');
  assert.ok(xAxisAfter, 'X=0 axis must still be present');
  assert.ok(
    Math.abs(xAxisAfter.geometry.coordinates[0][0] - 133.5) < 1e-9,
    `X=0 axis must follow the new origin lng (got ${xAxisAfter.geometry.coordinates[0][0]})`,
  );
});

// ===========================================================================
// I-23 — spacing-input clamp + regeneration (AC 2, 7)
// ===========================================================================

test('Grid: changing the spacing regenerates the grid and the input value reflects the clamp', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');
  const spacing = spacingInputOf(root);

  const before = api.map.getSource('coord-tools:grid').data.features.length;

  // Increase the spacing 10x — line count must drop substantially.
  spacing.value = '1000';
  spacing._fire('change');
  const after = api.map.getSource('coord-tools:grid').data.features.length;
  assert.ok(after < before, `coarser spacing must reduce line count (before=${before}, after=${after})`);
});

test('Grid: a below-min spacing is corrected to MIN on commit (AC 2)', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const spacing = spacingInputOf(root);

  spacing.value = '5'; // below MIN=10
  spacing._fire('change');
  assert.equal(spacing.value, String(GRID_SPACING_MIN_M));
});

test('Grid: an above-max spacing is corrected to MAX on commit (AC 2)', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const spacing = spacingInputOf(root);

  spacing.value = '999999';
  spacing._fire('change');
  assert.equal(spacing.value, String(GRID_SPACING_MAX_M));
});

// ===========================================================================
// I-23 — state writes coord_tools.grid_enabled / grid_spacing_m (AC 7)
// ===========================================================================

test('Grid: toggling and resizing write to coord_tools.grid_enabled and grid_spacing_m', () => {
  const { doc, toolbar, api, state } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  const btn = gridButtonOf(root);
  const spacing = spacingInputOf(root);

  assert.equal(state._coordTools().grid_enabled, false);

  btn._fire('click');
  assert.equal(state._coordTools().grid_enabled, true);
  assert.equal(state._coordTools().grid_spacing_m, GRID_SPACING_DEFAULT_M);

  spacing.value = '250';
  spacing._fire('change');
  assert.equal(state._coordTools().grid_spacing_m, 250);

  btn._fire('click');
  assert.equal(state._coordTools().grid_enabled, false);
});

// ===========================================================================
// I-23 — terrain teardown (AC 5)
// ===========================================================================

test('Grid: clearing terrain disables the toggle and removes the grid', () => {
  const { doc, toolbar, api, state } = makeHarness({ terrain: TERRAIN });
  const { root } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');
  assert.ok(api.map.getSource('coord-tools:grid'));

  state._setTerrain(null);

  assert.equal(gridButtonOf(root).disabled, true, 'grid toggle disabled when terrain cleared');
  assert.equal(spacingInputOf(root).disabled, true);
  assert.equal(api.map.getSource('coord-tools:grid'), undefined, 'grid layers removed');
  assert.equal(api.map.getSource('coord-tools:grid-axes'), undefined);
});

// ===========================================================================
// I-23 — disposal (AC 6)
// ===========================================================================

test('dispose removes the coord-tools:grid and coord-tools:grid-axes layers and sources', () => {
  const { doc, toolbar, api } = makeHarness({ terrain: TERRAIN });
  const { root, dispose } = createCoordTools(toolbar, api, doc);
  gridButtonOf(root)._fire('click');
  assert.ok(api.map.getSource('coord-tools:grid'));
  assert.ok(api.map.getSource('coord-tools:grid-axes'));

  dispose();

  assert.equal(api.map.getSource('coord-tools:grid'), undefined);
  assert.equal(api.map.getSource('coord-tools:grid-axes'), undefined);
  assert.equal(api.map.getLayer('coord-tools:grid'), undefined);
  assert.equal(api.map.getLayer('coord-tools:grid-axes'), undefined);
});


