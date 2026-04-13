/**
 * test-state.js — Unit tests for the state proxy.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-state.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createState, StateContractViolation, StateSerialiseViolation } from '../state.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeState(overrides = {}) {
  const contracts = new Map([
    ['module-a', { reads: ['terrain', 'placements'], writes: ['sensor_library'] }],
    ['module-b', { reads: [], writes: ['terrain'] }],
    ...Object.entries(overrides).map(([id, c]) => [id, c]),
  ]);
  return createState(contracts);
}

// ---------------------------------------------------------------------------
// get() tests
// ---------------------------------------------------------------------------

test('get() returns null for unset key', () => {
  const state = makeState();
  assert.equal(state.get('module-a', 'terrain'), null);
});

test('get() returns deep-frozen clone after set', () => {
  const state = makeState();
  state.setState('sensor_library', [{ name: 'Radar-1' }]);

  const val = state.get('module-a', 'sensor_library');
  assert.deepEqual(val, [{ name: 'Radar-1' }]);
  // Must be frozen
  assert.throws(() => { val[0].name = 'mutated'; }, /Cannot assign/);
});

test('get() throws StateContractViolation for undeclared key', () => {
  const state = makeState();
  assert.throws(
    () => state.get('module-a', 'zones'),
    (err) => err instanceof StateContractViolation
      && err.message.includes('module-a')
      && err.message.includes('zones')
  );
});

test('get() throws StateContractViolation for unknown module', () => {
  const state = makeState();
  assert.throws(
    () => state.get('ghost-module', 'terrain'),
    (err) => err instanceof StateContractViolation && err.message.includes('ghost-module')
  );
});

test('get() throws StateContractViolation for invalid state key', () => {
  const state = makeState();
  assert.throws(
    () => state.get('module-a', 'not_a_real_key'),
    (err) => err instanceof StateContractViolation && err.message.includes('not_a_real_key')
  );
});

test('get() allows reading a key that is in writes[] (writer can also read)', () => {
  const state = makeState();
  state.setState('sensor_library', ['x']);
  assert.deepEqual(state.get('module-a', 'sensor_library'), ['x']);
});

// ---------------------------------------------------------------------------
// set() tests
// ---------------------------------------------------------------------------

test('set() writes value and returns undefined', () => {
  const state = makeState();
  const result = state.set('module-b', 'terrain', { dem_path: '/a/b.tif' });
  assert.equal(result, undefined);
  assert.deepEqual(state.getState('terrain'), { dem_path: '/a/b.tif' });
});

test('set() throws StateContractViolation for key not in writes[]', () => {
  const state = makeState();
  assert.throws(
    () => state.set('module-a', 'terrain', {}),
    (err) => err instanceof StateContractViolation
      && err.message.includes('module-a')
      && err.message.includes('terrain')
  );
});

test('set() throws StateContractViolation for unknown module', () => {
  const state = makeState();
  assert.throws(
    () => state.set('ghost-module', 'terrain', {}),
    (err) => err instanceof StateContractViolation
  );
});

test('set() throws StateSerialiseViolation for a plain function value', () => {
  const state = makeState();
  // JSON.stringify(() => {}) returns undefined; JSON.parse(undefined) throws.
  assert.throws(
    () => state.set('module-b', 'terrain', () => {}),
    (err) => err instanceof StateSerialiseViolation
  );
});

test('set() throws StateSerialiseViolation for undefined', () => {
  const state = makeState();
  assert.throws(
    () => state.set('module-b', 'terrain', undefined),
    (err) => err instanceof StateSerialiseViolation
  );
});

test('set() throws StateSerialiseViolation for a circular reference', () => {
  const state = makeState();
  const obj = {};
  obj.self = obj; // circular reference — JSON.stringify throws TypeError
  assert.throws(
    () => state.set('module-b', 'terrain', obj),
    (err) => err instanceof StateSerialiseViolation
  );
});

test('set() accepts null', () => {
  const state = makeState();
  state.set('module-b', 'terrain', null);
  assert.equal(state.getState('terrain'), null);
});

test('set() accepts arrays and nested objects', () => {
  const state = makeState();
  const payload = { sensors: [{ id: 's1', pos: [1.0, 2.0] }] };
  state.set('module-a', 'sensor_library', payload);
  assert.deepEqual(state.getState('sensor_library'), payload);
});

// ---------------------------------------------------------------------------
// watch() and watcher notification tests
// ---------------------------------------------------------------------------

test('watch() fires callback synchronously on set()', () => {
  const state = makeState();
  const calls = [];
  state.watch('terrain', (newVal, oldVal) => calls.push({ newVal, oldVal }));

  state.set('module-b', 'terrain', { dem_path: '/x.tif' });

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].newVal, { dem_path: '/x.tif' });
  assert.equal(calls[0].oldVal, null);
});

test('watch() fires with correct oldVal on second set()', () => {
  const state = makeState();
  const calls = [];
  state.watch('terrain', (n, o) => calls.push({ n, o }));

  state.set('module-b', 'terrain', { dem_path: '/a.tif' });
  state.set('module-b', 'terrain', { dem_path: '/b.tif' });

  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1].o, { dem_path: '/a.tif' });
  assert.deepEqual(calls[1].n, { dem_path: '/b.tif' });
});

test('watch() fires on setState() (shell bypass)', () => {
  const state = makeState();
  const calls = [];
  state.watch('terrain', (n) => calls.push(n));
  state.setState('terrain', { dem_path: '/shell.tif' });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], { dem_path: '/shell.tif' });
});

test('watch() unsubscribe stops further notifications', () => {
  const state = makeState();
  const calls = [];
  const unsubscribe = state.watch('terrain', (n) => calls.push(n));

  state.set('module-b', 'terrain', { dem_path: '/a.tif' });
  unsubscribe();
  state.set('module-b', 'terrain', { dem_path: '/b.tif' });

  assert.equal(calls.length, 1);
});

test('watch() multiple watchers all fire', () => {
  const state = makeState();
  const a = [];
  const b = [];
  state.watch('terrain', (n) => a.push(n));
  state.watch('terrain', (n) => b.push(n));

  state.set('module-b', 'terrain', { dem_path: '/x.tif' });

  assert.equal(a.length, 1);
  assert.equal(b.length, 1);
});

test('watcher error does not break subsequent watchers', () => {
  const state = makeState();
  const calls = [];
  state.watch('terrain', () => { throw new Error('watcher boom'); });
  state.watch('terrain', (n) => calls.push(n));

  assert.doesNotThrow(() => state.set('module-b', 'terrain', { dem_path: '/x.tif' }));
  assert.equal(calls.length, 1);
});

// ---------------------------------------------------------------------------
// setState / getState (shell-only bypass)
// ---------------------------------------------------------------------------

test('setState() bypasses all checks', () => {
  const state = makeState();
  // Writing a key not in any module's writes[] — shell bypass must succeed
  state.setState('zones', { priority: [], exclusion: [] });
  assert.deepEqual(state.getState('zones'), { priority: [], exclusion: [] });
});

test('getState() returns null for never-set key', () => {
  const state = makeState();
  assert.equal(state.getState('zones'), null);
});
