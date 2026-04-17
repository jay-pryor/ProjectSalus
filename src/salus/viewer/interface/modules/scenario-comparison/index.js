/**
 * scenario-comparison/index.js — Scenario Comparison Module (S14.12).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Loads a saved viewer_data.js (or .json) export of a second scenario (B) and
 * compares it with the current simulation (A).  Produces:
 *   - a side-by-side summary table (coverage, cost, largest gap, worst corridor,
 *     kill-chain margin best/worst)
 *   - an overlay diff map (A-only / B-only / both) via POST /api/compare
 *   - a swipe divider that filters composite features by longitude
 *   - scenario-B sensor markers (outlined circles)
 *   - a rolling "A: X% | B: Y% | Delta: Z" summary that updates with the
 *     divider position.
 *
 * Reads:       terrain, sim_results
 * Writes:      scenario_b_sim_results
 * Emits:       comparison:loaded
 * Subscribes:  (none)
 * Map sources: scenario-comparison:a-only-src, :b-only-src, :both-src,
 *              :a-sensors-src, :b-sensors-src, :a-composite-src, :b-composite-src
 * Map layers:  scenario-comparison:a-only-fill, :b-only-fill, :both-fill,
 *              :a-sensors-circle, :b-sensors-circle,
 *              :a-composite-fill, :b-composite-fill
 *
 * File-format note: the Slice 14 export writes `window.SALUS_DATA={...};`.
 * We extract the JSON object with a regex and parse via JSON.parse rather
 * than eval() to avoid arbitrary-code-execution risk on user-selected files.
 * A `.json` file is parsed directly. Any mismatch is surfaced to the user.
 */

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

/** Watchdog timeout for /api/compare (ms). Hung backend → error banner, not spinner. */
const _COMPARE_TIMEOUT_MS = 30_000;

const _MODE_OVERLAY = 'overlay';
const _MODE_SWIPE = 'swipe';

const _PREFIX = 'scenario-comparison:';

// Layer / source IDs — one place to keep them in sync
const _SRC_A_ONLY    = `${_PREFIX}a-only-src`;
const _SRC_B_ONLY    = `${_PREFIX}b-only-src`;
const _SRC_BOTH      = `${_PREFIX}both-src`;
const _SRC_A_COMP    = `${_PREFIX}a-composite-src`;
const _SRC_B_COMP    = `${_PREFIX}b-composite-src`;
const _SRC_A_SENSORS = `${_PREFIX}a-sensors-src`;
const _SRC_B_SENSORS = `${_PREFIX}b-sensors-src`;

const _LYR_A_ONLY    = `${_PREFIX}a-only-fill`;
const _LYR_B_ONLY    = `${_PREFIX}b-only-fill`;
const _LYR_BOTH      = `${_PREFIX}both-fill`;
const _LYR_A_COMP    = `${_PREFIX}a-composite-fill`;
const _LYR_B_COMP    = `${_PREFIX}b-composite-fill`;
const _LYR_A_SENSORS = `${_PREFIX}a-sensors-circle`;
const _LYR_B_SENSORS = `${_PREFIX}b-sensors-circle`;

const _ALL_SOURCES = [
  _SRC_A_ONLY, _SRC_B_ONLY, _SRC_BOTH,
  _SRC_A_COMP, _SRC_B_COMP,
  _SRC_A_SENSORS, _SRC_B_SENSORS,
];
const _ALL_LAYERS = [
  _LYR_A_ONLY, _LYR_B_ONLY, _LYR_BOTH,
  _LYR_A_COMP, _LYR_B_COMP,
  _LYR_A_SENSORS, _LYR_B_SENSORS,
];

// ---------------------------------------------------------------------------
// File parsing helpers (exported for unit tests)
// ---------------------------------------------------------------------------

/**
 * Extract the SALUS_DATA payload from a viewer_data.js text blob.
 * Returns the parsed object on success, or throws with a clear message.
 *
 * The expected format is:  window.SALUS_DATA={...};\n
 * We match non-greedy up to the last `};` and JSON.parse the inner literal.
 */
export function _parseScenarioJsText(text) {
  // Allow whitespace and optional leading semicolons / comments
  const match = /window\.SALUS_DATA\s*=\s*(\{[\s\S]*\})\s*;?\s*$/m.exec(text);
  if (!match) {
    throw new Error('File does not match the expected "window.SALUS_DATA={...}" format.');
  }
  return JSON.parse(match[1]);
}

/**
 * Parse scenario-B file contents based on filename extension.
 * Delegates to _parseScenarioJsText for .js, JSON.parse for .json.
 */
export function _parseScenarioFile(text, filename) {
  const lower = String(filename ?? '').toLowerCase();
  if (lower.endsWith('.js')) return _parseScenarioJsText(text);
  if (lower.endsWith('.json')) return JSON.parse(text);
  // No extension — try JSON first, fall back to JS extraction
  try {
    return JSON.parse(text);
  } catch (_) {
    return _parseScenarioJsText(text);
  }
}

