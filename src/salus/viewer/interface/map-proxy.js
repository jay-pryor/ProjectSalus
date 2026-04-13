/**
 * map-proxy.js — Scoped map proxy for module isolation.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.5 and §2.6 (map:)
 *
 * Invariants enforced:
 *   - Only the 15 listed methods are exposed. Destructive map operations
 *     (setStyle, remove, addControl, setTerrain, setBearing, setPitch) are
 *     absent from the proxy and cannot be reached.
 *   - addSource(id) and addLayer({id}) must use IDs prefixed with
 *     `{layerIdPrefix}:`. Unprefixed IDs throw LayerPrefixViolation.
 *   - removeSource and removeLayer also enforce the prefix so a module
 *     cannot accidentally remove another module's layers.
 *   - The raw map instance is captured in a closure. There is no property
 *     on the returned object that exposes it.
 */

// ---------------------------------------------------------------------------
// Custom error type
// ---------------------------------------------------------------------------

export class LayerPrefixViolation extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'LayerPrefixViolation';
  }
}

// ---------------------------------------------------------------------------
// Allowed map method names (informational — not used for runtime dispatch,
// but useful for documentation and testing completeness).
// ---------------------------------------------------------------------------

export const ALLOWED_MAP_METHODS = new Set([
  'addSource', 'removeSource', 'getSource',
  'addLayer', 'removeLayer', 'getLayer',
  'setLayoutProperty', 'setPaintProperty',
  'on', 'off',
  'getCanvas',
  'flyTo', 'fitBounds',
  'project', 'unproject',
  'queryRenderedFeatures',
]);

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a scoped map proxy for a module.
 *
 * @param {object} mapInstance - raw MapLibreGL Map instance (captured in closure)
 * @param {string} layerIdPrefix - module's layer_id_prefix from manifest
 * @returns {object} restricted map handle
 */
export function createMapProxy(mapInstance, layerIdPrefix) {
  const prefix = layerIdPrefix + ':';

  function assertPrefix(id, methodName) {
    if (!id.startsWith(prefix)) {
      throw new LayerPrefixViolation(
        `${methodName}('${id}') — ID must start with '${prefix}' ` +
        `(module layer_id_prefix: '${layerIdPrefix}')`
      );
    }
  }

  // Each method is an explicit delegation — no dynamic dispatch, no way to
  // access the raw instance via getOwnPropertyNames or prototype walking.
  return Object.freeze({
    addSource(id, spec) {
      assertPrefix(id, 'addSource');
      return mapInstance.addSource(id, spec);
    },
    removeSource(id) {
      assertPrefix(id, 'removeSource');
      return mapInstance.removeSource(id);
    },
    getSource(id) {
      return mapInstance.getSource(id);
    },
    addLayer(spec, beforeId) {
      assertPrefix(spec.id, 'addLayer');
      return beforeId !== undefined
        ? mapInstance.addLayer(spec, beforeId)
        : mapInstance.addLayer(spec);
    },
    removeLayer(id) {
      assertPrefix(id, 'removeLayer');
      return mapInstance.removeLayer(id);
    },
    getLayer(id) {
      return mapInstance.getLayer(id);
    },
    setLayoutProperty(layerId, name, value) {
      return mapInstance.setLayoutProperty(layerId, name, value);
    },
    setPaintProperty(layerId, name, value) {
      return mapInstance.setPaintProperty(layerId, name, value);
    },
    on(event, layerIdOrHandler, handler) {
      return handler !== undefined
        ? mapInstance.on(event, layerIdOrHandler, handler)
        : mapInstance.on(event, layerIdOrHandler);
    },
    off(event, layerIdOrHandler, handler) {
      return handler !== undefined
        ? mapInstance.off(event, layerIdOrHandler, handler)
        : mapInstance.off(event, layerIdOrHandler);
    },
    getCanvas() {
      return mapInstance.getCanvas();
    },
    flyTo(options) {
      return mapInstance.flyTo(options);
    },
    fitBounds(bounds, options) {
      return options !== undefined
        ? mapInstance.fitBounds(bounds, options)
        : mapInstance.fitBounds(bounds);
    },
    project(lngLat) {
      return mapInstance.project(lngLat);
    },
    unproject(point) {
      return mapInstance.unproject(point);
    },
    queryRenderedFeatures(point, options) {
      return options !== undefined
        ? mapInstance.queryRenderedFeatures(point, options)
        : mapInstance.queryRenderedFeatures(point);
    },
  });
}
