/**
 * test-coord-tools.js — Unit tests for the coord-tools shell-owned subsystem
 * and its I-20 infrastructure (toolbar shell, `coord_tools` state key).
 *
 * Run: node --test src/salus/viewer/interface/tests/test-coord-tools.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { createCoordTools, COORD_TOOLS_LAYER_PREFIX } from '../coord-tools/index.js';
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
  };
}

function makeDoc() {
  return { createElement: (tag) => makeElement(tag) };
}

/** A valid api handle: a real coord-tools scoped map proxy + a state handle. */
function makeApi() {
  const calls = [];
  const mockMap = {
    addSource(id) { calls.push(['addSource', id]); },
    addLayer(spec) { calls.push(['addLayer', spec.id]); },
    queryTerrainElevation(lngLat) { calls.push(['queryTerrainElevation', lngLat]); return 0; },
  };
  let coordState = null;
  return {
    map: createMapProxy(mockMap, 'coord-tools', { allowTerrainQuery: true }),
    state: {
      get: () => coordState,
      set: (v) => { coordState = v; },
    },
  };
}

/** Pull the stub buttons (those carrying data-tool) out of a rendered root. */
function toolButtons(root) {
  return root.children.filter((c) => c.dataset && c.dataset.tool);
}

// ---------------------------------------------------------------------------
// Toolbar mounting
// ---------------------------------------------------------------------------

test('createCoordTools mounts a .coord-tools root into the toolbar element', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { root } = createCoordTools(toolbar, makeApi(), doc);

  assert.equal(toolbar.children.length, 1);
  assert.equal(toolbar.children[0], root);
  assert.equal(root.className, 'coord-tools');
  assert.equal(root.parentNode, toolbar);
});

test('the toolbar shell renders a label and an X/Y/Z readout', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { root } = createCoordTools(toolbar, makeApi(), doc);

  const label = root.children.find((c) => c.className === 'coord-tools-label');
  assert.ok(label, 'a .coord-tools-label must be rendered');
  assert.equal(label.textContent, 'Coordinate Tools');

  const readout = root.children.find((c) => c.dataset.role === 'readout');
  assert.ok(readout, 'a readout element must be rendered');
  // I-20 shows placeholders only — no live coordinates yet.
  assert.match(readout.textContent, /X: —/);
  assert.match(readout.textContent, /Y: —/);
  assert.match(readout.textContent, /Z: —/);
});

test('the toolbar renders the set-origin, measure and grid tool stubs', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { root } = createCoordTools(toolbar, makeApi(), doc);

  const tools = toolButtons(root).map((b) => b.dataset.tool);
  assert.deepEqual(tools.sort(), ['grid', 'measure', 'set-origin']);
});

test('every I-20 tool control is rendered disabled (stubbed for I-21–I-23)', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { root } = createCoordTools(toolbar, makeApi(), doc);

  const buttons = toolButtons(root);
  assert.equal(buttons.length, 3);
  for (const btn of buttons) {
    assert.equal(btn.disabled, true, `tool '${btn.dataset.tool}' must be disabled in I-20`);
    assert.equal(btn.tag, 'button');
  }
});

// ---------------------------------------------------------------------------
// Persistence across module navigation
// ---------------------------------------------------------------------------

test('the toolbar is unaffected by module panel navigation', () => {
  // The coord-tools toolbar is shell chrome: it lives in #coord-toolbar, not
  // the #panel-slot the mode manager swaps. Simulate a module switch — clear
  // the panel slot and mount a new panel — and confirm the toolbar persists.
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const panelSlot = makeElement('div');

  const { root } = createCoordTools(toolbar, makeApi(), doc);

  // Module A mounts a panel, then is unmounted, then module B mounts one.
  panelSlot.appendChild(makeElement('div')); // module A panel
  panelSlot.children.length = 0;             // mode-manager clears the slot
  panelSlot.appendChild(makeElement('div')); // module B panel

  // The toolbar and its contents are untouched by any of that.
  assert.equal(toolbar.children.length, 1);
  assert.equal(toolbar.children[0], root);
  assert.equal(toolButtons(root).length, 3);
  // Controls keep their interactive state (still disabled, still buttons).
  for (const btn of toolButtons(root)) {
    assert.equal(btn.disabled, true);
  }
});

