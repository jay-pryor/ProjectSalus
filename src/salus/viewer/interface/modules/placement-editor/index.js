/**
 * placement-editor/index.js — Placement Editor Module (S14.5).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * The sole writer of the `placements` state key. Accepts placement:pending
 * events (from Library Browser, Gap Analysis) to add new sensors. Accepts
 * optimiser:complete events to present proposed placements for review before
 * committing to state.
 *
 * Reads:       terrain, sensor_library, effector_library, placements
 * Writes:      placements
 * Emits:       placement:added, placement:removed, placement:moved
 * Subscribes:  placement:pending, optimiser:complete, optimiser:apply
 * Map sources: placement-editor:sensors-source,
 *              placement-editor:bearing-lines-source,
 *              placement-editor:wedges-source,
 *              placement-editor:pending-ghost-source,
 *              placement-editor:optimiser-ghost-source
 * Map layers:  placement-editor:wedges-fill,
 *              placement-editor:bearing-lines,
 *              placement-editor:pending-ghost,
 *              placement-editor:optimiser-ghost,
 *              placement-editor:sensors-circle,
 *              placement-editor:sensors-label,
 *              placement-editor:sensors-type-badge
 */

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

/** Data-driven colour per sensor type — matches Library Browser badges. */
const LAYER_COLOURS = {
  Radar: '#f97316',
  RF: '#a855f7',
  EO_IR: '#22c55e',
  Acoustic: '#06b6d4',
};

/** Single-character / two-character abbreviation for type badge on circle. */
const LAYER_ABBREV = {
  Radar: 'R',
  RF: 'RF',
  EO_IR: 'E',
  Acoustic: 'A',
};

/** Length of bearing indicator line in degrees (~1 km at mid-latitudes). */
const BEARING_LINE_LENGTH = 0.01;

/** Radius of bearing wedge fill in degrees (~200 m). */
const WEDGE_RADIUS = 0.002;

// ---------------------------------------------------------------------------
// GeoJSON builder helpers
// ---------------------------------------------------------------------------

function _colourFor(sensorType) {
  return LAYER_COLOURS[sensorType] ?? '#888888';
}

function _buildSensorsFC(placements) {
  const features = (placements ?? []).map((p, i) => ({
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [Number(p.lng ?? 0), Number(p.lat ?? 0)],
    },
    properties: {
      index: i,
      sensor_name: p.sensor_name ?? '',
      sensor_type: p.sensor_type ?? '',
      type_abbrev: LAYER_ABBREV[p.sensor_type ?? ''] ?? '?',
    },
  }));
  return { type: 'FeatureCollection', features };
}

function _buildBearingLinesFC(placements) {
  const features = [];
  for (let i = 0; i < (placements ?? []).length; i++) {
    const p = placements[i];
    if ((p.azimuth_coverage_deg ?? 360) >= 360) continue; // omnidirectional
    const lat = Number(p.lat ?? 0);
    const lng = Number(p.lng ?? 0);
    const bearingRad = (p.bearing_deg ?? 0) * Math.PI / 180;
    const cosLat = Math.cos(lat * Math.PI / 180);
    if (cosLat === 0) continue; // guard against lat=±90 (pole) division by zero
    // WGS84 latitude correction on longitude offset — prevents misaligned wedges
    const dlat = BEARING_LINE_LENGTH * Math.cos(bearingRad);
    const dlng = BEARING_LINE_LENGTH * Math.sin(bearingRad) / cosLat;
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [[lng, lat], [lng + dlng, lat + dlat]],
      },
      properties: { index: i },
    });
  }
  return { type: 'FeatureCollection', features };
}

