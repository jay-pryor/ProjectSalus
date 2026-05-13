/**
 * test-mode-manager.js — Unit tests for the mode manager.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-mode-manager.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createModeManager } from '../mode-manager.js';
import { createState } from '../state.js';
import { createBus } from '../bus.js';

// ---------------------------------------------------------------------------
// Mock DOM
// ---------------------------------------------------------------------------

function makeElement(tag = 'div') {
  return {
    _tag: tag,
    _children: [],
    _listeners: {},
    disabled: false,
    title: '',
    textContent: '',
    id: '',
    dataset: {},
    appendChild(child) { this._children.push(child); return child; },
    removeChild(child) {
      const i = this._children.indexOf(child);
      if (i !== -1) this._children.splice(i, 1);
    },
    addEventListener(event, handler) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(handler);
    },
    get firstChild() { return this._children[0] ?? null; },
    /** Helper for tests: simulate a click event */
    click() {
      for (const h of (this._listeners['click'] ?? [])) h();
    },
  };
}

function makeMockDoc() {
  const elements = [];
  return {
    _elements: elements,
    createElement(tag) {
      const el = makeElement(tag);
      elements.push(el);
      return el;
    },
  };
}

// ---------------------------------------------------------------------------
// State factory (contracts for test modules)
// ---------------------------------------------------------------------------

function makeStateForModules(moduleIds) {
  const contracts = new Map(moduleIds.map(id => [id, { reads: [], writes: [] }]));
  return createState(contracts);
}

function makeBusForModules(moduleIds) {
  const contracts = new Map(moduleIds.map(id => [id, { emits: [], subscribes: [] }]));
  return createBus(contracts);
}

// Stub bus for tests that don't exercise bus functionality
const stubBus = { emit() {}, on() { return () => {}; }, createScopedBus() { return { emit() {}, on() { return () => {}; } }; } };

// ---------------------------------------------------------------------------
// Module registry factory
// ---------------------------------------------------------------------------

function makeEntry(id, { prerequisites = [], label = id } = {}, loadModule = null) {
  const unmountCalls = [];
  const initCalls = [];

  const api = { moduleId: id, panel: { mount() {}, onUnmount(cb) { unmountCalls.push(cb); } } };

  const entry = {
    manifest: { id, label, prerequisites, layer_id_prefix: id },
    api,
    runUnmount() {
      for (const cb of unmountCalls) cb();
      unmountCalls.length = 0;
    },
    loadModule: loadModule ?? (() => Promise.resolve({ init(a) { initCalls.push(a.moduleId); } })),
    _unmountCalls: unmountCalls,
    _initCalls: initCalls,
  };
  return entry;
}

// ---------------------------------------------------------------------------
// Tests: nav bar construction
// ---------------------------------------------------------------------------

test('init() creates one button per module', () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [makeEntry('mod-a'), makeEntry('mod-b')];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  // 2 module buttons + 1 back button
  assert.equal(nav._children.length, 3);
});

test('init() labels buttons from manifest.label', () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [makeEntry('mod-a', { label: 'Load Terrain' })];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  const btn = nav._children[0];
  assert.equal(btn.textContent, 'Load Terrain');
});

// ---------------------------------------------------------------------------
// Tests: prerequisite gating
// ---------------------------------------------------------------------------

test('button is disabled when prerequisite is null', () => {
  const doc = makeMockDoc();
  const stateContracts = new Map([
    ['terrain-writer', { reads: [], writes: ['terrain'] }],
    ['needs-terrain', { reads: [], writes: [] }],
  ]);
  const state = createState(stateContracts);

  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [
    makeEntry('terrain-writer'),
    makeEntry('needs-terrain', { prerequisites: ['terrain'] }),
  ];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  const needsTerrainBtn = nav._children.find(b => b.dataset.moduleId === 'needs-terrain');
  assert.equal(needsTerrainBtn.disabled, true);
});

test('button tooltip lists missing prerequisites', () => {
  const doc = makeMockDoc();
  const stateContracts = new Map([
    ['terrain-writer', { reads: [], writes: ['terrain'] }],
    ['needs-terrain', { reads: [], writes: [] }],
  ]);
  const state = createState(stateContracts);

  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [
    makeEntry('terrain-writer'),
    makeEntry('needs-terrain', { prerequisites: ['terrain'] }),
  ];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  const needsTerrainBtn = nav._children.find(b => b.dataset.moduleId === 'needs-terrain');
  assert.ok(needsTerrainBtn.title.includes('terrain'));
});

