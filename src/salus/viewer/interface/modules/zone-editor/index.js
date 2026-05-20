/**
 * zone-editor/index.js — Zone and Priority Editor module (S14.7-3, S14.7-4).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Reads:        terrain (prerequisite only — checked by shell)
 * Writes:       zones
 * Emits:        zone:added, zone:removed,
 *               drawmode:entered, drawmode:exited (I-22 — emitted around the
 *               click-capturing draw and vertex-edit modes so the coord-tools
 *               measurement tool stays mutually exclusive with them)
 * Map sources:  zone-editor:priority-source
 *               zone-editor:exclusion-source
 *               zone-editor:working-source
 *               zone-editor:edit-handles-source
 *               zone-editor:edit-midpoints-source
 * Map layers:   zone-editor:priority-fill
 *               zone-editor:priority-label
 *               zone-editor:exclusion-fill
 *               zone-editor:exclusion-outline
 *               zone-editor:working-fill
 *               zone-editor:working-outline
 *               zone-editor:working-vertices
 *               zone-editor:edit-handles
 *               zone-editor:edit-midpoints
 *
 * Drawing interaction (S14.7-5): uses api.map.on('click'/'dblclick') directly.
 * See map-proxy.js for the rationale behind this choice.
 *
 * Hatched fill note: MapLibreGL exclusion zones would ideally use a
 * canvas-generated hatch image registered via map.addImage() and referenced
 * by fill-pattern. Since addImage is not exposed on the map proxy, the
 * exclusion fill uses a semi-transparent red fill with a dashed outline as a
 * visually equivalent approximation.
 *
 * Isolation invariants observed:
 *   - No cross-module imports (MUST Rule 1).
 *   - All external access through injected api (MUST Rule 2).
 *   - Exactly { init(api) } exported (MUST Rule 3).
 *   - Only 'zones' written; only declared events emitted (MUST Rules 4, 10).
 *   - Every watch() and map listener paired with cleanup in onUnmount (MUST 9, 15).
 */

// ---------------------------------------------------------------------------
// Panel HTML template (mirrors panel.html — both files must stay in sync)
// ---------------------------------------------------------------------------

const PANEL_HTML = `
<div id="ze-panel" class="module-panel">
  <h2 class="panel-title">Zone Editor</h2>
  <div id="ze-toolbar" class="toolbar">
    <button id="ze-draw-btn" class="action-btn">Draw Zone</button>
    <div class="form-group" id="ze-type-group">
      <label for="ze-zone-type" class="form-label">Zone type</label>
      <select id="ze-zone-type" class="select-input">
        <option value="priority">Priority</option>
        <option value="exclusion">Exclusion</option>
      </select>
    </div>
  </div>
  <p id="ze-draw-hint" class="hint-msg" hidden>Click to place polygon vertices. Double-click to close (min 3 points).</p>
  <div id="ze-form" hidden>
    <h3 class="form-subtitle">Confirm Zone</h3>
    <div class="form-group">
      <label for="ze-zone-name" class="form-label">Zone name</label>
      <input type="text" id="ze-zone-name" class="text-input" placeholder="Zone 1">
    </div>
    <div class="form-group" id="ze-threshold-group" hidden>
      <label for="ze-threshold" class="form-label">Coverage threshold (%)</label>
      <input type="number" id="ze-threshold" class="num-input" min="0" max="100" placeholder="80">
      <p id="ze-threshold-error" class="error-msg" hidden></p>
    </div>
    <div class="form-group" id="ze-reason-group" hidden>
      <label for="ze-reason" class="form-label">Reason (optional)</label>
      <input type="text" id="ze-reason" class="text-input" placeholder="e.g. Communications mast footprint">
    </div>
    <div class="form-actions">
      <button id="ze-confirm-btn" class="confirm-btn">Confirm</button>
      <button id="ze-cancel-btn" class="cancel-btn">Cancel</button>
    </div>
  </div>
  <div id="ze-edit-bar" hidden>
    <span id="ze-edit-label" class="edit-label">Editing zone</span>
    <button id="ze-done-edit-btn" class="done-btn">Done</button>
  </div>
  <div id="ze-zone-list" class="item-list"></div>
</div>
`;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIORITY_COLOUR    = '#22c55e';  // green
const EXCLUSION_COLOUR   = '#ef4444';  // red
const WORKING_COLOUR     = '#ffffff';
const HANDLE_COLOUR      = '#3b82f6';
const MIDPOINT_COLOUR    = '#93c5fd';

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

