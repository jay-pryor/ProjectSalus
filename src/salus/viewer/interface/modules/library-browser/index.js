/**
 * library-browser/index.js — Sensor and effector catalogue browser.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Reads:       sensor_library, effector_library
 * Emits:       placement:pending,
 *              drawmode:entered, drawmode:exited (I-22 — emitted around the
 *              click-to-place mode, which captures an unscoped map click, so
 *              the coord-tools measurement tool stays mutually exclusive with it)
 * Map sources: library-browser:drag-ghost
 * Map layers:  library-browser:drag-ghost-circle
 *
 * sensor_library and effector_library are pre-populated by the shell before
 * any module is initialised, so api.state.get() at mount time always returns
 * the current catalogue data.
 *
 * Placement is initiated in two ways:
 *   1. Drag-and-drop: drag an entry's drag handle onto the map canvas.
 *   2. Click-to-place: click "Place" in an expanded spec card, then click
 *      on the map. Escape cancels click-to-place mode.
 */

/**
 * Spec fields shown in each entry's expanded card, in declaration order.
 * To add a field to the spec table, add one entry here — no other change needed.
 */
const SPEC_DISPLAY_FIELDS = [
  { key: 'type',                 label: 'Type',             format: v => _esc(v ?? '—') },
  { key: 'max_range_m',          label: 'Max Range',        format: v => v != null ? `${(v / 1000).toFixed(1)} km` : '—' },
  { key: 'azimuth_coverage_deg', label: 'Azimuth Coverage', format: v => v != null ? `${v}°` : '—' },
  { key: 'cost_aud',             label: 'Cost (AUD)',        format: v => v != null ? `$${Number(v).toLocaleString()}` : '—' },
  { key: 'confidence',           label: 'Confidence',       format: _fmtConfidence },
];

function _fmtConfidence(v) {
  if (!v) return '—';
  return v === 'measured' ? 'Measured (vendor-published)' : 'Estimated ⚠';
}

/** Escape HTML special characters to prevent XSS in innerHTML template literals. */
function _esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Background colours for type badges (matches Placement Editor layer colours). */
const TYPE_BADGE_COLOURS = {
  Radar:    '#f97316',
  RF:       '#a855f7',
  EO_IR:    '#22c55e',
  Acoustic: '#06b6d4',
};

const _EMPTY_FC = Object.freeze({ type: 'FeatureCollection', features: [] });

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function _badgeBg(type) {
  return TYPE_BADGE_COLOURS[type] ?? '#6b7280';
}

function _specTableHtml(def) {
  const rows = SPEC_DISPLAY_FIELDS
    .map(({ key, label, format }) =>
      `<tr>` +
      `<td style="color:#aaa;padding:2px 8px 2px 0;white-space:nowrap;font-size:12px">${_esc(label)}</td>` +
      `<td style="padding:2px 0;font-size:12px">${format(def[key])}</td>` +
      `</tr>`
    )
    .join('');
  return `<table style="border-collapse:collapse;width:100%">${rows}</table>`;
}

/**
 * Build a single library entry row (collapsed header + expandable spec card).
 * Returns { row, handle, placeBtn, def }.
 */
function _buildEntry(def) {
  const row = document.createElement('div');
  row.style.cssText = 'border-bottom:1px solid #1e1e30';

  // --- Header row (always visible) ---
  const header = document.createElement('div');
  header.style.cssText =
    'display:flex;align-items:center;gap:6px;padding:5px 8px;cursor:pointer;user-select:none';

  const badge = document.createElement('span');
  badge.style.cssText =
    `background:${_badgeBg(def.type ?? '')};color:#fff;padding:1px 5px;border-radius:3px;` +
    `font-size:11px;font-weight:600;flex-shrink:0`;
  badge.textContent = (def.type ?? '?').slice(0, 5);

  const nameSp = document.createElement('span');
  nameSp.textContent = def.name ?? '(unnamed)';
  nameSp.style.cssText =
    'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px';

  const arrow = document.createElement('span');
  arrow.textContent = '▶';
  arrow.style.cssText = 'font-size:10px;color:#6b7280;flex-shrink:0;transition:transform 0.12s';
  arrow.setAttribute('aria-hidden', 'true');

  const handle = document.createElement('span');
  handle.setAttribute('draggable', 'true');
  handle.textContent = '⠿';
  handle.title = 'Drag to place on map';
  handle.setAttribute('aria-label', `Drag ${def.name ?? 'item'} to place on map`);
  handle.style.cssText = 'cursor:grab;color:#6b7280;font-size:14px;padding:0 4px;flex-shrink:0';

  header.append(badge, nameSp, arrow, handle);

  // --- Expandable spec card ---
  const detail = document.createElement('div');
  detail.style.cssText = 'display:none;padding:6px 10px 10px';
  detail.innerHTML = _specTableHtml(def);

  const placeBtn = document.createElement('button');
  placeBtn.textContent = 'Place';
  placeBtn.setAttribute('aria-label', `Place ${def.name ?? 'item'} by clicking on the map`);
  placeBtn.style.cssText =
    'margin-top:8px;padding:4px 14px;background:#0f3460;color:#fff;' +
    'border:1px solid #2266aa;border-radius:3px;cursor:pointer;font-size:12px';
  detail.appendChild(placeBtn);

  // Toggle expand/collapse on header click (drag handle click does not toggle)
  let expanded = false;
  header.addEventListener('click', e => {
    if (e.target === handle) return;
    expanded = !expanded;
    detail.style.display = expanded ? 'block' : 'none';
    arrow.style.transform = expanded ? 'rotate(90deg)' : '';
  });

  row.append(header, detail);
  return { row, handle, placeBtn, def };
}

