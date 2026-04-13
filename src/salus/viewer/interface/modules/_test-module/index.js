/**
 * _test-module/index.js — Stub module for shell integration testing.
 *
 * Proves that the full shell pipeline works end-to-end:
 *   - manifest discovery and validation
 *   - API injection
 *   - panel mounting
 *   - onUnmount registration
 *
 * This module intentionally has no state reads/writes, no map layers,
 * and no bus events. It is only present in modules/index.json for
 * integration tests; it is not included in production deployments.
 */

export function init(api) {
  console.log(`[${api.moduleId}]: init`);

  const panel = document.createElement('div');
  panel.id = `panel-${api.moduleId}`;
  panel.setAttribute('data-test-panel', 'true');
  panel.textContent = 'Test Module Panel';
  panel.style.padding = '16px';

  api.panel.mount(panel);

  api.panel.onUnmount(() => {
    console.log(`[${api.moduleId}]: unmount`);
  });
}
