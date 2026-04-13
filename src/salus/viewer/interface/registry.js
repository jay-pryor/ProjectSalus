/**
 * registry.js — Module discovery, manifest validation, and API injection.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.2, §2.7, §2.8
 *
 * Validation rules enforced at startup:
 *   1. Required fields present: id, label, reads, writes, emits, subscribes
 *   2. ID uniqueness across loaded modules
 *   3. Valid state keys: all reads[]/writes[] in VALID_STATE_KEYS
 *   4. Single writer: no state key in writes[] also declared by another module
 *   5. Valid events: all emits[]/subscribes[] in VALID_EVENTS
 *   6. Reachable prerequisites: prerequisites[] keys are written by some loaded module
 *   7. Unique layer_id_prefix across loaded modules
 *
 * A module that fails any rule is logged and skipped. The shell continues.
 */

import { VALID_STATE_KEYS, VALID_EVENTS } from './state-schema.js';

// ---------------------------------------------------------------------------
// Required manifest fields
// ---------------------------------------------------------------------------

const REQUIRED_FIELDS = ['id', 'label', 'reads', 'writes', 'emits', 'subscribes'];

// ---------------------------------------------------------------------------
// Single-manifest field validation
// ---------------------------------------------------------------------------

/**
 * Validate a single manifest against field-level rules only.
 * Does not check cross-manifest invariants (uniqueness, single-writer, etc.)
 *
 * @param {object} manifest - raw manifest object
 * @returns {string[]} error messages; empty array means the manifest is field-valid
 */
