/**
 * saturation-analyser/index.js — Saturation Analyser Module (S14.10).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Read-only analysis module. Consumes sim_results.saturation_result to display
 * effector utilisation, saturation threshold, and approach vectors on the map
 * for a configurable simultaneous threat count (slider 1–20).
 *
 * Reads:       terrain, sim_results
 * Writes:      (none)
 * Emits:       (none)
 * Subscribes:  simulation:complete
 * Map sources: saturation-analyser:approach-vectors-source
 *              saturation-analyser:overwhelmed-effectors-source
 * Map layers:  saturation-analyser:approach-vectors-line
 *              saturation-analyser:overwhelmed-effectors-circle
 */

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

const _SLIDER_MIN = 1;
const _SLIDER_MAX = 20;

// ── Approach vector colour constants ─────────────────────────────────────────
const _COLOR_ENGAGED    = '#22c55e';
const _COLOR_UNENGAGED  = '#ef4444';

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

/**
 * Generate N evenly-spaced approach vectors toward terrain centre.
 * Each vector is a LineString from a perimeter point to the terrain centre.
 * Returns GeoJSON features array.
 */
function _buildApproachVectorFeatures(N, bounds, engagedCount) {
  if (!bounds || bounds.length < 4) return [];
  const [west, south, east, north] = bounds;
  const cx = (west + east) / 2;
  const cy = (south + north) / 2;
  const hw = (east - west) / 2;
  const hh = (north - south) / 2;
  const radius = Math.max(hw, hh) * 1.05;

  const features = [];
  for (let i = 0; i < N; i++) {
    const bearing = (i * 360 / N) * Math.PI / 180;
    // Point on perimeter (rough ellipse approximation)
    const perimLng = cx + Math.sin(bearing) * radius;
    const perimLat = cy + Math.cos(bearing) * radius;
    const colour = i < engagedCount ? _COLOR_ENGAGED : _COLOR_UNENGAGED;
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[perimLng, perimLat], [cx, cy]] },
      properties: { colour },
    });
  }
  return features;
}

// ---------------------------------------------------------------------------
// SVG chart renderer — effector utilisation bar chart
// ---------------------------------------------------------------------------

function _renderEffectorChartSvg(satResult) {
  if (!satResult) return '';
  const utilisation = satResult.per_effector_utilisation ?? {};
  const entries = Object.entries(utilisation);
  if (entries.length === 0) {
    return '<p style="color:#6b7280;font-size:11px;margin:0">No effector utilisation data.</p>';
  }

  const W = 220, H = 100;
  const ML = 28, MR = 14, MT = 12, MB = 36;
  const chartW = W - ML - MR;
  const chartH = H - MT - MB;
  const barW = chartW / entries.length;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;overflow:visible">`;
  svg += `<g transform="translate(${ML},${MT})">`;

  entries.forEach(([name, frac], i) => {
    const x  = i * barW;
    const fracNum = Math.min(1, Math.max(0, Number(frac) || 0));
    const bh = Math.max(fracNum * chartH, 1);
    const y  = chartH - bh;
    const colour = fracNum >= 0.9 ? '#ef4444' : '#22c55e';
    svg += `<rect x="${x + 1}" y="${y}" width="${barW - 2}" height="${bh}" fill="${colour}" rx="2" opacity="0.9"/>`;
    const shortName = name.length > 8 ? name.slice(0, 7) + '\u2026' : name;
    svg += `<text x="${x + barW / 2}" y="${chartH + 14}" text-anchor="middle" style="font-size:9px;fill:#6b7280">${shortName}</text>`;
    svg += `<text x="${x + barW / 2}" y="${chartH + 26}" text-anchor="middle" style="font-size:9px;fill:#6b7280">${(fracNum * 100).toFixed(0)}%</text>`;
  });

  // 100% threshold line
  svg += `<line x1="0" y1="0" x2="${chartW}" y2="0" stroke="#f97316" stroke-width="1.5" stroke-dasharray="5 3"/>`;
  svg += `<text x="${chartW + 2}" y="4" style="font-size:9px;fill:#f97316">100%</text>`;
  svg += `<text x="-4" y="${chartH}" text-anchor="end" style="font-size:9px;fill:#6b7280">0</text>`;
  svg += `<text x="${chartW / 2}" y="${chartH + 38}" text-anchor="middle" style="font-size:9px;fill:#6b7280">Effector Utilisation</text>`;

  svg += `</g></svg>`;
  return svg;
}