test('button is enabled when prerequisite becomes non-null', () => {
  const doc = makeMockDoc();
  const stateContracts = new Map([
    ['terrain-writer', { reads: [], writes: ['terrain'] }],
    ['needs-terrain', { reads: [], writes: [] }],
  ]);
  const state = createState(stateContracts);

  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [
    makeEntry('terrain-writer'),
    makeEntry('needs-terrain', { prerequisites: ['terrain'] }),
  ];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  const needsTerrainBtn = nav._children.find(b => b.dataset.moduleId === 'needs-terrain');
  assert.equal(needsTerrainBtn.disabled, true);

  // Simulate terrain being loaded
  state.setState('terrain', { dem_path: '/x.tif' });

  assert.equal(needsTerrainBtn.disabled, false);
  assert.equal(needsTerrainBtn.title, '');
});

test('button with no prerequisites is enabled immediately', () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const registry = [makeEntry('mod-a')];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  const btn = nav._children[0];
  assert.equal(btn.disabled, false);
});

// ---------------------------------------------------------------------------
// Tests: module activation and lazy init
// ---------------------------------------------------------------------------

test('activateModule calls loadModule and init(api) on first activation', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const entry = makeEntry('mod-a');
  const mm = createModeManager(nav, slot, state, stubBus, [entry], doc);
  mm.init();

  await mm.activateModule('mod-a');

  assert.deepEqual(entry._initCalls, ['mod-a']);
});

test('re-activating the already-active module short-circuits before init', async () => {
  // Tests the `if (moduleId === activeModuleId) return;` guard at the top
  // of activateModule. Note: this is NOT a guarantee of "init only once per
  // session" — under D-492, init runs every time the user navigates BACK to
  // a module (see "navigating away and back re-runs init" below).
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const entry = makeEntry('mod-a');
  const mm = createModeManager(nav, slot, state, stubBus, [entry], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-a'); // same module already active — no-op

  assert.equal(entry._initCalls.length, 1);
});

test('activateModule is a no-op if module is already active', async () => {
  // Companion to the test above — asserts activeModuleId is unchanged and
  // init did not re-run for the already-active module.
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const entry = makeEntry('mod-a');
  const mm = createModeManager(nav, slot, state, stubBus, [entry], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-a');

  // activeModuleId unchanged; init only ran once because the same-module
  // short-circuit fired (not because of any one-shot init contract).
  assert.equal(mm.activeModuleId, 'mod-a');
  assert.equal(entry._initCalls.length, 1);
});

// ---------------------------------------------------------------------------
// Tests: panel lifecycle — onUnmount callbacks
// ---------------------------------------------------------------------------

test('switching modules calls runUnmount on outgoing module', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const unmountCalls = [];

  const entryA = makeEntry('mod-a');
  const entryB = makeEntry('mod-b');

  // Override loadModule for mod-a to register onUnmount
  let aApi = null;
  entryA.loadModule = () => Promise.resolve({
    init(api) {
      aApi = api;
      api.panel.onUnmount(() => unmountCalls.push('a-unmounted'));
    },
  });

  const mm = createModeManager(nav, slot, state, stubBus, [entryA, entryB], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');

  assert.deepEqual(unmountCalls, ['a-unmounted']);
});

test('onUnmount callbacks fire in registration order', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const order = [];
  const entryA = makeEntry('mod-a');
  entryA.loadModule = () => Promise.resolve({
    init(api) {
      api.panel.onUnmount(() => order.push('first'));
      api.panel.onUnmount(() => order.push('second'));
    },
  });

  const entryB = makeEntry('mod-b');
  const mm = createModeManager(nav, slot, state, stubBus, [entryA, entryB], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');

  assert.deepEqual(order, ['first', 'second']);
});

// ---------------------------------------------------------------------------
// Tests: state.ui updates
// ---------------------------------------------------------------------------

test('activateModule updates state.ui.active_module_id', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  state.setState('ui', { active_module_id: null, nav_history: [] });

  const entry = makeEntry('mod-a');
  const mm = createModeManager(nav, slot, state, stubBus, [entry], doc);
  mm.init();

  await mm.activateModule('mod-a');

  assert.equal(state.getState('ui').active_module_id, 'mod-a');
});

test('nav history grows as modules are activated', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b', 'mod-c']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  state.setState('ui', { active_module_id: null, nav_history: [] });

  const registry = [makeEntry('mod-a'), makeEntry('mod-b'), makeEntry('mod-c')];
  const mm = createModeManager(nav, slot, state, stubBus, registry, doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');
  await mm.activateModule('mod-c');

  // mod-a and mod-b should be in history
  const ui = state.getState('ui');
  assert.ok(ui.nav_history.includes('mod-a'));
  assert.ok(ui.nav_history.includes('mod-b'));
});

// ---------------------------------------------------------------------------
// Tests: D-492 — init() re-runs on every activation (panel re-mount)
// ---------------------------------------------------------------------------

test('D-492: navigating away and back re-runs init() (panel re-mount)', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const entryA = makeEntry('mod-a');
  const entryB = makeEntry('mod-b');
  const mm = createModeManager(nav, slot, state, stubBus, [entryA, entryB], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');
  await mm.activateModule('mod-a'); // back to A — panel must re-mount

  // mod-a init called twice: once on first activation, again on re-activation
  assert.equal(entryA._initCalls.length, 2);
});

test('D-492: each re-mount cycle runs the module\'s onUnmount once', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['mod-a', 'mod-b']);
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const unmountCalls = [];
  const entryA = makeEntry('mod-a');
  entryA.loadModule = () => Promise.resolve({
    init(api) {
      api.panel.onUnmount(() => unmountCalls.push('a-unmounted'));
    },
  });
  const entryB = makeEntry('mod-b');

  const mm = createModeManager(nav, slot, state, stubBus, [entryA, entryB], doc);
  mm.init();

  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');
  await mm.activateModule('mod-a');
  await mm.activateModule('mod-b');

  // Two complete mount→unmount cycles for mod-a → two unmount fires
  assert.deepEqual(unmountCalls, ['a-unmounted', 'a-unmounted']);
});

