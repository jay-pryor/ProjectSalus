/**
 * state-schema.js — Canonical ground truth for the shared state and event system.
 *
 * All entries in module manifest reads[], writes[], emits[], subscribes[]
 * must appear here. Imported by state.js, bus.js, and registry.js so that
 * any contract check uses a single authoritative source.
 *
 * Source of truth: docs/Technical/InterfaceArchitecture.md §2.4 and §3.
 */

/** All valid top-level state keys (Section 3). */
export const VALID_STATE_KEYS = new Set([
  'terrain',
  'sensor_library',
  'effector_library',
  'placements',
  'zones',
  'threat_corridors',
  'constraints',
  'sim_results',
  'optimiser_results',
  'scenario_b_sim_results',
  'report_config',
  'ui',
]);

/** All valid event names (Section 2.4). */
export const VALID_EVENTS = new Set([
  'terrain:loaded',
  'placement:pending',
  'placement:added',
  'placement:removed',
  'placement:moved',
  'simulation:started',
  'simulation:progress',
  'simulation:complete',
  'simulation:failed',
  'zone:added',
  'zone:removed',
  'constraint:updated',
  'optimiser:started',
  'optimiser:complete',
  'optimiser:failed',
  'optimiser:apply',
  'corridor:added',
  'corridor:removed',
  'comparison:loaded',
  'report:generated',
  'scenario:loaded',
  'scenario:saved',
  'shell:library-load-error',
]);
