/**
 * optimiser/index.js — Optimiser Module (S14.11).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Reads:       terrain, zones, constraints, sensor_library, effector_library,
 *              threat_corridors, placements
 * Writes:      optimiser_results, placements (Apply action merges proposals)
 * Emits:       optimiser:started, optimiser:complete, optimiser:failed,
 *              placement:added (one per applied placement)
 * Subscribes:  zone:added, zone:removed, constraint:updated
 * Map sources: optimiser:ghost-sensors
 * Map layers:  optimiser:ghost-sensors-circle
 *
 * Note on placements write: S14.11-3 specifies that the Apply button merges
 * proposed_placements into the placements state key. manifest.json therefore
 * declares placements in both reads[] and writes[]. When S14.5 (Placement
 * Editor) is built it will become the sole writer; at that point S14.5 will
 * subscribe to optimiser:complete instead of this module writing placements
 * directly. For now (S14.5 absent) this module handles the merge.
 */

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

/** Optimiser objective options — maps to backend scoring function name. */
const OBJECTIVES = [
  { id: 'maximise_coverage',              label: 'Maximise composite coverage' },
  { id: 'maximise_critical_zone_coverage', label: 'Maximise critical-zone coverage' },
  { id: 'minimise_cost',                  label: 'Minimise cost at target coverage' },
];

// ---------------------------------------------------------------------------
// SSE stream parser
// ---------------------------------------------------------------------------

/**
 * Parse accumulated SSE buffer text into discrete events.
 * Events are separated by blank lines (\n\n).
 * Returns { events: [{type, data}], remaining: string }.
 */
