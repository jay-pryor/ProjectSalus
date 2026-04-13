# Interface Module Standard — Salus

> Applies to: all `.js`, `.html`, and `manifest.json` files under
> `src/salus/viewer/static/` and `modules/`
>
> Does NOT apply to Python files, test files, or configuration files.

The rules in this standard enforce the architectural invariants defined in
`docs/InterfaceArchitecturePlanning.md`. They exist to keep modules
independently shippable, testable, and portable to multi-user without
rewrites.

---

## MUST Rules

### Isolation

1. **Never import another module's files.** The only external things a module
   imports are: its own internal files (panel.js, map-layers.js, etc.) and
   platform libraries (MapLibreGL, etc.). Cross-module imports break the
   independence guarantee.

2. **Never reach outside the injected `api` object.** Do not use `window.*`
   for cross-module communication. Do not obtain a reference to the shell,
   the raw state object, or the raw MapLibreGL map instance by any means
   other than what `api` exposes.

3. **`index.js` must export exactly `{ init(api) }` and nothing else.**
   Other exports create an implicit public interface that other modules might
   depend on.

### State contract

4. **Only read and write state keys declared in `manifest.json`.** The keys
   in `reads[]` and `writes[]` are the module's public contract. Accessing
   undeclared keys means the contract is wrong and must be updated, not the
   code silently worked around.

5. **Never write non-serialisable values to state.** No functions, no class
   instances with methods, no DOM nodes, no `undefined`. The entire state
   must be `JSON.stringify`-able at any point.

6. **Only one module writes each state key.** If you need to write a key
   already owned by another module, the correct fix is an event, not a
   direct write.

### Reactive reads

7. **Never call `api.state.get(key)` immediately after `api.state.set(key)`
   in the same synchronous call stack.** This pattern will silently return
   stale data if the state layer becomes async (multi-user). Use
   `api.state.watch()` instead.

8. **All UI that reacts to state changes must be driven by
   `api.state.watch()`.** The watcher callback is the single source of truth
   for rendering. A module that reads state outside of a watcher will
   desynchronise when another client or the optimiser updates state.

9. **Every `api.state.watch()` call must be paired with an unsubscribe in
   `api.panel.onUnmount()`.** Unwatched subscriptions continue firing after
   the module is deactivated, causing phantom updates and memory leaks.

### Event contracts

10. **Only emit events declared in `manifest.json` `emits[]`.** Undeclared
    emits break the auditable event graph — reviewers cannot trace event flow
    from manifests alone.

11. **Only subscribe to events declared in `manifest.json` `subscribes[]`.**
    Same reason.

12. **Every `api.bus.on()` call must be paired with an unsubscribe in
    `api.panel.onUnmount()`.**

### Map layer scoping

13. **All source and layer IDs must start with `{layer_id_prefix}:`.** Example:
    `placement-editor:sensors-circle`. This prefix is declared in
    `manifest.json`. It prevents ID collisions between modules and makes it
    possible to remove all of a module's layers by scanning for the prefix.

14. **Only call map methods listed in Section 2.6 of the architecture doc.**
    Do not attempt to call `setStyle()`, `remove()`, `addControl()`,
    `getStyle()`, `setTerrain()`, `setBearing()`, or `setPitch()`. The
    injected map proxy does not expose these; obtaining the raw map by any
    other means violates the canvas permanence invariant.

15. **All map event listeners must be removed in `api.panel.onUnmount()`.**

### Manifest

16. **`manifest.json` must declare `id`, `label`, `reads`, `writes`,
    `prerequisites`, `emits`, `subscribes`, and `layer_id_prefix`.** All
    fields are required. Missing fields cause the shell to reject the module
    at startup.

17. **`prerequisites` must list every state key the module needs to be
    non-null before it can function.** The shell uses this to disable the
    module's navigation button — if it is wrong, the module will activate
    before its data is ready.

---

## SHOULD Rules

1. Unsubscribe functions from `watch()` and `bus.on()` should be stored in
   a local array and iterated in a single `onUnmount` cleanup block, rather
   than multiple individual cleanup calls.

2. Initial panel render (populating UI when the panel first mounts) may use
   `api.state.get()` once. All subsequent updates must come from `watch()`.
   Add a comment marking the one-time read so reviewers do not flag it.

3. Map layers should be added in `addLayer(..., beforeId)` order so their
   z-order is deterministic regardless of which other modules happen to be
   loaded.

4. `manifest.json` `description` should accurately describe current
   behaviour, not aspirational behaviour. It is shown in the UI's module
   tooltip.

---

## Quick Reference — Correct Patterns

```javascript
// index.js — correct shape
export function init(api) {
  const unsubs = []

  // One-time initial render — get() is acceptable here
  const initial = api.state.get('placements')  // OK: initial render only
  renderList(initial)

  // All reactive updates via watch()
  unsubs.push(api.state.watch('placements', (placements) => {
    renderList(placements)
  }))

  // Events — only declared ones
  unsubs.push(api.bus.on('optimiser:complete', (result) => {
    api.state.set('placements', result.proposed_placements)
  }))

  // Map layers — prefixed IDs only
  api.map.addSource('placement-editor:sensors', { type: 'geojson', data: ... })
  api.map.addLayer({ id: 'placement-editor:sensors-circle', ... })

  // Cleanup — all subscriptions and listeners
  api.panel.onUnmount(() => {
    unsubs.forEach(u => u())
    api.map.removeLayer('placement-editor:sensors-circle')
    api.map.removeSource('placement-editor:sensors')
  })
}
```
