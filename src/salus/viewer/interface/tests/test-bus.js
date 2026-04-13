/**
 * test-bus.js — Unit tests for the event bus.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-bus.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createBus, EventContractViolation } from '../bus.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeBus(overrides = {}) {
  const contracts = new Map([
    ['module-a', { emits: ['terrain:loaded'], subscribes: ['scenario:loaded'] }],
    ['module-b', { emits: ['placement:added'], subscribes: ['terrain:loaded'] }],
    ...Object.entries(overrides).map(([id, c]) => [id, c]),
  ]);
  return createBus(contracts);
}

// ---------------------------------------------------------------------------
// createScopedBus — unknown module
// ---------------------------------------------------------------------------

test('createScopedBus throws EventContractViolation for unknown module', () => {
  const bus = makeBus();
  assert.throws(
    () => bus.createScopedBus('ghost'),
    (err) => err instanceof EventContractViolation && err.message.includes('ghost')
  );
});

// ---------------------------------------------------------------------------
// emit() contract enforcement
// ---------------------------------------------------------------------------

test('emit() throws EventContractViolation for undeclared event', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  assert.throws(
    () => scopedA.emit('placement:added', {}),
    (err) => err instanceof EventContractViolation
      && err.message.includes('module-a')
      && err.message.includes('placement:added')
  );
});

test('emit() throws EventContractViolation for invalid event name', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  assert.throws(
    () => scopedA.emit('not:a:real:event', {}),
    (err) => err instanceof EventContractViolation
  );
});

// ---------------------------------------------------------------------------
// on() contract enforcement
// ---------------------------------------------------------------------------

test('on() throws EventContractViolation for undeclared subscription', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  assert.throws(
    () => scopedA.on('terrain:loaded', () => {}),
    (err) => err instanceof EventContractViolation
      && err.message.includes('module-a')
      && err.message.includes('terrain:loaded')
  );
});

test('on() throws EventContractViolation for invalid event name', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  assert.throws(
    () => scopedA.on('not:valid', () => {}),
    (err) => err instanceof EventContractViolation
  );
});

// ---------------------------------------------------------------------------
// emit → on cross-module delivery
// ---------------------------------------------------------------------------

test('declared emit fires declared subscriber in other module', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  const scopedB = bus.createScopedBus('module-b');

  const received = [];
  scopedB.on('terrain:loaded', (data) => received.push(data));
  scopedA.emit('terrain:loaded', { source: 'test' });

  assert.equal(received.length, 1);
  assert.deepEqual(received[0], { source: 'test' });
});

test('emit data is passed correctly to multiple subscribers', () => {
  const bus = makeBus({
    'module-c': { emits: ['terrain:loaded'], subscribes: ['terrain:loaded'] },
  });
  const scopedA = bus.createScopedBus('module-a');
  const scopedB = bus.createScopedBus('module-b');
  const scopedC = bus.createScopedBus('module-c');

  const b_received = [];
  const c_received = [];
  scopedB.on('terrain:loaded', (d) => b_received.push(d));
  scopedC.on('terrain:loaded', (d) => c_received.push(d));

  scopedA.emit('terrain:loaded', { dem_path: '/x.tif' });

  assert.equal(b_received.length, 1);
  assert.equal(c_received.length, 1);
  assert.deepEqual(b_received[0], { dem_path: '/x.tif' });
});

// ---------------------------------------------------------------------------
// on() unsubscribe
// ---------------------------------------------------------------------------

test('on() returns unsubscribe function that stops delivery', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');
  const scopedB = bus.createScopedBus('module-b');

  const received = [];
  const unsub = scopedB.on('terrain:loaded', (d) => received.push(d));

  scopedA.emit('terrain:loaded', { n: 1 });
  unsub();
  scopedA.emit('terrain:loaded', { n: 2 });

  assert.equal(received.length, 1);
  assert.deepEqual(received[0], { n: 1 });
});

// ---------------------------------------------------------------------------
// Shell-level unrestricted bus
// ---------------------------------------------------------------------------

test('shell-level emit fires cross-module subscriber', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');

  const received = [];
  const unsub = scopedA.on('scenario:loaded', (d) => received.push(d));

  bus.emit('scenario:loaded', { version: 2 });
  unsub();

  assert.equal(received.length, 1);
  assert.deepEqual(received[0], { version: 2 });
});

test('shell-level on() receives events from scoped modules', () => {
  const bus = makeBus();
  const scopedA = bus.createScopedBus('module-a');

  const received = [];
  const unsub = bus.on('terrain:loaded', (d) => received.push(d));

  scopedA.emit('terrain:loaded', { x: 1 });
  unsub();

  assert.equal(received.length, 1);
  assert.deepEqual(received[0], { x: 1 });
});
