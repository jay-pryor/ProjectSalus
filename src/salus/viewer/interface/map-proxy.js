/**
 * map-proxy.js — Scoped map proxy for module isolation.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.5 and §2.6 (map:)
 *
 * Invariants enforced:
 *   - Only the 16 listed methods are exposed to regular modules. Destructive
 *     map operations (setStyle, remove, addControl, setTerrain, setBearing,
 *     setPitch) are absent from the proxy and cannot be reached.
 *   - Exception: when options.allowTerrainSource=true (terrain-loader only),
 *     the proxy additionally exposes setTerrainSource() which delegates to
 *     setTerrain() internally (architectural exception per S14.3-3).
 *   - Exception: when options.allowTerrainQuery=true (coord-tools subsystem
 *     only), the proxy additionally exposes queryTerrainElevation() — a
 *     non-destructive read of the 3D terrain (architectural opt-in per I-20).
 *   - addSource(id) and addLayer({id}) must use IDs prefixed with
 *     `{layerIdPrefix}:`. Unprefixed IDs throw LayerPrefixViolation.
 *   - removeSource and removeLayer also enforce the prefix so a module
 *     cannot accidentally remove another module's layers.
 *   - The raw map instance is captured in a closure. There is no property
 *     on the returned object that exposes it.
 *
 * ---------------------------------------------------------------------------
 * S14.7-5 Architectural Decision: drawing interaction approach
 * ---------------------------------------------------------------------------
 * The threat-corridor-editor and zone-editor modules require polygon and
 * route drawing on the map canvas. The spec offered two options:
 *
 *   Option A — Expose addDrawControl(mode)/removeDrawControl() on the proxy
 *              and use a bundled maplibre-gl-draw library.
 *
 *   Option B — Use api.map.on('click'/'dblclick') directly and manage draw
 *              state inside each module with vanilla JS.
 *
 * We chose Option B for the following reasons:
 *   1. addControl is a destructive method (it modifies the map DOM and
 *      lifecycle). Exposing it — even as addDrawControl — weakens the
 *      proxy's isolation guarantee.
 *   2. maplibre-gl-draw requires bundling a significant external dependency
 *      that may conflict with the MapLibreGL version in the shell.
 *   3. The drawing interactions required (click to add point, dblclick to
 *      close, drag to move vertex) map directly onto the 'click', 'dblclick',
 *      'mousedown', 'mousemove', and 'mouseup' events already permitted by
 *      the proxy. No new proxy surface is needed.
 *   4. Module cleanup via api.map.off() is already the established pattern
 *      for listener removal in onUnmount.
 *
 * If a richer drawing UX (snapping, undo, touch) is required in future, the
 * correct upgrade path is to add a dedicated map.addDrawControl() proxy method
 * with its own allowDrawControl flag (mirroring allowTerrainSource) and a
 * corresponding entry in DRAW_EXTRA_METHODS — not to remove this decision.
 * ---------------------------------------------------------------------------
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
// Allowed map method names — base set available to all modules.
// When options.allowTerrainSource=true, setTerrainSource is also present on
// the proxy (architectural exception for terrain-loader only — D-331).
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

/** Extra method present only when options.allowTerrainSource=true. */
export const TERRAIN_LOADER_EXTRA_METHODS = new Set(['setTerrainSource']);

/** Extra method present only when options.allowTerrainQuery=true. */
export const COORD_TOOLS_EXTRA_METHODS = new Set(['queryTerrainElevation']);

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a scoped map proxy for a module.
 *
 * @param {object} mapInstance - raw MapLibreGL Map instance (captured in closure)
 * @param {string} layerIdPrefix - module's layer_id_prefix from manifest
 * @param {object} [options]
 * @param {boolean} [options.allowTerrainSource=false] - when true, adds the
 *   setTerrainSource(sourceId) method. This is an architectural exception for the
 *   terrain-loader module only — no other module should modify the map's terrain
 *   property. The shell sets this flag explicitly for terrain-loader.
 * @param {boolean} [options.allowTerrainQuery=false] - when true, adds the
 *   queryTerrainElevation(lngLat) method. This is an architectural opt-in for
 *   the coord-tools shell-owned subsystem only. The shell sets this flag
 *   explicitly for the coord-tools map proxy.
 * @returns {object} restricted map handle
 */
export function createMapProxy(mapInstance, layerIdPrefix, options = {}) {
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
  const proxy = {
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
  };

  // Architectural exception: terrain-loader is the only module that may
  // update the map's 3D terrain source.  The shell enables this via
  // options.allowTerrainSource; all other modules get no such method.
  if (options.allowTerrainSource) {
    proxy.setTerrainSource = function setTerrainSource(sourceId) {
      // sourceId === null clears the 3D terrain canvas
      return sourceId === null
        ? mapInstance.setTerrain(null)
        : mapInstance.setTerrain({ source: sourceId });
    };
  }

  // Architectural opt-in: the coord-tools subsystem reads the ground
  // elevation under the cursor to build its Z readout (I-21). queryTerrain-
  // Elevation is a pure read — it samples the already-loaded 3D terrain and
  // mutates no map state — so exposing it weakens no isolation guarantee;
  // it is gated behind a flag only so the surface stays minimal for modules
  // that have no need of it. The shell enables this via options.allow-
  // TerrainQuery for the coord-tools map proxy alone.
  //
  // Return contract (D-603): MapLibre's queryTerrainElevation returns a
  // number in metres, or `null` when no 3D terrain source is set (no DEM
  // loaded yet) or the point lies outside the loaded terrain tiles. The
  // proxy delegates that contract verbatim — callers (the I-21 Z readout)
  // MUST treat `null` as "elevation unavailable" and not as a coordinate.
  if (options.allowTerrainQuery) {
    /**
     * Sample the ground elevation of the 3D terrain under a lng/lat.
     * @param {[number, number]|object} lngLat - MapLibre LngLatLike
     * @returns {number|null} elevation in metres, or null when no terrain
     *   is loaded or the point is outside the loaded tiles.
     */
    proxy.queryTerrainElevation = function queryTerrainElevation(lngLat) {
      return mapInstance.queryTerrainElevation(lngLat);
    };
  }

  return Object.freeze(proxy);
}
