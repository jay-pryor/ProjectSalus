/**
 * gap-analysis/index.js — Gap Analysis Module (S14.9).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Displays a ranked list of coverage gaps from sim_results, sorted by
 * severity score (area × zone-priority weight).  Provides fly-to navigation
 * to each gap centroid and emits placement:pending for suggested sensors.
 *
 * Reads:       terrain, sim_results, zones, sensor_library
 * Writes:      (none)
 * Emits:       placement:pending
 * Subscribes:  simulation:complete
 * Map sources: (none — navigates via api.map.flyTo only)
 * Map layers:  (none)
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Severity labels and their sort weights. */
const SEVERITY = Object.freeze({ Critical: 3, High: 2, Medium: 1 });

/** Zone min_coverage_pct threshold above which a zone is "high-priority". */
const HIGH_PRIORITY_ZONE_THRESHOLD = 90;

const SEVERITY_COLOURS = Object.freeze({
  Critical: '#f87171',
  High:     '#fbbf24',
  Medium:   '#94a3b8',
});

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

/**
 * Compute approximate polygon area in square metres using the shoelace
 * formula with a WGS84 latitude correction.
 * @param {[number, number][]} ring  Outer ring as [lng, lat] coordinate pairs.
 * @returns {number} Area in m².
 */
function _polygonAreaM2(ring) {
  if (!ring || ring.length < 3) return 0;
  // Shoelace area in square degrees
  let areaDeg2 = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    areaDeg2 += x1 * y2 - x2 * y1;
  }
  areaDeg2 = Math.abs(areaDeg2) / 2;
  // Convert to m² using average latitude
  const avgLat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
  const cosLat = Math.cos(avgLat * Math.PI / 180);
  const METRES_PER_DEG = 111320;
  return areaDeg2 * METRES_PER_DEG * METRES_PER_DEG * cosLat;
}

/**
 * Compute the centroid of a polygon's outer ring.
 * @param {[number, number][]} ring  Outer ring as [lng, lat] coordinate pairs.
 * @returns {[number, number]} [lng, lat]
 */
function _ringCentroid(ring) {
  if (!ring || ring.length === 0) return [0, 0];
  const lngSum = ring.reduce((s, c) => s + c[0], 0);
  const latSum = ring.reduce((s, c) => s + c[1], 0);
  return [lngSum / ring.length, latSum / ring.length];
}

/**
 * Point-in-polygon test using the ray casting algorithm.
 * @param {[number, number]} point  [lng, lat]
 * @param {[number, number][]} ring  Polygon outer ring as [lng, lat] pairs.
 * @returns {boolean}
 */
