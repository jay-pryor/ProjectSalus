/**
 * Salus Interactive Coverage Viewer — app.js
 *
 * Reads window.SALUS_DATA (written by package_viewer into viewer_data.js) and
 * renders:
 *   - MapLibreGL 3D terrain (Terrarium tiles served from tiles/{z}/{x}/{y}.png)
 *   - Hillshade layer for terrain depth cues
 *   - Toggle-able coverage layers draped on terrain surface
 *   - Sensor placement markers with popup details
 *   - Threat corridor overlays
 *   - Gap click-to-inspect
 *   - Kill chain Gantt chart sidebar (S14-4)
 *   - Saturation bar chart sidebar (S14-4)
 */

'use strict';

// ── Layer colour palette ─────────────────────────────────────────────────────
const LAYER_COLOURS = {
  composite: '#3b82f6',   // blue
  gaps:      '#ef4444',   // red
  EO_IR:     '#22c55e',   // green
  Radar:     '#f97316',   // orange
  RF:        '#a855f7',   // purple
  Acoustic:  '#06b6d4',   // cyan
  Effector:  '#eab308',   // yellow
};

const LAYER_LABELS = {
  composite: 'Composite Coverage',
  gaps:      'Coverage Gaps',
  EO_IR:     'EO/IR',
  Radar:     'Radar',
  RF:        'RF',
  Acoustic:  'Acoustic',
  Effector:  'Effector',
};

function layerColour(key) {
  return LAYER_COLOURS[key] || '#94a3b8';
}

function layerLabel(key) {
  return LAYER_LABELS[key] || key;
}

// Terrain tiles are served as static files under tiles/{z}/{x}/{y}.png by the
// HTTP server.  No custom protocol handler is needed — MapLibreGL fetches them
// directly via standard HTTP.  The salus:// addProtocol approach was removed
// because MapLibreGL v3 fetches raster-dem tiles inside a Web Worker; protocol
// handlers registered on the main thread are not proxied to the worker for
// that source type, so all terrain tile requests silently fail.

