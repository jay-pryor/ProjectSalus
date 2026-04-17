/**
 * coverage-viewer/index.js — Coverage Viewer Module (S14.9).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Displays simulation results as toggleable GeoJSON fill layers draped on the
 * 3D terrain.  Provides per-zone compliance indicators, bearing-line overlays
 * for directional sensors, gap click-to-inspect, and zone-compliance hover
 * tooltips.
 *
 * Reads:       terrain, placements, sim_results
 * Writes:      (none)
 * Emits:       placement:pending  (gap click with suggested sensor)
 * Subscribes:  simulation:complete
 * Map sources: coverage-viewer:{type}-source   (7 display layers)
 *              coverage-viewer:bearing-lines-source
 *              coverage-viewer:zone-compliance-source
 * Map layers:  coverage-viewer:zone-compliance-outline
 *              coverage-viewer:{type}-fill        (7)
 *              coverage-viewer:{type}-outline     (7)
 *              coverage-viewer:bearing-lines
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Length of bearing-extremity line in degrees (~1 km at mid-latitudes). */
const BEARING_LINE_LENGTH = 0.01;

/** How many percentage-points below a zone's requirement is still "marginal". */
const ZONE_MARGINAL_THRESHOLD = 5;

/**
 * Ordered list of display layers.  Matches sim_results.layers keys.
 * Composite and gaps have enlarged opacities per spec.
 */
const DISPLAY_LAYERS = [
  { key: 'Radar',     label: 'Radar',     colour: '#f97316', opacity: 0.25 },
  { key: 'RF',        label: 'RF',        colour: '#a855f7', opacity: 0.25 },
  { key: 'EO_IR',     label: 'EO/IR',     colour: '#22c55e', opacity: 0.25 },
  { key: 'Acoustic',  label: 'Acoustic',  colour: '#06b6d4', opacity: 0.25 },
  { key: 'composite', label: 'Composite', colour: '#3b82f6', opacity: 0.30 },
  { key: 'gaps',      label: 'Gaps',      colour: '#ef4444', opacity: 0.40 },
  { key: 'effectors', label: 'Effectors', colour: '#f59e0b', opacity: 0.25 },
];

const ZONE_COMPLIANCE_COLOURS = {
  pass:     '#4ade80',
  fail:     '#f87171',
  marginal: '#fbbf24',
};

// ---------------------------------------------------------------------------
// GeoJSON helpers
// ---------------------------------------------------------------------------

/** Determine zone compliance status from actual vs required coverage. */
function _complianceStatus(actualPct, requiredPct) {
  if (actualPct >= requiredPct) return 'pass';
  if (actualPct >= requiredPct - ZONE_MARGINAL_THRESHOLD) return 'marginal';
  return 'fail';
}

/**
 * Return the gaps GeoJSON from sim_results with a `gap_index` property
 * added to each feature so click-to-highlight can target individual polygons.
 */
function _gapsWithIndex(simResults) {
  const src = simResults?.layers?.gaps ?? { type: 'FeatureCollection', features: [] };
  const features = (src.features ?? []).map((f, i) => ({
    ...f,
    properties: { ...(f.properties ?? {}), gap_index: i },
  }));
  return { type: 'FeatureCollection', features };
}

/**
 * Build bearing-extremity lines for all directional sensors in
 * sim_results.sensor_placements.  Uses WGS84 latitude correction on the
 * longitude offset.  Returns a GeoJSON FeatureCollection.
 */
