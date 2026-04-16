/**
 * simulation-runner/index.js — Simulation Runner Module (S14.8).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Sole writer of the `sim_results` state key. Serialises the current
 * terrain + placements + threat_corridors + zones into a ScenarioConfig,
 * POSTs it to /api/simulate, consumes the SSE response stream, and writes
 * the result to state on completion.
 *
 * Reads:       terrain, placements, threat_corridors, zones
 * Writes:      sim_results
 * Emits:       simulation:started, simulation:progress,
 *              simulation:complete, simulation:failed
 * Subscribes:  (none)
 * Map sources: (none)
 * Map layers:  (none)
 */

// ---------------------------------------------------------------------------
// SSE stream parser (same contract as optimiser module)
// ---------------------------------------------------------------------------

/**
 * Parse accumulated SSE buffer text into discrete events.
 * Events are separated by blank lines (\n\n).
 * Returns { events: [{type, data}], remaining: string }.
 */
function _parseSseBuffer(buffer) {
  const events = [];
  const blocks = buffer.split('\n\n');
  const remaining = blocks.pop() ?? '';
  for (const block of blocks) {
    if (!block.trim()) continue;
    let eventType = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event: '))      eventType = line.slice(7).trim();
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
  let latestPlacements = null;
  let latestThreatCorridors = null;
  let latestZones = null;

  // Run-time state
  let abortController = null;
  let isRunning = false;
  let simCompleted = false;   // true after first successful completion; for stale detection
  let elapsedInterval = null;
  let elapsedStart = 0;

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Simulation Runner';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  // ---- Pre-flight checklist ----
  const checklistSection = document.createElement('div');
  checklistSection.setAttribute('data-testid', 'checklist-section');
  checklistSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';

  const checklistHeading = document.createElement('div');
  checklistHeading.textContent = 'Pre-flight Checklist';
  checklistHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:8px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  checklistSection.appendChild(checklistHeading);

  function _makeCheckRow(testId, label) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:4px;font-size:12px';
    const icon = document.createElement('span');
    icon.setAttribute('data-testid', `${testId}-icon`);
    icon.style.cssText = 'font-size:13px;width:16px;text-align:center';
    const text = document.createElement('span');
    text.setAttribute('data-testid', `${testId}-label`);
    text.textContent = label;
    text.style.cssText = 'color:#aaa';
    row.append(icon, text);
    checklistSection.appendChild(row);
    return { icon, text };
  }

  const terrainCheck   = _makeCheckRow('check-terrain',   'Terrain loaded');
  const sensorsCheck   = _makeCheckRow('check-sensors',   'Sensors placed');
  const corridorsCheck = _makeCheckRow('check-corridors', 'Corridors defined');
  const zonesCheck     = _makeCheckRow('check-zones',     'Zones defined (optional)');

  panel.appendChild(checklistSection);

  // ---- Run / Cancel row ----
  const runRow = document.createElement('div');
  runRow.style.cssText =
    'padding:10px 12px;border-bottom:1px solid #1e1e30;display:flex;gap:8px;flex-shrink:0';

  const runBtn = document.createElement('button');
  runBtn.textContent = 'Run Simulation';
  runBtn.setAttribute('data-testid', 'run-btn');
  runBtn.disabled = true;
  runBtn.style.cssText =
    'flex:1;padding:6px 14px;background:#0f3460;color:#fff;' +
    'border:1px solid #2266aa;border-radius:3px;cursor:pointer;font-size:13px;font-weight:600';

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.setAttribute('data-testid', 'cancel-btn');
  cancelBtn.style.cssText =
    'display:none;padding:6px 14px;background:#3f1f1f;color:#fca5a5;' +
    'border:1px solid #7f3030;border-radius:3px;cursor:pointer;font-size:13px';
  cancelBtn.style.display = 'none'; // explicit for mock DOM compatibility

  runRow.append(runBtn, cancelBtn);
  panel.appendChild(runRow);

  // ---- Progress section ----
  const progressSection = document.createElement('div');
  progressSection.setAttribute('data-testid', 'progress-section');
  progressSection.style.cssText =
    'display:none;padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';
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
    'font-size:11px;color:#aaa;min-height:16px;max-height:80px;overflow-y:auto';
  progressSection.appendChild(progressLog);

  const timerEl = document.createElement('div');
  timerEl.setAttribute('data-testid', 'elapsed-timer');
  timerEl.textContent = '00:00';
  timerEl.style.cssText = 'font-size:11px;color:#666;margin-top:4px;font-variant-numeric:tabular-nums';
  progressSection.appendChild(timerEl);

  panel.appendChild(progressSection);

  // ---- Stale results banner ----
  const staleBanner = document.createElement('div');
  staleBanner.setAttribute('data-testid', 'stale-banner');
  staleBanner.textContent = 'Results may be stale \u2014 re-run simulation';
  staleBanner.style.cssText =
    'display:none;margin:6px 12px;padding:6px 10px;background:#3f2f10;' +
    'color:#fcd34d;border-radius:3px;font-size:12px;flex-shrink:0';
  staleBanner.style.display = 'none'; // explicit for mock DOM compatibility
  panel.appendChild(staleBanner);

  // ---- Results summary section ----
  const resultsSection = document.createElement('div');
  resultsSection.setAttribute('data-testid', 'results-section');
  resultsSection.style.cssText = 'display:none;padding:8px 12px;flex-shrink:0';
  resultsSection.style.display = 'none';

  const resultsHeading = document.createElement('div');
  resultsHeading.textContent = 'Simulation Results';
  resultsHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  resultsSection.appendChild(resultsHeading);

  const resultsTable = document.createElement('table');
  resultsTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px';

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

  const coverageCell      = _makeResultRow('Composite coverage',        'results-coverage');
  const gapAreaCell       = _makeResultRow('Largest gap area',          'results-gap-area');
  const corridorCovCell   = _makeResultRow('Worst corridor coverage',   'results-corridor-cov');
  resultsSection.appendChild(resultsTable);
  panel.appendChild(resultsSection);

  // -------------------------------------------------------------------------
  // Checklist helpers
  // -------------------------------------------------------------------------

  function _setCheckItem(item, ok, optional) {
    item.icon.textContent = ok ? '\u2713' : (optional ? '\u2013' : '\u2717');
    item.icon.style.color  = ok ? '#4ade80' : (optional ? '#666' : '#f87171');
    item.text.style.color  = ok ? '#e0e0e0' : '#aaa';
  }

  function _hasSensors(placements) {
    if (!placements) return false;
    // Support both documented schema { sensors: [] } and flat array (S14.5 format)
    if (Array.isArray(placements)) return placements.length > 0;
    return (placements.sensors?.length ?? 0) > 0;
  }

  function _updateChecklist() {
    const hasTerrain   = latestTerrain != null;
    const hasSensors   = _hasSensors(latestPlacements);
    const hasCorridors = Array.isArray(latestThreatCorridors)
      ? latestThreatCorridors.length > 0
      : latestThreatCorridors != null;
    const hasZones     = latestZones != null &&
      ((latestZones.priority?.length ?? 0) > 0 || (latestZones.exclusion?.length ?? 0) > 0);

    _setCheckItem(terrainCheck,   hasTerrain,   false);
    _setCheckItem(sensorsCheck,   hasSensors,   false);
    _setCheckItem(corridorsCheck, hasCorridors, true);
    _setCheckItem(zonesCheck,     hasZones,     true);

    runBtn.disabled = isRunning || !(hasTerrain && hasSensors);
  }

  // -------------------------------------------------------------------------
  // Stale-results check
  // -------------------------------------------------------------------------

  function _checkStale() {
    if (simCompleted && !isRunning) {
      staleBanner.style.display = 'block';
    }
  }

  // -------------------------------------------------------------------------
  // Timer helpers
  // -------------------------------------------------------------------------

  function _startTimer() {
    _stopTimer(); // idempotent — cancel any live interval before creating a new one
    elapsedStart = Date.now();
    timerEl.textContent = '00:00';
    elapsedInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - elapsedStart) / 1000);
      const min = Math.floor(elapsed / 60);
      const sec = elapsed % 60;
      timerEl.textContent =
        `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    }, 1000);
  }

  function _stopTimer() {
    if (elapsedInterval) {
      clearInterval(elapsedInterval);
      elapsedInterval = null;
    }
  }

  // -------------------------------------------------------------------------
  // Log helpers
  // -------------------------------------------------------------------------

  function _appendLog(message) {
    const line = document.createElement('div');
    line.textContent = message;
    progressLog.appendChild(line);
    // Scroll to bottom — show latest message
    progressLog.scrollTop = progressLog.scrollHeight;
  }

  function _clearLog() {
    while (progressLog.firstChild) progressLog.removeChild(progressLog.firstChild);
  }

  // -------------------------------------------------------------------------
  // Run simulation (async)
  // -------------------------------------------------------------------------

  async function _runSimulation() {
    if (isRunning) return;

    isRunning = true;
    staleBanner.style.display = 'none';
    runBtn.disabled = true;
    cancelBtn.style.display = 'block';
    progressSection.style.display = 'block';
    resultsSection.style.display = 'none';
    progressFill.style.width = '0%';
    _clearLog();
    _appendLog('Starting\u2026');
    _startTimer();

    api.bus.emit('simulation:started', {});

    abortController = new AbortController();

    // Serialise state into ScenarioConfig
    let bodyJson;
    try {
      const sensors = Array.isArray(latestPlacements)
        ? latestPlacements
        : (latestPlacements?.sensors ?? []);
      const effectors = Array.isArray(latestPlacements)
        ? []
        : (latestPlacements?.effectors ?? []);

      bodyJson = JSON.stringify({
        site_dem_path:       latestTerrain?.dem_path ?? null,
        sensor_placements:   sensors,
        effector_placements: effectors,
        threat_corridors:    latestThreatCorridors ?? [],
        zones:               latestZones ?? {},
      });
    } catch (e) {
      _stopTimer();
      isRunning = false;
      runBtn.disabled = false;
      cancelBtn.style.display = 'none';
      _appendLog(`\u2717 Serialisation error: ${e.message}`);
      api.bus.emit('simulation:failed', { error: e.message });
      return;
    }

    try {
      const response = await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: bodyJson,
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error('Server response has no body — streaming not supported in this environment');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamCompleted = false; // set true when _onComplete() is called via 'complete' event

      try {
        while (true) {
          if (abortController && abortController.signal.aborted) break;
          const { done, value } = await reader.read();
          if (done) break;
          if (!value) continue;
          buffer += decoder.decode(value, { stream: true });
          const { events, remaining } = _parseSseBuffer(buffer);
          buffer = remaining;

          for (const evt of events) {
            if (evt.type === 'progress') {
              let data = {};
              try { data = JSON.parse(evt.data); } catch (_) {
                console.warn('[simulation-runner] malformed progress event data:', evt.data);
              }
              if (data.message) _appendLog(data.message);
              if (data.pct != null) {
                const pct = Number(data.pct);
                if (isNaN(pct)) {
                  console.warn('[simulation-runner] malformed pct value in progress event:', data.pct);
                } else {
                  progressFill.style.width = `${Math.min(100, pct)}%`;
                }
              }
              api.bus.emit('simulation:progress', {
                message: data.message ?? '',
                pct: data.pct ?? 0,
              });
            } else if (evt.type === 'complete') {
              let result;
              try {
                result = JSON.parse(evt.data);
              } catch (parseErr) {
                throw new Error(
                  `Simulation succeeded but result could not be parsed: ${parseErr.message}`
                );
              }
              if (!result || typeof result !== 'object' || Array.isArray(result)) {
                throw new Error('Simulation complete payload is not an object');
              }
              streamCompleted = true;
              _onComplete(result);
              return; // stream done
            } else if (evt.type === 'error') {
              let data = {};
              try { data = JSON.parse(evt.data); } catch (_) {
                console.warn('[simulation-runner] malformed error event data:', evt.data);
              }
              const msg = data.message ?? 'Unknown server error';
              _appendLog(`\u2717 ${msg}`);
              _stopTimer();
              isRunning = false;
              abortController = null; // D-373: null out controller consistently
              _updateChecklist(); // re-enable run button
              cancelBtn.style.display = 'none';
              api.bus.emit('simulation:failed', { error: msg });
              return;
            }
          }
        }
      } finally {
        // D-372: release the reader lock regardless of how the loop exits
        // Guard: reader.cancel may not exist in all environments or test mocks
        try {
          if (typeof reader.cancel === 'function') reader.cancel();
        } catch (_) { /* ignore cancel errors */ }
      }

      // D-369: stream ended without a 'complete' event — treat as failure
      if (!streamCompleted && !(abortController && abortController.signal.aborted)) {
        const msg = 'Stream ended without a result — the server may have closed the connection early';
        _appendLog(`\u2717 ${msg}`);
        _stopTimer();
        isRunning = false;
        abortController = null;
        _updateChecklist();
        cancelBtn.style.display = 'none';
        api.bus.emit('simulation:failed', { error: msg });
        return;
      }

    } catch (err) {
      _stopTimer();
      isRunning = false;
      _updateChecklist();
      cancelBtn.style.display = 'none';

      if (err.name === 'AbortError') {
        _appendLog('Simulation cancelled');
      } else {
        _appendLog(`\u2717 Error: ${err.message}`);
        api.bus.emit('simulation:failed', { error: err.message });
      }
    }
  }

  // -------------------------------------------------------------------------
  // On complete — write results and update UI
  // -------------------------------------------------------------------------

  function _onComplete(simResults) {
    _stopTimer();
    isRunning = false;
    simCompleted = true;
    abortController = null;

    api.state.set('sim_results', simResults);
    api.bus.emit('simulation:complete', {
      coverage_pct: simResults.stats?.coverage_pct ?? null,
    });

    progressFill.style.width = '100%';
    _appendLog('Simulation complete.');
    cancelBtn.style.display = 'none';
    staleBanner.style.display = 'none';
    _updateChecklist(); // re-enable run button

    // Show result summary
    const stats = simResults.stats ?? {};
    coverageCell.textContent =
      stats.coverage_pct != null
        ? `${Number(stats.coverage_pct).toFixed(1)}%`
        : '\u2014';
    gapAreaCell.textContent =
      stats.largest_gap_area_m2 != null
        ? `${Number(stats.largest_gap_area_m2).toLocaleString()} m\u00b2`
        : '\u2014';
    corridorCovCell.textContent =
      stats.worst_corridor_coverage_pct != null
        ? `${Number(stats.worst_corridor_coverage_pct).toFixed(1)}%`
        : '\u2014';
    resultsSection.style.display = 'block';
  }

  // -------------------------------------------------------------------------
  // Button event listeners
  // -------------------------------------------------------------------------

  runBtn.addEventListener('click', () => {
    _runSimulation().catch((err) => {
      console.error('[simulation-runner] unhandled error in _runSimulation:', err);
    });
  });

  cancelBtn.addEventListener('click', () => {
    if (abortController) abortController.abort();
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestTerrain         = api.state.get('terrain');           // OK: initial render only
  latestPlacements      = api.state.get('placements');        // OK: initial render only
  latestThreatCorridors = api.state.get('threat_corridors');  // OK: initial render only
  latestZones           = api.state.get('zones');             // OK: initial render only
  _updateChecklist();

  api.panel.mount(panel);

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('terrain', (t) => {
    latestTerrain = t;
    _updateChecklist();
    _checkStale(); // loading a new DEM invalidates existing results
  }));

  unsubs.push(api.state.watch('placements', (p) => {
    latestPlacements = p;
    _updateChecklist();
    _checkStale();
  }));

  unsubs.push(api.state.watch('threat_corridors', (c) => {
    latestThreatCorridors = c;
    _updateChecklist();
    _checkStale();
  }));

  unsubs.push(api.state.watch('zones', (z) => {
    latestZones = z;
    _updateChecklist();
    _checkStale(); // changing zones invalidates existing results
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    _stopTimer();
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
  });
}