/**
 * Validate a parsed scenario-B payload has the minimum fields required for
 * comparison.  Returns { ok: true } or { ok: false, reason: string }.
 */
export function _validateScenarioBPayload(obj) {
  if (obj == null || typeof obj !== 'object' || Array.isArray(obj)) {
    return { ok: false, reason: 'Payload is not a JSON object.' };
  }
  if (!obj.layers || typeof obj.layers !== 'object') {
    return { ok: false, reason: 'Missing "layers" object (expected a composite coverage layer).' };
  }
  // "composite" is the key we rely on for the diff; other layer keys are optional
  if (!obj.layers.composite || typeof obj.layers.composite !== 'object') {
    return { ok: false, reason: 'Missing "layers.composite" FeatureCollection.' };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Feature centroid utilities (feature-level swipe filtering)
// ---------------------------------------------------------------------------

/**
 * Compute a rough longitude centroid for a GeoJSON feature.
 * Used only by the swipe filter to decide which side of the divider a feature
 * belongs to.  For features straddling the divider, centroid classification is
 * an acknowledged approximation (polygon-edge precision isn't possible without
 * a spatial clip, which is server-side via /api/compare).
 */
export function _featureCentroidLng(feature) {
  const g = feature?.geometry;
  if (!g) return null;
  const coords = g.coordinates;
  if (coords == null) return null;

  // Flatten arbitrary coordinate nesting into a list of [lng, lat] positions
  const positions = [];
  function walk(node) {
    if (!Array.isArray(node)) return;
    // A [lng, lat] position has two numeric elements
    if (typeof node[0] === 'number' && typeof node[1] === 'number') {
      positions.push(node);
      return;
    }
    for (const child of node) walk(child);
  }
  walk(coords);

  if (positions.length === 0) return null;
  let sum = 0;
  for (const p of positions) sum += p[0];
  return sum / positions.length;
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];
  const docListeners = [];

  // Local mirrors — avoid cross-key get() inside watch() callbacks
  let latestSimResults = null;
  let latestScenarioB  = null;

  // UI state
  let currentMode = _MODE_OVERLAY;
  let xFraction = 0.5;
  let filename = null;
  let loadedTimestamp = null;
  let diffFetchInflight = null;  // AbortController for the in-flight compare request

  // -------------------------------------------------------------------------
  // Map sources + layers (pre-created; populated later from state)
  // -------------------------------------------------------------------------
  function _addSourceAndLayer(srcId, lyrId, lyrSpec) {
    api.map.addSource(srcId, { type: 'geojson', data: _EMPTY_FC });
    api.map.addLayer({ ...lyrSpec, id: lyrId, source: srcId });
  }

  // Diff layers (hidden by default — only shown in overlay mode)
  _addSourceAndLayer(_SRC_BOTH, _LYR_BOTH, {
    type: 'fill',
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#94a3b8', 'fill-opacity': 0.20 },
  });
  _addSourceAndLayer(_SRC_A_ONLY, _LYR_A_ONLY, {
    type: 'fill',
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#ef4444', 'fill-opacity': 0.35 },
  });
  _addSourceAndLayer(_SRC_B_ONLY, _LYR_B_ONLY, {
    type: 'fill',
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#22c55e', 'fill-opacity': 0.35 },
  });

  // Composite layers used in swipe mode (hidden by default)
  _addSourceAndLayer(_SRC_A_COMP, _LYR_A_COMP, {
    type: 'fill',
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.30 },
  });
  _addSourceAndLayer(_SRC_B_COMP, _LYR_B_COMP, {
    type: 'fill',
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.30 },
  });

  // Sensor placement markers (both scenarios, always shown when scenario B loaded)
  _addSourceAndLayer(_SRC_A_SENSORS, _LYR_A_SENSORS, {
    type: 'circle',
    layout: { visibility: 'none' },
    paint: {
      'circle-radius': 7,
      'circle-color': '#3b82f6',
      'circle-opacity': 0.9,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
    },
  });
  _addSourceAndLayer(_SRC_B_SENSORS, _LYR_B_SENSORS, {
    type: 'circle',
    layout: { visibility: 'none' },
    paint: {
      'circle-radius': 7,
      'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#f59e0b',
    },
  });

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0';

  const heading = document.createElement('div');
  heading.textContent = 'Scenario Comparison';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0';
  panel.appendChild(heading);

  // ---- File picker section ----
  const fileSection = document.createElement('div');
  fileSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30';

  const fileLabel = document.createElement('div');
  fileLabel.textContent = 'Load Scenario B (viewer_data.js or .json)';
  fileLabel.style.cssText = 'font-size:12px;color:#aaa;margin-bottom:6px;font-weight:600';
  fileSection.appendChild(fileLabel);

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.js,.json';
  fileInput.setAttribute('data-testid', 'file-input');
  fileInput.style.cssText = 'width:100%;color:#e0e0e0;font-size:12px';
  fileSection.appendChild(fileInput);

  const loadedIndicator = document.createElement('div');
  loadedIndicator.setAttribute('data-testid', 'loaded-indicator');
  loadedIndicator.style.cssText =
    'display:none;margin-top:6px;padding:6px 8px;background:#0f3460;' +
    'color:#93c5fd;border-radius:3px;font-size:11px';
  loadedIndicator.style.display = 'none';
  fileSection.appendChild(loadedIndicator);

  const loadError = document.createElement('div');
  loadError.setAttribute('data-testid', 'load-error');
  loadError.style.cssText =
    'display:none;margin-top:6px;padding:6px 8px;background:#3f1f1f;' +
    'color:#fca5a5;border-radius:3px;font-size:11px';
  loadError.style.display = 'none';
  fileSection.appendChild(loadError);

  panel.appendChild(fileSection);

  // ---- Mode selector ----
  const modeSection = document.createElement('div');
  modeSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30';

  const modeLabel = document.createElement('div');
  modeLabel.textContent = 'Overlay Mode';
  modeLabel.style.cssText = 'font-size:12px;color:#aaa;margin-bottom:6px;font-weight:600';
  modeSection.appendChild(modeLabel);

  function _makeModeRadio(value, label) {
    const row = document.createElement('label');
    row.style.cssText =
      'display:flex;align-items:center;gap:8px;font-size:13px;' +
      'color:#e0e0e0;cursor:pointer;margin-bottom:4px';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'scenario-comparison-mode';
    radio.value = value;
    radio.setAttribute('data-testid', `mode-${value}`);
    if (value === currentMode) radio.checked = true;
    radio.addEventListener('change', () => {
      if (radio.checked) _setMode(value);
    });
    const text = document.createElement('span');
    text.textContent = label;
    row.append(radio, text);
    modeSection.appendChild(row);
  }
  _makeModeRadio(_MODE_OVERLAY, 'Overlay diff (A-only / B-only / both)');
  _makeModeRadio(_MODE_SWIPE, 'Swipe divider');
  panel.appendChild(modeSection);

  // ---- Diff layer visibility toggles ----
  const toggleSection = document.createElement('div');
  toggleSection.setAttribute('data-testid', 'toggle-section');
  toggleSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;display:none';
  toggleSection.style.display = 'none';

  const toggleHeading = document.createElement('div');
  toggleHeading.textContent = 'Diff Layers';
  toggleHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  toggleSection.appendChild(toggleHeading);

  function _makeToggle(testId, label, colour, layerId) {
    const row = document.createElement('label');
    row.style.cssText =
      'display:flex;align-items:center;gap:8px;font-size:12px;' +
      'color:#e0e0e0;cursor:pointer;margin-bottom:4px';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.setAttribute('data-testid', testId);
    cb.addEventListener('change', () => {
      _setLayerVisibility(layerId, cb.checked);
    });
    const swatch = document.createElement('span');
    swatch.style.cssText =
      `display:inline-block;width:10px;height:10px;background:${colour};` +
      'border-radius:2px;border:1px solid #444';
    const text = document.createElement('span');
    text.textContent = label;
    row.append(cb, swatch, text);
    toggleSection.appendChild(row);
    return cb;
  }

  const aOnlyToggle = _makeToggle('toggle-a-only', 'A only (in A, not B)', '#ef4444', _LYR_A_ONLY);
  const bOnlyToggle = _makeToggle('toggle-b-only', 'B only (in B, not A)', '#22c55e', _LYR_B_ONLY);
  const bothToggle  = _makeToggle('toggle-both',   'Both (covered by A and B)', '#94a3b8', _LYR_BOTH);
  panel.appendChild(toggleSection);

  // ---- Rolling swipe summary ----
  const swipeSummary = document.createElement('div');
  swipeSummary.setAttribute('data-testid', 'swipe-summary');
  swipeSummary.style.cssText =
    'display:none;padding:10px 12px;border-bottom:1px solid #1e1e30;' +
    'font-size:13px;color:#e0e0e0;font-family:monospace';
  swipeSummary.style.display = 'none';
  panel.appendChild(swipeSummary);

  // ---- Summary table ----
  const tableSection = document.createElement('div');
  tableSection.setAttribute('data-testid', 'summary-section');
  tableSection.style.cssText = 'padding:10px 12px;display:none';
  tableSection.style.display = 'none';

  const tableHeading = document.createElement('div');
  tableHeading.textContent = 'Comparison Summary';
  tableHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  tableSection.appendChild(tableHeading);

  const summaryTable = document.createElement('table');
  summaryTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px';

  function _makeSummaryRow(rowLabel, testIdA, testIdB) {
    const tr = document.createElement('tr');
    const tdLabel = document.createElement('td');
    tdLabel.textContent = rowLabel;
    tdLabel.style.cssText = 'color:#aaa;padding:3px 8px 3px 0;white-space:nowrap';
    const tdA = document.createElement('td');
    tdA.setAttribute('data-testid', testIdA);
    tdA.style.cssText = 'color:#93c5fd;padding:3px 8px;text-align:right';
    const tdB = document.createElement('td');
    tdB.setAttribute('data-testid', testIdB);
    tdB.style.cssText = 'color:#fde68a;padding:3px 8px;text-align:right';
    tr.append(tdLabel, tdA, tdB);
    summaryTable.appendChild(tr);
    return { a: tdA, b: tdB };
  }

  // Header row
  const headerRow = document.createElement('tr');
  const hEmpty = document.createElement('td');
  hEmpty.textContent = '';
  const hA = document.createElement('td');
  hA.textContent = 'A (current)';
  hA.style.cssText = 'color:#93c5fd;padding:3px 8px;text-align:right;font-weight:600';
  const hB = document.createElement('td');
  hB.textContent = 'B (loaded)';
  hB.style.cssText = 'color:#fde68a;padding:3px 8px;text-align:right;font-weight:600';
  headerRow.append(hEmpty, hA, hB);
  summaryTable.appendChild(headerRow);

  const coverageCells   = _makeSummaryRow('Coverage',          'summary-a-coverage',   'summary-b-coverage');
  const costCells       = _makeSummaryRow('Cost (AUD)',        'summary-a-cost',       'summary-b-cost');
  const gapCells        = _makeSummaryRow('Largest gap (m²)',  'summary-a-gap',        'summary-b-gap');
  const worstCorrCells  = _makeSummaryRow('Worst corridor',    'summary-a-worstcorr',  'summary-b-worstcorr');
  const killChainCells  = _makeSummaryRow('Kill-chain margin', 'summary-a-killchain',  'summary-b-killchain');

  tableSection.appendChild(summaryTable);
  panel.appendChild(tableSection);

  // -------------------------------------------------------------------------
  // Swipe divider DOM (added to the map canvas parent when swipe mode active)
  // -------------------------------------------------------------------------
  let dividerEl = null;
  let dividerDragging = false;

  function _ensureDivider() {
    if (dividerEl != null) return dividerEl;
    const canvas = api.map.getCanvas();
    const parent = canvas?.parentElement;
    if (!parent) return null;
    const el = document.createElement('div');
    el.setAttribute('data-testid', 'swipe-divider');
    el.style.cssText =
      'position:absolute;top:0;bottom:0;width:4px;background:#f1f5f9;' +
      'cursor:ew-resize;z-index:10;box-shadow:0 0 4px rgba(0,0,0,0.4)';
    el.style.left = `${xFraction * 100}%`;
    parent.appendChild(el);
    el.addEventListener('mousedown', _onDividerMouseDown);
    dividerEl = el;
    return el;
  }

  function _removeDivider() {
    if (dividerEl == null) return;
    const parent = dividerEl.parentElement;
    if (parent && typeof parent.removeChild === 'function') {
      parent.removeChild(dividerEl);
    }
    dividerEl = null;
    dividerDragging = false;
  }

  function _onDividerMouseDown(evt) {
    dividerDragging = true;
    if (evt && typeof evt.preventDefault === 'function') evt.preventDefault();
  }

  function _onDocumentMouseMove(evt) {
    if (!dividerDragging) return;
    const canvas = api.map.getCanvas();
    const rect = canvas && typeof canvas.getBoundingClientRect === 'function'
      ? canvas.getBoundingClientRect()
      : null;
    if (!rect || !rect.width) return;
    const clientX = evt?.clientX ?? 0;
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    _setDividerPosition(frac);
  }

  function _onDocumentMouseUp() {
    dividerDragging = false;
  }

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function _setLayerVisibility(layerId, visible) {
    if (!api.map.getLayer(layerId)) return;
    try {
      // setLayoutProperty on the proxy falls through to MapLibre's implementation
      api.map.setLayoutProperty?.(layerId, 'visibility', visible ? 'visible' : 'none');
    } catch (e) {
      console.warn(`[scenario-comparison] setLayoutProperty failed for ${layerId}:`, e);
    }
  }

  function _setSourceData(srcId, fc) {
    const src = api.map.getSource(srcId);
    if (!src || typeof src.setData !== 'function') return;
    src.setData(fc ?? _EMPTY_FC);
  }

  function _fcOrEmpty(value) {
    if (value && typeof value === 'object' && Array.isArray(value.features)) return value;
    return _EMPTY_FC;
  }

  function _formatPct(val) {
    if (val == null || Number.isNaN(Number(val))) return '\u2014';
    return `${Number(val).toFixed(1)}%`;
  }

  function _formatAud(val) {
    if (val == null || Number.isNaN(Number(val))) return '\u2014';
    return `$${Number(val).toLocaleString()}`;
  }

  function _formatArea(val) {
    if (val == null || Number.isNaN(Number(val))) return '\u2014';
    return `${Math.round(Number(val)).toLocaleString()}`;
  }

  /** Worst corridor coverage across corridor_results (min coverage_pct). */
  function _worstCorridorCoveragePct(results) {
    if (!Array.isArray(results) || results.length === 0) return null;
    let worst = Number.POSITIVE_INFINITY;
    for (const r of results) {
      const v = r?.coverage_pct;
      if (typeof v === 'number' && v < worst) worst = v;
    }
    return Number.isFinite(worst) ? worst : null;
  }

  /** Kill-chain margin best/worst string, e.g. "best 4.2s / worst -1.1s". */
  function _killChainMarginSummary(results) {
    if (!Array.isArray(results) || results.length === 0) return null;
    let best = Number.NEGATIVE_INFINITY;
    let worst = Number.POSITIVE_INFINITY;
    for (const r of results) {
      const m = r?.margin_s;
      if (typeof m === 'number') {
        if (m > best)  best = m;
        if (m < worst) worst = m;
      }
    }
    if (!Number.isFinite(best) || !Number.isFinite(worst)) return null;
    return `best ${best.toFixed(1)}s / worst ${worst.toFixed(1)}s`;
  }

  function _totalCostAud(payload) {
    // Stats may include total_cost_aud; optimiser_results may also carry it.
    // We look at both possible locations.
    if (payload?.stats?.total_cost_aud != null) return payload.stats.total_cost_aud;
    if (payload?.total_cost_aud != null) return payload.total_cost_aud;
    return null;
  }

  function _coveragePct(payload) {
    // Interface schema (from /api/simulate) uses stats.coverage_pct;
    // viewer_data.js exports use stats.total_coverage_pct. Accept both.
    if (payload?.stats?.coverage_pct != null) return payload.stats.coverage_pct;
    if (payload?.stats?.total_coverage_pct != null) return payload.stats.total_coverage_pct;
    if (payload?.total_coverage_pct != null) return payload.total_coverage_pct;
    return null;
  }

  function _largestGap(payload) {
    // stats.largest_gap_area_m2 = simulation-runner naming;
    // stats.largest_contiguous_gap_m2 = viewer_data.js naming.
    if (payload?.stats?.largest_gap_area_m2 != null) return payload.stats.largest_gap_area_m2;
    if (payload?.stats?.largest_contiguous_gap_m2 != null) return payload.stats.largest_contiguous_gap_m2;
    if (payload?.largest_contiguous_gap_m2 != null) return payload.largest_contiguous_gap_m2;
    return null;
  }

  // -------------------------------------------------------------------------
  // Summary table rendering
  // -------------------------------------------------------------------------
  function _renderSummaryTable() {
    const A = latestSimResults;
    const B = latestScenarioB;

    // Show the section only when scenario B is loaded
    tableSection.style.display = (B != null) ? 'block' : 'none';
    if (B == null) return;

    coverageCells.a.textContent = _formatPct(_coveragePct(A));
    coverageCells.b.textContent = _formatPct(_coveragePct(B));

    costCells.a.textContent = _formatAud(_totalCostAud(A));
    costCells.b.textContent = _formatAud(_totalCostAud(B));

    gapCells.a.textContent = _formatArea(_largestGap(A));
    gapCells.b.textContent = _formatArea(_largestGap(B));

    worstCorrCells.a.textContent = _formatPct(_worstCorridorCoveragePct(A?.corridor_results));
    worstCorrCells.b.textContent = _formatPct(_worstCorridorCoveragePct(B?.corridor_results));

    const aKc = _killChainMarginSummary(A?.kill_chain_results);
    const bKc = _killChainMarginSummary(B?.kill_chain_results);
    killChainCells.a.textContent = aKc ?? '\u2014';
    killChainCells.b.textContent = bKc ?? '\u2014';
  }

  // -------------------------------------------------------------------------
  // Sensor placement rendering
  // -------------------------------------------------------------------------
  function _sensorsFcFrom(payload) {
    // Scenario-B payloads from viewer_data.js carry a pre-built GeoJSON FC
    if (payload?.sensor_placements && Array.isArray(payload.sensor_placements.features)) {
      return payload.sensor_placements;
    }
    // Current sim_results may not have sensor_placements as a FeatureCollection
    // (the simulation-runner writes raster/image coverage).  Fall back to any
    // placements-like array the payload carries.
    if (Array.isArray(payload?.placements)) {
      return {
        type: 'FeatureCollection',
        features: payload.placements.map(p => ({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [p.lng ?? 0, p.lat ?? 0],
          },
          properties: { name: p.sensor_name ?? '' },
        })),
      };
    }
    return _EMPTY_FC;
  }

  function _renderSensorLayers() {
    const B = latestScenarioB;
    _setSourceData(_SRC_A_SENSORS, _sensorsFcFrom(latestSimResults));
    _setSourceData(_SRC_B_SENSORS, _sensorsFcFrom(B));
    // A sensors shown whenever B is loaded (so the user can see both)
    _setLayerVisibility(_LYR_A_SENSORS, B != null);
    _setLayerVisibility(_LYR_B_SENSORS, B != null);
  }

  // -------------------------------------------------------------------------
  // Overlay diff mode — POST /api/compare and populate layers
  // -------------------------------------------------------------------------
  async function _fetchDiff() {
    const A = latestSimResults;
    const B = latestScenarioB;
    if (A == null || B == null) return;

    // Cancel any previous in-flight request before launching a new one
    // D-401: log abort failures so proxy shape changes don't go unnoticed
    if (diffFetchInflight) {
      try {
        diffFetchInflight.abort();
      } catch (e) {
        console.warn('[scenario-comparison] previous abort() threw:', e);
      }
    }
    const ctrl = new AbortController();
    diffFetchInflight = ctrl;

    // D-399: watchdog timeout so a hung backend surfaces as an error rather
    // than leaving the UI in a spinning-forever state
    const watchdog = setTimeout(() => {
      try { ctrl.abort(); } catch (_) { /* terminal state; nothing to do */ }
    }, _COMPARE_TIMEOUT_MS);

    const aComposite = A?.layers?.composite ?? _EMPTY_FC;
    const bComposite = B?.layers?.composite ?? _EMPTY_FC;

    let body;
    try {
      body = JSON.stringify({ a_composite: aComposite, b_composite: bComposite });
    } catch (e) {
      loadError.textContent = `Failed to serialise compare request: ${e.message}`;
      loadError.style.display = 'block';
      clearTimeout(watchdog);
      if (diffFetchInflight === ctrl) diffFetchInflight = null;
      return;
    }

    let diff;
    let succeeded = false;
    try {
      const resp = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: ctrl.signal,
      });
      if (!resp || !resp.ok) {
        const status = resp ? resp.status : 'no response';
        throw new Error(`/api/compare failed: HTTP ${status}`);
      }
      diff = await resp.json();
      succeeded = true;
    } catch (err) {
      clearTimeout(watchdog);
      if (err && err.name === 'AbortError') {
        // If we aborted due to the watchdog (signal.aborted set by us), surface
        // that; a user-initiated abort (new request starting) is silent.
        if (diffFetchInflight !== ctrl && ctrl.signal.aborted) {
          // Superseded by a newer call — nothing to report
        } else {
          console.warn('[scenario-comparison] /api/compare timed out.');
          loadError.textContent =
            `Diff computation timed out after ${_COMPARE_TIMEOUT_MS / 1000}s. ` +
            'The comparison may be too large; try a simpler scenario.';
          loadError.style.display = 'block';
        }
        if (diffFetchInflight === ctrl) diffFetchInflight = null;
        // D-400: do NOT clear the existing diff sources — the user now sees
        // the stale result with an error banner (accurate) rather than an
        // empty diff (ambiguous: identical vs. failed)
        return;
      }
      console.warn('[scenario-comparison] diff fetch failed:', err);
      loadError.textContent = `Diff computation failed: ${err.message ?? err}`;
      loadError.style.display = 'block';
    } finally {
      clearTimeout(watchdog);
      if (diffFetchInflight === ctrl) diffFetchInflight = null;
    }

    // D-400: only overwrite the diff sources with the response on success.
    // On failure the previous diff (if any) stays on the map together with
    // the error banner, so the user can distinguish "identical scenarios"
    // (both sources empty but no error) from "backend failed" (error banner
    // visible, sources retain prior state).
    if (succeeded) {
      _setSourceData(_SRC_A_ONLY, _fcOrEmpty(diff.a_only));
      _setSourceData(_SRC_B_ONLY, _fcOrEmpty(diff.b_only));
      _setSourceData(_SRC_BOTH,   _fcOrEmpty(diff.both));
    }
    _applyModeVisibility();
  }

  // -------------------------------------------------------------------------
  // Swipe mode — populate composite sources and filter by divider longitude
  // -------------------------------------------------------------------------
  function _setSwipeCompositeSources() {
    const aFc = _fcOrEmpty(latestSimResults?.layers?.composite);
    const bFc = _fcOrEmpty(latestScenarioB?.layers?.composite);
    _setSourceData(_SRC_A_COMP, aFc);
    _setSourceData(_SRC_B_COMP, bFc);
  }

  // D-402: log unproject failures so the swipe filter's "no filter" fallback
  // does not silently render both scenarios on both sides of the divider
  let _unprojectFailureLogged = false;
  function _logUnprojectFailure(err) {
    if (_unprojectFailureLogged) return;
    _unprojectFailureLogged = true;
    console.warn(
      '[scenario-comparison] api.map.unproject failed — swipe filter will ' +
      'pass all features through. This indicates the map is not fully ready.',
      err,
    );
  }

  function _dividerLngFromFraction(frac) {
    const canvas = api.map.getCanvas();
    const rect = canvas && typeof canvas.getBoundingClientRect === 'function'
      ? canvas.getBoundingClientRect()
      : null;
    if (!rect || !rect.width) {
      try {
        const pt = api.map.unproject([frac * 500, 0]);
        return pt?.lng ?? null;
      } catch (err) {
        _logUnprojectFailure(err);
        return null;
      }
    }
    const pixelX = frac * rect.width;
    try {
      const pt = api.map.unproject([pixelX, rect.height / 2]);
      return pt?.lng ?? null;
    } catch (err) {
      _logUnprojectFailure(err);
      return null;
    }
  }

  function _applySwipeFilter() {
    const dividerLng = _dividerLngFromFraction(xFraction);
    const aFcRaw = _fcOrEmpty(latestSimResults?.layers?.composite);
    const bFcRaw = _fcOrEmpty(latestScenarioB?.layers?.composite);

    let aFc = aFcRaw;
    let bFc = bFcRaw;
    if (dividerLng != null) {
      aFc = {
        type: 'FeatureCollection',
        features: aFcRaw.features.filter(f => {
          const c = _featureCentroidLng(f);
          return c == null || c <= dividerLng;
        }),
      };
      bFc = {
        type: 'FeatureCollection',
        features: bFcRaw.features.filter(f => {
          const c = _featureCentroidLng(f);
          return c == null || c >= dividerLng;
        }),
      };
    }
    _setSourceData(_SRC_A_COMP, aFc);
    _setSourceData(_SRC_B_COMP, bFc);
  }

  function _updateSwipeSummary() {
    const aPct = _coveragePct(latestSimResults);
    const bPct = _coveragePct(latestScenarioB);
    if (aPct == null || bPct == null) {
      swipeSummary.textContent = 'A: \u2014 | B: \u2014 | Delta: \u2014';
      return;
    }
    // Proportional mix: left of divider = A, right = B
    const mix = (Number(aPct) * xFraction) + (Number(bPct) * (1 - xFraction));
    const delta = Number(bPct) - Number(aPct);
    const sign = delta >= 0 ? '+' : '';
    swipeSummary.textContent =
      `A: ${Number(aPct).toFixed(1)}% | B: ${Number(bPct).toFixed(1)}% | ` +
      `Delta: ${sign}${delta.toFixed(1)}pp | At divider: ${mix.toFixed(1)}%`;
  }

  function _setDividerPosition(frac) {
    xFraction = frac;
    if (dividerEl) dividerEl.style.left = `${frac * 100}%`;
    if (currentMode === _MODE_SWIPE) {
      _applySwipeFilter();
      _updateSwipeSummary();
    }
  }

  // -------------------------------------------------------------------------
  // Mode switching
  // -------------------------------------------------------------------------
  function _applyModeVisibility() {
    const bLoaded = latestScenarioB != null;

    // Overlay-only layers
    const overlayVis = (bLoaded && currentMode === _MODE_OVERLAY);
    _setLayerVisibility(_LYR_A_ONLY, overlayVis && aOnlyToggle.checked);
    _setLayerVisibility(_LYR_B_ONLY, overlayVis && bOnlyToggle.checked);
    _setLayerVisibility(_LYR_BOTH,   overlayVis && bothToggle.checked);

    // Swipe-only layers
    const swipeVis = (bLoaded && currentMode === _MODE_SWIPE);
    _setLayerVisibility(_LYR_A_COMP, swipeVis);
    _setLayerVisibility(_LYR_B_COMP, swipeVis);

    // Toggles section is relevant only in overlay mode
    toggleSection.style.display = (bLoaded && currentMode === _MODE_OVERLAY) ? 'block' : 'none';

    // Swipe divider + swipe summary
    swipeSummary.style.display = (bLoaded && currentMode === _MODE_SWIPE) ? 'block' : 'none';
    if (bLoaded && currentMode === _MODE_SWIPE) {
      _ensureDivider();
      _setSwipeCompositeSources();
      _applySwipeFilter();
      _updateSwipeSummary();
    } else {
      _removeDivider();
    }
  }

  function _setMode(mode) {
    currentMode = mode;
    _applyModeVisibility();
    if (mode === _MODE_OVERLAY && latestScenarioB != null) {
      _fetchDiff().catch(e => console.warn('[scenario-comparison] fetchDiff:', e));
    }
  }

  // -------------------------------------------------------------------------
  // File load handling
  // -------------------------------------------------------------------------
  async function _handleFileChange(evt) {
    loadError.style.display = 'none';
    loadError.textContent = '';
    const file = evt?.target?.files?.[0] ?? fileInput.files?.[0] ?? null;
    if (!file) return;

    let text;
    try {
      // file.text() is the modern File API; fall back to FileReader if absent
      if (typeof file.text === 'function') {
        text = await file.text();
      } else if (typeof globalThis.FileReader === 'function') {
        text = await new Promise((resolve, reject) => {
          const reader = new globalThis.FileReader();
          reader.onload = () => resolve(String(reader.result ?? ''));
          reader.onerror = () => reject(reader.error ?? new Error('FileReader failure'));
          reader.readAsText(file);
        });
      } else {
        throw new Error('No File API available to read the selected file.');
      }
    } catch (err) {
      loadError.textContent = `Failed to read file: ${err.message ?? err}`;
      loadError.style.display = 'block';
      return;
    }

    let parsed;
    try {
      parsed = _parseScenarioFile(text, file.name);
    } catch (err) {
      loadError.textContent = `Parse error: ${err.message ?? err}`;
      loadError.style.display = 'block';
      return;
    }

    const validation = _validateScenarioBPayload(parsed);
    if (!validation.ok) {
      loadError.textContent = `Invalid scenario B: ${validation.reason}`;
      loadError.style.display = 'block';
      return;
    }

    filename = file.name;
    loadedTimestamp = new Date().toISOString();
    loadedIndicator.textContent = `Loaded: ${filename} \u2014 ${loadedTimestamp}`;
    loadedIndicator.style.display = 'block';

    // Commit to state — watcher fires the subsequent rendering
    api.state.set('scenario_b_sim_results', parsed);
    api.bus.emit('comparison:loaded', { filename, timestamp: loadedTimestamp });
  }

  fileInput.addEventListener('change', (evt) => {
    _handleFileChange(evt).catch(err => {
      console.error('[scenario-comparison] _handleFileChange threw:', err);
    });
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestSimResults = api.state.get('sim_results');            // OK: initial render only
  latestScenarioB  = api.state.get('scenario_b_sim_results'); // OK: initial render only

  api.panel.mount(panel);
  _renderSummaryTable();
  _renderSensorLayers();
  _applyModeVisibility();
  if (latestScenarioB != null && currentMode === _MODE_OVERLAY) {
    _fetchDiff().catch(err => console.warn('[scenario-comparison] initial diff:', err));
  }

  // -------------------------------------------------------------------------
  // Reactive updates
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results', (v) => {
    latestSimResults = v;
    _renderSummaryTable();
    _renderSensorLayers();
    if (latestScenarioB != null) {
      if (currentMode === _MODE_OVERLAY) {
        _fetchDiff().catch(e => console.warn('[scenario-comparison] refetch diff:', e));
      } else {
        _setSwipeCompositeSources();
        _applySwipeFilter();
        _updateSwipeSummary();
      }
    }
  }));

  unsubs.push(api.state.watch('scenario_b_sim_results', (v) => {
    latestScenarioB = v;
    _renderSummaryTable();
    _renderSensorLayers();
    _applyModeVisibility();
    if (v != null && currentMode === _MODE_OVERLAY) {
      _fetchDiff().catch(e => console.warn('[scenario-comparison] refetch diff:', e));
    }
  }));

  // -------------------------------------------------------------------------
  // Document-level divider drag listeners
  // -------------------------------------------------------------------------
  if (globalThis.document && typeof globalThis.document.addEventListener === 'function') {
    globalThis.document.addEventListener('mousemove', _onDocumentMouseMove);
    globalThis.document.addEventListener('mouseup',   _onDocumentMouseUp);
    docListeners.push(['mousemove', _onDocumentMouseMove]);
    docListeners.push(['mouseup',   _onDocumentMouseUp]);
  }

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    // D-401: log abort failures so proxy shape changes don't go unnoticed
    if (diffFetchInflight) {
      try {
        diffFetchInflight.abort();
      } catch (e) {
        console.warn('[scenario-comparison] onUnmount abort() threw:', e);
      }
      diffFetchInflight = null;
    }
    for (const u of unsubs) { if (typeof u === 'function') u(); }
    unsubs.length = 0;

    for (const [event, handler] of docListeners) {
      try {
        globalThis.document?.removeEventListener(event, handler);
      } catch (e) {
        console.warn(`[scenario-comparison] removeEventListener(${event}) failed:`, e);
      }
    }
    docListeners.length = 0;

    _removeDivider();

    for (const layerId of _ALL_LAYERS) {
      if (api.map.getLayer(layerId)) api.map.removeLayer(layerId);
    }
    for (const srcId of _ALL_SOURCES) {
      if (api.map.getSource(srcId)) api.map.removeSource(srcId);
    }
  });
}
