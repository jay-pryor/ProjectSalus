/**
 * kill-chain-analyser/index.js — Kill Chain Analyser Module (S14.10).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Read-only analysis module. Consumes sim_results.kill_chain_results and
 * threat_corridors to display the D-T-I-D-E-A engagement timeline per
 * corridor, with map visualisation of the selected corridor, first-detection
 * point, and engagement marker.
 *
 * Reads:       terrain, sim_results, threat_corridors
 * Writes:      (none)
 * Emits:       (none)
 * Subscribes:  simulation:complete
 * Map sources: kill-chain-analyser:selected-corridor-source
 *              kill-chain-analyser:detection-event-source
 *              kill-chain-analyser:engagement-marker-source
 * Map layers:  kill-chain-analyser:selected-corridor-line
 *              kill-chain-analyser:detection-event-circles
 *              kill-chain-analyser:engagement-marker
 */

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

// Approximate metres-to-degrees at mid-latitude (for positioning)
const _M_PER_DEG_LAT = 111_320;

// ---------------------------------------------------------------------------
// Haversine distance helper
// ---------------------------------------------------------------------------

/** Returns approximate distance in metres between two [lng, lat] points. */
function _distanceM(a, b) {
  const R = 6_371_000;
  const dLat = (b[1] - a[1]) * Math.PI / 180;
  const dLng = (b[0] - a[0]) * Math.PI / 180;
  const lat1 = a[1] * Math.PI / 180;
  const lat2 = b[1] * Math.PI / 180;
  const sinDLat = Math.sin(dLat / 2);
  const sinDLng = Math.sin(dLng / 2);
  const c = sinDLat * sinDLat + Math.cos(lat1) * Math.cos(lat2) * sinDLng * sinDLng;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(c)));
}

/**
 * Walk backward along waypoints from the last point by distFromEnd metres.
 * Returns interpolated [lng, lat].
 */
function _interpolateAlongPath(waypoints, distFromEnd) {
  if (!waypoints || waypoints.length < 2) {
    return waypoints && waypoints.length > 0 ? waypoints[0] : [0, 0];
  }
  let remaining = Math.max(0, distFromEnd);
  for (let i = waypoints.length - 1; i > 0; i--) {
    const segLen = _distanceM(waypoints[i - 1], waypoints[i]);
    if (segLen <= 0) continue;
    if (remaining <= segLen) {
      const t = 1 - remaining / segLen;
      return [
        waypoints[i - 1][0] + t * (waypoints[i][0] - waypoints[i - 1][0]),
        waypoints[i - 1][1] + t * (waypoints[i][1] - waypoints[i - 1][1]),
      ];
    }
    remaining -= segLen;
  }
  return waypoints[0];
}

/** Compute bounding box of a set of [lng, lat] waypoints. Returns [west, south, east, north]. */
function _waypointsBounds(waypoints) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const [lng, lat] of waypoints) {
    if (lng < west)  west  = lng;
    if (lng > east)  east  = lng;
    if (lat < south) south = lat;
    if (lat > north) north = lat;
  }
  const pad = 0.005;
  return [west - pad, south - pad, east + pad, north + pad];
}

// ---------------------------------------------------------------------------
// Gantt chart SVG renderer
// ---------------------------------------------------------------------------

/**
 * Render an SVG Gantt chart showing available vs required kill chain time.
 * Returns an SVG string or empty string when no data.
 */