// ── Map bootstrap ────────────────────────────────────────────────────────────
function initMap(data) {
  const [west, south, east, north] = data.bounds_wgs84;
  const [lon, lat] = data.centre_wgs84;

  const map = new maplibregl.Map({
    container: 'map',
    style: buildMapStyle(data),
    center: [lon, lat],
    zoom: 14,
    pitch: 50,
    bearing: 0,
    maxPitch: 85,
    antialias: true,
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-right');
  map.addControl(new maplibregl.FullscreenControl(), 'top-right');

  // Surface MapLibreGL errors (e.g. terrain tile 404s) in the console so
  // rendering failures are visible during development.
  map.on('error', (e) => { console.error('[salus] MapLibreGL error:', e.error); });

  map.on('load', () => {
    addCoverageLayers(map, data);
    addSensorMarkers(map, data);
    addCorridorLayers(map, data);
    setupGapInspect(map);
    setupSidebar(data);
    buildLayerControls(map, data);
    map.fitBounds([[west, south], [east, north]], { padding: 40, duration: 800, pitch: 50, bearing: 0 });
  });

  return map;
}

// ── Map style (base + terrain) ───────────────────────────────────────────────
function buildMapStyle(data) {
  // terrain_tile_count is the number of PNG files successfully written to disk.
  // terrain_min_zoom / terrain_max_zoom are always serialised (non-optional),
  // so they cannot be used as a presence guard on their own.
  const hasTerrainTiles = (data.terrain_tile_count || 0) > 0;

  const sources = {};
  const layers = [];

  if (hasTerrainTiles) {
    sources['terrain-dem'] = {
      type: 'raster-dem',
      tiles: ['tiles/{z}/{x}/{y}.png'],
      tileSize: 256,
      encoding: 'terrarium',
      minzoom: data.terrain_min_zoom,
      maxzoom: data.terrain_max_zoom,
    };
  }

  // Minimal base style — dark background with no external tile dependencies
  layers.push({
    id: 'background',
    type: 'background',
    paint: { 'background-color': '#1a2235' },
  });

  // Hillshade gives terrain visual depth — slopes facing the virtual sun are
  // bright, slopes away are dark.  Without this layer terrain looks flat even
  // when the elevation mesh is correctly deforming the surface.
  if (hasTerrainTiles) {
    layers.push({
      id: 'hillshade',
      type: 'hillshade',
      source: 'terrain-dem',
      paint: {
        'hillshade-illumination-anchor': 'viewport',
        'hillshade-exaggeration': 0.5,
        'hillshade-shadow-color': '#1a1a2e',
        'hillshade-highlight-color': '#ffffff',
      },
    });
  }

  const style = {
    version: 8,
    sources,
    layers,
    // Sky atmosphere for depth cues when pitched
    sky: {
      'sky-color': '#199EF3',
      'sky-horizon-blend': 0.5,
      'horizon-color': '#ffffff',
      'horizon-fog-blend': 0.5,
      'fog-color': '#0000ff',
      'fog-ground-blend': 1.0,
    },
  };

  // Include terrain in the initial style so MapLibreGL activates the terrain
  // rendering pipeline from startup.  Without this the library calls
  // setTerrain(null) at style-load time (erasing any dynamically-set terrain).
  if (hasTerrainTiles) {
    style.terrain = { source: 'terrain-dem', exaggeration: 2.0 };
  }

  return style;
}

// ── Coverage layers ──────────────────────────────────────────────────────────
function addCoverageLayers(map, data) {
  const layerKeys = Object.keys(data.layers);

  for (const key of layerKeys) {
    const geojson = data.layers[key];
    if (!geojson || !geojson.features || geojson.features.length === 0) continue;

    const sourceId = `source-${key}`;
    const fillId = `fill-${key}`;
    const outlineId = `outline-${key}`;
    const colour = layerColour(key);

    map.addSource(sourceId, { type: 'geojson', data: geojson });

    // Fill polygon
    map.addLayer({
      id: fillId,
      type: 'fill',
      source: sourceId,
      paint: {
        'fill-color': colour,
        'fill-opacity': key === 'gaps' ? 0.35 : 0.25,
      },
    });

    // Outline
    map.addLayer({
      id: outlineId,
      type: 'line',
      source: sourceId,
      paint: {
        'line-color': colour,
        'line-width': key === 'gaps' ? 1.5 : 1,
        'line-opacity': 0.7,
      },
    });
  }

  // Enable 3D terrain now that layers are loaded
  if (map.getSource('terrain-dem')) {
    map.setTerrain({ source: 'terrain-dem', exaggeration: 2.0 });
    // Sky layer for atmosphere
    map.addLayer({
      id: 'sky',
      type: 'sky',
      paint: {
        'sky-type': 'atmosphere',
        'sky-atmosphere-sun': [0.0, 90.0],
        'sky-atmosphere-sun-intensity': 15,
      },
    });
  }
}

// ── Sensor markers ───────────────────────────────────────────────────────────
function addSensorMarkers(map, data) {
  if (!data.sensor_placements || !data.sensor_placements.features) return;

  map.addSource('sensors', { type: 'geojson', data: data.sensor_placements });

  map.addLayer({
    id: 'sensors-circle',
    type: 'circle',
    source: 'sensors',
    paint: {
      'circle-radius': 7,
      'circle-color': '#f8fafc',
      'circle-stroke-color': '#1e293b',
      'circle-stroke-width': 2,
    },
  });

  map.addLayer({
    id: 'sensors-label',
    type: 'symbol',
    source: 'sensors',
    layout: {
      'text-field': ['get', 'sensor_name'],
      'text-size': 11,
      'text-offset': [0, 1.4],
      'text-anchor': 'top',
    },
    paint: {
      'text-color': '#f8fafc',
      'text-halo-color': '#0f172a',
      'text-halo-width': 1.5,
    },
  });

  // Popup on click
  map.on('click', 'sensors-circle', (e) => {
    const props = e.features[0].properties;
    const coords = e.features[0].geometry.coordinates;
    const rows = Object.entries(props)
      .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
      .join('');
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(coords)
      .setHTML(`<table class="popup-table">${rows}</table>`)
      .addTo(map);
  });

  map.on('mouseenter', 'sensors-circle', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'sensors-circle', () => {
    map.getCanvas().style.cursor = '';
  });
}

// ── Corridor overlays ────────────────────────────────────────────────────────
function addCorridorLayers(map, data) {
  if (!data.corridor_results || data.corridor_results.length === 0) return;

  const features = data.corridor_results
    .filter(c => c.path_wgs84 && c.path_wgs84.length >= 2)
    .map((c, i) => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: c.path_wgs84 },
      properties: {
        corridor_index: i,
        threat_name: c.threat_name || `Corridor ${i + 1}`,
        coverage_fraction: c.coverage_fraction || 0,
        covered_length_m: c.covered_length_m || 0,
        total_length_m: c.total_length_m || 0,
      },
    }));

  if (features.length === 0) return;

  map.addSource('corridors', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features },
  });

  map.addLayer({
    id: 'corridors-line',
    type: 'line',
    source: 'corridors',
    paint: {
      'line-color': '#f97316',
      'line-width': 2,
      'line-dasharray': [3, 2],
      'line-opacity': 0.85,
    },
  });

  // Click corridor → show kill chain in sidebar
  map.on('click', 'corridors-line', (e) => {
    const idx = e.features[0].properties.corridor_index;
    showKillChain(idx, data);
    const panel = document.getElementById('panel-killchain');
    if (panel) {
      panel.classList.remove('hidden');
      panel.scrollIntoView({ behavior: 'smooth' });
    }
  });

  map.on('mouseenter', 'corridors-line', () => {
    map.getCanvas().style.cursor = 'crosshair';
  });
  map.on('mouseleave', 'corridors-line', () => {
    map.getCanvas().style.cursor = '';
  });
}

