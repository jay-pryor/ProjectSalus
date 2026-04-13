/**
 * test-registry.js — Unit tests for module registry.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-registry.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  validateManifestFields,
  validateManifests,
  buildContracts,
  discoverModules,
  createModuleAPI,
} from '../registry.js';
import { createState } from '../state.js';
import { createBus } from '../bus.js';

// ---------------------------------------------------------------------------
// Minimal valid manifest factory
// ---------------------------------------------------------------------------

function makeManifest(overrides = {}) {
  return {
    id: 'test-module',
    label: 'Test Module',
    reads: [],
    writes: [],
    emits: [],
    subscribes: [],
    prerequisites: [],
    layer_id_prefix: 'test-module',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// validateManifestFields — required fields
// ---------------------------------------------------------------------------

test('validateManifestFields returns empty array for valid manifest', () => {
  const errors = validateManifestFields(makeManifest());
  assert.deepEqual(errors, []);
});

test('validateManifestFields reports missing id', () => {
  const m = makeManifest();
  delete m.id;
  const errors = validateManifestFields(m);
  assert.ok(errors.some(e => e.includes('id')), 'expected error about missing id');
});

test('validateManifestFields reports all missing required fields', () => {
  const errors = validateManifestFields({});
  const fields = ['id', 'label', 'reads', 'writes', 'emits', 'subscribes'];
  for (const f of fields) {
    assert.ok(errors.some(e => e.includes(f)), `expected error about '${f}'`);
  }
});

test('validateManifestFields reports unknown state key in reads[]', () => {
  const m = makeManifest({ reads: ['not_a_real_key'] });
  const errors = validateManifestFields(m);
  assert.ok(errors.some(e => e.includes('not_a_real_key')));
});

test('validateManifestFields reports unknown state key in writes[]', () => {
  const m = makeManifest({ writes: ['fake_key'] });
  const errors = validateManifestFields(m);
  assert.ok(errors.some(e => e.includes('fake_key')));
});

test('validateManifestFields reports unknown event in emits[]', () => {
  const m = makeManifest({ emits: ['made:up:event'] });
  const errors = validateManifestFields(m);
  assert.ok(errors.some(e => e.includes('made:up:event')));
});

test('validateManifestFields reports unknown event in subscribes[]', () => {
  const m = makeManifest({ subscribes: ['also:fake'] });
  const errors = validateManifestFields(m);
  assert.ok(errors.some(e => e.includes('also:fake')));
});

test('validateManifestFields accepts valid state keys and events', () => {
  const m = makeManifest({
    reads: ['terrain', 'placements'],
    writes: ['sensor_library'],
    emits: ['terrain:loaded'],
    subscribes: ['scenario:loaded'],
  });
  assert.deepEqual(validateManifestFields(m), []);
});

// ---------------------------------------------------------------------------
// validateManifests — cross-manifest rules
// ---------------------------------------------------------------------------

test('validateManifests returns single valid manifest', () => {
  const { valid, invalid } = validateManifests([makeManifest()]);
  assert.equal(valid.length, 1);
  assert.equal(invalid.length, 0);
});

test('validateManifests detects duplicate module IDs', () => {
  const m1 = makeManifest({ id: 'same', label: 'A' });
  const m2 = makeManifest({ id: 'same', label: 'B', layer_id_prefix: 'same-b' });
  const { invalid } = validateManifests([m1, m2]);
  assert.equal(invalid.length, 1);
  assert.ok(invalid[0].errors.some(e => e.includes('Duplicate')));
});

test('validateManifests detects single-writer violation — both modules flagged', () => {
  const m1 = makeManifest({ id: 'mod-a', writes: ['terrain'], layer_id_prefix: 'mod-a' });
  const m2 = makeManifest({ id: 'mod-b', writes: ['terrain'], layer_id_prefix: 'mod-b' });
  const { valid, invalid } = validateManifests([m1, m2]);
  assert.equal(valid.length, 0);
  assert.equal(invalid.length, 2);
  for (const entry of invalid) {
    assert.ok(entry.errors.some(e => e.includes('Single-writer') && e.includes('terrain')));
  }
});

test('validateManifests detects duplicate layer_id_prefix', () => {
  const m1 = makeManifest({ id: 'mod-a', layer_id_prefix: 'shared-prefix' });
  const m2 = makeManifest({ id: 'mod-b', layer_id_prefix: 'shared-prefix' });
  const { invalid } = validateManifests([m1, m2]);
  assert.ok(invalid.some(e => e.errors.some(err => err.includes('layer_id_prefix'))));
});

test('validateManifests detects unreachable prerequisite', () => {
  // terrain is not written by any module in this set
  const m = makeManifest({ id: 'mod-a', prerequisites: ['terrain'], layer_id_prefix: 'mod-a' });
  const { invalid } = validateManifests([m]);
  assert.equal(invalid.length, 1);
  assert.ok(invalid[0].errors.some(e => e.includes('terrain') && e.includes('prerequisites')));
});

test('validateManifests accepts prerequisite written by another module', () => {
  const writer = makeManifest({ id: 'terrain-loader', writes: ['terrain'], layer_id_prefix: 'terrain-loader' });
  const consumer = makeManifest({ id: 'placement-editor', prerequisites: ['terrain'], layer_id_prefix: 'placement-editor' });
  const { valid, invalid } = validateManifests([writer, consumer]);
  assert.equal(valid.length, 2);
  assert.equal(invalid.length, 0);
});

test('validateManifests skips violating module but keeps valid ones', () => {
  const good = makeManifest({ id: 'good-module', layer_id_prefix: 'good-module' });
  const bad = makeManifest({ id: 'bad-module', reads: ['not_valid_key'], layer_id_prefix: 'bad-module' });
  const { valid, invalid } = validateManifests([good, bad]);
  assert.equal(valid.length, 1);
  assert.equal(valid[0].id, 'good-module');
  assert.equal(invalid.length, 1);
  assert.equal(invalid[0].manifest.id, 'bad-module');
});

// ---------------------------------------------------------------------------
// buildContracts
// ---------------------------------------------------------------------------

test('buildContracts builds stateContracts and busContracts', () => {
  const manifests = [
    makeManifest({ id: 'mod-a', reads: ['terrain'], writes: ['sensor_library'],
                   emits: ['terrain:loaded'], subscribes: ['scenario:loaded'] }),
  ];
  const { stateContracts, busContracts } = buildContracts(manifests);

  const sc = stateContracts.get('mod-a');
  assert.deepEqual(sc.reads, ['terrain']);
  assert.deepEqual(sc.writes, ['sensor_library']);

  const bc = busContracts.get('mod-a');
  assert.deepEqual(bc.emits, ['terrain:loaded']);
  assert.deepEqual(bc.subscribes, ['scenario:loaded']);
});

// ---------------------------------------------------------------------------
// discoverModules — with mock fetch
// ---------------------------------------------------------------------------

function makeFetch(responses) {
  // responses: { [url]: { ok: bool, body: any } }
  return async (url) => {
    const response = responses[url];
    if (!response) {
      return { ok: false, status: 404, json: async () => null };
    }
    return {
      ok: response.ok ?? true,
      status: response.status ?? 200,
      json: async () => response.body,
    };
  };
}

test('discoverModules returns valid manifests from mock fetch', async () => {
  const manifest = makeManifest({ id: 'terrain-loader', layer_id_prefix: 'terrain-loader' });
  const fetchFn = makeFetch({
    './modules/index.json': { body: ['terrain-loader'] },
    './modules/terrain-loader/manifest.json': { body: manifest },
  });

  const result = await discoverModules('.', fetchFn);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 'terrain-loader');
});

test('discoverModules returns empty array when index.json fetch fails', async () => {
  const fetchFn = makeFetch({});
  const result = await discoverModules('.', fetchFn);
  assert.deepEqual(result, []);
});

test('discoverModules skips module whose manifest fetch fails', async () => {
  const fetchFn = makeFetch({
    './modules/index.json': { body: ['missing-module'] },
    // No manifest entry for missing-module
  });
  const result = await discoverModules('.', fetchFn);
  assert.deepEqual(result, []);
});

test('discoverModules skips invalid manifest and loads valid sibling', async () => {
  const good = makeManifest({ id: 'good', layer_id_prefix: 'good' });
  const bad = makeManifest({ id: 'bad', reads: ['not_valid_key'], layer_id_prefix: 'bad' });

  const fetchFn = makeFetch({
    './modules/index.json': { body: ['good', 'bad'] },
    './modules/good/manifest.json': { body: good },
    './modules/bad/manifest.json': { body: bad },
  });

  const result = await discoverModules('.', fetchFn);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 'good');
});

test('discoverModules skips violating module from duplicate-writer pair', async () => {
  const m1 = makeManifest({ id: 'writer-a', writes: ['terrain'], layer_id_prefix: 'writer-a' });
  const m2 = makeManifest({ id: 'writer-b', writes: ['terrain'], layer_id_prefix: 'writer-b' });

  const fetchFn = makeFetch({
    './modules/index.json': { body: ['writer-a', 'writer-b'] },
    './modules/writer-a/manifest.json': { body: m1 },
    './modules/writer-b/manifest.json': { body: m2 },
  });

  const result = await discoverModules('.', fetchFn);
  // Both should be skipped (single-writer violation)
  assert.equal(result.length, 0);
});

// ---------------------------------------------------------------------------
// createModuleAPI
// ---------------------------------------------------------------------------

test('createModuleAPI returns api with correct moduleId', () => {
  const m = makeManifest({ id: 'mod-a', reads: ['terrain'], writes: ['sensor_library'] });
  const state = createState(new Map([['mod-a', { reads: ['terrain'], writes: ['sensor_library'] }]]));
  const bus = createBus(new Map([['mod-a', { emits: [], subscribes: [] }]]));
  const scopedBus = bus.createScopedBus('mod-a');

  const mockProxy = {};
  const mockSlot = { firstChild: null, removeChild() {}, appendChild() {} };

  const { api } = createModuleAPI('mod-a', m, state, scopedBus, mockProxy, mockSlot);

  assert.equal(api.moduleId, 'mod-a');
});

test('createModuleAPI api.panel.onUnmount callbacks fire on runUnmount()', () => {
  const m = makeManifest({ id: 'mod-a' });
  const state = createState(new Map([['mod-a', { reads: [], writes: [] }]]));
  const bus = createBus(new Map([['mod-a', { emits: [], subscribes: [] }]]));
  const scopedBus = bus.createScopedBus('mod-a');

  const mockSlot = { firstChild: null, removeChild() {}, appendChild() {} };

  const calls = [];
  const { api, runUnmount } = createModuleAPI('mod-a', m, state, scopedBus, {}, mockSlot);

  api.panel.onUnmount(() => calls.push('cb1'));
  api.panel.onUnmount(() => calls.push('cb2'));

  runUnmount();

  assert.deepEqual(calls, ['cb1', 'cb2']);
});

test('createModuleAPI runUnmount() clears callbacks after firing', () => {
  const m = makeManifest({ id: 'mod-a' });
  const state = createState(new Map([['mod-a', { reads: [], writes: [] }]]));
  const bus = createBus(new Map([['mod-a', { emits: [], subscribes: [] }]]));
  const scopedBus = bus.createScopedBus('mod-a');

  const mockSlot = { firstChild: null, removeChild() {}, appendChild() {} };

  const calls = [];
  const { api, runUnmount } = createModuleAPI('mod-a', m, state, scopedBus, {}, mockSlot);

  api.panel.onUnmount(() => calls.push('once'));
  runUnmount();
  runUnmount(); // second call should fire nothing

  assert.deepEqual(calls, ['once']);
});
