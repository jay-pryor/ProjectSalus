/**
 * state.js — Shared state store with per-module contract enforcement.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.3
 *
 * Invariants enforced here:
 *   - Modules may only read keys declared in reads[] or writes[].
 *   - Modules may only write keys declared in writes[].
 *   - Written values must be JSON-serialisable (no functions, DOM nodes, etc.).
 *   - Returned values are deep-frozen to prevent mutation without set().
 *
 * Multi-user note: set() is synchronous and notifies watchers immediately.
 * The interface (set → watcher call) is the seam for async state in multi-user:
 * modules that follow watch() will require no changes if set() becomes async.
 */

import { VALID_STATE_KEYS } from './state-schema.js';

// ---------------------------------------------------------------------------
// Custom error types
// ---------------------------------------------------------------------------

export class StateContractViolation extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'StateContractViolation';
  }
}

export class StateSerialiseViolation extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'StateSerialiseViolation';
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isSerializable(value) {
  if (value === undefined) return false;
  try {
    JSON.parse(JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function deepFreeze(obj) {
  if (obj === null || typeof obj !== 'object') return obj;
  for (const key of Object.keys(obj)) {
    deepFreeze(obj[key]);
  }
  return Object.freeze(obj);
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create the shared state store.
 *
 * @param {Map<string, {reads: string[], writes: string[]}>} moduleContracts
 *   Map of moduleId → {reads, writes} from validated manifests.
 * @returns {{ get, set, watch, setState, getState }}
 */
export function createState(moduleContracts) {
  // Raw values — never exposed directly.
  const _values = {};

  // key → Set<callback>
  const _watchers = new Map();

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  function _notify(key, newVal, oldVal) {
    const cbs = _watchers.get(key);
    if (!cbs) return;
    for (const cb of cbs) {
      try {
        cb(newVal, oldVal);
      } catch (err) {
        console.error(`State watcher error on key '${key}':`, err);
      }
    }
  }

  function _contract(moduleId) {
    const c = moduleContracts.get(moduleId);
    if (!c) {
      throw new StateContractViolation(`Unknown module: '${moduleId}'`);
    }
    return c;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Read a state key for a module.
     * Returns a deep-frozen clone of the value (null if unset).
     * Throws StateContractViolation if the key is not declared in reads[] or writes[].
     */
    get(moduleId, key) {
      if (!VALID_STATE_KEYS.has(key)) {
        throw new StateContractViolation(`'${key}' is not a valid state key`);
      }
      const { reads, writes } = _contract(moduleId);
      if (!reads.includes(key) && !writes.includes(key)) {
        throw new StateContractViolation(
          `Module '${moduleId}' attempted to read '${key}' but did not declare it in reads[] or writes[]`
        );
      }
      const raw = _values[key] ?? null;
      return deepFreeze(structuredClone(raw));
    },

    /**
     * Write a state key for a module.
     * Throws StateContractViolation if key not in writes[].
     * Throws StateSerialiseViolation if value is not JSON-serialisable.
     * Notifies watchers synchronously after write.
     */
    set(moduleId, key, value) {
      if (!VALID_STATE_KEYS.has(key)) {
        throw new StateContractViolation(`'${key}' is not a valid state key`);
      }
      const { writes } = _contract(moduleId);
      if (!writes.includes(key)) {
        throw new StateContractViolation(
          `Module '${moduleId}' attempted to write '${key}' but only declared writes: [${writes.join(', ')}]`
        );
      }
      if (!isSerializable(value)) {
        throw new StateSerialiseViolation(
          `Module '${moduleId}' attempted to write non-serialisable value to '${key}'`
        );
      }
      const old = _values[key] ?? null;
      _values[key] = value;
      _notify(key, value, old);
    },

    /**
     * Subscribe to changes on a key.
     * Callback receives (newValue, oldValue).
     * Returns an unsubscribe function — call it in api.panel.onUnmount().
     * No contract check: any caller may watch any valid key.
     */
    watch(key, callback) {
      if (!_watchers.has(key)) _watchers.set(key, new Set());
      _watchers.get(key).add(callback);
      return () => {
        const set = _watchers.get(key);
        if (set) set.delete(callback);
      };
    },

    /**
     * Shell-only bypass — writes directly without contract checks.
     * Used for initial state population and scenario load/save.
     */
    setState(key, value) {
      const old = _values[key] ?? null;
      _values[key] = value;
      _notify(key, value, old);
    },

    /**
     * Shell-only direct read without contract checks.
     */
    getState(key) {
      return _values[key] ?? null;
    },
  };
}