// ── Gap click-to-inspect ─────────────────────────────────────────────────────
/**
 * Approximate polygon area in m² using the shoelace formula on WGS84 coordinates.
 * Accurate to within ~1% for small (<50 km²) polygons at mid-latitudes.
 * @param {object} geometry - GeoJSON Polygon geometry
 * @returns {number|null}
 */
function roughAreaM2(geometry) {
  if (!geometry || geometry.type !== 'Polygon' || !geometry.coordinates.length) return null;
  const ring = geometry.coordinates[0];
  if (ring.length < 4) return null;
  const avgLat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
  const cosLat = Math.cos(avgLat * Math.PI / 180);
  const degToM = 111_000;
  let area = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    area += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1]);
  }
  return Math.abs(area) * 0.5 * degToM * degToM * cosLat;
}

function setupGapInspect(map) {
  map.on('click', 'fill-gaps', (e) => {
    const tooltip = document.getElementById('gap-tooltip');
    const info = document.getElementById('gap-info');
    if (!tooltip || !info) return;

    const lngLat = e.lngLat;
    const geom = e.features && e.features[0] && e.features[0].geometry;
    const area = geom ? roughAreaM2(geom) : null;
    const areaText = area !== null
      ? `Area: ~${area < 1e6 ? area.toFixed(0) + ' m²' : (area / 1e6).toFixed(2) + ' km²'}<br>`
      : '';
    info.innerHTML =
      `${areaText}` +
      `Lat: ${lngLat.lat.toFixed(5)}<br>` +
      `Lon: ${lngLat.lng.toFixed(5)}<br>` +
      `<span style="color:#6b7280;font-size:11px">Click elsewhere to dismiss</span>`;
    tooltip.classList.remove('hidden');
  });

  map.on('click', (e) => {
    // Dismiss tooltip when clicking away from gap layer
    const features = map.queryRenderedFeatures(e.point, { layers: ['fill-gaps'] });
    if (features.length === 0) {
      document.getElementById('gap-tooltip')?.classList.add('hidden');
    }
  });
}