// ---------------------------------------------------------------------------
// Tests: D-493 — optimiser:apply handoff routing
// ---------------------------------------------------------------------------

test('D-493: optimiser:apply activates placement-editor when inactive', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['optimiser', 'placement-editor']);
  state.setState('ui', { active_module_id: null, nav_history: [] });
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const bus = makeBusForModules(['optimiser', 'placement-editor']);

  const optimiser = makeEntry('optimiser');
  const placementEditor = makeEntry('placement-editor');
  const mm = createModeManager(nav, slot, state, bus, [optimiser, placementEditor], doc);
  mm.init();

  await mm.activateModule('optimiser');
  assert.equal(mm.activeModuleId, 'optimiser');

  // Optimiser emits optimiser:apply. placement-editor is inactive, but the
  // mode-manager must route the event by activating placement-editor and
  // re-emitting so its scoped subscription fires.
  bus.emit('optimiser:apply', { proposed: [{ sensor_name: 'X' }] });

  // Wait for the async activation chain to settle
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));

  assert.equal(mm.activeModuleId, 'placement-editor',
    'mode-manager must activate placement-editor on optimiser:apply');
  assert.ok(placementEditor._initCalls.includes('placement-editor'),
    'placement-editor.init must have run as part of the handoff');
});

test('D-493: optimiser:apply re-emit reaches placement-editor\'s scoped listener', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['optimiser', 'placement-editor']);
  state.setState('ui', { active_module_id: null, nav_history: [] });
  const nav = makeElement('nav');
  const slot = makeElement('div');

  // Use a real bus contract: placement-editor declares subscribes for optimiser:apply
  const contracts = new Map([
    ['optimiser', { emits: ['optimiser:apply'], subscribes: [] }],
    ['placement-editor', { emits: [], subscribes: ['optimiser:apply'] }],
  ]);
  const bus = createBus(contracts);

  // placement-editor.init: register the scoped optimiser:apply listener
  const receivedPayloads = [];
  const placementEditor = makeEntry('placement-editor');
  placementEditor.api = {
    moduleId: 'placement-editor',
    panel: { mount() {}, onUnmount(cb) { placementEditor._unmountCalls.push(cb); } },
    bus: bus.createScopedBus('placement-editor'),
  };
  placementEditor.loadModule = () => Promise.resolve({
    init(api) {
      const off = api.bus.on('optimiser:apply', (p) => receivedPayloads.push(p));
      api.panel.onUnmount(off);
    },
  });

  const optimiser = makeEntry('optimiser');
  const mm = createModeManager(nav, slot, state, bus, [optimiser, placementEditor], doc);
  mm.init();

  await mm.activateModule('optimiser');

  const payload = { proposed: [{ sensor_name: 'Y' }] };
  bus.emit('optimiser:apply', payload);

  // Yield several ticks for the handoff promise chain (activateModule is async)
  for (let i = 0; i < 4; i++) await new Promise(r => setTimeout(r, 0));

  assert.equal(receivedPayloads.length, 1,
    'placement-editor must receive the re-emitted optimiser:apply exactly once');
  assert.deepEqual(receivedPayloads[0], payload);
});