/** Close a ring: append the first coordinate at the end if not already closed. */
function _closeRing(coords) {
  if (coords.length < 2) return [...coords];
  const first = coords[0];
  const last  = coords[coords.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return coords.map(c => [...c]);
  return [...coords.map(c => [...c]), [...first]];
}

/** Build a GeoJSON Polygon Feature from an unordered ring of coordinates. */
function _polygonFeature(zone) {
  const ring = _closeRing(zone.coordinates);
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [ring] },
    properties: {
      id: zone.id,
      name: zone.name,
      label: zone.coverage_threshold_pct != null
        ? `${zone.coverage_threshold_pct}%`
        : zone.name,
    },
  };
}

/** Build GeoJSON FeatureCollections for priority and exclusion zones. */
function _buildZoneFCs(zones) {
  const priority  = { type: 'FeatureCollection', features: [] };
  const exclusion = { type: 'FeatureCollection', features: [] };
  for (const z of (zones ?? [])) {
    const feat = _polygonFeature(z);
    if (z.type === 'exclusion') {
      exclusion.features.push(feat);
    } else {
      priority.features.push(feat);
    }
  }
  return { priority, exclusion };
}

/** Build GeoJSON for in-progress polygon vertices. */
function _workingGeoJSON(vertices) {
  if (vertices.length === 0) return _EMPTY_FC;
  const features = vertices.map(([lng, lat]) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    properties: {},
  }));
  if (vertices.length >= 2) {
    // Closing line for preview (include first vertex at end for closed look)
    const coords = [...vertices, vertices[0]];
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: coords },
      properties: { is_outline: true },
    });
  }
  if (vertices.length >= 3) {
    // Fill preview (closed polygon)
    const ring = _closeRing(vertices);
    features.push({
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [ring] },
      properties: { is_fill: true },
    });
  }
  return { type: 'FeatureCollection', features };
}

