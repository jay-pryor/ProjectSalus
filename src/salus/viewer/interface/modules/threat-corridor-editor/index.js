/**
 * threat-corridor-editor/index.js — Threat Corridor Editor module (S14.7-1, S14.7-2).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Reads:        terrain (prerequisite only — checked by shell)
 * Writes:       threat_corridors
 * Emits:        corridor:added, corridor:removed,
 *               drawmode:entered, drawmode:exited (I-22 — emitted around the
 *               click-capturing draw, waypoint-edit and protected-point-pick
 *               modes so the coord-tools measurement tool stays mutually
 *               exclusive with them)
 * Map sources:  threat-corridor-editor:routes-source
 *               threat-corridor-editor:routes-arrow-source
 *               threat-corridor-editor:working-source
 *               threat-corridor-editor:protected-point-source
 *               threat-corridor-editor:edit-handles-source
 * Map layers:   threat-corridor-editor:routes-line
 *               threat-corridor-editor:routes-arrow
 *               threat-corridor-editor:working-line
 *               threat-corridor-editor:working-points
 *               threat-corridor-editor:protected-point
 *               threat-corridor-editor:edit-handles
 *
 * Drawing interaction (S14.7-5): uses api.map.on('click'/'dblclick') directly.
 * See docs/Technical/InterfaceArchitecture.md and map-proxy.js for the
 * architectural rationale behind this choice over addControl/removeControl.
 *
 * Isolation invariants observed:
 *   - No cross-module imports (MUST Rule 1).
 *   - All external access through injected api (MUST Rule 2).
 *   - Exactly { init(api) } exported (MUST Rule 3).
 *   - Only 'threat_corridors' written; only declared events emitted (MUST Rules 4, 10).
 *   - Every watch() and map listener paired with cleanup in onUnmount (MUST 9, 15).
 */

// ---------------------------------------------------------------------------
// Panel HTML template (mirrors panel.html — both files must stay in sync)
// ---------------------------------------------------------------------------

const PANEL_HTML = `
<div id="tce-panel" class="module-panel">
  <h2 class="panel-title">Threat Corridors</h2>
  <div id="tce-toolbar" class="toolbar">
    <button id="tce-draw-btn" class="action-btn">Draw Route</button>
    <button id="tce-point-btn" class="action-btn">Pick Protected Point</button>
  </div>
  <div id="tce-protected-info" hidden>
    <span class="field-label">Protected Point:</span>
    <span id="tce-point-coords" class="field-value">—</span>
    <button id="tce-clear-point-btn" class="clear-btn" aria-label="Clear protected point">&#x2715;</button>
  </div>
  <p id="tce-draw-hint" class="hint-msg" hidden>Click to add waypoints. Double-click to finish (min 2 waypoints).</p>
  <p id="tce-point-hint" class="hint-msg" hidden>Click on the map to place the protected point.</p>
  <div id="tce-form" hidden>
    <h3 class="form-subtitle">Confirm Route</h3>
    <div class="form-group">
      <label for="tce-name-input" class="form-label">Route name</label>
      <input type="text" id="tce-name-input" class="text-input" placeholder="Route 1">
    </div>
    <div class="form-group">
      <label for="tce-profile-select" class="form-label">Threat profile</label>
      <select id="tce-profile-select" class="select-input">
        <option value="Low">Low</option>
        <option value="Medium">Medium</option>
        <option value="High">High</option>
        <option value="Critical">Critical</option>
      </select>
    </div>
    <div class="form-group">
      <label for="tce-altitude-input" class="form-label">Altitude (m)</label>
      <input type="number" id="tce-altitude-input" class="num-input" min="0" placeholder="50">
    </div>
    <div class="form-group">
      <label for="tce-speed-input" class="form-label">Speed (m/s)</label>
      <input type="number" id="tce-speed-input" class="num-input" min="0" placeholder="30">
    </div>
    <div class="form-actions">
      <button id="tce-confirm-btn" class="confirm-btn">Confirm</button>
      <button id="tce-cancel-btn" class="cancel-btn">Cancel</button>
    </div>
  </div>
  <div id="tce-edit-bar" hidden>
    <span id="tce-edit-label" class="edit-label">Editing route</span>
    <button id="tce-done-edit-btn" class="done-btn">Done</button>
  </div>
  <div id="tce-route-list" class="item-list"></div>
</div>
`;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROFILE_COLOURS = {
  Low:      '#22c55e',
  Medium:   '#f97316',
  High:     '#ef4444',
  Critical: '#7c3aed',
};

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function _esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _genId() {
  return Math.random().toString(36).slice(2, 10);
}