function _pointInRing(point, ring) {
  const [px, py] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    // Guard horizontal edges: (yj - yi) === 0 would produce ±Infinity, flipping
    // the inside flag incorrectly.  Standard ray-cast: horizontal edges cannot
    // be intersected by a horizontal ray, so skip them.
    const intersect =
      (yi > py) !== (yj > py) &&
      yj !== yi &&
      px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

// ---------------------------------------------------------------------------
// Gap scoring helpers
// ---------------------------------------------------------------------------

/**
 * Determine severity badge for a gap given its centroid and the current zones.
 * - Critical: centroid inside a high-priority zone (min_coverage_pct >= 90)
 * - High:     centroid inside any priority zone
 * - Medium:   no zone overlap
 *
 * @param {[number, number]} centroid  [lng, lat]
 * @param {{priority: object[]}} zones
 * @returns {'Critical'|'High'|'Medium'}
 */
function _gapSeverity(centroid, zones) {
  for (const zone of (zones?.priority ?? [])) {
    const geom = zone.geometry;
    if (!geom) continue;
    const rings = geom.type === 'MultiPolygon'
      ? geom.coordinates.map(poly => poly[0])   // outer ring of each sub-polygon
      : geom.type === 'Polygon'
        ? [geom.coordinates[0]]                  // outer ring of the single polygon
        : [];
    const inside = rings.some(ring => ring && ring.length >= 3 && _pointInRing(centroid, ring));
    if (!inside) continue;
    const minPct = zone.min_coverage_pct ?? 0;
    return minPct >= HIGH_PRIORITY_ZONE_THRESHOLD ? 'Critical' : 'High';
  }
  return 'Medium';
}

/**
 * Score a gap: area_m2 × severity weight.  Higher = more important to fix.
 * @param {number} areaM2
 * @param {'Critical'|'High'|'Medium'} severity
 * @returns {number}
 */
function _gapScore(areaM2, severity) {
  return areaM2 * (SEVERITY[severity] ?? 1);
}

/**
 * Build a list of scored gap entries from sim_results and zones, sorted
 * descending by score (most severe first).
 *
 * @param {object|null} simResults
 * @param {object|null} zones
 * @returns {Array<{id:number, areaM2:number, severity:string, score:number,
 *                  centroid:[number,number], feature:object, suggestion:object|null}>}
 */
function _buildGapList(simResults, zones) {
  const gapsFC = simResults?.layers?.gaps ?? { type: 'FeatureCollection', features: [] };
  const suggestions = simResults?.gap_suggestions ?? [];
  const entries = [];

  for (let i = 0; i < (gapsFC.features ?? []).length; i++) {
    const feat = gapsFC.features[i];
    const ring = feat.geometry?.coordinates?.[0];
    if (!ring || ring.length < 3) continue;
    const areaM2   = _polygonAreaM2(ring);
    const centroid = _ringCentroid(ring);
    const severity = _gapSeverity(centroid, zones);
    const score    = _gapScore(areaM2, severity);
    const suggestion = suggestions[i] ?? null;
    entries.push({ id: i, areaM2, severity, score, centroid, feature: feat, suggestion });
  }

  // Sort descending by score
  entries.sort((a, b) => b.score - a.score);
  return entries;
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirrors
  let latestSimResults = null;
  let latestZones      = null;

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.setAttribute('data-testid', 'gap-analysis-panel');
  panel.style.cssText =
    'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Gap Analysis';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  const listContainer = document.createElement('div');
  listContainer.setAttribute('data-testid', 'gap-list');
  listContainer.style.cssText = 'flex:1;overflow-y:auto';
  panel.appendChild(listContainer);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function _clearList() {
    while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
  }

  function _renderList() {
    _clearList();
    const entries = _buildGapList(latestSimResults, latestZones);

    if (entries.length === 0) {
      const empty = document.createElement('div');
      empty.setAttribute('data-testid', 'gap-list-empty');
      empty.textContent = latestSimResults
        ? 'No gaps detected in simulation results.'
        : 'Run a simulation to see gap analysis.';
      empty.style.cssText =
        'padding:16px 12px;font-size:12px;color:#666;text-align:center';
      listContainer.appendChild(empty);
      return;
    }

    for (const entry of entries) {
      const card = document.createElement('div');
      card.setAttribute('data-testid', `gap-card-${entry.id}`);
      card.style.cssText =
        'padding:8px 12px;border-bottom:1px solid #1e1e30';

      // ---- Header row: gap ID + severity badge + fly-to ----
      const headerRow = document.createElement('div');
      headerRow.style.cssText =
        'display:flex;align-items:center;gap:6px;margin-bottom:4px';

      const idEl = document.createElement('span');
      idEl.textContent = `Gap #${entry.id}`;
      idEl.style.cssText = 'font-size:12px;font-weight:600;color:#e0e0e0;flex:1';

      const badge = document.createElement('span');
      badge.setAttribute('data-testid', `gap-severity-${entry.id}`);
      badge.textContent = entry.severity;
      badge.style.cssText =
        `font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;` +
        `background:${SEVERITY_COLOURS[entry.severity] ?? '#888'}22;` +
        `color:${SEVERITY_COLOURS[entry.severity] ?? '#888'};` +
        `border:1px solid ${SEVERITY_COLOURS[entry.severity] ?? '#888'}66`;

      const flyBtn = document.createElement('button');
      flyBtn.textContent = 'Fly to';
      flyBtn.setAttribute('data-testid', `fly-to-btn-${entry.id}`);
      flyBtn.style.cssText =
        'font-size:11px;padding:2px 7px;background:#1e1e30;color:#93c5fd;' +
        'border:1px solid #2244aa;border-radius:3px;cursor:pointer';

      const entryRef = entry; // closure
      flyBtn.addEventListener('click', () => {
        api.map.flyTo({
          center: entryRef.centroid,
          zoom:   16,
        });
      });

      headerRow.append(idEl, badge, flyBtn);
      card.appendChild(headerRow);

      // ---- Area row ----
      const areaEl = document.createElement('div');
      areaEl.setAttribute('data-testid', `gap-area-${entry.id}`);
      areaEl.textContent =
        `Area: ${Math.round(entry.areaM2).toLocaleString()} m\u00b2`;
      areaEl.style.cssText = 'font-size:11px;color:#aaa;margin-bottom:4px';
      card.appendChild(areaEl);

      // ---- Suggestion card (if suggestion is present) ----
      if (
        entry.suggestion &&
        entry.suggestion.lat != null &&
        entry.suggestion.lng != null
      ) {
        const sugCard = document.createElement('div');
        sugCard.setAttribute('data-testid', `gap-suggestion-${entry.id}`);
        sugCard.style.cssText =
          'margin-top:4px;padding:5px 8px;background:#0f1a2e;border:1px solid #223355;' +
          'border-radius:3px';

        const sugLabel = document.createElement('div');
        sugLabel.textContent = 'Suggested sensor';
        sugLabel.style.cssText = 'font-size:10px;color:#6688aa;margin-bottom:3px;font-weight:600';

        const sugType = document.createElement('div');
        sugType.textContent =
          `${entry.suggestion.definition?.type ?? 'Unknown'}: ` +
          `${entry.suggestion.definition?.name ?? 'Unknown'}`;
        sugType.style.cssText = 'font-size:11px;color:#e0e0e0;margin-bottom:4px';

        const placeBtn = document.createElement('button');
        placeBtn.textContent = 'Place this';
        placeBtn.setAttribute('data-testid', `place-btn-${entry.id}`);
        placeBtn.style.cssText =
          'font-size:11px;padding:2px 8px;background:#065f46;color:#6ee7b7;' +
          'border:1px solid #059669;border-radius:3px;cursor:pointer';

        placeBtn.addEventListener('click', () => {
          api.bus.emit('placement:pending', {
            lat:        entryRef.suggestion.lat,
            lng:        entryRef.suggestion.lng,
            definition: entryRef.suggestion.definition ?? null,
          });
        });

        sugCard.append(sugLabel, sugType, placeBtn);
        card.appendChild(sugCard);
      }

      listContainer.appendChild(card);
    }
  }

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestSimResults = api.state.get('sim_results'); // OK: initial render only
  latestZones      = api.state.get('zones');        // OK: initial render only

  api.panel.mount(panel);
  _renderList();

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results', (sr) => {
    latestSimResults = sr;
    _renderList();
  }));

  unsubs.push(api.state.watch('zones', (z) => {
    latestZones = z;
    _renderList();
  }));

  // -------------------------------------------------------------------------
  // Bus subscriptions
  // -------------------------------------------------------------------------
  // simulation:complete is declared in manifest subscribes[]; the sim_results
  // state watch drives the actual render.
  unsubs.push(api.bus.on('simulation:complete', () => {}));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
    // No map layers to clean up — this module only navigates via api.map.flyTo.
  });
}