// ---------------------------------------------------------------------------
// Disposal
// ---------------------------------------------------------------------------

test('dispose() removes the toolbar root from the DOM', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { root, dispose } = createCoordTools(toolbar, makeApi(), doc);

  assert.equal(toolbar.children.length, 1);
  dispose();
  assert.equal(toolbar.children.length, 0);
  assert.equal(root.parentNode, null);
});

test('dispose() is idempotent — a second call does not throw', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const { dispose } = createCoordTools(toolbar, makeApi(), doc);

  dispose();
  assert.doesNotThrow(() => dispose());
});

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

test('createCoordTools throws TypeError when toolbarEl is not a DOM element', () => {
  const doc = makeDoc();
  assert.throws(() => createCoordTools(null, makeApi(), doc), TypeError);
  assert.throws(() => createCoordTools({}, makeApi(), doc), TypeError);
});

test('createCoordTools throws TypeError when api is missing or not an object', () => {
  const doc = makeDoc();
  const toolbar = makeElement('header');
  assert.throws(() => createCoordTools(toolbar, null, doc), TypeError);
  assert.throws(() => createCoordTools(toolbar, 'nope', doc), TypeError);
});

test('createCoordTools throws when api.map lacks the allowTerrainQuery opt-in', () => {
  // D-604: a map handle without queryTerrainElevation must be rejected at the
  // cause, not deferred to a later I-21 crash.
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const goodState = { get: () => null, set: () => {} };
  assert.throws(() => createCoordTools(toolbar, { state: goodState }, doc), TypeError);
  assert.throws(
    () => createCoordTools(toolbar, { map: {}, state: goodState }, doc),
    TypeError,
  );
});

test('createCoordTools throws when api.state is not a { get, set } handle', () => {
  // D-605: a malformed state handle must fail at construction.
  const doc = makeDoc();
  const toolbar = makeElement('header');
  const goodMap = makeApi().map;
  assert.throws(() => createCoordTools(toolbar, { map: goodMap }, doc), TypeError);
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: {} }, doc),
    TypeError,
  );
  assert.throws(
    () => createCoordTools(toolbar, { map: goodMap, state: { get: () => null } }, doc),
    TypeError,
  );
});

// ---------------------------------------------------------------------------
// Scoped map proxy — coord-tools layers are prefix-enforced (AC 5)
// ---------------------------------------------------------------------------

test('COORD_TOOLS_LAYER_PREFIX is the coord-tools prefix', () => {
  assert.equal(COORD_TOOLS_LAYER_PREFIX, 'coord-tools');
});

test('the subsystem map proxy enforces the coord-tools layer prefix', () => {
  // Any layer the subsystem later adds must carry the coord-tools: prefix.
  const proxy = createMapProxy({ addSource() {}, addLayer() {} }, 'coord-tools', {
    allowTerrainQuery: true,
  });
  assert.doesNotThrow(() => proxy.addSource('coord-tools:grid', { type: 'geojson' }));
  assert.throws(
    () => proxy.addSource('grid', { type: 'geojson' }),
    (err) => err instanceof LayerPrefixViolation,
  );
});

// ---------------------------------------------------------------------------
// `coord_tools` state key (AC 4)
// ---------------------------------------------------------------------------

test('coord_tools is a valid state key', () => {
  assert.ok(VALID_STATE_KEYS.has('coord_tools'));
});

test('the shell can read and write the coord_tools state key', () => {
  // The shell uses the bypass path (setState/getState) — coord_tools is
  // shell-owned, like ui.
  const state = createState(new Map());
  assert.equal(state.getState('coord_tools'), null);

  const skeleton = {
    origin_lnglat: null,
    grid_enabled: false,
    grid_spacing_m: null,
    measure: null,
  };
  state.setState('coord_tools', skeleton);
  assert.deepEqual(state.getState('coord_tools'), skeleton);
});

test('no module declares coord_tools in its reads[] or writes[] contract', () => {
  // coord_tools is shell-owned: like ui, no module may claim it.
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