function _profileColour(profile) {
  return PROFILE_COLOURS[profile] ?? '#6b7280';
}

/** Build GeoJSON LineString FC for confirmed routes. */
function _routesGeoJSON(routes) {
  return {
    type: 'FeatureCollection',
    features: routes.map(r => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: r.waypoints },
      properties: { id: r.id, color: _profileColour(r.threat_profile) },
    })),
  };
}

/** Build GeoJSON Point FC at segment midpoints for directional arrows. */
function _arrowsGeoJSON(routes) {
  const features = [];
  for (const r of routes) {
    for (let i = 0; i < r.waypoints.length - 1; i++) {
      const [x1, y1] = r.waypoints[i];
      const [x2, y2] = r.waypoints[i + 1];
      const bearing = (Math.atan2(x2 - x1, y2 - y1) * 180 / Math.PI + 360) % 360;
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [(x1 + x2) / 2, (y1 + y2) / 2] },
        properties: { bearing, color: _profileColour(r.threat_profile) },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

/** Build GeoJSON for in-progress drawing waypoints (Points + optional LineString). */
function _workingGeoJSON(waypoints) {
  if (waypoints.length === 0) return _EMPTY_FC;
  const features = waypoints.map(([lng, lat]) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    properties: {},
  }));
  if (waypoints.length >= 2) {
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: waypoints },
      properties: { is_working_line: true },
    });
  }
  return { type: 'FeatureCollection', features };
}

/** Build GeoJSON Point for the protected site point. */
function _protectedGeoJSON(pt) {
  if (!pt) return _EMPTY_FC;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [pt.lng, pt.lat] },
      properties: {},
    }],
  };
}