// ---------------------------------------------------------------------------
// SVG chart renderer — targets vs unengaged bar chart
// ---------------------------------------------------------------------------

function _renderTargetsChartSvg(satResult, selectedN) {
  if (!satResult) return '';
  const capacity  = satResult.simultaneous_engagement_capacity ?? 0;
  const threshold = satResult.saturation_threshold_n ?? (_SLIDER_MAX + 1);

  const W = 220, H = 80;
  const ML = 28, MR = 14, MT = 12, MB = 26;
  const chartW = W - ML - MR;
  const chartH = H - MT - MB;

  // Build N → unengaged count for display
  const maxN = Math.min(_SLIDER_MAX, Math.max(threshold, capacity, 1));
  const barW = chartW / maxN;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;overflow:visible">`;
  svg += `<g transform="translate(${ML},${MT})">`;

  for (let n = 1; n <= maxN; n++) {
    const unengaged = Math.max(0, n - capacity);
    const frac = unengaged / n;
    const bh = Math.max(frac * chartH, n >= threshold ? 2 : 0);
    const y = chartH - bh;
    const x = (n - 1) * barW;
    const isSelected = n === selectedN;
    const colour = n < threshold ? '#22c55e' : '#ef4444';
    svg += `<rect x="${x + 0.5}" y="${y}" width="${barW - 1}" height="${bh}" fill="${colour}" rx="1" opacity="${isSelected ? 1.0 : 0.55}"/>`;
    if (isSelected) {
      svg += `<rect x="${x + 0.5}" y="0" width="${barW - 1}" height="${chartH}" fill="none" stroke="#fff" stroke-width="1" rx="1"/>`;
    }
  }

  // Axis
  svg += `<line x1="0" y1="${chartH}" x2="${chartW}" y2="${chartH}" stroke="#333355" stroke-width="1"/>`;
  svg += `<text x="${chartW / 2}" y="${chartH + 20}" text-anchor="middle" style="font-size:9px;fill:#6b7280">Simultaneous threats (N)</text>`;
  svg += `<text x="-4" y="${chartH}" text-anchor="end" style="font-size:9px;fill:#6b7280">0</text>`;

  // Threshold marker
  if (threshold <= maxN) {
    const tx = (threshold - 1) * barW;
    svg += `<line x1="${tx}" y1="0" x2="${tx}" y2="${chartH}" stroke="#f97316" stroke-width="1.5" stroke-dasharray="3 2"/>`;
  }

  svg += `</g></svg>`;
  return svg;
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  let latestSimResults = null;
  let latestTerrain    = null;
  let currentN         = _SLIDER_MIN;

  // -------------------------------------------------------------------------
  // Map sources and layers
  // -------------------------------------------------------------------------
  api.map.addSource('saturation-analyser:approach-vectors-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addLayer({
    id: 'saturation-analyser:approach-vectors-line',
    type: 'line',
    source: 'saturation-analyser:approach-vectors-source',
    paint: {
      'line-color': ['coalesce', ['get', 'colour'], _COLOR_ENGAGED],
      'line-width': 2,
      'line-opacity': 0.8,
    },
  });

  api.map.addSource('saturation-analyser:overwhelmed-effectors-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addLayer({
    id: 'saturation-analyser:overwhelmed-effectors-circle',
    type: 'circle',
    source: 'saturation-analyser:overwhelmed-effectors-source',
    paint: {
      'circle-radius': 20,
      'circle-color': 'transparent',
      'circle-stroke-width': 3,
      'circle-stroke-color': '#ef4444',
      'circle-opacity': 0.9,
    },
  });

  // -------------------------------------------------------------------------
  // Map helpers
  // -------------------------------------------------------------------------

  function _setSource(id, fc) {
    const src = api.map.getSource(id);
    if (src) src.setData(fc ?? _EMPTY_FC);
  }

  function _updateMapLayers(N) {
    const sat = latestSimResults?.saturation_result ?? null;
    const bounds = latestTerrain?.bounds_wgs84 ?? null;

    if (!bounds) {
      _setSource('saturation-analyser:approach-vectors-source', _EMPTY_FC);
      _setSource('saturation-analyser:overwhelmed-effectors-source', _EMPTY_FC);
      return;
    }

    const capacity = sat?.simultaneous_engagement_capacity ?? 0;
    const engagedCount = Math.min(N, capacity);
    const features = _buildApproachVectorFeatures(N, bounds, engagedCount);
    _setSource('saturation-analyser:approach-vectors-source', {
      type: 'FeatureCollection',
      features,
    });

    // Overwhelmed effectors: no position data available in sim_results currently —
    // source stays empty. When the API provides effector positions, add them here.
    _setSource('saturation-analyser:overwhelmed-effectors-source', _EMPTY_FC);
  }

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Saturation Analyser';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  // ---- No-data notice ----
  const noDataNotice = document.createElement('div');
  noDataNotice.setAttribute('data-testid', 'no-data-notice');
  noDataNotice.style.cssText =
    'display:none;margin:10px 12px;padding:8px;background:#1e1e30;' +
    'color:#6b7280;border-radius:3px;font-size:12px';
  noDataNotice.textContent = 'No saturation results available. Run a simulation with saturation analysis enabled.';
  panel.appendChild(noDataNotice);

  // ---- Slider section ----
  const sliderSection = document.createElement('div');
  sliderSection.setAttribute('data-testid', 'slider-section');
  sliderSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0;display:none';

  const sliderLabel = document.createElement('div');
  sliderLabel.style.cssText = 'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.06em';
  sliderLabel.textContent = 'Simultaneous Threats';
  sliderSection.appendChild(sliderLabel);

  const sliderRow = document.createElement('div');
  sliderRow.style.cssText = 'display:flex;align-items:center;gap:8px';

  const slider = document.createElement('input');
  slider.type = 'range';
  slider.setAttribute('data-testid', 'threat-count-slider');
  slider.min = String(_SLIDER_MIN);
  slider.max = String(_SLIDER_MAX);
  slider.value = String(currentN);
  slider.style.cssText = 'flex:1;accent-color:#3b82f6';

  const sliderValue = document.createElement('div');
  sliderValue.setAttribute('data-testid', 'slider-value');
  sliderValue.textContent = String(currentN);
  sliderValue.style.cssText =
    'min-width:24px;text-align:center;font-size:14px;font-weight:600;' +
    'color:#e0e0e0;font-variant-numeric:tabular-nums';

  sliderRow.append(slider, sliderValue);
  sliderSection.appendChild(sliderRow);
  panel.appendChild(sliderSection);

  // ---- Threshold section ----
  const thresholdSection = document.createElement('div');
  thresholdSection.setAttribute('data-testid', 'threshold-section');
  thresholdSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0;display:none';

  const thresholdRow = document.createElement('div');
  thresholdRow.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px';

  const thresholdLabel = document.createElement('div');
  thresholdLabel.style.cssText = 'font-size:12px;color:#aaa';
  thresholdLabel.textContent = 'Saturation threshold';

  const thresholdValue = document.createElement('div');
  thresholdValue.setAttribute('data-testid', 'threshold-value');
  thresholdValue.style.cssText = 'font-size:12px;font-weight:600;color:#f97316';

  thresholdRow.append(thresholdLabel, thresholdValue);
  thresholdSection.appendChild(thresholdRow);

  const capacityRow = document.createElement('div');
  capacityRow.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px';

  const capacityLabel = document.createElement('div');
  capacityLabel.style.cssText = 'font-size:12px;color:#aaa';
  capacityLabel.textContent = 'Engagement capacity';

  const capacityValue = document.createElement('div');
  capacityValue.setAttribute('data-testid', 'capacity-value');
  capacityValue.style.cssText = 'font-size:12px;font-weight:600;color:#4ade80';

  capacityRow.append(capacityLabel, capacityValue);
  thresholdSection.appendChild(capacityRow);

  // Unengaged badge
  const unengagedRow = document.createElement('div');
  unengagedRow.style.cssText = 'display:flex;justify-content:space-between;align-items:center';

  const unengagedLabel = document.createElement('div');
  unengagedLabel.style.cssText = 'font-size:12px;color:#aaa';
  unengagedLabel.textContent = 'Unengaged at N';

  const unengagedBadge = document.createElement('div');
  unengagedBadge.setAttribute('data-testid', 'unengaged-badge');
  unengagedBadge.style.cssText =
    'padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;background:#3f1f1f;color:#fca5a5';

  unengagedRow.append(unengagedLabel, unengagedBadge);
  thresholdSection.appendChild(unengagedRow);

  panel.appendChild(thresholdSection);

  // ---- Effector utilisation chart ----
  const utilSection = document.createElement('div');
  utilSection.setAttribute('data-testid', 'utilisation-section');
  utilSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0;display:none';

  const utilHeading = document.createElement('div');
  utilHeading.textContent = 'Effector Utilisation';
  utilHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  utilSection.appendChild(utilHeading);

  const utilChartContainer = document.createElement('div');
  utilChartContainer.setAttribute('data-testid', 'utilisation-chart');
  utilSection.appendChild(utilChartContainer);

  panel.appendChild(utilSection);

  // ---- Targets vs unengaged chart ----
  const targetsSection = document.createElement('div');
  targetsSection.setAttribute('data-testid', 'targets-section');
  targetsSection.style.cssText = 'padding:8px 12px;flex-shrink:0;display:none';

  const targetsHeading = document.createElement('div');
  targetsHeading.textContent = 'Unengaged vs Threat Count';
  targetsHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  targetsSection.appendChild(targetsHeading);

  const targetsChartContainer = document.createElement('div');
  targetsChartContainer.setAttribute('data-testid', 'targets-chart');
  targetsSection.appendChild(targetsChartContainer);

  panel.appendChild(targetsSection);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _computeUnengaged(N) {
    const sat = latestSimResults?.saturation_result ?? null;
    if (!sat) return 0;
    const capacity = sat.simultaneous_engagement_capacity ?? 0;
    return Math.max(0, N - capacity);
  }

  function _renderPanel(N) {
    const sat = latestSimResults?.saturation_result ?? null;

    if (!sat) {
      noDataNotice.style.display = 'block';
      sliderSection.style.display = 'none';
      thresholdSection.style.display = 'none';
      utilSection.style.display = 'none';
      targetsSection.style.display = 'none';
      return;
    }

    noDataNotice.style.display = 'none';
    sliderSection.style.display = 'block';
    thresholdSection.style.display = 'block';
    utilSection.style.display = 'block';
    targetsSection.style.display = 'block';

    const capacity  = sat.simultaneous_engagement_capacity ?? 0;
    const threshold = sat.saturation_threshold_n ?? null;

    capacityValue.textContent  = String(capacity);
    thresholdValue.textContent = threshold != null
      ? `System saturates at ${threshold} simultaneous threats`
      : 'Not reached within sweep range';

    const unengaged = _computeUnengaged(N);
    unengagedBadge.textContent = String(unengaged);
    unengagedBadge.style.background = unengaged > 0 ? '#3f1f1f' : '#0f3460';
    unengagedBadge.style.color      = unengaged > 0 ? '#fca5a5' : '#93c5fd';

    utilChartContainer.innerHTML  = _renderEffectorChartSvg(sat);
    targetsChartContainer.innerHTML = _renderTargetsChartSvg(sat, N);

    _updateMapLayers(N);
  }

  // -------------------------------------------------------------------------
  // Slider interaction
  // -------------------------------------------------------------------------

  slider.addEventListener('input', () => {
    const N = parseInt(slider.value, 10) || _SLIDER_MIN;
    currentN = N;
    sliderValue.textContent = String(N);
    _renderPanel(N);
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() acceptable for initial render
  // -------------------------------------------------------------------------
  latestSimResults = api.state.get('sim_results');  // OK: initial render only
  latestTerrain    = api.state.get('terrain');       // OK: initial render only
  _renderPanel(currentN);

  api.panel.mount(panel);

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results', (r) => {
    latestSimResults = r;
    _renderPanel(currentN);
  }));

  unsubs.push(api.state.watch('terrain', (t) => {
    latestTerrain = t;
    _updateMapLayers(currentN);
  }));

  // -------------------------------------------------------------------------
  // Bus subscription — simulation:complete resets slider to 1
  // -------------------------------------------------------------------------
  unsubs.push(api.bus.on('simulation:complete', () => {
    currentN = _SLIDER_MIN;
    slider.value = String(_SLIDER_MIN);
    sliderValue.textContent = String(_SLIDER_MIN);
    _renderPanel(_SLIDER_MIN);
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
    const layers = [
      'saturation-analyser:approach-vectors-line',
      'saturation-analyser:overwhelmed-effectors-circle',
    ];
    const sources = [
      'saturation-analyser:approach-vectors-source',
      'saturation-analyser:overwhelmed-effectors-source',
    ];
    for (const id of layers) {
      if (api.map.getLayer(id)) api.map.removeLayer(id);
    }
    for (const id of sources) {
      if (api.map.getSource(id)) api.map.removeSource(id);
    }
  });
}