// ── Sidebar ──────────────────────────────────────────────────────────────────
function setupSidebar(data) {
  // Title
  const titleEl = document.getElementById('scenario-title');
  if (titleEl) titleEl.textContent = data.scenario_name.replace(/_/g, ' ');

  // Generated at
  const genEl = document.getElementById('generated-at');
  if (genEl) genEl.textContent = `Generated: ${data.generated_at}`;

  // Coverage stats
  renderStats(data);

  // Kill chain
  if (data.kill_chain_results && data.kill_chain_results.length > 0) {
    document.getElementById('panel-killchain')?.classList.remove('hidden');
    buildKillChainSelect(data);
    showKillChain(0, data);
  }

  // Saturation
  if (data.saturation_result) {
    document.getElementById('panel-saturation')?.classList.remove('hidden');
    renderSaturationChart(data.saturation_result);
  }

  // Sidebar toggle
  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    const sb = document.getElementById('sidebar');
    sb?.classList.toggle('collapsed');
    document.body.classList.toggle('sidebar-collapsed');
  });
}

// ── Stats panel ───────────────────────────────────────────────────────────────
function renderStats(data) {
  const container = document.getElementById('stats-content');
  if (!container) return;

  const s = data.stats;
  const totalPct = (s.total_coverage_pct || 0).toFixed(1);
  const gapKm2 = ((s.gap_area_m2 || 0) / 1e6).toFixed(3);

  // Colour the bar based on coverage quality
  const pctNum = parseFloat(totalPct);
  const barColour = pctNum >= 80 ? '#22c55e' : pctNum >= 60 ? '#f97316' : '#ef4444';

  let html = `
    <div class="coverage-bar-wrap">
      <div class="coverage-bar-label">
        <span>Total Coverage</span><span>${totalPct}%</span>
      </div>
      <div class="coverage-bar-track">
        <div class="coverage-bar-fill" style="width:${totalPct}%;background:${barColour}"></div>
      </div>
    </div>`;

  const perLayer = s.per_layer_coverage_pct || {};
  for (const [k, v] of Object.entries(perLayer)) {
    const c = layerColour(k);
    const lbl = layerLabel(k);
    html += `
    <div class="coverage-bar-wrap">
      <div class="coverage-bar-label">
        <span style="color:${c}">${lbl}</span><span>${v.toFixed(1)}%</span>
      </div>
      <div class="coverage-bar-track">
        <div class="coverage-bar-fill" style="width:${v}%;background:${c}"></div>
      </div>
    </div>`;
  }

  html += `
    <div class="stat-row" style="margin-top:8px">
      <span class="stat-label">Gap area</span>
      <span class="stat-value">${gapKm2} km²</span>
    </div>`;

  if (s.per_zone_coverage_pct) {
    for (const [zone, pct] of Object.entries(s.per_zone_coverage_pct)) {
      html += `
      <div class="stat-row">
        <span class="stat-label">${zone}</span>
        <span class="stat-value">${pct.toFixed(1)}%</span>
      </div>`;
    }
  }

  container.innerHTML = html;
}

// ── Layer controls ────────────────────────────────────────────────────────────
function buildLayerControls(map, data) {
  const container = document.getElementById('layer-controls');
  if (!container) return;

  const layerKeys = Object.keys(data.layers);
  // Render composite first, then gaps, then sensor layers
  const ordered = [
    'composite',
    'gaps',
    ...layerKeys.filter(k => k !== 'composite' && k !== 'gaps'),
    'sensors',
    'corridors',
  ];

  for (const key of ordered) {
    const colour = layerColour(key);
    const label = layerLabel(key);

    // Determine which map layers this toggle controls
    const mapLayerIds = key === 'sensors'
      ? ['sensors-circle', 'sensors-label']
      : key === 'corridors'
        ? ['corridors-line']
        : [`fill-${key}`, `outline-${key}`];

    // Only show toggles for layers that actually exist
    if (!mapLayerIds.some(id => map.getLayer(id))) continue;

    const row = document.createElement('label');
    row.className = 'layer-toggle';

    const swatch = document.createElement('span');
    swatch.className = 'layer-swatch';
    swatch.style.background = colour;
    if (key === 'sensors') swatch.style.borderRadius = '50%';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'layer-name';
    nameSpan.textContent = label;

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'layer-checkbox';
    cb.checked = true;
    cb.addEventListener('change', () => {
      const vis = cb.checked ? 'visible' : 'none';
      mapLayerIds.forEach(id => {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
      });
    });

    row.appendChild(swatch);
    row.appendChild(nameSpan);
    row.appendChild(cb);
    container.appendChild(row);
  }
}

