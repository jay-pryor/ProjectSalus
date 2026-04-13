/**
 * bus.js — Event bus with per-module contract enforcement.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.4
 *
 * Each module receives a scoped bus handle that only permits emitting events
 * declared in its manifest emits[] and subscribing to events in subscribes[].
 * The underlying EventTarget is never exposed to modules.
 *
 * The shell receives the unscoped bus (emit/on with no restrictions) for
 * broadcasting scenario:loaded, scenario:saved, etc.
 */

import { VALID_EVENTS } from './state-schema.js';

// ---------------------------------------------------------------------------
// Custom error type
// ---------------------------------------------------------------------------

export class EventContractViolation extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'EventContractViolation';
  }
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create the event bus.
 *
 * @param {Map<string, {emits: string[], subscribes: string[]}>} moduleContracts
 * @returns {{ createScopedBus, emit, on }}
 */
export function createBus(moduleContracts) {
  // Single underlying event target — never exposed outside this closure.
  const _target = new EventTarget();

  // ---------------------------------------------------------------------------
  // Raw (shell-level) helpers
  // ---------------------------------------------------------------------------

  function _rawEmit(event, data) {
    _target.dispatchEvent(new CustomEvent(event, { detail: data }));
  }

  function _rawOn(event, callback) {
    const handler = (e) => callback(e.detail);
    _target.addEventListener(event, handler);
    // Return unsubscribe function.
    return () => _target.removeEventListener(event, handler);
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Create a scoped bus handle for a module.
     * Enforces emits[] and subscribes[] contracts from the module's manifest.
     */
    createScopedBus(moduleId) {
      const contract = moduleContracts.get(moduleId);
      if (!contract) {
        throw new EventContractViolation(`Unknown module: '${moduleId}'`);
      }
      const { emits, subscribes } = contract;

      return {
        /**
         * Emit a declared event.
         * Throws EventContractViolation if event not in emits[].
         */
        emit(event, data) {
          if (!VALID_EVENTS.has(event)) {
            throw new EventContractViolation(`'${event}' is not a valid event`);
          }
          if (!emits.includes(event)) {
            throw new EventContractViolation(
              `Module '${moduleId}' attempted to emit '${event}' but only declared emits: [${emits.join(', ')}]`
            );
          }
          _rawEmit(event, data);
        },

        /**
         * Subscribe to a declared event.
         * Throws EventContractViolation if event not in subscribes[].
         * Returns an unsubscribe function.
         */
        on(event, callback) {
          if (!VALID_EVENTS.has(event)) {
            throw new EventContractViolation(`'${event}' is not a valid event`);
          }
          if (!subscribes.includes(event)) {
            throw new EventContractViolation(
              `Module '${moduleId}' attempted to subscribe to '${event}' but only declared subscribes: [${subscribes.join(', ')}]`
            );
          }
          return _rawOn(event, callback);
        },
      };
    },

    // Shell-only: unrestricted emit and subscribe.
    emit: _rawEmit,
    on: _rawOn,
  };
}