function _parseSseBuffer(buffer) {
  const events = [];
  const blocks = buffer.split('\n\n');
  // Last block may be incomplete — keep it in the remainder
  const remaining = blocks.pop() ?? '';
  for (const block of blocks) {
    if (!block.trim()) continue;
    let eventType = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) eventType = line.slice(7).trim();
      else if (line.startsWith('data: '))  data = line.slice(6).trim();
    }
    if (data) events.push({ type: eventType, data });
  }
  return { events, remaining };
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirrors — avoids cross-key get() inside watch() callbacks
  let latestTerrain = null;
  let latestZones = null;
  let latestConstraints = null;
  let latestSensors = null;
  let latestEffectors = null;
  let latestThreatCorridors = null;
  let latestPlacements = null;
  let latestOptimiserResults = null;

  // Run-time state
  let currentObjective = OBJECTIVES[0].id;
  let abortController = null;
  let isRunning = false;
  let isStale = false;

  // -------------------------------------------------------------------------
  // Ghost marker map source + layer
  // -------------------------------------------------------------------------
  api.map.addSource('optimiser:ghost-sensors', {
    type: 'geojson',
    data: _EMPTY_FC,
  });
  api.map.addLayer({
    id: 'optimiser:ghost-sensors-circle',
    type: 'circle',
    source: 'optimiser:ghost-sensors',
    paint: {
      'circle-radius': 16,
      'circle-color': '#4ade80',
      'circle-opacity': 0.25,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#4ade80',
      'circle-stroke-opacity': 0.8,
    },
  });

  function _setGhostMarkers(placements) {
    const src = api.map.getSource('optimiser:ghost-sensors');
    if (!src) return;
    const features = (placements ?? []).map(p => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lng ?? 0, p.lat ?? 0] },
      properties: { name: p.sensor_name ?? '' },
    }));
    src.setData({ type: 'FeatureCollection', features });
  }

  function _clearGhostMarkers() {
    const src = api.map.getSource('optimiser:ghost-sensors');
    if (src) src.setData(_EMPTY_FC);
  }

  // -------------------------------------------------------------------------
  // Panel DOM construction
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0';

  // Heading
  const heading = document.createElement('div');
  heading.textContent = 'Optimiser';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0';
  panel.appendChild(heading);

  // ---- Objective selector ----
  const objectiveSection = document.createElement('div');
  objectiveSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30';

  const objectiveLabel = document.createElement('div');
  objectiveLabel.textContent = 'Objective';
  objectiveLabel.style.cssText = 'font-size:12px;color:#aaa;margin-bottom:6px;font-weight:600';
  objectiveSection.appendChild(objectiveLabel);

  for (const obj of OBJECTIVES) {
    const row = document.createElement('label');
    row.style.cssText =
      'display:flex;align-items:center;gap:8px;font-size:13px;' +
      'color:#e0e0e0;cursor:pointer;margin-bottom:4px';

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'optimiser-objective';
    radio.value = obj.id;
    radio.setAttribute('data-testid', `objective-${obj.id}`);
    if (obj.id === currentObjective) radio.checked = true;

    radio.addEventListener('change', () => {
      if (radio.checked) currentObjective = obj.id;
    });

    const lbl = document.createElement('span');
    lbl.textContent = obj.label;
    row.append(radio, lbl);
    objectiveSection.appendChild(row);
  }
  panel.appendChild(objectiveSection);

  // ---- Constraint summary ----
  const constraintSection = document.createElement('div');
  constraintSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30';

  const constraintHeading = document.createElement('div');
  constraintHeading.textContent = 'Constraints';
  constraintHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  constraintSection.appendChild(constraintHeading);

  const constraintTable = document.createElement('table');
  constraintTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px';

  function _makeConstraintRow(label) {
    const tr = document.createElement('tr');
    const tdLabel = document.createElement('td');
    tdLabel.textContent = label;
    tdLabel.style.cssText = 'color:#aaa;padding:2px 8px 2px 0;white-space:nowrap';
    const tdValue = document.createElement('td');
    tdValue.style.cssText = 'color:#e0e0e0;padding:2px 0';
    tr.append(tdLabel, tdValue);
    constraintTable.appendChild(tr);
    return tdValue;
  }

  const budgetCell      = _makeConstraintRow('Budget');
  const maxSensorsCell  = _makeConstraintRow('Max sensors');
  const maxEffectorsCell = _makeConstraintRow('Max effectors');
  constraintSection.appendChild(constraintTable);
  panel.appendChild(constraintSection);

  // ---- Parameters-changed notice ----
  const paramNotice = document.createElement('div');
  paramNotice.setAttribute('data-testid', 'param-notice');
  paramNotice.style.cssText =
    'display:none;margin:6px 12px;padding:6px 10px;background:#1e3a5f;' +
    'color:#93c5fd;border-radius:3px;font-size:12px';
  paramNotice.style.display = 'none'; // explicit for mock DOM compatibility
  paramNotice.textContent = 'Parameters changed \u2014 re-run optimiser to update.';
  panel.appendChild(paramNotice);

  // ---- Run / Cancel buttons ----
  const runRow = document.createElement('div');
  runRow.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;display:flex;gap:8px';

  const runBtn = document.createElement('button');
  runBtn.textContent = 'Run Optimiser';
  runBtn.setAttribute('data-testid', 'run-btn');
  runBtn.style.cssText =
    'flex:1;padding:6px 14px;background:#0f3460;color:#fff;' +
    'border:1px solid #2266aa;border-radius:3px;cursor:pointer;font-size:13px;font-weight:600';

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.setAttribute('data-testid', 'cancel-btn');
  cancelBtn.style.cssText =
    'display:none;padding:6px 14px;background:#3f1f1f;color:#fca5a5;' +
    'border:1px solid #7f3030;border-radius:3px;cursor:pointer;font-size:13px';

  runRow.append(runBtn, cancelBtn);
  panel.appendChild(runRow);

  // ---- Progress section ----
  const progressSection = document.createElement('div');
  progressSection.setAttribute('data-testid', 'progress-section');
  progressSection.style.cssText =
    'display:none;padding:8px 12px;border-bottom:1px solid #1e1e30';
  progressSection.style.display = 'none';

  const progressBarWrap = document.createElement('div');
  progressBarWrap.style.cssText =
    'background:#1e1e30;border-radius:3px;overflow:hidden;height:8px;margin-bottom:6px';
  const progressFill = document.createElement('div');
  progressFill.setAttribute('data-testid', 'progress-fill');
  progressFill.style.cssText =
    'height:100%;width:0%;background:#3b82f6;transition:width 0.3s;border-radius:3px';
  progressBarWrap.appendChild(progressFill);
  progressSection.appendChild(progressBarWrap);

  const progressLog = document.createElement('div');
  progressLog.setAttribute('data-testid', 'progress-log');
  progressLog.style.cssText =
    'font-size:12px;color:#aaa;min-height:16px;font-style:italic';
  progressSection.appendChild(progressLog);
  panel.appendChild(progressSection);

  // ---- Results-stale notice ----
  const resultsStaleNotice = document.createElement('div');
  resultsStaleNotice.setAttribute('data-testid', 'results-stale-notice');
  resultsStaleNotice.style.cssText =
    'display:none;margin:6px 12px;padding:6px 10px;background:#3f2f10;' +
    'color:#fcd34d;border-radius:3px;font-size:12px';
  resultsStaleNotice.style.display = 'none'; // explicit for mock DOM compatibility
  resultsStaleNotice.textContent =
    'Zone or constraint changed \u2014 previous optimiser results may no longer be valid. Re-run to update.';
  panel.appendChild(resultsStaleNotice);

  // ---- Results section ----
  const resultsSection = document.createElement('div');
  resultsSection.setAttribute('data-testid', 'results-section');
  resultsSection.style.cssText = 'display:none;padding:8px 12px';
  resultsSection.style.display = 'none'; // explicit for mock DOM compatibility

  const resultsHeading = document.createElement('div');
  resultsHeading.textContent = 'Proposed Configuration';
  resultsHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  resultsSection.appendChild(resultsHeading);

  const resultsTable = document.createElement('table');
  resultsTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px;margin-bottom:8px';

  function _makeResultRow(label, testId) {
    const tr = document.createElement('tr');
    const tdL = document.createElement('td');
    tdL.textContent = label;
    tdL.style.cssText = 'color:#aaa;padding:2px 8px 2px 0;white-space:nowrap';
    const tdV = document.createElement('td');
    tdV.setAttribute('data-testid', testId);
    tdV.style.cssText = 'color:#e0e0e0;padding:2px 0';
    tr.append(tdL, tdV);
    resultsTable.appendChild(tr);
    return tdV;
  }

  const resultsCoverageCell = _makeResultRow('Coverage', 'results-coverage');
  const resultsCostCell     = _makeResultRow('Total cost', 'results-cost');
  const resultsScoreCell    = _makeResultRow('Score', 'results-score');
  resultsSection.appendChild(resultsTable);

  const satisfiedEl = document.createElement('div');
  satisfiedEl.setAttribute('data-testid', 'results-satisfied');
  satisfiedEl.style.cssText = 'font-size:12px;color:#4ade80;margin-bottom:4px';
  resultsSection.appendChild(satisfiedEl);

  const violatedEl = document.createElement('div');
  violatedEl.setAttribute('data-testid', 'results-violated');
  violatedEl.style.cssText = 'font-size:12px;color:#f87171;margin-bottom:8px';
  resultsSection.appendChild(violatedEl);

  const applyBtn = document.createElement('button');
  applyBtn.textContent = 'Apply';
  applyBtn.setAttribute('data-testid', 'apply-btn');
  applyBtn.style.cssText =
    'margin-right:8px;padding:5px 18px;background:#065f46;color:#fff;' +
    'border:1px solid #059669;border-radius:3px;cursor:pointer;font-size:13px;font-weight:600';

  const discardBtn = document.createElement('button');
  discardBtn.textContent = 'Discard';
  discardBtn.setAttribute('data-testid', 'discard-btn');
  discardBtn.style.cssText =
    'padding:5px 18px;background:#3f1f1f;color:#fca5a5;' +
    'border:1px solid #7f3030;border-radius:3px;cursor:pointer;font-size:13px';

  const actionRow = document.createElement('div');
  actionRow.append(applyBtn, discardBtn);
  resultsSection.appendChild(actionRow);
  panel.appendChild(resultsSection);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _renderConstraintSummary() {
    const c = latestConstraints ?? {};
    budgetCell.textContent =
      c.max_cost_aud != null ? `$${Number(c.max_cost_aud).toLocaleString()}` : 'No limit';
    maxSensorsCell.textContent =
      c.max_sensors != null ? String(c.max_sensors) : 'No limit';
    maxEffectorsCell.textContent =
      c.max_effectors != null ? String(c.max_effectors) : 'No limit';
  }

  function _checkStale() {
    if (latestOptimiserResults != null && !isRunning) {
      isStale = true;
      resultsStaleNotice.style.display = 'block';
    }
  }

  function _showResults(results) {
    resultsCoverageCell.textContent =
      results.coverage_pct != null ? `${Number(results.coverage_pct).toFixed(1)}%` : '\u2014';
    resultsCostCell.textContent =
      results.total_cost_aud != null
        ? `$${Number(results.total_cost_aud).toLocaleString()}`
        : '\u2014';
    resultsScoreCell.textContent =
      results.score != null ? Number(results.score).toFixed(3) : '\u2014';

    const sat = results.satisfied_constraints ?? [];
    const viol = results.violated_constraints ?? [];
    satisfiedEl.textContent =
      sat.length > 0 ? `\u2713 Satisfied: ${sat.join(', ')}` : '';
    violatedEl.textContent =
      viol.length > 0 ? `\u26a0 Violated: ${viol.join(', ')}` : '';

    resultsSection.style.display = 'block';
    _setGhostMarkers(results.proposed_placements);
  }

  function _hideResults() {
    resultsSection.style.display = 'none';
    _clearGhostMarkers();
  }

  // -------------------------------------------------------------------------
  // Run optimiser (async)
  // -------------------------------------------------------------------------

  async function _runOptimiser() {
    if (isRunning) return;

    isRunning = true;
    isStale = false;
    resultsStaleNotice.style.display = 'none';
    paramNotice.style.display = 'none';

    runBtn.style.display = 'none';
    cancelBtn.style.display = 'block';
    progressSection.style.display = 'block';
    progressFill.style.width = '0%';
    progressLog.textContent = 'Starting\u2026';

    api.bus.emit('optimiser:started', { objective: currentObjective });

    abortController = new AbortController();

    // D-355: Guard against non-serialisable state values before fetch
    let bodyJson;
    try {
      bodyJson = JSON.stringify({
        zones: latestZones,
        constraints: latestConstraints,
        sensor_library_filter: latestConstraints?.allowed_sensor_ids ?? null,
        effector_library_filter: latestConstraints?.allowed_effector_ids ?? null,
        terrain: latestTerrain?.dem_path ?? null,
        objective: currentObjective,
      });
    } catch (e) {
      throw new Error(
        `Failed to serialise request body — state may contain non-serialisable values: ${e.message}`
      );
    }

    try {
      const response = await fetch('/api/optimise', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: bodyJson,
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: HTTP ${response.status}`);
      }

      // D-354: Guard against null body (streaming unsupported in some environments)
      if (!response.body) {
        throw new Error('Server response has no body — streaming not supported in this environment');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        // Check for abort between reads
        if (abortController && abortController.signal.aborted) break;
        const { done, value } = await reader.read();
        if (done) break;
        if (!value) continue; // D-358: skip empty chunks from non-spec readers
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = _parseSseBuffer(buffer);
        buffer = remaining;

        for (const evt of events) {
          if (evt.type === 'progress') {
            let data = {};
            // D-356: log malformed progress data for diagnostics
            try { data = JSON.parse(evt.data); } catch (_) {
              console.warn('[optimiser] malformed progress event data:', evt.data);
            }
            if (data.message) progressLog.textContent = data.message;
            if (data.coverage_pct != null) {
              progressFill.style.width =
                `${Math.min(100, Number(data.coverage_pct) || 0)}%`;
            }
          } else if (evt.type === 'complete') {
            // D-350: wrap parse in try/catch to distinguish parse failure from network failure
            let result;
            try {
              result = JSON.parse(evt.data);
            } catch (parseErr) {
              throw new Error(
                `Optimiser succeeded but result could not be parsed: ${parseErr.message}`
              );
            }
            // D-351: validate result is a non-null object before using it
            if (!result || typeof result !== 'object' || Array.isArray(result)) {
              throw new Error('Optimiser complete payload is not an object');
            }
            latestOptimiserResults = result;
            api.state.set('optimiser_results', result);
            // D-353: let the watch drive _showResults; remove direct call to avoid double-render
            api.bus.emit('optimiser:complete', result);
            progressFill.style.width = '100%';
            progressLog.textContent = 'Optimisation complete.';
          } else if (evt.type === 'error') {
            let data = {};
            // D-357: log malformed error data for diagnostics
            try { data = JSON.parse(evt.data); } catch (_) {
              console.warn('[optimiser] malformed error event data:', evt.data);
            }
            throw new Error(data.message ?? 'Optimiser returned an error');
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        progressLog.textContent = 'Cancelled.';
      } else {
        progressLog.textContent = `Error: ${err.message}`;
        api.bus.emit('optimiser:failed', { message: err.message });
      }
    } finally {
      isRunning = false;
      abortController = null;
      runBtn.style.display = 'block';
      cancelBtn.style.display = 'none';
    }
  }

  runBtn.addEventListener('click', () => {
    _runOptimiser().catch(err => {
      console.error('[optimiser] unexpected error in _runOptimiser:', err);
    });
  });

  cancelBtn.addEventListener('click', () => {
    if (abortController) abortController.abort();
  });

  // -------------------------------------------------------------------------
  // Apply / Discard
  // -------------------------------------------------------------------------

  applyBtn.addEventListener('click', () => {
    if (!latestOptimiserResults) return;
    const proposed = latestOptimiserResults.proposed_placements ?? [];
    const current = latestPlacements ?? [];
    const merged = [...current, ...proposed];
    api.state.set('placements', merged); // watch fires -> latestPlacements = p
    for (const p of proposed) {
      api.bus.emit('placement:added', p);
    }
    _clearGhostMarkers();
    latestOptimiserResults = null;
    api.state.set('optimiser_results', null);
    _hideResults();
    isStale = false;
    resultsStaleNotice.style.display = 'none';
  });

  discardBtn.addEventListener('click', () => {
    _clearGhostMarkers();
    latestOptimiserResults = null;
    api.state.set('optimiser_results', null);
    _hideResults();
    isStale = false;
    resultsStaleNotice.style.display = 'none';
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestTerrain         = api.state.get('terrain');          // OK: initial render only
  latestZones           = api.state.get('zones');             // OK: initial render only
  latestConstraints     = api.state.get('constraints');       // OK: initial render only
  latestSensors         = api.state.get('sensor_library');    // OK: initial render only
  latestEffectors       = api.state.get('effector_library');  // OK: initial render only
  latestThreatCorridors = api.state.get('threat_corridors');  // OK: initial render only
  latestPlacements      = api.state.get('placements');        // OK: initial render only
  latestOptimiserResults = api.state.get('optimiser_results'); // OK: initial render only

  api.panel.mount(panel);
  _renderConstraintSummary();
  if (latestOptimiserResults != null) _showResults(latestOptimiserResults);

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('constraints', (c) => {
    latestConstraints = c;
    _renderConstraintSummary();
    _checkStale();
  }));

  unsubs.push(api.state.watch('zones', (z) => {
    latestZones = z;
    _checkStale();
  }));

  unsubs.push(api.state.watch('terrain',          (t)  => { latestTerrain = t; }));
  unsubs.push(api.state.watch('sensor_library',   (s)  => { latestSensors = s; }));
  unsubs.push(api.state.watch('effector_library', (e)  => { latestEffectors = e; }));
  unsubs.push(api.state.watch('threat_corridors', (tc) => { latestThreatCorridors = tc; }));
  unsubs.push(api.state.watch('placements',       (p)  => { latestPlacements = p; }));

  unsubs.push(api.state.watch('optimiser_results', (r) => {
    latestOptimiserResults = r;
    if (r != null) {
      _showResults(r);
    } else {
      _hideResults();
    }
  }));

  // -------------------------------------------------------------------------
  // Bus subscriptions (S14.11-1, S14.11-4)
  // -------------------------------------------------------------------------
  function _onParamChange() {
    paramNotice.style.display = 'block';
    _checkStale();
  }

  unsubs.push(api.bus.on('zone:added',         _onParamChange));
  unsubs.push(api.bus.on('zone:removed',        _onParamChange));
  unsubs.push(api.bus.on('constraint:updated',  _onParamChange));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    if (abortController) abortController.abort();
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
    if (api.map.getLayer('optimiser:ghost-sensors-circle')) {
      api.map.removeLayer('optimiser:ghost-sensors-circle');
    }
    if (api.map.getSource('optimiser:ghost-sensors')) {
      api.map.removeSource('optimiser:ghost-sensors');
    }
  });
}