export function validateManifestFields(manifest) {
  const errors = [];

  // Rule 1: Required fields
  for (const field of REQUIRED_FIELDS) {
    if (!(field in manifest)) {
      errors.push(`Missing required field: '${field}'`);
    }
  }
  if (errors.length > 0) return errors;

  // Rule 3: Valid state keys
  for (const key of manifest.reads ?? []) {
    if (!VALID_STATE_KEYS.has(key)) {
      errors.push(`reads[] contains unknown state key: '${key}'`);
    }
  }
  for (const key of manifest.writes ?? []) {
    if (!VALID_STATE_KEYS.has(key)) {
      errors.push(`writes[] contains unknown state key: '${key}'`);
    }
  }

  // Rule 5: Valid events
  for (const event of manifest.emits ?? []) {
    if (!VALID_EVENTS.has(event)) {
      errors.push(`emits[] contains unknown event: '${event}'`);
    }
  }
  for (const event of manifest.subscribes ?? []) {
    if (!VALID_EVENTS.has(event)) {
      errors.push(`subscribes[] contains unknown event: '${event}'`);
    }
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Cross-manifest validation
// ---------------------------------------------------------------------------

/**
 * Validate a collection of manifests against all rules including cross-manifest
 * invariants (uniqueness, single-writer, prerequisites, layer prefix).
 *
 * @param {object[]} manifests - array of raw manifest objects
 * @returns {{ valid: object[], invalid: {manifest: object, errors: string[]}[] }}
 */
export function validateManifests(manifests) {
  const invalid = [];
  const fieldValidated = [];

  // --- First pass: field-level validation and ID uniqueness ---
  const seenIds = new Set();

  for (const manifest of manifests) {
    const errors = validateManifestFields(manifest);

    if ('id' in manifest) {
      if (seenIds.has(manifest.id)) {
        errors.push(`Duplicate module id: '${manifest.id}'`);
      } else {
        seenIds.add(manifest.id);
      }
    }

    if (errors.length > 0) {
      invalid.push({ manifest, errors });
    } else {
      fieldValidated.push(manifest);
    }
  }

  // --- Build lookup structures for cross-manifest checks ---

  // Rule 4: key → Set<moduleId> for single-writer detection
  const keyWriters = new Map();
  for (const manifest of fieldValidated) {
    for (const key of manifest.writes ?? []) {
      if (!keyWriters.has(key)) keyWriters.set(key, new Set());
      keyWriters.get(key).add(manifest.id);
    }
  }

  // Rule 6: all state keys written by any field-valid module
  const allWrittenKeys = new Set(keyWriters.keys());

  // --- Second pass: cross-manifest validation ---
  const valid = [];
  const seenPrefixes = new Set();

  for (const manifest of fieldValidated) {
    const errors = [];

    // Rule 4: Single writer
    for (const key of manifest.writes ?? []) {
      const writers = keyWriters.get(key);
      if (writers && writers.size > 1) {
        const others = [...writers].filter(id => id !== manifest.id).join(', ');
        errors.push(
          `Single-writer violation: '${key}' is also declared in writes[] by: ${others}`
        );
      }
    }

    // Rule 6: Reachable prerequisites
    for (const key of manifest.prerequisites ?? []) {
      if (!allWrittenKeys.has(key)) {
        errors.push(
          `prerequisites[] key '${key}' is not written by any loaded module`
        );
      }
    }

    // Rule 7: Unique layer_id_prefix
    const prefix = manifest.layer_id_prefix ?? manifest.id;
    if (seenPrefixes.has(prefix)) {
      errors.push(`Duplicate layer_id_prefix: '${prefix}'`);
    } else {
      seenPrefixes.add(prefix);
    }

    if (errors.length > 0) {
      invalid.push({ manifest, errors });
    } else {
      valid.push(manifest);
    }
  }

  return { valid, invalid };
}

// ---------------------------------------------------------------------------
// Contract extraction
// ---------------------------------------------------------------------------

/**
 * Build per-module contract maps for the state proxy and event bus.
 *
 * @param {object[]} validManifests - manifests that passed validateManifests()
 * @returns {{
 *   stateContracts: Map<string, {reads: string[], writes: string[]}>,
 *   busContracts: Map<string, {emits: string[], subscribes: string[]}>
 * }}
 */
export function buildContracts(validManifests) {
  const stateContracts = new Map();
  const busContracts = new Map();

  for (const manifest of validManifests) {
    stateContracts.set(manifest.id, {
      reads: manifest.reads ?? [],
      writes: manifest.writes ?? [],
    });
    busContracts.set(manifest.id, {
      emits: manifest.emits ?? [],
      subscribes: manifest.subscribes ?? [],
    });
  }

  return { stateContracts, busContracts };
}

// ---------------------------------------------------------------------------
// Module discovery
// ---------------------------------------------------------------------------

/**
 * Discover and validate all modules by fetching modules/index.json then
 * each module's manifest.json.  Invalid modules are logged and skipped —
 * a bad module never crashes the shell.
 *
 * @param {string} baseUrl - interface root URL (e.g. '.' or 'http://localhost:5000')
 * @param {Function} [fetchFn] - injectable fetch implementation (default: global fetch)
 * @returns {Promise<object[]>} array of valid, validated manifest objects
 */
export async function discoverModules(baseUrl, fetchFn = globalThis.fetch) {
  const indexUrl = `${baseUrl}/modules/index.json`;
  let moduleIds;

  try {
    const resp = await fetchFn(indexUrl);
    if (!resp.ok) {
      console.error(`[registry] Failed to load module index: ${indexUrl} (HTTP ${resp.status})`);
      return [];
    }
    moduleIds = await resp.json();
  } catch (err) {
    console.error(`[registry] Failed to load module index: ${err.message}`);
    return [];
  }

  if (!Array.isArray(moduleIds)) {
    console.error(`[registry] modules/index.json must be a JSON array of module IDs`);
    return [];
  }

  // Fetch each manifest; skip modules whose fetch fails
  const rawManifests = [];
  for (const id of moduleIds) {
    const manifestUrl = `${baseUrl}/modules/${id}/manifest.json`;
    try {
      const resp = await fetchFn(manifestUrl);
      if (!resp.ok) {
        console.warn(
          `[registry] Skipping module '${id}': manifest fetch failed (HTTP ${resp.status})`
        );
        continue;
      }
      const manifest = await resp.json();
      // Guard: manifest.json must be a non-null plain object, not an array or primitive
      if (manifest === null || typeof manifest !== 'object' || Array.isArray(manifest)) {
        console.warn(
          `[registry] Skipping module '${id}': manifest.json must be a JSON object, got ${
            manifest === null ? 'null' : Array.isArray(manifest) ? 'array' : typeof manifest
          }`
        );
        continue;
      }
      rawManifests.push(manifest);
    } catch (err) {
      console.warn(`[registry] Skipping module '${id}': ${err.message}`);
    }
  }

  // Validate all fetched manifests together (cross-manifest rules need the full set)
  const { valid, invalid } = validateManifests(rawManifests);

  for (const { manifest, errors } of invalid) {
    console.warn(
      `[registry] Skipping module '${manifest.id ?? '(unknown)'}': ${errors.join('; ')}`
    );
  }

  return valid;
}

// ---------------------------------------------------------------------------
// API injection
// ---------------------------------------------------------------------------

/**
 * Construct the injected API object for a module (Section 2.6).
 * The raw state, bus, and map instances are never included.
 *
 * @param {string} moduleId
 * @param {object} manifest - validated manifest for this module
 * @param {object} state - full state store (createState() return value)
 * @param {object} scopedBus - scoped bus handle (createScopedBus(moduleId))
 * @param {object} mapProxy - scoped map proxy (createMapProxy())
 * @param {HTMLElement} panelSlot - DOM element that panels mount into
 * @returns {{ api: object, runUnmount: Function }}
 */
export function createModuleAPI(moduleId, manifest, state, scopedBus, mapProxy, panelSlot) {
  const unmountCallbacks = [];

  /**
   * Run all registered onUnmount callbacks and clear the list.
   * Called by the mode manager when deactivating this module.
   */
  function runUnmount() {
    for (const cb of unmountCallbacks) {
      try {
        cb();
      } catch (err) {
        console.error(`[${moduleId}] onUnmount callback threw:`, err);
      }
    }
    unmountCallbacks.length = 0;
  }

  const api = Object.freeze({
    moduleId,

    state: Object.freeze({
      get(key) {
        return state.get(moduleId, key);
      },
      set(key, value) {
        return state.set(moduleId, key, value);
      },
      watch(key, callback) {
        return state.watch(key, callback);
      },
    }),

    bus: Object.freeze({
      emit(event, data) {
        return scopedBus.emit(event, data);
      },
      on(event, callback) {
        return scopedBus.on(event, callback);
      },
    }),

    map: mapProxy,

    panel: Object.freeze({
      mount(element) {
        if (element == null || typeof element !== 'object' || typeof element.nodeType !== 'number') {
          throw new TypeError(
            `api.panel.mount(element): expected a DOM Element, got ${element === null ? 'null' : typeof element}`
          );
        }
        while (panelSlot.firstChild) {
          panelSlot.removeChild(panelSlot.firstChild);
        }
        panelSlot.appendChild(element);
      },
      onUnmount(callback) {
        unmountCallbacks.push(callback);
      },
    }),
  });

  return { api, runUnmount };
}