/** Build GeoJSON Point FC for edit-mode waypoint handles. */
function _editHandlesGeoJSON(waypoints) {
  return {
    type: 'FeatureCollection',
    features: waypoints.map(([lng, lat], idx) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: { index: idx },
    })),
  };
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // In-memory mirrors — write to state after every mutation
  let corridors = [];
  let protectedPoint = null;

  // Draw mode state
  let drawMode = false;
  let workingWaypoints = [];

  // Edit mode state
  let editingId = null;
  let editingWaypoints = [];
  let editCleanup = null;

  // Protected-point picking state
  let pickingPoint = false;
  let pickPointCleanup = null;

  // -------------------------------------------------------------------------
  // Map sources and layers — all created at mount, destroyed at unmount
  // -------------------------------------------------------------------------

  api.map.addSource('threat-corridor-editor:routes-source', {
    type: 'geojson', data: _EMPTY_FC,
  });
  api.map.addSource('threat-corridor-editor:routes-arrow-source', {
    type: 'geojson', data: _EMPTY_FC,
  });
  api.map.addSource('threat-corridor-editor:working-source', {
    type: 'geojson', data: _EMPTY_FC,
  });
  api.map.addSource('threat-corridor-editor:protected-point-source', {
    type: 'geojson', data: _EMPTY_FC,
  });
  api.map.addSource('threat-corridor-editor:edit-handles-source', {
    type: 'geojson', data: _EMPTY_FC,
  });

  // Confirmed routes — dashed line coloured by threat profile
  api.map.addLayer({
    id: 'threat-corridor-editor:routes-line',
    type: 'line',
    source: 'threat-corridor-editor:routes-source',
    paint: {
      'line-color': ['get', 'color'],
      'line-width': 2.5,
      'line-dasharray': [4, 2],
    },
  });

  // Directional arrows at segment midpoints
  // Uses 'triangle-15' icon; the icon renders when the map style includes it.
  api.map.addLayer({
    id: 'threat-corridor-editor:routes-arrow',
    type: 'symbol',
    source: 'threat-corridor-editor:routes-arrow-source',
    layout: {
      'icon-image': 'triangle-15',
      'icon-rotate': ['get', 'bearing'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
    },
    paint: {
      'icon-color': ['get', 'color'],
    },
  });

  // In-progress route line (connecting drawn waypoints during draw mode)
  api.map.addLayer({
    id: 'threat-corridor-editor:working-line',
    type: 'line',
    source: 'threat-corridor-editor:working-source',
    filter: ['==', '$type', 'LineString'],
    paint: {
      'line-color': '#ffffff',
      'line-width': 1.5,
      'line-dasharray': [2, 1],
      'line-opacity': 0.7,
    },
  });

  // In-progress waypoint circles
  api.map.addLayer({
    id: 'threat-corridor-editor:working-points',
    type: 'circle',
    source: 'threat-corridor-editor:working-source',
    filter: ['==', '$type', 'Point'],
    paint: {
      'circle-radius': 5,
      'circle-color': '#22c55e',
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
    },
  });

  // Protected-point pulsing circle
  api.map.addLayer({
    id: 'threat-corridor-editor:protected-point',
    type: 'circle',
    source: 'threat-corridor-editor:protected-point-source',
    paint: {
      'circle-radius': 10,
      'circle-color': '#facc15',
      'circle-opacity': 0.85,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  });

  // Edit-mode waypoint drag handles
  api.map.addLayer({
    id: 'threat-corridor-editor:edit-handles',
    type: 'circle',
    source: 'threat-corridor-editor:edit-handles-source',
    paint: {
      'circle-radius': 7,
      'circle-color': '#3b82f6',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  });

  // -------------------------------------------------------------------------
  // Source update helpers
  // -------------------------------------------------------------------------

  function _updateRoutesSources() {
    const rSrc = api.map.getSource('threat-corridor-editor:routes-source');
    if (rSrc) rSrc.setData(_routesGeoJSON(corridors));
    const aSrc = api.map.getSource('threat-corridor-editor:routes-arrow-source');
    if (aSrc) aSrc.setData(_arrowsGeoJSON(corridors));
  }

  function _updateWorkingSource() {
    const src = api.map.getSource('threat-corridor-editor:working-source');
    if (src) src.setData(_workingGeoJSON(workingWaypoints));
  }

  function _updateProtectedPointSource() {
    const src = api.map.getSource('threat-corridor-editor:protected-point-source');
    if (src) src.setData(_protectedGeoJSON(protectedPoint));
  }

  function _updateEditHandlesSource() {
    const src = api.map.getSource('threat-corridor-editor:edit-handles-source');
    if (src) src.setData(_editHandlesGeoJSON(editingWaypoints));
  }

  // -------------------------------------------------------------------------
  // State write — canonical flat array shape ThreatCorridor[]
  // (docs/Technical/InterfaceArchitecture.md §3).  The scenario-wide
  // protected_point is denormalised onto each corridor so the canonical
  // schema can remain a flat array while still carrying the asset location.
  // -------------------------------------------------------------------------

  /** Defensive deep-clone of a waypoints list — drops non-array entries. */
  function _cloneWaypoints(raw) {
    if (!Array.isArray(raw)) return [];
    const out = [];
    for (const wp of raw) {
      if (Array.isArray(wp)) out.push([...wp]);
      // Non-array entries (e.g. null from a half-saved scenario) are skipped
      // rather than crashing the watch callback (D-421).
    }
    return out;
  }

  function _writeState() {
    const payload = corridors.map(r => ({
      id: r.id,
      name: r.name,
      threat_profile: r.threat_profile,
      altitude_m: r.altitude_m,
      speed_ms: r.speed_ms,
      waypoints: _cloneWaypoints(r.waypoints),
      protected_point: protectedPoint,
    }));
    api.state.set('threat_corridors', payload);
  }

  // Rebuild the in-memory corridors/protectedPoint from the canonical shape.
  // Defensively accepts either the flat array or the legacy {routes, protected_point}
  // object form — the latter only appears from callers that predate this change.
  // Empty array deliberately preserves the in-memory protectedPoint (the canonical
  // schema has no place to store it without a corridor) — see D-420 follow-up.
  function _readCanonical(val) {
    if (Array.isArray(val)) {
      const list = val.map(r => ({
        ...r,
        waypoints: _cloneWaypoints(r?.waypoints),
      }));
      const derivedPoint = list.length > 0 ? (list[0].protected_point ?? null) : protectedPoint;
      return { list, protectedPoint: derivedPoint };
    }
    if (val && typeof val === 'object') {
      const list = (Array.isArray(val.routes) ? val.routes : []).map(r => ({
        ...r,
        waypoints: _cloneWaypoints(r?.waypoints),
      }));
      return { list, protectedPoint: val.protected_point ?? null };
    }
    return { list: [], protectedPoint };
  }

  // -------------------------------------------------------------------------
  // Panel build
  // -------------------------------------------------------------------------

  const container = document.createElement('div');
  container.innerHTML = PANEL_HTML;

  const drawBtn          = container.querySelector('#tce-draw-btn');
  const pointBtn         = container.querySelector('#tce-point-btn');
  const protectedInfo    = container.querySelector('#tce-protected-info');
  const pointCoordsEl    = container.querySelector('#tce-point-coords');
  const clearPointBtn    = container.querySelector('#tce-clear-point-btn');
  const drawHint         = container.querySelector('#tce-draw-hint');
  const pointHint        = container.querySelector('#tce-point-hint');
  const formEl           = container.querySelector('#tce-form');
  const nameInput        = container.querySelector('#tce-name-input');
  const profileSelect    = container.querySelector('#tce-profile-select');
  const altitudeInput    = container.querySelector('#tce-altitude-input');
  const speedInput       = container.querySelector('#tce-speed-input');
  const confirmBtn       = container.querySelector('#tce-confirm-btn');
  const cancelBtn        = container.querySelector('#tce-cancel-btn');
  const editBar          = container.querySelector('#tce-edit-bar');
  const editLabelEl      = container.querySelector('#tce-edit-label');
  const doneEditBtn      = container.querySelector('#tce-done-edit-btn');
  const routeListEl      = container.querySelector('#tce-route-list');

  // -------------------------------------------------------------------------
  // Route list rendering
  // -------------------------------------------------------------------------

  function _clearEl(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function _rebuildRouteList() {
    _clearEl(routeListEl);
    for (const route of corridors) {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid #252540';

      const colourDot = document.createElement('span');
      colourDot.style.cssText =
        `width:10px;height:10px;border-radius:50%;flex-shrink:0;` +
        `background:${_profileColour(route.threat_profile)}`;

      const nameSp = document.createElement('span');
      nameSp.textContent = route.name;
      nameSp.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px';

      const editBtn = document.createElement('button');
      editBtn.textContent = '✏';
      editBtn.title = 'Edit waypoints';
      editBtn.style.cssText = 'padding:2px 5px;background:none;border:1px solid #3b82f6;border-radius:3px;color:#3b82f6;cursor:pointer;font-size:12px';
      editBtn.addEventListener('click', () => _enterEditMode(route.id));

      const trashBtn = document.createElement('button');
      trashBtn.textContent = '🗑';
      trashBtn.title = 'Remove route';
      trashBtn.style.cssText = 'padding:2px 5px;background:none;border:1px solid #ef4444;border-radius:3px;color:#ef4444;cursor:pointer;font-size:12px';
      trashBtn.addEventListener('click', () => _removeRoute(route.id));

      row.append(colourDot, nameSp, editBtn, trashBtn);
      routeListEl.appendChild(row);
    }
  }

  // -------------------------------------------------------------------------
  // Draw mode
  // -------------------------------------------------------------------------

  function _onDrawClick(e) {
    const lngLat = api.map.unproject(e.point);
    if (!lngLat) return;
    workingWaypoints.push([lngLat.lng, lngLat.lat]);
    _updateWorkingSource();
  }

  function _onDrawDblClick(e) {
    // The browser fires a click event immediately before dblclick; pop the
    // duplicate tail waypoint that the preceding click already appended (D-342).
    if (workingWaypoints.length > 0) workingWaypoints.pop();
    if (workingWaypoints.length < 2) return;
    _stopDrawMode();
    _showForm();
  }

  function _startDrawMode() {
    drawMode = true;
    if (drawBtn) drawBtn.textContent = 'Stop Drawing';
    if (drawHint) drawHint.hidden = false;
    // D-613: emit drawmode:entered BEFORE setting the cursor, so the coord-tools
    // measure-mode exit (which restores its saved cursor) cannot overwrite the
    // crosshair this draw mode is about to set.
    api.bus.emit('drawmode:entered', { mode: 'draw' });
    api.map.getCanvas().style.cursor = 'crosshair';
    api.map.on('click', _onDrawClick);
    api.map.on('dblclick', _onDrawDblClick);
  }

  function _stopDrawMode() {
    drawMode = false;
    if (drawBtn) drawBtn.textContent = 'Draw Route';
    if (drawHint) drawHint.hidden = true;
    api.map.getCanvas().style.cursor = '';
    api.map.off('click', _onDrawClick);
    api.map.off('dblclick', _onDrawDblClick);
    api.bus.emit('drawmode:exited', { mode: 'draw' });
  }

  // -------------------------------------------------------------------------
  // Route confirmation form
  // -------------------------------------------------------------------------

  function _showForm() {
    formEl.hidden = false;
    if (nameInput) nameInput.value = '';
    if (profileSelect) profileSelect.value = 'Low';
    if (altitudeInput) altitudeInput.value = '';
    if (speedInput) speedInput.value = '';
  }

  function _hideForm() {
    formEl.hidden = true;
  }

  function _onConfirmRoute() {
    if (workingWaypoints.length < 2) {
      _hideForm();
      workingWaypoints = [];
      _updateWorkingSource();
      return;
    }
    const name = (nameInput ? String(nameInput.value).trim() : '') || `Route ${corridors.length + 1}`;
    const profile = (profileSelect ? String(profileSelect.value) : '') || 'Low';
    const altStr = altitudeInput ? altitudeInput.value : '';
    const spdStr = speedInput ? speedInput.value : '';
    const altitudeM = altStr !== '' ? parseFloat(altStr) : null;
    const speedMs  = spdStr !== '' ? parseFloat(spdStr) : null;

    const route = {
      id: _genId(),
      name,
      threat_profile: profile,
      altitude_m: Number.isFinite(altitudeM) ? altitudeM : null,
      speed_ms:   Number.isFinite(speedMs)   ? speedMs   : null,
      waypoints: workingWaypoints.map(wp => [...wp]),
    };

    corridors.push(route);
    workingWaypoints = [];

    _updateWorkingSource();
    _updateRoutesSources();
    _rebuildRouteList();
    _writeState();
    _hideForm();

    api.bus.emit('corridor:added', { id: route.id, name: route.name });
  }

  function _onCancelRoute() {
    workingWaypoints = [];
    _updateWorkingSource();
    _hideForm();
  }

  if (confirmBtn) confirmBtn.addEventListener('click', _onConfirmRoute);
  if (cancelBtn)  cancelBtn.addEventListener('click', _onCancelRoute);

  // -------------------------------------------------------------------------
  // Route removal
  // -------------------------------------------------------------------------

  function _removeRoute(routeId) {
    const idx = corridors.findIndex(r => r.id === routeId);
    if (idx === -1) return;
    const removed = corridors[idx];
    corridors.splice(idx, 1);

    // Exit edit mode if we were editing this route
    if (editingId === routeId) _exitEditMode(false);

    _updateRoutesSources();
    _rebuildRouteList();
    _writeState();

    api.bus.emit('corridor:removed', { id: removed.id, name: removed.name });
  }

  // -------------------------------------------------------------------------
  // Edit mode (S14.7-2)
  // -------------------------------------------------------------------------

  function _enterEditMode(routeId) {
    if (editingId) _exitEditMode(false);
    if (drawMode) _stopDrawMode();

    const route = corridors.find(r => r.id === routeId);
    if (!route) return;

    editingId = routeId;
    editingWaypoints = route.waypoints.map(wp => [...wp]);
    // Waypoint editing captures map clicks/drags — same coord-tools signal.
    api.bus.emit('drawmode:entered', { mode: 'edit' });

    _updateEditHandlesSource();
    if (editBar) editBar.hidden = false;
    if (editLabelEl) editLabelEl.textContent = `Editing: ${_esc(route.name)}`;

    let dragging = false;
    let dragIdx = -1;

    function _onHandleMouseDown(e) {
      const features = api.map.queryRenderedFeatures(e.point, {
        layers: ['threat-corridor-editor:edit-handles'],
      });
      if (!features || !features.length) return;
      // Validate index before trusting queryRenderedFeatures properties (D-338)
      const rawIdx = features[0].properties.index;
      if (!Number.isInteger(rawIdx) || rawIdx < 0 || rawIdx >= editingWaypoints.length) return;
      dragging = true;
      dragIdx = rawIdx;
      api.map.getCanvas().style.cursor = 'grabbing';
      e.preventDefault && e.preventDefault();
    }

    function _onMouseMove(e) {
      if (!dragging || dragIdx < 0) return;
      const pt = e.point ?? { x: e.offsetX, y: e.offsetY };
      const lngLat = api.map.unproject(pt);
      if (!lngLat) return;
      editingWaypoints[dragIdx] = [lngLat.lng, lngLat.lat];
      _updateEditHandlesSource();
      // Rebuild route source preview with edited waypoints
      const preview = corridors.map(r =>
        r.id === editingId ? { ...r, waypoints: editingWaypoints } : r
      );
      const rSrc = api.map.getSource('threat-corridor-editor:routes-source');
      if (rSrc) rSrc.setData(_routesGeoJSON(preview));
    }

    function _onMouseUp() {
      dragging = false;
      dragIdx = -1;
      api.map.getCanvas().style.cursor = '';
    }

    // Right-click on a handle removes that waypoint (min 2 must remain)
    function _onHandleContextMenu(e) {
      const features = api.map.queryRenderedFeatures(e.point, {
        layers: ['threat-corridor-editor:edit-handles'],
      });
      if (!features || !features.length) return;
      // Validate index before trusting queryRenderedFeatures properties (D-339)
      const rawIdx = features[0].properties.index;
      if (!Number.isInteger(rawIdx) || rawIdx < 0 || rawIdx >= editingWaypoints.length) return;
      if (editingWaypoints.length <= 2) return; // enforce minimum 2 waypoints
      editingWaypoints.splice(rawIdx, 1);
      _updateEditHandlesSource();
      const preview = corridors.map(r =>
        r.id === editingId ? { ...r, waypoints: editingWaypoints } : r
      );
      const rSrc = api.map.getSource('threat-corridor-editor:routes-source');
      if (rSrc) rSrc.setData(_routesGeoJSON(preview));
    }

    // Click on the route line while in edit mode inserts a new waypoint at the
    // nearest segment position
    function _onLineClick(e) {
      if (!editingId) return;
      const lngLat = api.map.unproject(e.point);
      if (!lngLat) return;
      // Find the nearest segment and insert after its start index
      let bestIdx = 0;
      let bestDist = Infinity;
      for (let i = 0; i < editingWaypoints.length - 1; i++) {
        const [x1, y1] = editingWaypoints[i];
        const mx = (x1 + editingWaypoints[i + 1][0]) / 2;
        const my = (y1 + editingWaypoints[i + 1][1]) / 2;
        const d = (lngLat.lng - mx) ** 2 + (lngLat.lat - my) ** 2;
        if (d < bestDist) { bestDist = d; bestIdx = i; }
      }
      editingWaypoints.splice(bestIdx + 1, 0, [lngLat.lng, lngLat.lat]);
      _updateEditHandlesSource();
    }

    api.map.on('mousedown', 'threat-corridor-editor:edit-handles', _onHandleMouseDown);
    api.map.on('contextmenu', 'threat-corridor-editor:edit-handles', _onHandleContextMenu);
    api.map.on('click', 'threat-corridor-editor:routes-line', _onLineClick);
    api.map.getCanvas().addEventListener('mousemove', _onMouseMove);
    api.map.getCanvas().addEventListener('mouseup', _onMouseUp);

    editCleanup = () => {
      api.map.off('mousedown', 'threat-corridor-editor:edit-handles', _onHandleMouseDown);
      api.map.off('contextmenu', 'threat-corridor-editor:edit-handles', _onHandleContextMenu);
      api.map.off('click', 'threat-corridor-editor:routes-line', _onLineClick);
      api.map.getCanvas().removeEventListener('mousemove', _onMouseMove);
      api.map.getCanvas().removeEventListener('mouseup', _onMouseUp);
      api.map.getCanvas().style.cursor = '';
      const emptySrc = api.map.getSource('threat-corridor-editor:edit-handles-source');
      if (emptySrc) emptySrc.setData(_EMPTY_FC);
      if (editBar) editBar.hidden = true;
      editingId = null;
      editingWaypoints = [];
      editCleanup = null;
    };
  }

  function _exitEditMode(commit) {
    if (!editingId) return;
    api.bus.emit('drawmode:exited', { mode: 'edit' });
    if (commit) {
      // Write the edited waypoints into the corridors array
      const idx = corridors.findIndex(r => r.id === editingId);
      if (idx !== -1) {
        corridors[idx] = { ...corridors[idx], waypoints: editingWaypoints.map(wp => [...wp]) };
      }
      _updateRoutesSources();
      _writeState();
    } else {
      // Revert: restore sources from current corridors state
      _updateRoutesSources();
    }
    if (editCleanup) {
      editCleanup();
    } else {
      // Defensive: cleanup was never registered — reset state to avoid zombie (D-347)
      editingId = null;
      editingWaypoints = [];
    }
  }

  if (doneEditBtn) {
    doneEditBtn.addEventListener('click', () => _exitEditMode(true));
  }

  // -------------------------------------------------------------------------
  // Protected-point picker
  // -------------------------------------------------------------------------

  function _onPickPointClick(e) {
    const lngLat = api.map.unproject(e.point);
    if (!lngLat) return;
    protectedPoint = { lat: lngLat.lat, lng: lngLat.lng };
    _stopPickPoint();
    _updateProtectedPointSource();
    _updateProtectedInfoPanel();
    _writeState();
  }

  function _stopPickPoint() {
    if (!pickingPoint) return; // defence-in-depth — never emit an unmatched exited
    pickingPoint = false;
    if (pickPointCleanup) pickPointCleanup();
    pickPointCleanup = null;
    api.map.getCanvas().style.cursor = '';
    if (pointHint) pointHint.hidden = true;
    api.bus.emit('drawmode:exited', { mode: 'pick' });
  }

  function _startPickPoint() {
    if (drawMode) _stopDrawMode();
    if (pickingPoint) { _stopPickPoint(); return; }
    pickingPoint = true;
    // D-613: emit drawmode:entered BEFORE setting the cursor (see _startDrawMode).
    api.bus.emit('drawmode:entered', { mode: 'pick' });
    api.map.getCanvas().style.cursor = 'crosshair';
    if (pointHint) pointHint.hidden = false;
    api.map.on('click', _onPickPointClick);
    pickPointCleanup = () => {
      api.map.off('click', _onPickPointClick);
    };
  }

  function _updateProtectedInfoPanel() {
    if (!protectedInfo || !pointCoordsEl) return;
    if (protectedPoint) {
      protectedInfo.hidden = false;
      pointCoordsEl.textContent =
        `${protectedPoint.lat.toFixed(5)}°, ${protectedPoint.lng.toFixed(5)}°`;
    } else {
      protectedInfo.hidden = true;
    }
  }

  if (drawBtn) {
    drawBtn.addEventListener('click', () => {
      if (drawMode) {
        _stopDrawMode();
      } else {
        if (pickingPoint) _stopPickPoint();
        _startDrawMode();
      }
    });
  }

  if (pointBtn) pointBtn.addEventListener('click', _startPickPoint);

  // -------------------------------------------------------------------------
  // Persistent idle-mode handler — click a route line to enter edit mode (S14.7-2, D-346)
  // -------------------------------------------------------------------------

  function _onRouteLineClick(e) {
    if (drawMode || editingId || pickingPoint) return;
    const features = api.map.queryRenderedFeatures(e.point, {
      layers: ['threat-corridor-editor:routes-line'],
    });
    if (!features || !features.length) return;
    const id = features[0].properties.id;
    if (id) _enterEditMode(String(id));
  }
  api.map.on('click', 'threat-corridor-editor:routes-line', _onRouteLineClick);

  if (clearPointBtn) {
    clearPointBtn.addEventListener('click', () => {
      protectedPoint = null;
      _updateProtectedPointSource();
      _updateProtectedInfoPanel();
      _writeState();
    });
  }

  // -------------------------------------------------------------------------
  // Reactive state watch — sync from external updates (e.g. scenario load)
  // -------------------------------------------------------------------------

  unsubs.push(api.state.watch('threat_corridors', (val) => {
    if (val == null) return;
    const parsed = _readCanonical(val);
    corridors = parsed.list;
    protectedPoint = parsed.protectedPoint;
    _updateRoutesSources();
    _updateProtectedPointSource();
    _updateProtectedInfoPanel();
    _rebuildRouteList();
  }));

  // -------------------------------------------------------------------------
  // Initial render from existing state (one-time get — acceptable per SHOULD rule 2)
  // -------------------------------------------------------------------------

  const initState = api.state.get('threat_corridors');
  if (initState) {
    const parsed = _readCanonical(initState);
    corridors = parsed.list;
    protectedPoint = parsed.protectedPoint;
    _updateRoutesSources();
    _updateProtectedPointSource();
    _updateProtectedInfoPanel();
    _rebuildRouteList();
  }

  api.panel.mount(container);

  // -------------------------------------------------------------------------
  // Cleanup — all sources, layers, listeners removed in one block (S14.7-2)
  // -------------------------------------------------------------------------

  api.panel.onUnmount(() => {
    // Exit active modes first
    if (drawMode) _stopDrawMode();
    if (editingId) _exitEditMode(false);
    if (pickingPoint) _stopPickPoint();

    // Remove persistent idle-mode route-line click handler
    api.map.off('click', 'threat-corridor-editor:routes-line', _onRouteLineClick);

    // Unsubscribe all state watches
    unsubs.forEach(u => u());

    // Remove layers (must be before sources)
    const layers = [
      'threat-corridor-editor:edit-handles',
      'threat-corridor-editor:protected-point',
      'threat-corridor-editor:working-points',
      'threat-corridor-editor:working-line',
      'threat-corridor-editor:routes-arrow',
      'threat-corridor-editor:routes-line',
    ];
    for (const id of layers) {
      if (api.map.getLayer(id)) api.map.removeLayer(id);
    }

    // Remove sources
    const sources = [
      'threat-corridor-editor:edit-handles-source',
      'threat-corridor-editor:protected-point-source',
      'threat-corridor-editor:working-source',
      'threat-corridor-editor:routes-arrow-source',
      'threat-corridor-editor:routes-source',
    ];
    for (const id of sources) {
      if (api.map.getSource(id)) api.map.removeSource(id);
    }
  });
}