test('D-493: optimiser:apply is a no-op routing when placement-editor already active', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['optimiser', 'placement-editor']);
  state.setState('ui', { active_module_id: null, nav_history: [] });
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const bus = makeBusForModules(['optimiser', 'placement-editor']);

  const optimiser = makeEntry('optimiser');
  const placementEditor = makeEntry('placement-editor');
  const mm = createModeManager(nav, slot, state, bus, [optimiser, placementEditor], doc);
  mm.init();

  await mm.activateModule('placement-editor');
  const initCallsBefore = placementEditor._initCalls.length;

  // Already on placement-editor — router must NOT re-activate or re-emit
  bus.emit('optimiser:apply', { proposed: [] });

  await new Promise(r => setTimeout(r, 0));

  assert.equal(mm.activeModuleId, 'placement-editor');
  assert.equal(placementEditor._initCalls.length, initCallsBefore,
    'placement-editor must not be re-init when handoff target is already active');
});

test('D-493: rapid duplicate optimiser:apply emits collapse to one activation', async () => {
  // Regression guard against the race where a user clicks Apply twice within
  // one tick: both emits hit _routeHandoff before the first's activateModule
  // has yielded, both could schedule interleaved activate-then-reemit
  // sequences. The per-event _pendingHandoff guard must collapse the second
  // emit to a no-op.
  const doc = makeMockDoc();
  const state = makeStateForModules(['optimiser', 'placement-editor']);
  state.setState('ui', { active_module_id: null, nav_history: [] });
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const bus = makeBusForModules(['optimiser', 'placement-editor']);

  const optimiser = makeEntry('optimiser');
  const placementEditor = makeEntry('placement-editor');
  const mm = createModeManager(nav, slot, state, bus, [optimiser, placementEditor], doc);
  mm.init();

  await mm.activateModule('optimiser');

  // Two emits synchronously, no awaits between
  bus.emit('optimiser:apply', { proposed: [{ sensor_name: 'A' }] });
  bus.emit('optimiser:apply', { proposed: [{ sensor_name: 'B' }] });

  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0));

  assert.equal(placementEditor._initCalls.length, 1,
    'rapid duplicate emits must trigger exactly one activation, not race');
});

test('D-493: re-entry guard prevents infinite re-emit loop', async () => {
  const doc = makeMockDoc();
  const state = makeStateForModules(['optimiser', 'placement-editor']);
  state.setState('ui', { active_module_id: null, nav_history: [] });
  const nav = makeElement('nav');
  const slot = makeElement('div');

  const bus = makeBusForModules(['optimiser', 'placement-editor']);

  const optimiser = makeEntry('optimiser');
  const placementEditor = makeEntry('placement-editor');
  const mm = createModeManager(nav, slot, state, bus, [optimiser, placementEditor], doc);
  mm.init();

  await mm.activateModule('optimiser');

  bus.emit('optimiser:apply', { proposed: [] });

  // Drain microtasks: if the guard fails, the router would re-fire the event
  // indefinitely. Yield several macrotasks then assert init was called once.
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0));

  assert.equal(placementEditor._initCalls.length, 1,
    'handoff must result in exactly one placement-editor activation per emit');
});
