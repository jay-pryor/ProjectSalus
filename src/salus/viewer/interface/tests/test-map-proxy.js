/**
 * test-map-proxy.js — Unit tests for the scoped map proxy.
 *
 * Run: node --test src/salus/viewer/interface/tests/test-map-proxy.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createMapProxy, LayerPrefixViolation, ALLOWED_MAP_METHODS } from '../map-proxy.js';

// ---------------------------------------------------------------------------
// Mock MapLibreGL map
// ---------------------------------------------------------------------------

function makeMockMap() {
  const calls = [];
  const record = (method, ...args) => calls.push({ method, args });

  return {
    _calls: calls,
    addSource(id, spec) { record('addSource', id, spec); },
    removeSource(id) { record('removeSource', id); },
    getSource(id) { record('getSource', id); return { id }; },
    addLayer(spec, beforeId) { record('addLayer', spec, beforeId); },
    removeLayer(id) { record('removeLayer', id); },
    getLayer(id) { record('getLayer', id); return { id }; },
    setLayoutProperty(layerId, name, value) { record('setLayoutProperty', layerId, name, value); },
    setPaintProperty(layerId, name, value) { record('setPaintProperty', layerId, name, value); },
    on(event, layerOrHandler, handler) { record('on', event, layerOrHandler, handler); },
    off(event, layerOrHandler, handler) { record('off', event, layerOrHandler, handler); },
    getCanvas() { record('getCanvas'); return {}; },
    flyTo(opts) { record('flyTo', opts); },
    fitBounds(bounds, opts) { record('fitBounds', bounds, opts); },
    project(lngLat) { record('project', lngLat); return { x: 0, y: 0 }; },
    unproject(point) { record('unproject', point); return { lng: 0, lat: 0 }; },
    queryRenderedFeatures(point, opts) { record('queryRenderedFeatures', point, opts); return []; },
    // Methods that must NOT be exposed on the proxy
    setStyle() { record('setStyle'); },
    remove() { record('remove'); },
    addControl() { record('addControl'); },
    setTerrain() { record('setTerrain'); },
    setBearing() { record('setBearing'); },
    setPitch() { record('setPitch'); },
  };
}

// ---------------------------------------------------------------------------
// ALLOWED_MAP_METHODS completeness
// ---------------------------------------------------------------------------

test('ALLOWED_MAP_METHODS contains all 16 allowed methods', () => {
  const expected = [
    'addSource', 'removeSource', 'getSource',
    'addLayer', 'removeLayer', 'getLayer',
    'setLayoutProperty', 'setPaintProperty',
    'on', 'off',
    'getCanvas',
    'flyTo', 'fitBounds',
    'project', 'unproject',
    'queryRenderedFeatures',
  ];
  for (const m of expected) {
    assert.ok(ALLOWED_MAP_METHODS.has(m), `Expected '${m}' in ALLOWED_MAP_METHODS`);
  }
  assert.equal(ALLOWED_MAP_METHODS.size, expected.length);
});

// ---------------------------------------------------------------------------
// Prefix enforcement — addSource
// ---------------------------------------------------------------------------

test('addSource() accepts prefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.addSource('terrain-loader:dem', { type: 'raster-dem' });
  assert.equal(mock._calls[0].method, 'addSource');
  assert.equal(mock._calls[0].args[0], 'terrain-loader:dem');
});

test('addSource() throws LayerPrefixViolation for unprefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  assert.throws(
    () => proxy.addSource('dem', { type: 'raster-dem' }),
    (err) => err instanceof LayerPrefixViolation && err.message.includes('terrain-loader')
  );
  assert.equal(mock._calls.length, 0);
});

test('addSource() throws for another module\'s prefix', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'placement-editor');
  assert.throws(
    () => proxy.addSource('terrain-loader:dem', {}),
    (err) => err instanceof LayerPrefixViolation
  );
});

// ---------------------------------------------------------------------------
// Prefix enforcement — addLayer
// ---------------------------------------------------------------------------

test('addLayer() accepts prefixed spec.id', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.addLayer({ id: 'terrain-loader:hillshade', type: 'hillshade', source: 'terrain-loader:dem' });
  assert.equal(mock._calls[0].method, 'addLayer');
});

test('addLayer() throws LayerPrefixViolation for unprefixed spec.id', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  assert.throws(
    () => proxy.addLayer({ id: 'hillshade', type: 'hillshade' }),
    (err) => err instanceof LayerPrefixViolation
  );
});

test('addLayer() passes optional beforeId to underlying map', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.addLayer({ id: 'terrain-loader:fill', type: 'fill', source: 'x' }, 'terrain-loader:hillshade');
  assert.equal(mock._calls[0].args[1], 'terrain-loader:hillshade');
});

test('addLayer() omits beforeId when not provided', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.addLayer({ id: 'terrain-loader:fill', type: 'fill', source: 'x' });
  // Only 1 arg passed to underlying addLayer
  assert.equal(mock._calls[0].args[1], undefined);
});

// ---------------------------------------------------------------------------
// Prefix enforcement — removeSource / removeLayer
// ---------------------------------------------------------------------------

test('removeSource() accepts prefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.removeSource('terrain-loader:dem');
  assert.equal(mock._calls[0].method, 'removeSource');
});

test('removeSource() throws LayerPrefixViolation for unprefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  assert.throws(
    () => proxy.removeSource('dem'),
    (err) => err instanceof LayerPrefixViolation
  );
});

test('removeLayer() accepts prefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  proxy.removeLayer('terrain-loader:hillshade');
  assert.equal(mock._calls[0].method, 'removeLayer');
});

test('removeLayer() throws LayerPrefixViolation for unprefixed ID', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  assert.throws(
    () => proxy.removeLayer('hillshade'),
    (err) => err instanceof LayerPrefixViolation
  );
});

// ---------------------------------------------------------------------------
// Read-only methods — no prefix check
// ---------------------------------------------------------------------------

test('getSource() delegates without prefix check', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  const result = proxy.getSource('any-source');
  assert.deepEqual(result, { id: 'any-source' });
});

test('getLayer() delegates without prefix check', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'terrain-loader');
  const result = proxy.getLayer('any-layer');
  assert.deepEqual(result, { id: 'any-layer' });
});

// ---------------------------------------------------------------------------
// Other delegating methods
// ---------------------------------------------------------------------------

test('flyTo() delegates correctly', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  proxy.flyTo({ center: [10, 20], zoom: 8 });
  assert.equal(mock._calls[0].method, 'flyTo');
  assert.deepEqual(mock._calls[0].args[0], { center: [10, 20], zoom: 8 });
});

test('fitBounds() delegates with and without options', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  proxy.fitBounds([[10, 20], [30, 40]], { padding: 20 });
  assert.equal(mock._calls[0].method, 'fitBounds');
  proxy.fitBounds([[10, 20], [30, 40]]);
  assert.equal(mock._calls[1].method, 'fitBounds');
});

test('getCanvas() delegates correctly', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  proxy.getCanvas();
  assert.equal(mock._calls[0].method, 'getCanvas');
});

test('queryRenderedFeatures() delegates with and without options', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  proxy.queryRenderedFeatures({ x: 100, y: 200 }, { layers: ['foo'] });
  assert.equal(mock._calls[0].method, 'queryRenderedFeatures');
  proxy.queryRenderedFeatures({ x: 100, y: 200 });
  assert.equal(mock._calls[1].method, 'queryRenderedFeatures');
});

// ---------------------------------------------------------------------------
// Raw instance encapsulation
// ---------------------------------------------------------------------------

test('proxy does not expose raw map instance as any property', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  for (const key of Object.getOwnPropertyNames(proxy)) {
    assert.notEqual(proxy[key], mock, `proxy.${key} must not be the raw map instance`);
  }
});

test('proxy is frozen — cannot add new properties', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  assert.throws(() => { proxy._map = mock; }, /Cannot add property/);
});

// ---------------------------------------------------------------------------
// Destructive methods not on proxy
// ---------------------------------------------------------------------------

test('proxy does not expose setStyle', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  assert.equal(proxy.setStyle, undefined);
});

test('proxy does not expose remove', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  assert.equal(proxy.remove, undefined);
});

test('proxy does not expose setTerrain', () => {
  const mock = makeMockMap();
  const proxy = createMapProxy(mock, 'x');
  assert.equal(proxy.setTerrain, undefined);
});