/** Build GeoJSON for edit vertex handles and edge-midpoint insert handles. */
function _editHandlesGeoJSON(coords) {
  const handles = coords.map(([lng, lat], idx) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    properties: { index: idx, kind: 'vertex' },
  }));

  const midpoints = [];
  for (let i = 0; i < coords.length; i++) {
    const next = (i + 1) % coords.length;
    const [x1, y1] = coords[i];
    const [x2, y2] = coords[next];
    midpoints.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [(x1 + x2) / 2, (y1 + y2) / 2] },
      properties: { after_index: i, kind: 'midpoint' },
    });
  }

  return {
    handles: { type: 'FeatureCollection', features: handles },
    midpoints: { type: 'FeatureCollection', features: midpoints },
  };
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // In-memory zones array — always synced with state
  let zones = [];

  // Draw mode state
  let drawMode = false;
  let drawType = 'priority';
  let workingVertices = [];

  // Edit mode state
  let editingId = null;
  let editingCoords = [];
  let editCleanup = null;

  // -------------------------------------------------------------------------
  // Map sources and layers
  // -------------------------------------------------------------------------

  api.map.addSource('zone-editor:priority-source',    { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('zone-editor:exclusion-source',   { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('zone-editor:working-source',     { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('zone-editor:edit-handles-source',   { type: 'geojson', data: _EMPTY_FC });
  api.map.addSource('zone-editor:edit-midpoints-source', { type: 'geojson', data: _EMPTY_FC });

  // Priority zones — semi-transparent green fill + solid outline
  api.map.addLayer({
    id: 'zone-editor:priority-fill',
    type: 'fill',
    source: 'zone-editor:priority-source',
    paint: {
      'fill-color': PRIORITY_COLOUR,
      'fill-opacity': 0.25,
    },
  });
  api.map.addLayer({
    id: 'zone-editor:priority-label',
    type: 'symbol',
    source: 'zone-editor:priority-source',
    layout: {
      'text-field': ['get', 'label'],
      'text-size': 12,
      'text-anchor': 'center',
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': '#000000',
      'text-halo-width': 1,
    },
  });

  // Exclusion zones — semi-transparent red fill (approximates hatch) + dashed outline
  // Production note: replace fill with fill-pattern referencing a canvas-generated
  // hatch image registered via map.addImage() for true hatching.
  api.map.addLayer({
    id: 'zone-editor:exclusion-fill',
    type: 'fill',
    source: 'zone-editor:exclusion-source',
    paint: {
      'fill-color': EXCLUSION_COLOUR,
      'fill-opacity': 0.20,
    },
  });
  api.map.addLayer({
    id: 'zone-editor:exclusion-outline',
    type: 'line',
    source: 'zone-editor:exclusion-source',
    paint: {
      'line-color': EXCLUSION_COLOUR,
      'line-width': 2,
      'line-dasharray': [4, 2],
    },
  });

  // Working polygon — preview during draw
  api.map.addLayer({
    id: 'zone-editor:working-fill',
    type: 'fill',
    source: 'zone-editor:working-source',
    filter: ['==', '$type', 'Polygon'],
    paint: {
      'fill-color': WORKING_COLOUR,
      'fill-opacity': 0.12,
    },
  });
  api.map.addLayer({
    id: 'zone-editor:working-outline',
    type: 'line',
    source: 'zone-editor:working-source',
    filter: ['==', '$type', 'LineString'],
    paint: {
      'line-color': WORKING_COLOUR,
      'line-width': 1.5,
      'line-dasharray': [2, 1],
    },
  });
  api.map.addLayer({
    id: 'zone-editor:working-vertices',
    type: 'circle',
    source: 'zone-editor:working-source',
    filter: ['==', '$type', 'Point'],
    paint: {
      'circle-radius': 4,
      'circle-color': WORKING_COLOUR,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#000000',
    },
  });

  // Edit vertex handles
  api.map.addLayer({
    id: 'zone-editor:edit-handles',
    type: 'circle',
    source: 'zone-editor:edit-handles-source',
    paint: {
      'circle-radius': 7,
      'circle-color': HANDLE_COLOUR,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  });

  // Edit midpoint insert handles (slightly smaller, lighter)
  api.map.addLayer({
    id: 'zone-editor:edit-midpoints',
    type: 'circle',
    source: 'zone-editor:edit-midpoints-source',
    paint: {
      'circle-radius': 4,
      'circle-color': MIDPOINT_COLOUR,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
    },
  });

  // -------------------------------------------------------------------------
  // Source update helpers
  // -------------------------------------------------------------------------

  function _rebuildZoneSources() {
    const { priority, exclusion } = _buildZoneFCs(zones);
    const pSrc = api.map.getSource('zone-editor:priority-source');
    if (pSrc) pSrc.setData(priority);
    const eSrc = api.map.getSource('zone-editor:exclusion-source');
    if (eSrc) eSrc.setData(exclusion);
  }

  function _updateWorkingSource() {
    const src = api.map.getSource('zone-editor:working-source');
    if (src) src.setData(_workingGeoJSON(workingVertices));
  }

  function _updateEditHandlesSource() {
    const { handles, midpoints } = _editHandlesGeoJSON(editingCoords);
    const hSrc = api.map.getSource('zone-editor:edit-handles-source');
    if (hSrc) hSrc.setData(handles);
    const mSrc = api.map.getSource('zone-editor:edit-midpoints-source');
    if (mSrc) mSrc.setData(midpoints);
  }

  // -------------------------------------------------------------------------
  // State write — canonical shape {priority: PriorityZone[], exclusion: ExclusionZone[]}
  // (docs/Technical/InterfaceArchitecture.md §3).
  //
  // PriorityZone fields:  id, label, geometry (GeoJSON Polygon), min_coverage_pct
  // ExclusionZone fields: id, label, geometry (GeoJSON Polygon), reason
  //
  // The internal `zones` array uses `name`/`coordinates`/`coverage_threshold_pct`
  // for ergonomics inside the editor; the canonical names are the contract with
  // coverage-viewer (zone compliance display) and gap-analysis (severity scoring).
  // -------------------------------------------------------------------------

  /** Build a closed GeoJSON Polygon from an open ring of [lng, lat] pairs. */
  function _ringToPolygon(coordinates) {
    return {
      type: 'Polygon',
      coordinates: [_closeRing(coordinates)],
    };
  }

  function _writeState() {
    const priority = [];
    const exclusion = [];
    for (const z of zones) {
      const geometry = _ringToPolygon(z.coordinates);
      if (z.type === 'exclusion') {
        exclusion.push({
          id: z.id,
          label: z.name,
          geometry,
          reason: z.reason ?? null,
        });
      } else {
        priority.push({
          id: z.id,
          label: z.name,
          geometry,
          min_coverage_pct: z.coverage_threshold_pct ?? null,
        });
      }
    }
    api.state.set('zones', { priority, exclusion });
  }

  /** Drop a duplicated closing vertex if the ring is closed. */
  function _openRing(ring) {
    if (ring.length < 2) return ring.map(c => [...c]);
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first[0] === last[0] && first[1] === last[1]) {
      return ring.slice(0, -1).map(c => [...c]);
    }
    return ring.map(c => [...c]);
  }

  /**
   * Rebuild the tagged in-memory zones array from the canonical state shape.
   *
   * Accepts both canonical field names (label/geometry/min_coverage_pct) and
   * the legacy in-editor names (name/coordinates/coverage_threshold_pct) so a
   * scenario authored before the canonical migration still loads cleanly.
   *
   * Defensive against malformed entries: non-array val.priority/val.exclusion
   * are coerced to [] (D-422); zones with fewer than 3 ring vertices are
   * dropped with a warning (D-423) rather than producing a zero-vertex polygon
   * that MapLibreGL would silently render as nothing.
   */
  function _readCanonical(val) {
    if (!val || typeof val !== 'object') return [];

    function _ringFrom(z) {
      // Outer ring lookup: canonical first, then legacy.  Both may produce
      // an empty array, which we let through to the validity check below.
      const ring = z.geometry?.coordinates?.[0] ?? z.coordinates ?? [];
      return _openRing(ring);
    }

    function _validRing(ring, zoneId) {
      if (Array.isArray(ring) && ring.length >= 3) return true;
      console.warn(
        `[zone-editor] zone '${zoneId}' has fewer than 3 ring vertices ` +
        `(got ${Array.isArray(ring) ? ring.length : typeof ring}) — dropping.`
      );
      return false;
    }

    const priorityRaw = Array.isArray(val.priority) ? val.priority : [];
    const exclusionRaw = Array.isArray(val.exclusion) ? val.exclusion : [];

    const priority = priorityRaw
      .map(z => ({
        id: z.id,
        name: z.label ?? z.name ?? '',
        type: 'priority',
        coverage_threshold_pct: z.min_coverage_pct ?? z.coverage_threshold_pct ?? null,
        reason: null,
        coordinates: _ringFrom(z),
      }))
      .filter(z => _validRing(z.coordinates, z.id));
    const exclusion = exclusionRaw
      .map(z => ({
        id: z.id,
        name: z.label ?? z.name ?? '',
        type: 'exclusion',
        coverage_threshold_pct: null,
        reason: z.reason ?? null,
        coordinates: _ringFrom(z),
      }))
      .filter(z => _validRing(z.coordinates, z.id));
    return [...priority, ...exclusion];
  }

  // -------------------------------------------------------------------------
  // Panel build
  // -------------------------------------------------------------------------

  const container = document.createElement('div');
  container.innerHTML = PANEL_HTML;

  const drawBtn          = container.querySelector('#ze-draw-btn');
  const zoneTypeSelect   = container.querySelector('#ze-zone-type');
  const drawHint         = container.querySelector('#ze-draw-hint');
  const formEl           = container.querySelector('#ze-form');
  const nameInput        = container.querySelector('#ze-zone-name');
  const thresholdGroup   = container.querySelector('#ze-threshold-group');
  const thresholdInput   = container.querySelector('#ze-threshold');
  const thresholdError   = container.querySelector('#ze-threshold-error');
  const reasonGroup      = container.querySelector('#ze-reason-group');
  const reasonInput      = container.querySelector('#ze-reason');
  const confirmBtn       = container.querySelector('#ze-confirm-btn');
  const cancelBtn        = container.querySelector('#ze-cancel-btn');
  const editBar          = container.querySelector('#ze-edit-bar');
  const editLabelEl      = container.querySelector('#ze-edit-label');
  const doneEditBtn      = container.querySelector('#ze-done-edit-btn');
  const zoneListEl       = container.querySelector('#ze-zone-list');

  // -------------------------------------------------------------------------
  // Zone list rendering
  // -------------------------------------------------------------------------

  function _clearEl(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function _rebuildZoneList() {
    _clearEl(zoneListEl);
    for (const zone of zones) {
      const row = document.createElement('div');
      row.style.cssText =
        'display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid #252540';

      const typeDot = document.createElement('span');
      const dotColour = zone.type === 'exclusion' ? EXCLUSION_COLOUR : PRIORITY_COLOUR;
      typeDot.style.cssText =
        `width:10px;height:10px;border-radius:50%;flex-shrink:0;background:${dotColour}`;

      const nameSp = document.createElement('span');
      nameSp.textContent = zone.name;
      nameSp.style.cssText =
        'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px';

      const threshSp = document.createElement('span');
      threshSp.style.cssText = 'font-size:11px;color:#6b7280;flex-shrink:0';
      if (zone.type === 'priority' && zone.coverage_threshold_pct != null) {
        threshSp.textContent = `${zone.coverage_threshold_pct}%`;
      }

      const editBtn = document.createElement('button');
      editBtn.textContent = '✏';
      editBtn.title = 'Edit zone';
      editBtn.style.cssText =
        'padding:2px 5px;background:none;border:1px solid #3b82f6;border-radius:3px;color:#3b82f6;cursor:pointer;font-size:12px';
      editBtn.addEventListener('click', () => _enterEditMode(zone.id));

      const trashBtn = document.createElement('button');
      trashBtn.textContent = '🗑';
      trashBtn.title = 'Remove zone';
      trashBtn.setAttribute('data-zone-id', zone.id);
      trashBtn.style.cssText =
        'padding:2px 5px;background:none;border:1px solid #ef4444;border-radius:3px;color:#ef4444;cursor:pointer;font-size:12px';
      trashBtn.addEventListener('click', () => _removeZone(zone.id));

      row.append(typeDot, nameSp, threshSp, editBtn, trashBtn);
      zoneListEl.appendChild(row);
    }
  }

  // -------------------------------------------------------------------------
  // Draw mode
  // -------------------------------------------------------------------------

  function _onDrawClick(e) {
    const lngLat = api.map.unproject(e.point);
    if (!lngLat) return;
    workingVertices.push([lngLat.lng, lngLat.lat]);
    _updateWorkingSource();
  }

  function _onDrawDblClick(e) {
    // The browser fires a click event immediately before dblclick; pop the
    // duplicate tail vertex that the preceding click already appended (D-343).
    if (workingVertices.length > 0) workingVertices.pop();
    if (workingVertices.length < 3) return;
    _stopDrawMode();
    _showForm();
  }

  function _startDrawMode() {
    drawMode = true;
    drawType = (zoneTypeSelect ? String(zoneTypeSelect.value) : '') || 'priority';
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
    if (drawBtn) drawBtn.textContent = 'Draw Zone';
    if (drawHint) drawHint.hidden = true;
    api.map.getCanvas().style.cursor = '';
    api.map.off('click', _onDrawClick);
    api.map.off('dblclick', _onDrawDblClick);
    api.bus.emit('drawmode:exited', { mode: 'draw' });
  }

  // -------------------------------------------------------------------------
  // Zone confirmation form
  // -------------------------------------------------------------------------

  function _updateFormFieldVisibility(type) {
    const isPriority = type === 'priority';
    if (thresholdGroup) thresholdGroup.hidden = !isPriority;
    if (reasonGroup)    reasonGroup.hidden    = isPriority;
    if (thresholdError) thresholdError.hidden = true;
  }

  function _showForm() {
    if (formEl) formEl.hidden = false;
    if (nameInput) nameInput.value = '';
    if (thresholdInput) thresholdInput.value = '';
    if (reasonInput) reasonInput.value = '';
    if (thresholdError) thresholdError.hidden = true;
    _updateFormFieldVisibility(drawType);
  }

  function _hideForm() {
    if (formEl) formEl.hidden = true;
  }

  /** Validate and return the coverage threshold, or null if not applicable.
   *  Returns { ok: true, value } or { ok: false, message }. */
  function _validateThreshold(type, rawValue) {
    if (type !== 'priority') return { ok: true, value: null };
    const str = String(rawValue ?? '').trim();
    if (str === '') return { ok: true, value: null }; // optional — no threshold
    const num = parseFloat(str);
    if (!Number.isFinite(num) || num < 0 || num > 100) {
      return { ok: false, message: 'Coverage threshold must be a number between 0 and 100.' };
    }
    return { ok: true, value: num };
  }

  function _onConfirmZone() {
    if (workingVertices.length < 3) {
      _hideForm();
      workingVertices = [];
      _updateWorkingSource();
      return;
    }

    const name = (nameInput ? String(nameInput.value).trim() : '') || `Zone ${zones.length + 1}`;
    const type = drawType;
    const threshRaw = thresholdInput ? thresholdInput.value : '';
    const threshResult = _validateThreshold(type, threshRaw);

    if (!threshResult.ok) {
      if (thresholdError) {
        thresholdError.textContent = threshResult.message;
        thresholdError.hidden = false;
      }
      return; // Do NOT write state — user must correct input
    }

    if (thresholdError) thresholdError.hidden = true;

    const reasonVal = (reasonInput ? String(reasonInput.value).trim() : '') || null;

    const zone = {
      id: _genId(),
      name,
      type,
      coverage_threshold_pct: threshResult.value,
      reason: type === 'exclusion' ? reasonVal : null,
      coordinates: workingVertices.map(v => [...v]),
    };

    zones.push(zone);
    workingVertices = [];

    _updateWorkingSource();
    _rebuildZoneSources();
    _rebuildZoneList();
    _writeState();
    _hideForm();

    api.bus.emit('zone:added', { id: zone.id, name: zone.name, type: zone.type });
  }

  function _onCancelZone() {
    workingVertices = [];
    _updateWorkingSource();
    _hideForm();
  }

  if (confirmBtn) confirmBtn.addEventListener('click', _onConfirmZone);
  if (cancelBtn)  cancelBtn.addEventListener('click', _onCancelZone);

  // -------------------------------------------------------------------------
  // Zone removal (S14.7-4)
  // -------------------------------------------------------------------------

  function _removeZone(zoneId) {
    const idx = zones.findIndex(z => z.id === zoneId);
    if (idx === -1) return;
    const removed = zones[idx];

    if (editingId === zoneId) _exitEditMode(false);

    zones.splice(idx, 1);
    _rebuildZoneSources();
    _rebuildZoneList();
    _writeState();

    api.bus.emit('zone:removed', { id: removed.id, name: removed.name });
  }

  // -------------------------------------------------------------------------
  // Edit mode — vertex drag + edge-midpoint insert (S14.7-4)
  // -------------------------------------------------------------------------

  function _enterEditMode(zoneId) {
    if (editingId) _exitEditMode(false);
    if (drawMode) _stopDrawMode();

    const zone = zones.find(z => z.id === zoneId);
    if (!zone) return;

    editingId = zoneId;
    editingCoords = zone.coordinates.map(c => [...c]);
    // Vertex editing captures map clicks/drags — same coord-tools signal.
    api.bus.emit('drawmode:entered', { mode: 'edit' });

    _updateEditHandlesSource();
    if (editBar) editBar.hidden = false;
    if (editLabelEl) editLabelEl.textContent = `Editing: ${_esc(zone.name)}`;

    let dragging = false;
    let dragKind = null;
    let dragIdx  = -1;

    function _onHandleMouseDown(e) {
      const features = api.map.queryRenderedFeatures(e.point, {
        layers: ['zone-editor:edit-handles'],
      });
      if (!features || !features.length) return;
      // Validate index before trusting queryRenderedFeatures properties (D-340)
      const rawIdx = features[0].properties.index;
      if (!Number.isInteger(rawIdx) || rawIdx < 0 || rawIdx >= editingCoords.length) return;
      dragging = true;
      dragKind = 'vertex';
      dragIdx  = rawIdx;
      api.map.getCanvas().style.cursor = 'grabbing';
      e.preventDefault && e.preventDefault();
    }

    function _onMidpointMouseDown(e) {
      const features = api.map.queryRenderedFeatures(e.point, {
        layers: ['zone-editor:edit-midpoints'],
      });
      if (!features || !features.length) return;
      // Validate after_index before trusting queryRenderedFeatures properties (D-341)
      const rawAfterIdx = features[0].properties.after_index;
      if (!Number.isInteger(rawAfterIdx) || rawAfterIdx < 0 || rawAfterIdx >= editingCoords.length) return;
      // Insert new vertex after after_index, then start dragging it
      const afterIdx = rawAfterIdx;
      const [x1, y1] = editingCoords[afterIdx];
      const nextIdx  = (afterIdx + 1) % editingCoords.length;
      const [x2, y2] = editingCoords[nextIdx];
      editingCoords.splice(afterIdx + 1, 0, [(x1 + x2) / 2, (y1 + y2) / 2]);
      _updateEditHandlesSource();
      dragging = true;
      dragKind = 'vertex';
      dragIdx  = afterIdx + 1;
      api.map.getCanvas().style.cursor = 'grabbing';
      e.preventDefault && e.preventDefault();
    }

    function _onMouseMove(e) {
      if (!dragging || dragKind !== 'vertex' || dragIdx < 0) return;
      const pt = e.point ?? { x: e.offsetX, y: e.offsetY };
      const lngLat = api.map.unproject(pt);
      if (!lngLat) return;
      editingCoords[dragIdx] = [lngLat.lng, lngLat.lat];
      _updateEditHandlesSource();
      // Update zone preview
      const preview = zones.map(z =>
        z.id === editingId ? { ...z, coordinates: editingCoords } : z
      );
      const { priority, exclusion } = _buildZoneFCs(preview);
      const pSrc = api.map.getSource('zone-editor:priority-source');
      if (pSrc) pSrc.setData(priority);
      const eSrc = api.map.getSource('zone-editor:exclusion-source');
      if (eSrc) eSrc.setData(exclusion);
    }

    function _onMouseUp() {
      dragging = false;
      dragKind = null;
      dragIdx  = -1;
      api.map.getCanvas().style.cursor = '';
    }

    api.map.on('mousedown', 'zone-editor:edit-handles',   _onHandleMouseDown);
    api.map.on('mousedown', 'zone-editor:edit-midpoints', _onMidpointMouseDown);
    api.map.getCanvas().addEventListener('mousemove', _onMouseMove);
    api.map.getCanvas().addEventListener('mouseup',   _onMouseUp);

    editCleanup = () => {
      api.map.off('mousedown', 'zone-editor:edit-handles',   _onHandleMouseDown);
      api.map.off('mousedown', 'zone-editor:edit-midpoints', _onMidpointMouseDown);
      api.map.getCanvas().removeEventListener('mousemove', _onMouseMove);
      api.map.getCanvas().removeEventListener('mouseup',   _onMouseUp);
      api.map.getCanvas().style.cursor = '';
      const hSrc = api.map.getSource('zone-editor:edit-handles-source');
      if (hSrc) hSrc.setData(_EMPTY_FC);
      const mSrc = api.map.getSource('zone-editor:edit-midpoints-source');
      if (mSrc) mSrc.setData(_EMPTY_FC);
      if (editBar) editBar.hidden = true;
      editingId = null;
      editingCoords = [];
      editCleanup = null;
    };
  }

  function _exitEditMode(commit) {
    if (!editingId) return;
    api.bus.emit('drawmode:exited', { mode: 'edit' });
    if (commit) {
      const idx = zones.findIndex(z => z.id === editingId);
      if (idx !== -1) {
        zones[idx] = { ...zones[idx], coordinates: editingCoords.map(c => [...c]) };
      }
      _rebuildZoneSources();
      _writeState();
    } else {
      _rebuildZoneSources();
    }
    if (editCleanup) {
      editCleanup();
    } else {
      // Defensive: cleanup was never registered — reset state to avoid zombie (D-348)
      editingId = null;
      editingCoords = [];
    }
  }

  if (doneEditBtn) {
    doneEditBtn.addEventListener('click', () => _exitEditMode(true));
  }

  // -------------------------------------------------------------------------
  // Draw button — toggle draw mode
  // -------------------------------------------------------------------------

  if (drawBtn) {
    drawBtn.addEventListener('click', () => {
      if (drawMode) {
        _stopDrawMode();
      } else {
        if (editingId) _exitEditMode(false);
        _startDrawMode();
      }
    });
  }

  // -------------------------------------------------------------------------
  // Reactive state watch — rebuild map when state changes externally
  // -------------------------------------------------------------------------

  unsubs.push(api.state.watch('zones', (val) => {
    if (!val) return;
    zones = _readCanonical(val);
    _rebuildZoneSources();
    _rebuildZoneList();
  }));

  // -------------------------------------------------------------------------
  // Initial render from existing state
  // -------------------------------------------------------------------------

  const initState = api.state.get('zones');
  if (initState) {
    zones = _readCanonical(initState);
    _rebuildZoneSources();
    _rebuildZoneList();
  }

  api.panel.mount(container);

  // -------------------------------------------------------------------------
  // Cleanup — all sources, layers, listeners removed in one block (S14.7-3)
  // -------------------------------------------------------------------------

  api.panel.onUnmount(() => {
    if (drawMode)    _stopDrawMode();
    if (editingId)   _exitEditMode(false);

    unsubs.forEach(u => u());

    const layers = [
      'zone-editor:edit-midpoints',
      'zone-editor:edit-handles',
      'zone-editor:working-vertices',
      'zone-editor:working-outline',
      'zone-editor:working-fill',
      'zone-editor:exclusion-outline',
      'zone-editor:exclusion-fill',
      'zone-editor:priority-label',
      'zone-editor:priority-fill',
    ];
    for (const id of layers) {
      if (api.map.getLayer(id)) api.map.removeLayer(id);
    }

    const sources = [
      'zone-editor:edit-midpoints-source',
      'zone-editor:edit-handles-source',
      'zone-editor:working-source',
      'zone-editor:exclusion-source',
      'zone-editor:priority-source',
    ];
    for (const id of sources) {
      if (api.map.getSource(id)) api.map.removeSource(id);
    }
  });
}