function _buildBearingLinesFC(sensorPlacements) {
  const features = [];
  for (const feat of (sensorPlacements?.features ?? [])) {
    const props = feat.properties ?? {};
    const azimuth = props.azimuth_coverage_deg ?? 360;
    if (azimuth >= 360) continue;
    const coords = feat.geometry?.coordinates;
    // Guard: skip features with missing or incomplete geometry — placing lines
    // at Null Island (0, 0) would be silently incorrect.
    if (!coords || coords[0] == null || coords[1] == null) continue;
    const lng = Number(coords[0]);
    const lat = Number(coords[1]);
    const bearing = props.bearing_deg ?? 0;
    const halfAngle = azimuth / 2;
    const cosLat = Math.cos(lat * Math.PI / 180);
    if (cosLat === 0) continue; // guard against lat = ±90

    for (const angleDeg of [bearing - halfAngle, bearing + halfAngle]) {
      const rad = angleDeg * Math.PI / 180;
      const dlat = BEARING_LINE_LENGTH * Math.cos(rad);
      const dlng = BEARING_LINE_LENGTH * Math.sin(rad) / cosLat;
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [[lng, lat], [lng + dlng, lat + dlat]],
        },
        properties: { sensor_name: props.sensor_name ?? '' },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

/**
 * Build a zone compliance GeoJSON FeatureCollection from zones state and
 * per-zone coverage data from sim_results.  Each feature gets a
 * `compliance_status` property: "pass" | "marginal" | "fail".
 */
function _buildZoneComplianceFC(zones, perZoneCoverage) {
  const features = [];
  for (const zone of (zones?.priority ?? [])) {
    const label = zone.label ?? '';
    const requiredPct = zone.min_coverage_pct ?? 0;
    const actualPct = perZoneCoverage?.[label] ?? 0;
    if (!zone.geometry) continue;
    features.push({
      type: 'Feature',
      geometry: zone.geometry,
      properties: {
        zone_name: label,
        required_pct: requiredPct,
        actual_pct: actualPct,
        compliance_status: _complianceStatus(actualPct, requiredPct),
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

/**
 * Extract total composite coverage % from sim_results, handling both the
 * real API format (`total_coverage_pct`) and the test-fixture format
 * (`stats.coverage_pct`).
 */
function _getCoveragePct(simResults) {
  if (simResults == null) return null;
  if (simResults.total_coverage_pct != null) return simResults.total_coverage_pct;
  if (simResults.stats?.coverage_pct != null) return simResults.stats.coverage_pct;
  return null;
}

/** Extract the per-zone coverage dict from sim_results. */
function _getPerZoneCoverage(simResults) {
  return simResults?.per_zone_coverage_pct ?? {};
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirrors
  let latestSimResults = null;
  let latestZones     = null;

  // Layer visibility: key → boolean (all on by default)
  const layerVisible = new Map(DISPLAY_LAYERS.map(l => [l.key, true]));
  let zoneComplianceVisible = true;

  // Gap inspect popup
  let inspectPopup = null;
  let selectedGapIndex = -1;

  // Zone hover tooltip
  let zoneTip = null;

  // Checkbox DOM refs for visibility toggles (key → checkbox element)
  const checkboxes = new Map();

  // Stats panel DOM refs
  let coveragePctEl = null;
  let zoneTableBody = null;

  // -------------------------------------------------------------------------
  // Map sources
  // -------------------------------------------------------------------------
  for (const { key } of DISPLAY_LAYERS) {
    api.map.addSource(`coverage-viewer:${key}-source`, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
  }
  api.map.addSource('coverage-viewer:bearing-lines-source', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });
  api.map.addSource('coverage-viewer:zone-compliance-source', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  // -------------------------------------------------------------------------
  // Map layers (z-order: compliance → fills → outlines → bearing lines)
  // -------------------------------------------------------------------------
  api.map.addLayer({
    id:     'coverage-viewer:zone-compliance-outline',
    type:   'line',
    source: 'coverage-viewer:zone-compliance-source',
    paint:  {
      'line-color': [
        'match', ['get', 'compliance_status'],
        'pass', ZONE_COMPLIANCE_COLOURS.pass,
        'fail', ZONE_COMPLIANCE_COLOURS.fail,
        ZONE_COMPLIANCE_COLOURS.marginal,
      ],
      'line-width': 3,
    },
    layout: { visibility: 'visible' },
  });

  for (const { key, colour, opacity } of DISPLAY_LAYERS) {
    api.map.addLayer({
      id:     `coverage-viewer:${key}-fill`,
      type:   'fill',
      source: `coverage-viewer:${key}-source`,
      paint:  { 'fill-color': colour, 'fill-opacity': opacity },
    });
    api.map.addLayer({
      id:     `coverage-viewer:${key}-outline`,
      type:   'line',
      source: `coverage-viewer:${key}-source`,
      paint:  { 'line-color': colour, 'line-width': 1, 'line-opacity': 0.7 },
    });
  }

  api.map.addLayer({
    id:     'coverage-viewer:bearing-lines',
    type:   'line',
    source: 'coverage-viewer:bearing-lines-source',
    paint:  { 'line-color': '#94a3b8', 'line-width': 1, 'line-dasharray': [4, 2] },
  });

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.setAttribute('data-testid', 'coverage-viewer-panel');
  panel.style.cssText =
    'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Coverage Viewer';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  // ---- Layer Control Section ----
  const layerSection = document.createElement('div');
  layerSection.setAttribute('data-testid', 'layer-control-section');
  layerSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';

  const layerHeading = document.createElement('div');
  layerHeading.textContent = 'Layer Controls';
  layerHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  layerSection.appendChild(layerHeading);

  for (const { key, label, colour } of DISPLAY_LAYERS) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:4px';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.setAttribute('data-testid', `toggle-${key}`);
    cb.checked = true;
    cb.style.cssText = 'margin:0;cursor:pointer';

    const swatch = document.createElement('span');
    swatch.setAttribute('data-testid', `swatch-${key}`);
    swatch.style.cssText =
      `display:inline-block;width:12px;height:12px;border-radius:2px;` +
      `background:${colour};flex-shrink:0`;

    const lbl = document.createElement('span');
    lbl.textContent = label;
    lbl.style.cssText = 'font-size:12px;color:#ccc;flex:1';

    const k = key; // capture for closure
    cb.addEventListener('change', () => {
      layerVisible.set(k, cb.checked);
      const vis = cb.checked ? 'visible' : 'none';
      api.map.setLayoutProperty(`coverage-viewer:${k}-fill`,    'visibility', vis);
      api.map.setLayoutProperty(`coverage-viewer:${k}-outline`, 'visibility', vis);
    });

    checkboxes.set(key, cb);
    row.append(cb, swatch, lbl);
    layerSection.appendChild(row);
  }

  // Zone compliance toggle row
  const zoneRow = document.createElement('div');
  zoneRow.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:6px;margin-bottom:2px';

  const zoneCb = document.createElement('input');
  zoneCb.type = 'checkbox';
  zoneCb.setAttribute('data-testid', 'toggle-zone-compliance');
  zoneCb.checked = true;
  zoneCb.style.cssText = 'margin:0;cursor:pointer';

  const zoneSwatch = document.createElement('span');
  zoneSwatch.style.cssText =
    'display:inline-block;width:12px;height:3px;border-radius:1px;' +
    'background:#8888aa;flex-shrink:0;border:1px solid #aaa';

  const zoneLbl = document.createElement('span');
  zoneLbl.textContent = 'Zone compliance';
  zoneLbl.style.cssText = 'font-size:12px;color:#ccc;flex:1';

  zoneCb.addEventListener('change', () => {
    zoneComplianceVisible = zoneCb.checked;
    api.map.setLayoutProperty(
      'coverage-viewer:zone-compliance-outline', 'visibility',
      zoneCb.checked ? 'visible' : 'none',
    );
  });

  zoneRow.append(zoneCb, zoneSwatch, zoneLbl);
  layerSection.appendChild(zoneRow);
  panel.appendChild(layerSection);

  // ---- Statistics Section ----
  const statsSection = document.createElement('div');
  statsSection.setAttribute('data-testid', 'stats-section');
  statsSection.style.cssText = 'padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';

  const statsHeading = document.createElement('div');
  statsHeading.textContent = 'Coverage Statistics';
  statsHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  statsSection.appendChild(statsHeading);

  const coverageRow = document.createElement('div');
  coverageRow.style.cssText = 'display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px';

  const coverageLbl = document.createElement('span');
  coverageLbl.textContent = 'Composite coverage';
  coverageLbl.style.cssText = 'color:#aaa';

  coveragePctEl = document.createElement('span');
  coveragePctEl.setAttribute('data-testid', 'composite-coverage-pct');
  coveragePctEl.textContent = '\u2014';
  coveragePctEl.style.cssText = 'color:#e0e0e0;font-weight:600';

  coverageRow.append(coverageLbl, coveragePctEl);
  statsSection.appendChild(coverageRow);

  const zoneTableHeading = document.createElement('div');
  zoneTableHeading.textContent = 'Zone compliance';
  zoneTableHeading.style.cssText =
    'font-size:11px;color:#8888aa;margin-bottom:4px';
  statsSection.appendChild(zoneTableHeading);

  const zoneTable = document.createElement('table');
  zoneTable.setAttribute('data-testid', 'zone-compliance-table');
  zoneTable.style.cssText = 'border-collapse:collapse;width:100%;font-size:11px';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const title of ['Zone', 'Req %', 'Actual %', '']) {
    const th = document.createElement('th');
    th.textContent = title;
    th.style.cssText = 'color:#666;font-weight:400;padding:2px 4px 4px;text-align:left';
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  zoneTable.appendChild(thead);

  zoneTableBody = document.createElement('tbody');
  zoneTableBody.setAttribute('data-testid', 'zone-table-body');
  zoneTable.appendChild(zoneTableBody);
  statsSection.appendChild(zoneTable);
  panel.appendChild(statsSection);

  // ---- Legend Section ----
  const legendSection = document.createElement('div');
  legendSection.setAttribute('data-testid', 'legend-section');
  legendSection.style.cssText = 'padding:8px 12px;flex-shrink:0';

  const legendHeading = document.createElement('div');
  legendHeading.textContent = 'Legend';
  legendHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  legendSection.appendChild(legendHeading);

  for (const { key, label, colour } of DISPLAY_LAYERS) {
    const item = document.createElement('div');
    item.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:3px';

    const dot = document.createElement('span');
    dot.style.cssText =
      `display:inline-block;width:10px;height:10px;border-radius:2px;` +
      `background:${colour};flex-shrink:0`;

    const txt = document.createElement('span');
    txt.textContent = label;
    txt.style.cssText = 'font-size:11px;color:#aaa';

    item.append(dot, txt);
    legendSection.appendChild(item);
  }
  panel.appendChild(legendSection);

  // -------------------------------------------------------------------------
  // Inspect popup helpers (S14.9-4)
  // -------------------------------------------------------------------------

  function _removeInspectPopup() {
    if (inspectPopup && inspectPopup.parentElement) {
      inspectPopup.parentElement.removeChild(inspectPopup);
    }
    inspectPopup = null;
  }

  function _showInspectPopup(e, feature) {
    _removeInspectPopup();
    const canvas = api.map.getCanvas();
    const container = canvas?.parentElement;
    if (!container) return;

    const props = feature.properties ?? {};
    const gapAreaRaw  = props.area_m2 ?? props.gap_area_m2;
    const gapArea     = gapAreaRaw != null
      ? `${Number(gapAreaRaw).toLocaleString()} m\u00b2`
      : '\u2014';
    const covPct  = props.coverage_pct != null
      ? `${Number(props.coverage_pct).toFixed(1)}%`
      : '\u2014';
    const coveredBy = props.covered_by
      ? String(props.covered_by)
      : '\u2014';
    const missingTypes = props.missing_types
      ? String(props.missing_types)
      : '\u2014';

    const popup = document.createElement('div');
    popup.setAttribute('data-testid', 'gap-inspect-popup');
    popup.style.cssText =
      `position:absolute;left:${e.point.x + 10}px;top:${Math.max(0, e.point.y - 10)}px;` +
      `z-index:200;background:#1a1a2e;border:1px solid #333355;border-radius:4px;` +
      `padding:8px 10px;font-size:12px;color:#e0e0e0;min-width:180px;max-width:240px;` +
      `pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,0.5)`;

    function _row(label, value) {
      const div = document.createElement('div');
      div.style.cssText = 'display:flex;justify-content:space-between;gap:8px;margin-bottom:3px';
      const l = document.createElement('span');
      l.textContent = label;
      l.style.cssText = 'color:#888';
      const v = document.createElement('span');
      v.textContent = value;
      v.style.cssText = 'color:#e0e0e0';
      div.append(l, v);
      return div;
    }

    const title = document.createElement('div');
    title.textContent = `Gap #${props.gap_index ?? '?'}`;
    title.style.cssText = 'font-weight:600;margin-bottom:6px;color:#f87171';
    popup.appendChild(title);
    popup.appendChild(_row('Area', gapArea));
    popup.appendChild(_row('Coverage at point', covPct));
    popup.appendChild(_row('Covered by', coveredBy));
    popup.appendChild(_row('Missing', missingTypes));

    container.appendChild(popup);
    inspectPopup = popup;
  }

  // -------------------------------------------------------------------------
  // Zone tooltip helpers (S14.9-5)
  // -------------------------------------------------------------------------

  function _removeZoneTip() {
    if (zoneTip && zoneTip.parentElement) {
      zoneTip.parentElement.removeChild(zoneTip);
    }
    zoneTip = null;
  }

  function _showZoneTip(e, feature) {
    _removeZoneTip();
    const canvas = api.map.getCanvas();
    const container = canvas?.parentElement;
    if (!container) return;

    const props = feature.properties ?? {};
    const tip = document.createElement('div');
    tip.setAttribute('data-testid', 'zone-compliance-tooltip');
    tip.style.cssText =
      `position:absolute;left:${e.point.x + 12}px;top:${Math.max(0, e.point.y - 8)}px;` +
      `z-index:200;background:#1a1a2e;border:1px solid #333355;border-radius:4px;` +
      `padding:6px 10px;font-size:12px;color:#e0e0e0;min-width:160px;` +
      `pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,0.5)`;

    const statusColour = ZONE_COMPLIANCE_COLOURS[props.compliance_status] ?? '#888';
    const statusLabel  = props.compliance_status
      ? String(props.compliance_status).charAt(0).toUpperCase() +
        String(props.compliance_status).slice(1)
      : 'Unknown';

    const name = document.createElement('div');
    name.setAttribute('data-testid', 'zone-tip-name');
    name.textContent = props.zone_name ?? '';
    name.style.cssText = 'font-weight:600;margin-bottom:4px';
    tip.appendChild(name);

    function _tipRow(label, value) {
      const div = document.createElement('div');
      div.style.cssText = 'display:flex;justify-content:space-between;gap:8px;margin-bottom:2px';
      const l = document.createElement('span');
      l.textContent = label;
      l.style.cssText = 'color:#888;font-size:11px';
      const v = document.createElement('span');
      v.textContent = value;
      v.style.cssText = 'color:#e0e0e0;font-size:11px';
      div.append(l, v);
      return div;
    }

    tip.appendChild(_tipRow('Required', `${Number(props.required_pct ?? 0).toFixed(0)}%`));
    tip.appendChild(_tipRow('Actual',   `${Number(props.actual_pct   ?? 0).toFixed(1)}%`));

    const statusEl = document.createElement('div');
    statusEl.setAttribute('data-testid', 'zone-tip-status');
    statusEl.textContent = statusLabel;
    statusEl.style.cssText =
      `margin-top:4px;font-weight:600;font-size:11px;color:${statusColour}`;
    tip.appendChild(statusEl);

    container.appendChild(tip);
    zoneTip = tip;
  }

  // -------------------------------------------------------------------------
  // Map event handlers
  // -------------------------------------------------------------------------

  function _onGapClick(e) {
    const feature = e.features?.[0];
    if (!feature) return;
    const gapIndex = feature.properties?.gap_index ?? -1;
    selectedGapIndex = gapIndex;

    // Highlight selected gap by boosting its opacity
    if (gapIndex >= 0) {
      api.map.setPaintProperty('coverage-viewer:gaps-fill', 'fill-opacity', [
        'case', ['==', ['get', 'gap_index'], gapIndex], 0.75, 0.15,
      ]);
    }

    _showInspectPopup(e, feature);

    // Emit placement:pending if a gap suggestion is present
    const suggestion = feature.properties?.suggestion;
    if (
      suggestion &&
      typeof suggestion === 'object' &&
      suggestion.lat != null &&
      suggestion.lng != null
    ) {
      api.bus.emit('placement:pending', {
        lat:        suggestion.lat,
        lng:        suggestion.lng,
        definition: suggestion.definition ?? null,
      });
    }
  }

  function _onMapClick() {
    // Dismiss inspect popup and reset gap highlight on any non-gap click
    if (inspectPopup) {
      _removeInspectPopup();
      selectedGapIndex = -1;
      const gapLayer = DISPLAY_LAYERS.find(l => l.key === 'gaps');
      if (gapLayer) {
        api.map.setPaintProperty(
          'coverage-viewer:gaps-fill', 'fill-opacity', gapLayer.opacity,
        );
      }
    }
  }

  function _onZoneMouseenter(e) {
    const feature = e.features?.[0];
    if (!feature) return;
    _showZoneTip(e, feature);
  }

  function _onZoneMouseleave() {
    _removeZoneTip();
  }

  api.map.on('click', 'coverage-viewer:gaps-fill',                _onGapClick);
  api.map.on('click',                                              _onMapClick);
  api.map.on('mouseenter', 'coverage-viewer:zone-compliance-outline', _onZoneMouseenter);
  api.map.on('mouseleave', 'coverage-viewer:zone-compliance-outline', _onZoneMouseleave);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _renderStats(simResults) {
    const pct = _getCoveragePct(simResults);
    if (coveragePctEl) {
      coveragePctEl.textContent = pct != null
        ? `${Number(pct).toFixed(1)}%`
        : '\u2014';
    }

    if (!zoneTableBody) return;
    while (zoneTableBody.firstChild) zoneTableBody.removeChild(zoneTableBody.firstChild);

    const perZone  = _getPerZoneCoverage(simResults);
    const zones    = latestZones;
    for (const zone of (zones?.priority ?? [])) {
      const label       = zone.label ?? '';
      const requiredPct = zone.min_coverage_pct ?? 0;
      const actualPct   = perZone[label] ?? 0;
      const status      = _complianceStatus(actualPct, requiredPct);

      const tr = document.createElement('tr');

      const tdName = document.createElement('td');
      tdName.textContent = label;
      tdName.style.cssText = 'padding:2px 4px;color:#ccc';

      const tdReq = document.createElement('td');
      tdReq.textContent = `${Number(requiredPct).toFixed(0)}%`;
      tdReq.style.cssText = 'padding:2px 4px;color:#aaa';

      const tdAct = document.createElement('td');
      tdAct.textContent = `${Number(actualPct).toFixed(1)}%`;
      tdAct.style.cssText = 'padding:2px 4px;color:#e0e0e0';

      const tdIcon = document.createElement('td');
      tdIcon.setAttribute('data-testid', `zone-status-${label}`);
      tdIcon.style.cssText =
        `padding:2px 4px;font-weight:600;` +
        `color:${ZONE_COMPLIANCE_COLOURS[status] ?? '#888'}`;
      tdIcon.textContent =
        status === 'pass' ? '\u2713'
        : status === 'fail' ? '\u2717'
        : '\u223c'; // tilde for marginal

      tr.append(tdName, tdReq, tdAct, tdIcon);
      zoneTableBody.appendChild(tr);
    }
  }

  function _rebuildLayers(simResults) {
    if (simResults == null) return;

    // Update coverage fill/outline sources
    for (const { key } of DISPLAY_LAYERS) {
      const src = api.map.getSource(`coverage-viewer:${key}-source`);
      if (src) {
        const data = key === 'gaps'
          ? _gapsWithIndex(simResults)
          : (simResults.layers?.[key] ?? { type: 'FeatureCollection', features: [] });
        src.setData(data);
      }
    }

    // Bearing lines
    const blSrc = api.map.getSource('coverage-viewer:bearing-lines-source');
    if (blSrc) {
      blSrc.setData(_buildBearingLinesFC(simResults.sensor_placements));
    }

    // Zone compliance
    const perZone = _getPerZoneCoverage(simResults);
    const zcSrc   = api.map.getSource('coverage-viewer:zone-compliance-source');
    if (zcSrc) {
      zcSrc.setData(_buildZoneComplianceFC(latestZones, perZone));
    }

    // Reset any active gap highlight
    selectedGapIndex = -1;
    _removeInspectPopup();

    _renderStats(simResults);
  }

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestSimResults = api.state.get('sim_results'); // OK: initial render only
  latestZones      = api.state.get('zones');        // OK: initial render only

  api.panel.mount(panel);

  if (latestSimResults) {
    _rebuildLayers(latestSimResults);
  }

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results', (sr) => {
    latestSimResults = sr;
    _rebuildLayers(sr);
  }));

  unsubs.push(api.state.watch('zones', (z) => {
    latestZones = z;
    // Rebuild zone compliance layer and stats when zones state changes
    if (latestSimResults) {
      const perZone = _getPerZoneCoverage(latestSimResults);
      const zcSrc   = api.map.getSource('coverage-viewer:zone-compliance-source');
      if (zcSrc) zcSrc.setData(_buildZoneComplianceFC(latestZones, perZone));
      _renderStats(latestSimResults);
    }
  }));

  // -------------------------------------------------------------------------
  // Bus subscriptions
  // -------------------------------------------------------------------------
  // simulation:complete is declared in manifest subscribes[]; the sim_results
  // state watch drives the actual layer rebuild (watch fires before the event).
  unsubs.push(api.bus.on('simulation:complete', () => {
    // Rebuild if sim_results is now available but watch may not have fired
    // (e.g. if the event is re-emitted without a state change).
    if (latestSimResults) _rebuildLayers(latestSimResults);
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    _removeInspectPopup();
    _removeZoneTip();

    unsubs.forEach(u => { if (typeof u === 'function') u(); });

    api.map.off('click', 'coverage-viewer:gaps-fill',                    _onGapClick);
    api.map.off('click',                                                  _onMapClick);
    api.map.off('mouseenter', 'coverage-viewer:zone-compliance-outline', _onZoneMouseenter);
    api.map.off('mouseleave', 'coverage-viewer:zone-compliance-outline', _onZoneMouseleave);

    const layers = [
      'coverage-viewer:zone-compliance-outline',
      ...DISPLAY_LAYERS.flatMap(l => [
        `coverage-viewer:${l.key}-fill`,
        `coverage-viewer:${l.key}-outline`,
      ]),
      'coverage-viewer:bearing-lines',
    ];
    const sources = [
      ...DISPLAY_LAYERS.map(l => `coverage-viewer:${l.key}-source`),
      'coverage-viewer:bearing-lines-source',
      'coverage-viewer:zone-compliance-source',
    ];
    for (const id of layers)  { if (api.map.getLayer(id))  api.map.removeLayer(id); }
    for (const id of sources) { if (api.map.getSource(id)) api.map.removeSource(id); }
  });
}