// ── Kill chain chart (SVG Gantt) ──────────────────────────────────────────────
function buildKillChainSelect(data) {
  const sel = document.getElementById('killchain-select');
  if (!sel) return;

  const select = document.createElement('select');
  data.kill_chain_results.forEach((kc, i) => {
    const opt = document.createElement('option');
    opt.value = i;
    const corridorIdx = kc.corridor_index !== undefined ? kc.corridor_index : i;
    const label = (data.corridor_results[corridorIdx] || {}).threat_name || `Corridor ${i + 1}`;
    opt.textContent = `${label} — ${kc.engagement_feasible ? '✓ Feasible' : '✗ Infeasible'}`;
    select.appendChild(opt);
  });
  select.addEventListener('change', () => showKillChain(parseInt(select.value), data));
  sel.appendChild(select);
}

function showKillChain(idx, data) {
  const kc = data.kill_chain_results[idx];
  if (!kc) return;

  const container = document.getElementById('killchain-chart');
  if (!container) return;

  const W = 260, H = 110;
  const MARGIN = { top: 20, right: 10, bottom: 24, left: 72 };
  const chartW = W - MARGIN.left - MARGIN.right;
  const chartH = H - MARGIN.top - MARGIN.bottom;

  // available_time_s = window from first detection to drone arrival at asset
  // required_time_s  = sum of all kill-chain phase durations
  const available = kc.available_time_s || 0;
  const required  = kc.required_time_s  || 0;
  const toa = Math.max(available, required, 1);
  const scale = chartW / toa;

  const phases = [
    { label: 'Available', start: 0, end: available, colour: '#3b82f6' },
    { label: 'Required',  start: 0, end: required,  colour: kc.engagement_feasible ? '#22c55e' : '#ef4444' },
  ];

  const barH = 18;
  const rowGap = 28;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<g transform="translate(${MARGIN.left},${MARGIN.top})">`;

  // Background
  svg += `<rect x="0" y="0" width="${chartW}" height="${chartH}" fill="rgba(255,255,255,0.02)" rx="4"/>`;

  // Time axis ticks
  const nTicks = Math.min(6, Math.floor(toa));
  for (let i = 0; i <= nTicks; i++) {
    const t = (toa / nTicks) * i;
    const x = t * scale;
    svg += `<line x1="${x}" y1="0" x2="${x}" y2="${chartH}" class="gantt-tick"/>`;
    svg += `<text x="${x}" y="${chartH + 14}" text-anchor="middle" class="gantt-axis-label">${t.toFixed(0)}s</text>`;
  }

  // Phase bars
  phases.forEach((p, i) => {
    const y = i * rowGap + (chartH - phases.length * rowGap) / 2;
    const x0 = (p.start || 0) * scale;
    const x1 = (p.end || 0) * scale;
    const bw = Math.max(x1 - x0, 2);
    svg += `<text x="-4" y="${y + barH / 2 + 4}" text-anchor="end" class="gantt-label">${p.label}</text>`;
    svg += `<rect x="${x0}" y="${y}" width="${bw}" height="${barH}" fill="${p.colour}" rx="3" opacity="0.85"/>`;
  });

  // Arrival marker — drone reaches asset at available_time_s
  const arrivalX = available * scale;
  svg += `<line x1="${arrivalX}" y1="0" x2="${arrivalX}" y2="${chartH}" class="gantt-arrival"/>`;
  svg += `<text x="${arrivalX - 2}" y="-6" text-anchor="end" style="font-size:9px;fill:#ef4444">Arrival</text>`;

  // Margin text
  const marginText = kc.engagement_feasible
    ? `+${(kc.margin_s || 0).toFixed(1)}s margin`
    : `${(kc.margin_s || 0).toFixed(1)}s short`;
  svg += `<text x="${chartW}" y="${chartH + 14}" text-anchor="end"
    class="${kc.engagement_feasible ? 'gantt-margin-ok' : 'gantt-margin-fail'}">${marginText}</text>`;

  svg += `</g></svg>`;
  container.innerHTML = svg;
}

// ── Saturation chart ──────────────────────────────────────────────────────────
function renderSaturationChart(sat) {
  const container = document.getElementById('saturation-chart');
  const statsEl  = document.getElementById('saturation-stats');
  if (!container) return;

  // per_effector_utilisation: {effector_name: fraction_used} at saturation threshold - 1
  const utilisation = sat.per_effector_utilisation || {};
  const entries = Object.entries(utilisation);

  if (entries.length === 0) {
    container.innerHTML = '<p style="color:#6b7280;font-size:11px">No effector utilisation data.</p>';
    return;
  }

  const W = 260, H = 100;
  const MARGIN = { top: 12, right: 10, bottom: 36, left: 28 };
  const chartW = W - MARGIN.left - MARGIN.right;
  const chartH = H - MARGIN.top - MARGIN.bottom;

  const barW = chartW / entries.length;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<g transform="translate(${MARGIN.left},${MARGIN.top})">`;

  entries.forEach(([name, frac], i) => {
    const x = i * barW;
    const bh = Math.max(frac * chartH, 1);
    const y = chartH - bh;
    const cls = frac >= 0.9 ? 'sat-bar-nonzero' : 'sat-bar-zero';
    svg += `<rect class="sat-bar ${cls}" x="${x + 1}" y="${y}" width="${barW - 2}" height="${bh}"/>`;
    const shortName = name.length > 8 ? name.slice(0, 7) + '…' : name;
    svg += `<text x="${x + barW / 2}" y="${chartH + 14}" text-anchor="middle" class="sat-axis-label">${shortName}</text>`;
    svg += `<text x="${x + barW / 2}" y="${chartH + 26}" text-anchor="middle" class="sat-axis-label">${(frac * 100).toFixed(0)}%</text>`;
  });

  // 100% threshold line
  svg += `<line class="sat-threshold-line" x1="0" y1="0" x2="${chartW}" y2="0"/>`;
  svg += `<text x="${chartW + 2}" y="4" style="font-size:9px;fill:#f97316">100%</text>`;

  svg += `<text x="-4" y="${chartH}" text-anchor="end" class="sat-axis-label">0</text>`;
  svg += `<text x="${chartW / 2}" y="${chartH + 38}" text-anchor="middle" class="sat-axis-label">Effector Utilisation</text>`;

  svg += `</g></svg>`;
  container.innerHTML = svg;

  if (statsEl) {
    const cap = sat.simultaneous_engagement_capacity || 0;
    const thresh = sat.saturation_threshold_n;
    statsEl.innerHTML = `
      <div class="stat-row">
        <span class="stat-label">Engagement capacity</span>
        <span class="stat-value">${cap}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Saturation at</span>
        <span class="stat-value" style="color:${thresh != null && thresh <= 3 ? '#ef4444' : '#f97316'}">${thresh != null ? thresh + ' targets' : 'N/A'}</span>
      </div>`;
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────
(function () {
  const data = window.SALUS_DATA;
  if (!data) {
    document.body.innerHTML =
      '<div style="color:#ef4444;padding:40px;font-family:monospace">' +
      'viewer_data.js not loaded — run <code>salus viewer</code> to package the viewer.</div>';
    return;
  }
  document.title = `Salus — ${data.scenario_name}`;
  initMap(data);
}());