/**
 * Build grouped entry objects from a library dict (type → items[]).
 * Returns { sections: {type: [entry, ...]}, allEntries: [...] }.
 * Logs a warning and returns empty if libraryDict is not a plain object.
 */
function _buildGroupedEntries(libraryDict) {
  if (!libraryDict) return { sections: {}, allEntries: [] };
  if (typeof libraryDict !== 'object' || Array.isArray(libraryDict)) {
    console.warn('[library-browser] unexpected library format:', typeof libraryDict);
    return { sections: {}, allEntries: [] };
  }
  const sections = {};
  const allEntries = [];
  for (const [type, items] of Object.entries(libraryDict)) {
    sections[type] = [];
    for (const item of (items ?? [])) {
      const entry = _buildEntry(item);
      sections[type].push(entry);
      allEntries.push(entry);
    }
  }
  return { sections, allEntries };
}

/**
 * Build a collapsible section element (Sensors or Effectors) with type sub-groups.
 */
function _buildSectionEl(title, sections) {
  const section = document.createElement('div');
  section.style.cssText = 'border-bottom:1px solid #252540';

  const hdr = document.createElement('div');
  hdr.style.cssText =
    'padding:7px 10px;font-size:12px;font-weight:600;text-transform:uppercase;' +
    'letter-spacing:0.06em;color:#8888aa;cursor:pointer;user-select:none;' +
    'display:flex;justify-content:space-between;align-items:center';
  hdr.textContent = title;

  const collapseArrow = document.createElement('span');
  collapseArrow.textContent = '▼';
  collapseArrow.style.cssText = 'font-size:10px;transition:transform 0.12s';
  collapseArrow.setAttribute('aria-hidden', 'true');
  hdr.appendChild(collapseArrow);

  const body = document.createElement('div');
  for (const [type, entries] of Object.entries(sections)) {
    const groupLabel = document.createElement('div');
    groupLabel.textContent = type;
    groupLabel.style.cssText =
      'padding:3px 10px;font-size:11px;color:#6b7280;background:#1a1a2e;' +
      'font-weight:600;letter-spacing:0.04em;text-transform:uppercase';
    body.appendChild(groupLabel);
    for (const entry of entries) {
      body.appendChild(entry.row);
    }
  }

  let collapsed = false;
  hdr.addEventListener('click', () => {
    collapsed = !collapsed;
    body.style.display = collapsed ? 'none' : 'block';
    collapseArrow.style.transform = collapsed ? 'rotate(-90deg)' : '';
  });

  section.append(hdr, body);
  return section;
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];
  let draggingDef = null;   // definition currently being dragged
  let pendingDef = null;    // definition awaiting click-to-place confirmation
  let clickCancelFn = null; // cancel function for active click-to-place mode

  // Local mirrors of both library values — avoids get() inside watch() callbacks
  // (D-321: prevents stale read when both keys update in rapid succession)
  let latestSensors = null;
  let latestEffectors = null;

  // -------------------------------------------------------------------------
  // Ghost marker — permanent source with empty data; updated during drag/place
  // -------------------------------------------------------------------------
  api.map.addSource('library-browser:drag-ghost', {
    type: 'geojson',
    data: _EMPTY_FC,
  });
  api.map.addLayer({
    id: 'library-browser:drag-ghost-circle',
    type: 'circle',
    source: 'library-browser:drag-ghost',
    paint: {
      'circle-radius': 14,
      'circle-color': '#ffffff',
      'circle-opacity': 0.35,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.7,
    },
  });

  function _setGhost(lng, lat) {
    const src = api.map.getSource('library-browser:drag-ghost');
    if (src) {
      src.setData({
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [lng, lat] },
          properties: {},
        }],
      });
    }
  }

  function _clearGhost() {
    const src = api.map.getSource('library-browser:drag-ghost');
    if (src) src.setData(_EMPTY_FC);
  }

  // -------------------------------------------------------------------------
  // Click-to-place mode
  // -------------------------------------------------------------------------
  function _enterClickToPlace(def) {
    if (clickCancelFn) clickCancelFn(); // cancel any previous mode first
    pendingDef = def;
    // D-613: emit drawmode:entered BEFORE setting the cursor, so the coord-tools
    // measure-mode exit (which restores its saved cursor) cannot overwrite the
    // crosshair this mode is about to set.
    api.bus.emit('drawmode:entered', { mode: 'place' });
    api.map.getCanvas().style.cursor = 'crosshair';

    function _onMapClick(e) {
      // D-317: guard against unproject returning null/undefined
      const lngLat = api.map.unproject(e.point);
      if (!lngLat) return;
      const { lng, lat } = lngLat;
      const captured = pendingDef;
      _cancelClickToPlace();
      api.bus.emit('placement:pending', { lat, lng, definition: captured });
    }

    function _onKeyDown(e) {
      if (e.key === 'Escape') _cancelClickToPlace();
    }

    api.map.on('click', _onMapClick);
    // D-315: use getCanvas() rather than document to scope listener to map surface
    api.map.getCanvas().addEventListener('keydown', _onKeyDown);

    clickCancelFn = () => {
      api.map.off('click', _onMapClick);
      api.map.getCanvas().removeEventListener('keydown', _onKeyDown);
      api.map.getCanvas().style.cursor = '';
      _clearGhost();
      pendingDef = null;
      clickCancelFn = null;
      api.bus.emit('drawmode:exited', { mode: 'place' });
    };
  }

  function _cancelClickToPlace() {
    if (clickCancelFn) clickCancelFn();
  }

  // -------------------------------------------------------------------------
  // Map drag-and-drop handlers
  // -------------------------------------------------------------------------
  function _onDragOver(e) {
    e.preventDefault();
    if (!draggingDef) return;
    // D-318: guard against unproject returning null/undefined
    const lngLat = api.map.unproject({ x: e.offsetX, y: e.offsetY });
    if (!lngLat) return;
    _setGhost(lngLat.lng, lngLat.lat);
  }

  function _onDrop(e) {
    e.preventDefault();
    if (!draggingDef) return;
    const def = draggingDef;
    draggingDef = null;
    _clearGhost();
    // D-319: guard against unproject returning null/undefined to prevent emitting undefined coordinates
    const lngLat = api.map.unproject({ x: e.offsetX, y: e.offsetY });
    if (!lngLat) return;
    api.bus.emit('placement:pending', { lat: lngLat.lat, lng: lngLat.lng, definition: def });
  }

  api.map.on('dragover', _onDragOver);
  api.map.on('drop', _onDrop);

  // -------------------------------------------------------------------------
  // Panel build helpers
  // -------------------------------------------------------------------------
  function _attachDragListeners(entry) {
    entry.handle.addEventListener('dragstart', e => {
      // D-316: guard against missing dataTransfer (synthetic events, non-standard browsers)
      if (!e.dataTransfer) {
        draggingDef = null;
        return;
      }
      draggingDef = entry.def;
      e.dataTransfer.setData('application/json', JSON.stringify(entry.def));
      e.dataTransfer.effectAllowed = 'copy';
    });

    entry.handle.addEventListener('dragend', () => {
      draggingDef = null;
      _clearGhost();
    });

    entry.placeBtn.addEventListener('click', () => {
      _enterClickToPlace(entry.def);
    });
  }

  function _buildPanelEl(sensorLib, effectorLib) {
    const panel = document.createElement('div');
    panel.style.cssText = 'overflow-y:auto';

    const heading = document.createElement('div');
    heading.textContent = 'Library Browser';
    heading.style.cssText =
      'padding:10px 12px;font-size:14px;font-weight:600;' +
      'border-bottom:1px solid #252540;color:#e0e0e0';
    panel.appendChild(heading);

    const { sections: sSections, allEntries: sEntries } = _buildGroupedEntries(sensorLib);
    if (Object.keys(sSections).length > 0) {
      panel.appendChild(_buildSectionEl('Sensors', sSections));
    }
    for (const e of sEntries) _attachDragListeners(e);

    const { sections: eSections, allEntries: eEntries } = _buildGroupedEntries(effectorLib);
    if (Object.keys(eSections).length > 0) {
      panel.appendChild(_buildSectionEl('Effectors', eSections));
    }
    for (const e of eEntries) _attachDragListeners(e);

    return panel;
  }

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestSensors = api.state.get('sensor_library');    // OK: initial render only
  latestEffectors = api.state.get('effector_library'); // OK: initial render only
  api.panel.mount(_buildPanelEl(latestSensors, latestEffectors));

  // -------------------------------------------------------------------------
  // Reactive updates via watch() — all subsequent renders driven here.
  // D-321: use local mirrors to avoid cross-key get() inside watch() callbacks.
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sensor_library', (sensors) => {
    latestSensors = sensors;
    api.panel.mount(_buildPanelEl(latestSensors, latestEffectors));
  }));

  unsubs.push(api.state.watch('effector_library', (effectors) => {
    latestEffectors = effectors;
    api.panel.mount(_buildPanelEl(latestSensors, latestEffectors));
  }));

  // -------------------------------------------------------------------------
  // Cleanup — all subscriptions and map listeners removed in one block
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    _cancelClickToPlace();
    unsubs.forEach(u => u());
    api.map.off('dragover', _onDragOver);
    api.map.off('drop', _onDrop);
    if (api.map.getLayer('library-browser:drag-ghost-circle')) {
      api.map.removeLayer('library-browser:drag-ghost-circle');
    }
    if (api.map.getSource('library-browser:drag-ghost')) {
      api.map.removeSource('library-browser:drag-ghost');
    }
  });
}