function _buildWedgesFC(placements) {
  const features = [];
  for (let i = 0; i < (placements ?? []).length; i++) {
    const p = placements[i];
    const azimuth = p.azimuth_coverage_deg ?? 360;
    if (azimuth >= 360) continue;
    const lat = Number(p.lat ?? 0);
    const lng = Number(p.lng ?? 0);
    const bearing = p.bearing_deg ?? 0;
    const halfAngle = azimuth / 2;
    const startBearing = bearing - halfAngle;
    const steps = Math.max(8, Math.round(azimuth / 5));
    const cosLat = Math.cos(lat * Math.PI / 180);
    if (cosLat === 0) continue; // guard against lat=±90 (pole) division by zero
    const coords = [[lng, lat]];
    for (let j = 0; j <= steps; j++) {
      const angle = (startBearing + (j / steps) * azimuth) * Math.PI / 180;
      coords.push([
        lng + WEDGE_RADIUS * Math.sin(angle) / cosLat,
        lat + WEDGE_RADIUS * Math.cos(angle),
      ]);
    }
    coords.push([lng, lat]); // close polygon
    features.push({
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [coords] },
      properties: {
        index: i,
        sensor_type: p.sensor_type ?? '',
        colour: _colourFor(p.sensor_type ?? ''),
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

function _ghostFC(placements) {
  return {
    type: 'FeatureCollection',
    features: (placements ?? []).map(p => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [Number(p.lng ?? 0), Number(p.lat ?? 0)],
      },
      properties: { sensor_name: p.sensor_name ?? '' },
    })),
  };
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirror — avoids cross-key get() inside watch()
  let latestPlacements = null;

  // Selection and interaction state
  let selectedIndex = -1;
  let isDragging = false;
  let dragIndex = -1;

  // Pending placement state (placement:pending mode)
  let pendingDef = null; // { lat, lng, definition }

  // Optimiser modal state
  let optimiserProposed = null; // array of proposed placements

  // Map canvas — cached once for cursor management
  const canvas = api.map.getCanvas();

  // -------------------------------------------------------------------------
  // Map sources
  // -------------------------------------------------------------------------
  api.map.addSource('placement-editor:sensors-source',       { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('placement-editor:bearing-lines-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('placement-editor:wedges-source',        { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('placement-editor:pending-ghost-source', { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('placement-editor:optimiser-ghost-source', { type: 'geojson', data: _EMPTY_FC });

  // -------------------------------------------------------------------------
  // Map layers (order: wedges → bearing lines → ghost → circles → labels)
  // -------------------------------------------------------------------------
  api.map.addLayer({
    id: 'placement-editor:wedges-fill',
    type: 'fill',
    source: 'placement-editor:wedges-source',
    paint: { 'fill-color': ['get', 'colour'], 'fill-opacity': 0.20 },
  });

  api.map.addLayer({
    id: 'placement-editor:bearing-lines',
    type: 'line',
    source: 'placement-editor:bearing-lines-source',
    paint: { 'line-color': '#ef4444', 'line-width': 2 },
  });

  api.map.addLayer({
    id: 'placement-editor:pending-ghost',
    type: 'circle',
    source: 'placement-editor:pending-ghost-source',
    paint: {
      'circle-radius': 14,
      'circle-color': '#fbbf24',
      'circle-opacity': 0.30,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#fbbf24',
      'circle-stroke-opacity': 0.8,
    },
  });

  api.map.addLayer({
    id: 'placement-editor:optimiser-ghost',
    type: 'circle',
    source: 'placement-editor:optimiser-ghost-source',
    paint: {
      'circle-radius': 16,
      'circle-color': '#f97316',
      'circle-opacity': 0.20,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#f97316',
      'circle-stroke-opacity': 0.8,
    },
  });

  api.map.addLayer({
    id: 'placement-editor:sensors-circle',
    type: 'circle',
    source: 'placement-editor:sensors-source',
    paint: {
      'circle-radius': 12,
      'circle-color': [
        'match', ['get', 'sensor_type'],
        'Radar', '#f97316',
        'RF', '#a855f7',
        'EO_IR', '#22c55e',
        'Acoustic', '#06b6d4',
        '#888888',
      ],
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.8,
    },
  });

  api.map.addLayer({
    id: 'placement-editor:sensors-label',
    type: 'symbol',
    source: 'placement-editor:sensors-source',
    layout: {
      'text-field': ['get', 'sensor_name'],
      'text-anchor': 'top',
      'text-offset': [0, 1.2],
      'text-size': 11,
    },
    paint: {
      'text-color': '#e0e0e0',
      'text-halo-color': '#000000',
      'text-halo-width': 1,
    },
  });

  api.map.addLayer({
    id: 'placement-editor:sensors-type-badge',
    type: 'symbol',
    source: 'placement-editor:sensors-source',
    layout: {
      'text-field': ['get', 'type_abbrev'],
      'text-anchor': 'center',
      'text-size': 10,
    },
    paint: { 'text-color': '#ffffff' },
  });

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Placement Editor';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  // ---- Placement list ----
  const listContainer = document.createElement('div');
  listContainer.setAttribute('data-testid', 'placement-list');
  listContainer.style.cssText = 'flex:1;overflow-y:auto';
  panel.appendChild(listContainer);

  // ---- Confirm placement section (placement:pending mode) ----
  const confirmSection = document.createElement('div');
  confirmSection.setAttribute('data-testid', 'confirm-section');
  confirmSection.style.cssText =
    'display:none;padding:10px 12px;border-top:1px solid #1e1e30;' +
    'background:#0f1a2e;flex-shrink:0';
  confirmSection.style.display = 'none';

  const confirmHeading = document.createElement('div');
  confirmHeading.textContent = 'Confirm Placement';
  confirmHeading.style.cssText = 'font-size:12px;font-weight:600;color:#93c5fd;margin-bottom:8px';
  confirmSection.appendChild(confirmHeading);

  const confirmNameEl = document.createElement('div');
  confirmNameEl.setAttribute('data-testid', 'confirm-name');
  confirmNameEl.style.cssText = 'font-size:12px;color:#e0e0e0;margin-bottom:8px';
  confirmSection.appendChild(confirmNameEl);

  const bearingDial = document.createElement('div');
  bearingDial.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:8px';

  const bearingDialLabel = document.createElement('label');
  bearingDialLabel.textContent = 'Bearing:';
  bearingDialLabel.style.cssText = 'font-size:12px;color:#aaa';

  const bearingDialInput = document.createElement('input');
  bearingDialInput.type = 'number';
  bearingDialInput.setAttribute('data-testid', 'confirm-bearing-input');
  bearingDialInput.min = '0';
  bearingDialInput.max = '359';
  bearingDialInput.value = '0';
  bearingDialInput.style.cssText =
    'width:60px;background:#1e1e30;color:#e0e0e0;border:1px solid #333355;' +
    'border-radius:3px;padding:2px 6px;font-size:12px';

  bearingDial.append(bearingDialLabel, bearingDialInput);
  confirmSection.appendChild(bearingDial);

  const confirmRow = document.createElement('div');
  confirmRow.style.cssText = 'display:flex;gap:8px';

  const placeBtn = document.createElement('button');
  placeBtn.textContent = 'Place';
  placeBtn.setAttribute('data-testid', 'place-btn');
  placeBtn.style.cssText =
    'flex:1;padding:5px 10px;background:#065f46;color:#fff;' +
    'border:1px solid #059669;border-radius:3px;cursor:pointer;font-size:12px;font-weight:600';

  const cancelPendingBtn = document.createElement('button');
  cancelPendingBtn.textContent = 'Cancel';
  cancelPendingBtn.setAttribute('data-testid', 'cancel-pending-btn');
  cancelPendingBtn.style.cssText =
    'padding:5px 10px;background:#3f1f1f;color:#fca5a5;' +
    'border:1px solid #7f3030;border-radius:3px;cursor:pointer;font-size:12px';

  confirmRow.append(placeBtn, cancelPendingBtn);
  confirmSection.appendChild(confirmRow);
  panel.appendChild(confirmSection);

  // ---- Optimiser modal overlay ----
  const optimiserModal = document.createElement('div');
  optimiserModal.setAttribute('data-testid', 'optimiser-modal');
  optimiserModal.style.cssText =
    'display:none;padding:10px 12px;border-top:1px solid #1e1e30;' +
    'background:#1a1a0a;flex-shrink:0';
  optimiserModal.style.display = 'none';

  const modalHeading = document.createElement('div');
  modalHeading.textContent = 'Proposed Configuration';
  modalHeading.style.cssText =
    'font-size:12px;font-weight:600;color:#fb923c;margin-bottom:6px';
  optimiserModal.appendChild(modalHeading);

  const modalCount = document.createElement('div');
  modalCount.setAttribute('data-testid', 'modal-count');
  modalCount.style.cssText = 'font-size:12px;color:#e0e0e0;margin-bottom:8px';
  optimiserModal.appendChild(modalCount);

  const modalBtns = document.createElement('div');
  modalBtns.style.cssText = 'display:flex;gap:8px';

  const modalApplyBtn = document.createElement('button');
  modalApplyBtn.textContent = 'Apply';
  modalApplyBtn.setAttribute('data-testid', 'modal-apply-btn');
  modalApplyBtn.style.cssText =
    'flex:1;padding:5px 10px;background:#065f46;color:#fff;' +
    'border:1px solid #059669;border-radius:3px;cursor:pointer;font-size:12px;font-weight:600';

  const modalDiscardBtn = document.createElement('button');
  modalDiscardBtn.textContent = 'Discard';
  modalDiscardBtn.setAttribute('data-testid', 'modal-discard-btn');
  modalDiscardBtn.style.cssText =
    'padding:5px 10px;background:#3f1f1f;color:#fca5a5;' +
    'border:1px solid #7f3030;border-radius:3px;cursor:pointer;font-size:12px';

  modalBtns.append(modalApplyBtn, modalDiscardBtn);
  optimiserModal.appendChild(modalBtns);
  panel.appendChild(optimiserModal);

  // ---- Import / Export buttons ----
  const ioRow = document.createElement('div');
  ioRow.style.cssText =
    'padding:8px 12px;border-top:1px solid #1e1e30;display:flex;gap:8px;flex-shrink:0';

  const exportBtn = document.createElement('button');
  exportBtn.textContent = 'Export';
  exportBtn.setAttribute('data-testid', 'export-btn');
  exportBtn.style.cssText =
    'flex:1;padding:5px 10px;background:#1e1e30;color:#e0e0e0;' +
    'border:1px solid #333355;border-radius:3px;cursor:pointer;font-size:12px';

  const importFileInput = document.createElement('input');
  importFileInput.type = 'file';
  importFileInput.setAttribute('data-testid', 'import-file-input');
  importFileInput.accept = '.json';
  importFileInput.style.cssText = 'display:none';

  const importBtn = document.createElement('button');
  importBtn.textContent = 'Import';
  importBtn.setAttribute('data-testid', 'import-btn');
  importBtn.style.cssText =
    'flex:1;padding:5px 10px;background:#1e1e30;color:#e0e0e0;' +
    'border:1px solid #333355;border-radius:3px;cursor:pointer;font-size:12px';

  ioRow.append(exportBtn, importBtn, importFileInput);
  panel.appendChild(ioRow);

  // Import error / feedback notice
  const importErrorEl = document.createElement('div');
  importErrorEl.setAttribute('data-testid', 'import-error');
  importErrorEl.style.cssText =
    'display:none;padding:4px 12px 8px;font-size:11px;color:#f87171';
  importErrorEl.style.display = 'none';
  panel.appendChild(importErrorEl);

  // -------------------------------------------------------------------------
  // Helpers — clear container children
  // -------------------------------------------------------------------------
  function _clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _renderList() {
    _clearChildren(listContainer);
    const placements = latestPlacements ?? [];

    if (placements.length === 0) {
      const emptyEl = document.createElement('div');
      emptyEl.setAttribute('data-testid', 'empty-message');
      emptyEl.textContent = 'No placements yet.';
      emptyEl.style.cssText =
        'padding:12px;font-size:12px;color:#666;text-align:center';
      listContainer.appendChild(emptyEl);
      return;
    }

    for (let i = 0; i < placements.length; i++) {
      const p = placements[i];
      const row = document.createElement('div');
      row.setAttribute('data-testid', `placement-row-${i}`);
      row.style.cssText =
        `display:flex;align-items:center;gap:6px;padding:6px 10px;` +
        `border-bottom:1px solid #1e1e30;cursor:pointer;` +
        `background:${i === selectedIndex ? '#1a2a3a' : 'transparent'}`;

      const badge = document.createElement('span');
      badge.setAttribute('data-testid', `placement-badge-${i}`);
      badge.textContent = LAYER_ABBREV[p.sensor_type ?? ''] ?? '?';
      badge.style.cssText =
        `display:inline-block;width:22px;height:22px;border-radius:50%;` +
        `background:${_colourFor(p.sensor_type ?? '')};color:#fff;` +
        `font-size:10px;font-weight:700;text-align:center;line-height:22px;flex-shrink:0`;

      const nameEl = document.createElement('span');
      nameEl.setAttribute('data-testid', `placement-name-${i}`);
      nameEl.textContent = p.sensor_name ?? '(unnamed)';
      nameEl.style.cssText =
        'flex:1;font-size:12px;color:#e0e0e0;overflow:hidden;' +
        'text-overflow:ellipsis;white-space:nowrap';

      // Bearing input
      const bearingInput = document.createElement('input');
      bearingInput.type = 'number';
      bearingInput.setAttribute('data-testid', `bearing-input-${i}`);
      bearingInput.min = '0';
      bearingInput.max = '359';
      bearingInput.value = String(p.bearing_deg ?? 0);
      bearingInput.style.cssText =
        'width:50px;background:#1e1e30;color:#e0e0e0;border:1px solid #333355;' +
        'border-radius:3px;padding:2px 4px;font-size:11px';

      // Capture i in closure
      const idx = i;
      bearingInput.addEventListener('change', () => {
        const parsed = Number(bearingInput.value);
        if (!Number.isFinite(parsed)) return;
        const updated = (latestPlacements ?? []).map((pp, ii) =>
          ii === idx ? { ...pp, bearing_deg: ((parsed % 360) + 360) % 360 } : pp
        );
        api.state.set('placements', updated);
      });

      // Height override input
      const heightInput = document.createElement('input');
      heightInput.type = 'number';
      heightInput.setAttribute('data-testid', `height-input-${i}`);
      heightInput.placeholder = 'h m';
      heightInput.value = p.height_m != null ? String(p.height_m) : '';
      heightInput.style.cssText =
        'width:44px;background:#1e1e30;color:#e0e0e0;border:1px solid #333355;' +
        'border-radius:3px;padding:2px 4px;font-size:11px';

      heightInput.addEventListener('change', () => {
        const raw = heightInput.value;
        const parsed = raw !== '' ? Number(raw) : null;
        const updated = (latestPlacements ?? []).map((pp, ii) =>
          ii === idx ? { ...pp, height_m: parsed } : pp
        );
        api.state.set('placements', updated);
      });

      // Remove button
      const removeBtn = document.createElement('button');
      removeBtn.textContent = '\u00d7'; // ×
      removeBtn.setAttribute('data-testid', `remove-btn-${i}`);
      removeBtn.style.cssText =
        'padding:2px 6px;background:#3f1f1f;color:#fca5a5;border:1px solid #7f3030;' +
        'border-radius:3px;cursor:pointer;font-size:13px;flex-shrink:0';

      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const removed = (latestPlacements ?? [])[idx];
        const updated = (latestPlacements ?? []).filter((_, ii) => ii !== idx);
        api.state.set('placements', updated);
        if (removed) api.bus.emit('placement:removed', removed);
        if (selectedIndex === idx) selectedIndex = -1;
        else if (selectedIndex > idx) selectedIndex--;
      });

      row.addEventListener('click', () => {
        selectedIndex = idx;
        _renderList();
      });

      row.append(badge, nameEl, bearingInput, heightInput, removeBtn);
      listContainer.appendChild(row);
    }
  }

  function _rebuildSources() {
    const placements = latestPlacements ?? [];

    const sensorsSrc = api.map.getSource('placement-editor:sensors-source');
    if (sensorsSrc) sensorsSrc.setData(_buildSensorsFC(placements));

    const linesSrc = api.map.getSource('placement-editor:bearing-lines-source');
    if (linesSrc) linesSrc.setData(_buildBearingLinesFC(placements));

    const wedgesSrc = api.map.getSource('placement-editor:wedges-source');
    if (wedgesSrc) wedgesSrc.setData(_buildWedgesFC(placements));
  }

  // -------------------------------------------------------------------------
  // Map interactions (S14.5-3)
  // -------------------------------------------------------------------------

  function _onCircleMousedown(e) {
    const idx = e.features?.[0]?.properties?.index ?? -1;
    if (idx < 0) return;
    isDragging = true;
    dragIndex = idx;
    selectedIndex = idx;
    if (canvas) canvas.style.cursor = 'grabbing';
  }

  function _onMapMousemove(e) {
    if (!isDragging || dragIndex < 0) return;
    const placements = latestPlacements ?? [];
    if (dragIndex >= placements.length) return;
    // Live preview: update sensor source without committing to state
    const preview = placements.map((p, i) =>
      i === dragIndex
        ? { ...p, lat: e.lngLat?.lat ?? p.lat, lng: e.lngLat?.lng ?? p.lng }
        : p
    );
    const src = api.map.getSource('placement-editor:sensors-source');
    if (src) src.setData(_buildSensorsFC(preview));
  }

  function _onMapMouseup(e) {
    if (!isDragging || dragIndex < 0) return;
    const placements = latestPlacements ?? [];
    if (dragIndex < placements.length) {
      const original = placements[dragIndex];
      const newLat = e.lngLat?.lat ?? original?.lat;
      const newLng = e.lngLat?.lng ?? original?.lng;
      if (newLat == null || newLng == null) {
        isDragging = false;
        dragIndex = -1;
        if (canvas) canvas.style.cursor = pendingDef ? 'crosshair' : '';
        return;
      }
      const updated = placements.map((p, i) =>
        i === dragIndex ? { ...p, lat: newLat, lng: newLng } : p
      );
      api.state.set('placements', updated);
      api.bus.emit('placement:moved', { ...original, lat: newLat, lng: newLng });
    }
    isDragging = false;
    dragIndex = -1;
    if (canvas) canvas.style.cursor = pendingDef ? 'crosshair' : '';
  }

  function _onCircleClick(e) {
    if (isDragging) return;
    const idx = e.features?.[0]?.properties?.index ?? -1;
    if (idx < 0) return;
    selectedIndex = idx;
    _renderList();
    // Scroll selected row into view so it is visible in the panel list
    const row = listContainer.querySelector(`[data-testid="placement-row-${idx}"]`);
    if (row) row.scrollIntoView({ block: 'nearest' });
  }

  function _onCircleWheel(e) {
    const idx = e.features?.[0]?.properties?.index ?? -1;
    if (idx < 0 || idx !== selectedIndex) return;
    const placements = latestPlacements ?? [];
    if (idx >= placements.length) return;
    const delta = (e.originalEvent?.deltaY ?? 0) < 0 ? 5 : -5;
    const current = placements[idx].bearing_deg ?? 0;
    const newBearing = ((current + delta) % 360 + 360) % 360;
    const updated = placements.map((p, i) =>
      i === idx ? { ...p, bearing_deg: newBearing } : p
    );
    api.state.set('placements', updated);
  }

  function _onCircleContextmenu(e) {
    const idx = e.features?.[0]?.properties?.index ?? -1;
    if (idx < 0) return;
    const placements = latestPlacements ?? [];
    const removed = placements[idx];
    const updated = placements.filter((_, i) => i !== idx);
    api.state.set('placements', updated);
    if (removed) api.bus.emit('placement:removed', removed);
    if (selectedIndex === idx) selectedIndex = -1;
    else if (selectedIndex > idx) selectedIndex--;
  }

  function _onCircleMouseenter() {
    if (!isDragging && canvas) canvas.style.cursor = 'grab';
  }

  function _onCircleMouseleave() {
    if (!isDragging && canvas) canvas.style.cursor = pendingDef ? 'crosshair' : 'pointer';
  }

  api.map.on('mousedown',    'placement-editor:sensors-circle', _onCircleMousedown);
  api.map.on('mousemove',    _onMapMousemove);
  api.map.on('mouseup',      _onMapMouseup);
  api.map.on('click',        'placement-editor:sensors-circle', _onCircleClick);
  api.map.on('wheel',        'placement-editor:sensors-circle', _onCircleWheel);
  api.map.on('contextmenu',  'placement-editor:sensors-circle', _onCircleContextmenu);
  api.map.on('mouseenter',   'placement-editor:sensors-circle', _onCircleMouseenter);
  api.map.on('mouseleave',   'placement-editor:sensors-circle', _onCircleMouseleave);

  // -------------------------------------------------------------------------
  // Confirm-placement helpers (placement:pending mode)
  // -------------------------------------------------------------------------

  function _enterPendingMode(evt) {
    pendingDef = evt;
    if (canvas) canvas.style.cursor = 'crosshair';
    confirmNameEl.textContent = evt.definition?.name ?? 'New placement';
    bearingDialInput.value = String(evt.definition?.default_bearing ?? 0);
    confirmSection.style.display = 'block';
    const ghostSrc = api.map.getSource('placement-editor:pending-ghost-source');
    if (ghostSrc) ghostSrc.setData(_ghostFC([evt]));
  }

  function _exitPendingMode() {
    pendingDef = null;
    if (canvas) canvas.style.cursor = '';
    confirmSection.style.display = 'none';
    const ghostSrc = api.map.getSource('placement-editor:pending-ghost-source');
    if (ghostSrc) ghostSrc.setData(_EMPTY_FC);
  }

  placeBtn.addEventListener('click', () => {
    if (!pendingDef) return;
    if (!Number.isFinite(pendingDef.lat) || !Number.isFinite(pendingDef.lng)) return;
    const bearing = ((Number(bearingDialInput.value) % 360) + 360) % 360;
    const newPlacement = {
      sensor_name:          pendingDef.definition?.name ?? 'Sensor',
      sensor_type:          pendingDef.definition?.type ?? '',
      lat:                  pendingDef.lat,
      lng:                  pendingDef.lng,
      bearing_deg:          bearing,
      azimuth_coverage_deg: pendingDef.definition?.azimuth_coverage_deg ?? 360,
      height_m:             pendingDef.definition?.height_m ?? null,
    };
    const updated = [...(latestPlacements ?? []), newPlacement];
    api.state.set('placements', updated);
    api.bus.emit('placement:added', newPlacement);
    _exitPendingMode();
  });

  cancelPendingBtn.addEventListener('click', () => {
    _exitPendingMode();
  });

  // -------------------------------------------------------------------------
  // Optimiser modal helpers (optimiser:complete)
  // -------------------------------------------------------------------------

  function _showOptimiserModal(proposed) {
    optimiserProposed = proposed ?? [];
    const n = optimiserProposed.length;
    modalCount.textContent = `${n} proposed placement${n !== 1 ? 's' : ''}`;
    optimiserModal.style.display = 'block';
    const ghostSrc = api.map.getSource('placement-editor:optimiser-ghost-source');
    if (ghostSrc) ghostSrc.setData(_ghostFC(optimiserProposed));
  }

  function _hideOptimiserModal() {
    optimiserProposed = null;
    optimiserModal.style.display = 'none';
    const ghostSrc = api.map.getSource('placement-editor:optimiser-ghost-source');
    if (ghostSrc) ghostSrc.setData(_EMPTY_FC);
  }

  modalApplyBtn.addEventListener('click', () => {
    if (!optimiserProposed) return;
    const valid = optimiserProposed.filter(p => p != null && typeof p === 'object');
    const current = latestPlacements ?? [];
    const merged = [...current, ...valid];
    api.state.set('placements', merged);
    for (const p of valid) {
      api.bus.emit('placement:added', p);
    }
    _hideOptimiserModal();
  });

  modalDiscardBtn.addEventListener('click', () => {
    _hideOptimiserModal();
  });

  // -------------------------------------------------------------------------
  // Export YAML (S14.5-5)
  // -------------------------------------------------------------------------
  exportBtn.addEventListener('click', () => {
    let data;
    try {
      data = JSON.stringify(latestPlacements ?? [], null, 2);
    } catch (err) {
      console.error('[placement-editor] export serialisation failed:', err);
      return;
    }
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'placements.json';
    panel.appendChild(a);
    a.click();
    panel.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // -------------------------------------------------------------------------
  // Import YAML (S14.5-5)
  // -------------------------------------------------------------------------
  importBtn.addEventListener('click', () => {
    importFileInput.value = '';
    importFileInput.click();
  });

  importFileInput.addEventListener('change', () => {
    const file = importFileInput.files?.[0];
    if (!file) return;
    importErrorEl.style.display = 'none';
    const reader = new FileReader();
    reader.onerror = () => {
      importErrorEl.textContent = 'Could not read file.';
      importErrorEl.style.display = 'block';
    };
    reader.onload = (e) => {
      let parsed;
      try {
        parsed = JSON.parse(e.target.result);
      } catch (_) {
        importErrorEl.textContent = 'Invalid JSON file.';
        importErrorEl.style.display = 'block';
        return;
      }
      if (!Array.isArray(parsed)) {
        importErrorEl.textContent = 'File must contain a JSON array of placements.';
        importErrorEl.style.display = 'block';
        return;
      }
      for (const entry of parsed) {
        if (
          !entry ||
          typeof entry !== 'object' ||
          entry.sensor_name == null ||
          entry.lat == null ||
          entry.lng == null ||
          entry.bearing_deg == null
        ) {
          importErrorEl.textContent =
            'Each entry must have sensor_name, lat, lng, and bearing_deg.';
          importErrorEl.style.display = 'block';
          return;
        }
      }
      api.state.set('placements', parsed);
      importErrorEl.style.display = 'none';
    };
    reader.readAsText(file);
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestPlacements = api.state.get('placements') ?? []; // OK: initial render only
  api.panel.mount(panel);
  _renderList();
  _rebuildSources();

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('placements', (p) => {
    latestPlacements = p ?? [];
    _renderList();
    _rebuildSources();
  }));

  // -------------------------------------------------------------------------
  // Bus subscriptions (S14.5-4)
  // -------------------------------------------------------------------------
  unsubs.push(api.bus.on('placement:pending', (evt) => {
    if (evt && evt.lat != null && evt.lng != null) {
      if (evt.definition == null) {
        console.warn('[placement-editor] placement:pending received with null definition — sensor properties will use defaults');
      }
      _enterPendingMode(evt);
    }
  }));

  unsubs.push(api.bus.on('optimiser:complete', (evt) => {
    const proposed = evt?.proposed_placements ?? [];
    _showOptimiserModal(proposed);
  }));

  // D-435: optimiser delegates `placements` writes to placement-editor (single
  // writer rule). The optimiser emits `optimiser:apply` on its own Apply
  // button; we perform the merge + emit per-placement events here.
  unsubs.push(api.bus.on('optimiser:apply', (evt) => {
    const proposed = Array.isArray(evt?.proposed) ? evt.proposed : [];
    const valid = proposed.filter(p => p != null && typeof p === 'object');
    if (valid.length === 0) {
      // D-468: log the malformed/empty payload so the no-op is observable in
      // dev tools rather than silently swallowing the user's Apply action.
      console.warn(
        '[placement-editor] optimiser:apply produced no valid placements; nothing applied',
        evt,
      );
      return;
    }
    const current = latestPlacements ?? [];
    const merged = [...current, ...valid];
    api.state.set('placements', merged);
    for (const p of valid) {
      api.bus.emit('placement:added', p);
    }
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    _exitPendingMode();
    _hideOptimiserModal();

    unsubs.forEach(u => { if (typeof u === 'function') u(); });

    api.map.off('mousedown',   'placement-editor:sensors-circle', _onCircleMousedown);
    api.map.off('mousemove',   _onMapMousemove);
    api.map.off('mouseup',     _onMapMouseup);
    api.map.off('click',       'placement-editor:sensors-circle', _onCircleClick);
    api.map.off('wheel',       'placement-editor:sensors-circle', _onCircleWheel);
    api.map.off('contextmenu', 'placement-editor:sensors-circle', _onCircleContextmenu);
    api.map.off('mouseenter',  'placement-editor:sensors-circle', _onCircleMouseenter);
    api.map.off('mouseleave',  'placement-editor:sensors-circle', _onCircleMouseleave);

    const layers = [
      'placement-editor:wedges-fill',
      'placement-editor:bearing-lines',
      'placement-editor:pending-ghost',
      'placement-editor:optimiser-ghost',
      'placement-editor:sensors-circle',
      'placement-editor:sensors-label',
      'placement-editor:sensors-type-badge',
    ];
    const sources = [
      'placement-editor:sensors-source',
      'placement-editor:bearing-lines-source',
      'placement-editor:wedges-source',
      'placement-editor:pending-ghost-source',
      'placement-editor:optimiser-ghost-source',
    ];
    for (const id of layers)  { if (api.map.getLayer(id))  api.map.removeLayer(id); }
    for (const id of sources) { if (api.map.getSource(id)) api.map.removeSource(id); }
  });
}