function _renderGanttSvg(kc) {
  if (!kc) return '<p style="color:#6b7280;font-size:11px;margin:0">No kill chain data for this corridor.</p>';

  const available = kc.available_time_s ?? 0;
  const required  = kc.required_time_s  ?? 0;

  if (available <= 0 && required <= 0) {
    return '<p style="color:#6b7280;font-size:11px;margin:0">No detection — kill chain timeline unavailable.</p>';
  }

  const W = 260, H = 110;
  const ML = 72, MR = 10, MT = 20, MB = 24;
  const chartW = W - ML - MR;
  const chartH = H - MT - MB;

  const toa = Math.max(available, required, 1);
  const scale = chartW / toa;

  const phases = [
    { label: 'Available', start: 0, end: available, colour: '#3b82f6' },
    { label: 'Required',  start: 0, end: required,  colour: kc.engagement_feasible ? '#22c55e' : '#ef4444' },
  ];

  const barH = 18;
  const rowGap = 28;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;overflow:visible">`;
  svg += `<g transform="translate(${ML},${MT})">`;
  svg += `<rect x="0" y="0" width="${chartW}" height="${chartH}" fill="rgba(255,255,255,0.02)" rx="4"/>`;

  const nTicks = Math.min(6, Math.max(2, Math.floor(toa)));
  for (let i = 0; i <= nTicks; i++) {
    const t = (toa / nTicks) * i;
    const x = Math.round(t * scale);
    svg += `<line x1="${x}" y1="0" x2="${x}" y2="${chartH}" stroke="#333355" stroke-width="1"/>`;
    svg += `<text x="${x}" y="${chartH + 14}" text-anchor="middle" style="font-size:9px;fill:#6b7280">${t.toFixed(0)}s</text>`;
  }

  phases.forEach((p, i) => {
    const y = i * rowGap + (chartH - phases.length * rowGap) / 2;
    const x0 = 0;
    const x1 = Math.max((p.end || 0) * scale, 2);
    svg += `<text x="-4" y="${y + barH / 2 + 4}" text-anchor="end" style="font-size:10px;fill:#aaa">${p.label}</text>`;
    svg += `<rect x="${x0}" y="${y}" width="${x1}" height="${barH}" fill="${p.colour}" rx="3" opacity="0.85"/>`;
  });

  const arrivalX = Math.round(available * scale);
  svg += `<line x1="${arrivalX}" y1="0" x2="${arrivalX}" y2="${chartH}" stroke="#ef4444" stroke-width="2" stroke-dasharray="4 2"/>`;
  svg += `<text x="${arrivalX - 2}" y="-6" text-anchor="end" style="font-size:9px;fill:#ef4444">Arrival</text>`;

  const marginText = kc.engagement_feasible
    ? `+${(kc.margin_s || 0).toFixed(1)}s`
    : `${(kc.margin_s || 0).toFixed(1)}s`;
  const marginColour = kc.engagement_feasible ? '#4ade80' : '#fca5a5';
  svg += `<text x="${chartW}" y="${chartH + 22}" text-anchor="end" style="font-size:10px;fill:${marginColour}">${marginText}</text>`;

  svg += `</g></svg>`;
  return svg;
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  let latestSimResults    = null;
  let latestThreatCorridors = null;
  let selectedIdx         = 0;

  // -------------------------------------------------------------------------
  // Map sources and layers
  // -------------------------------------------------------------------------
  const _SOURCES = [
    'kill-chain-analyser:selected-corridor-source',
    'kill-chain-analyser:detection-event-source',
    'kill-chain-analyser:engagement-marker-source',
  ];

  api.map.addSource('kill-chain-analyser:selected-corridor-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addLayer({
    id: 'kill-chain-analyser:selected-corridor-line',
    type: 'line',
    source: 'kill-chain-analyser:selected-corridor-source',
    paint: {
      'line-color': ['coalesce', ['get', 'color'], '#f97316'],
      'line-width': 4,
      'line-opacity': 0.9,
    },
  });

  api.map.addSource('kill-chain-analyser:detection-event-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addLayer({
    id: 'kill-chain-analyser:detection-event-circles',
    type: 'circle',
    source: 'kill-chain-analyser:detection-event-source',
    paint: {
      'circle-radius': 8,
      'circle-color': '#facc15',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#fff',
    },
  });

  api.map.addSource('kill-chain-analyser:engagement-marker-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addLayer({
    id: 'kill-chain-analyser:engagement-marker',
    type: 'symbol',
    source: 'kill-chain-analyser:engagement-marker-source',
    layout: {
      'text-field': '★',
      'text-size': 22,
      'text-anchor': 'center',
    },
    paint: {
      'text-color': '#f97316',
      'text-halo-color': '#fff',
      'text-halo-width': 2,
    },
  });

  // -------------------------------------------------------------------------
  // Map helpers
  // -------------------------------------------------------------------------

  function _setSource(id, fc) {
    const src = api.map.getSource(id);
    if (src) src.setData(fc ?? _EMPTY_FC);
  }

  function _updateMapLayers(idx) {
    const kcResults  = latestSimResults?.kill_chain_results ?? [];
    // threat_corridors is the canonical flat ThreatCorridor[] shape
    // (docs/Technical/InterfaceArchitecture.md §3).
    const routes     = Array.isArray(latestThreatCorridors)
      ? latestThreatCorridors
      : (latestThreatCorridors?.routes ?? []);
    const kc         = kcResults[idx];
    const route      = routes[idx];

    if (!route || !Array.isArray(route.waypoints) || route.waypoints.length < 2) {
      _setSource('kill-chain-analyser:selected-corridor-source', _EMPTY_FC);
      _setSource('kill-chain-analyser:detection-event-source', _EMPTY_FC);
      _setSource('kill-chain-analyser:engagement-marker-source', _EMPTY_FC);
      return;
    }

    const waypoints = route.waypoints;
    const color = route.color ?? '#f97316';

    // Corridor line
    _setSource('kill-chain-analyser:selected-corridor-source', {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: waypoints },
        properties: { color },
      }],
    });

    // Fly to bounds
    try {
      const [west, south, east, north] = _waypointsBounds(waypoints);
      if ([west, south, east, north].every(Number.isFinite)) {
        api.map.fitBounds([[west, south], [east, north]], { padding: 60, duration: 800 });
      }
    } catch (err) {
      console.warn('[kill-chain-analyser] fitBounds failed:', err);
    }

    // Detection event circle (at first_detection_range_m from end of corridor)
    const detectionRangeM = kc?.first_detection_range_m ?? null;
    if (detectionRangeM != null && detectionRangeM > 0) {
      const detPt = _interpolateAlongPath(waypoints, detectionRangeM);
      _setSource('kill-chain-analyser:detection-event-source', {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: { type: 'Point', coordinates: detPt },
          properties: { label: `Detection at ${detectionRangeM.toFixed(0)} m` },
        }],
      });
      // Engagement marker at same location (first detection = first engagement attempt)
      _setSource('kill-chain-analyser:engagement-marker-source', {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: { type: 'Point', coordinates: detPt },
          properties: {},
        }],
      });
    } else {
      _setSource('kill-chain-analyser:detection-event-source', _EMPTY_FC);
      _setSource('kill-chain-analyser:engagement-marker-source', _EMPTY_FC);
    }
  }

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Kill Chain Analyser';
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
  noDataNotice.textContent = 'No kill chain results available. Run a simulation first.';
  panel.appendChild(noDataNotice);

  // ---- Corridor selector section ----
  const selectorSection = document.createElement('div');
  selectorSection.setAttribute('data-testid', 'corridor-selector-section');
  selectorSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';
  selectorSection.style.display = 'none';

  const selectorLabel = document.createElement('div');
  selectorLabel.textContent = 'Corridor';
  selectorLabel.style.cssText = 'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.06em';
  selectorSection.appendChild(selectorLabel);

  const selectorRow = document.createElement('div');
  selectorRow.style.cssText = 'display:flex;gap:6px;align-items:center';

  const corridorSelect = document.createElement('select');
  corridorSelect.setAttribute('data-testid', 'corridor-select');
  corridorSelect.style.cssText =
    'flex:1;background:#1e1e30;color:#e0e0e0;border:1px solid #333355;' +
    'border-radius:3px;padding:4px 6px;font-size:12px';

  const worstBtn = document.createElement('button');
  worstBtn.textContent = 'Worst';
  worstBtn.setAttribute('data-testid', 'worst-btn');
  worstBtn.style.cssText =
    'padding:4px 10px;background:#3f1f1f;color:#fca5a5;border:1px solid #7f3030;' +
    'border-radius:3px;cursor:pointer;font-size:12px;white-space:nowrap';

  selectorRow.append(corridorSelect, worstBtn);
  selectorSection.appendChild(selectorRow);
  panel.appendChild(selectorSection);

  // ---- Gantt chart section ----
  const ganttSection = document.createElement('div');
  ganttSection.setAttribute('data-testid', 'gantt-section');
  ganttSection.style.cssText =
    'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0;display:none';

  const ganttHeading = document.createElement('div');
  ganttHeading.textContent = 'Kill Chain Timeline';
  ganttHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:8px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  ganttSection.appendChild(ganttHeading);

  const ganttContainer = document.createElement('div');
  ganttContainer.setAttribute('data-testid', 'gantt-container');
  ganttSection.appendChild(ganttContainer);

  panel.appendChild(ganttSection);

  // ---- Stats section ----
  const statsSection = document.createElement('div');
  statsSection.setAttribute('data-testid', 'stats-section');
  statsSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0;display:none';

  const statsTable = document.createElement('table');
  statsTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px';

  function _makeStatRow(label, testId) {
    const tr = document.createElement('tr');
    const tdL = document.createElement('td');
    tdL.textContent = label;
    tdL.style.cssText = 'color:#aaa;padding:2px 8px 2px 0;white-space:nowrap';
    const tdV = document.createElement('td');
    tdV.setAttribute('data-testid', testId);
    tdV.style.cssText = 'color:#e0e0e0;padding:2px 0;font-variant-numeric:tabular-nums';
    tr.append(tdL, tdV);
    statsTable.appendChild(tr);
    return tdV;
  }

  const detectionRangeCell = _makeStatRow('Detection range',  'stat-detection-range');
  const availableTimeCell  = _makeStatRow('Available time',   'stat-available-time');
  const requiredTimeCell   = _makeStatRow('Required time',    'stat-required-time');
  const marginCell         = _makeStatRow('Margin',           'stat-margin');
  statsSection.appendChild(statsTable);

  // Kill chain gap warning
  const gapWarning = document.createElement('div');
  gapWarning.setAttribute('data-testid', 'gap-warning');
  gapWarning.style.cssText =
    'display:none;margin-top:6px;padding:6px 8px;background:#3f1f1f;' +
    'color:#fca5a5;border-radius:3px;font-size:12px';
  gapWarning.textContent = '⚠ Kill chain gap — drone reaches asset before engagement completes.';
  statsSection.appendChild(gapWarning);

  panel.appendChild(statsSection);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _getKillChainResults() {
    return latestSimResults?.kill_chain_results ?? [];
  }

  function _getRoutes() {
    // threat_corridors is the canonical flat ThreatCorridor[] shape.
    if (Array.isArray(latestThreatCorridors)) return latestThreatCorridors;
    return latestThreatCorridors?.routes ?? [];
  }

  function _populateSelect() {
    const kcResults = _getKillChainResults();
    const routes    = _getRoutes();
    const count     = Math.max(kcResults.length, routes.length);

    while (corridorSelect.firstChild) corridorSelect.removeChild(corridorSelect.firstChild);

    if (count === 0) {
      noDataNotice.style.display = 'block';
      selectorSection.style.display = 'none';
      ganttSection.style.display = 'none';
      statsSection.style.display = 'none';
      return;
    }

    noDataNotice.style.display = 'none';
    selectorSection.style.display = 'block';
    ganttSection.style.display = 'block';
    statsSection.style.display = 'block';

    for (let i = 0; i < count; i++) {
      const route = routes[i];
      const kc    = kcResults[i];
      const label = route?.label ?? `Corridor ${i + 1}`;
      const feasible = kc != null ? (kc.engagement_feasible ? ' ✓' : ' ✗') : '';
      const opt = document.createElement('option');
      opt.value = String(i);
      opt.textContent = label + feasible;
      corridorSelect.appendChild(opt);
    }

    corridorSelect.value = String(Math.min(selectedIdx, count - 1));
  }

  function _renderKillChain(idx) {
    const kcResults = _getKillChainResults();
    const routes    = _getRoutes();
    const count     = Math.max(kcResults.length, routes.length);

    if (count === 0) {
      noDataNotice.style.display = 'block';
      selectorSection.style.display = 'none';
      ganttSection.style.display = 'none';
      statsSection.style.display = 'none';
      _setSource('kill-chain-analyser:selected-corridor-source', _EMPTY_FC);
      _setSource('kill-chain-analyser:detection-event-source', _EMPTY_FC);
      _setSource('kill-chain-analyser:engagement-marker-source', _EMPTY_FC);
      return;
    }

    const kc = kcResults[idx] ?? null;

    // Gantt chart
    ganttContainer.innerHTML = _renderGanttSvg(kc);

    // Stats
    if (kc) {
      detectionRangeCell.textContent =
        kc.first_detection_range_m != null
          ? `${Number(kc.first_detection_range_m).toFixed(0)} m`
          : '—';
      availableTimeCell.textContent =
        kc.available_time_s != null ? `${Number(kc.available_time_s).toFixed(1)} s` : '—';
      requiredTimeCell.textContent =
        kc.required_time_s != null ? `${Number(kc.required_time_s).toFixed(1)} s` : '—';

      const margin = kc.margin_s ?? null;
      if (margin != null) {
        const sign = margin >= 0 ? '+' : '';
        marginCell.textContent = `${sign}${Number(margin).toFixed(1)} s`;
        marginCell.style.color = margin >= 0 ? '#4ade80' : '#f87171';
      } else {
        marginCell.textContent = '—';
        marginCell.style.color = '#e0e0e0';
      }

      gapWarning.style.display = kc.engagement_feasible === false ? 'block' : 'none';
    } else {
      detectionRangeCell.textContent = '—';
      availableTimeCell.textContent  = '—';
      requiredTimeCell.textContent   = '—';
      marginCell.textContent         = '—';
      gapWarning.style.display       = 'none';
    }

    // Map layers
    _updateMapLayers(idx);
  }

  function _selectWorstCorridor() {
    const kcResults = _getKillChainResults();
    if (kcResults.length === 0) return;
    let worstIdx = 0;
    let worstMargin = Infinity;
    for (let i = 0; i < kcResults.length; i++) {
      const m = kcResults[i]?.margin_s ?? Infinity;
      if (m < worstMargin) { worstMargin = m; worstIdx = i; }
    }
    selectedIdx = worstIdx;
    corridorSelect.value = String(worstIdx);
    _renderKillChain(worstIdx);
  }

  // -------------------------------------------------------------------------
  // Event listeners
  // -------------------------------------------------------------------------
  corridorSelect.addEventListener('change', () => {
    const parsed = parseInt(corridorSelect.value, 10);
    selectedIdx = Number.isNaN(parsed) ? 0 : parsed;
    _renderKillChain(selectedIdx);
  });

  worstBtn.addEventListener('click', () => {
    _selectWorstCorridor();
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() acceptable for initial render
  // -------------------------------------------------------------------------
  latestSimResults      = api.state.get('sim_results');         // OK: initial render only
  latestThreatCorridors = api.state.get('threat_corridors');    // OK: initial render only
  _populateSelect();
  _renderKillChain(selectedIdx);

  api.panel.mount(panel);

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results', (r) => {
    latestSimResults = r;
    _populateSelect();
    _renderKillChain(selectedIdx);
  }));

  unsubs.push(api.state.watch('threat_corridors', (c) => {
    latestThreatCorridors = c;
    _populateSelect();
    _renderKillChain(selectedIdx);
  }));

  unsubs.push(api.state.watch('terrain', (_t) => { /* terrain prerequisite only */ }));

  // -------------------------------------------------------------------------
  // Bus subscription — simulation:complete re-renders for current corridor
  // -------------------------------------------------------------------------
  unsubs.push(api.bus.on('simulation:complete', () => {
    // sim_results watch fires first; this is a belt-and-braces re-render
    _renderKillChain(selectedIdx);
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
    const layers = [
      'kill-chain-analyser:selected-corridor-line',
      'kill-chain-analyser:detection-event-circles',
      'kill-chain-analyser:engagement-marker',
    ];
    const sources = [
      'kill-chain-analyser:selected-corridor-source',
      'kill-chain-analyser:detection-event-source',
      'kill-chain-analyser:engagement-marker-source',
    ];
    for (const id of layers) {
      if (api.map.getLayer(id)) api.map.removeLayer(id);
    }
    for (const id of sources) {
      if (api.map.getSource(id)) api.map.removeSource(id);
    }
  });
}
