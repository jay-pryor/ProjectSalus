/**
 * terrain-loader/index.js — Terrain Loader module (S14.3).
 *
 * Responsibilities (per InterfaceArchitecture.md §4.1):
 *   - Accept a DEM (and optional DSM) GeoTIFF file from the user.
 *   - POST the file to POST /api/terrain/load, which runs the existing
 *     Python GDAL pipeline and returns terrain metadata.
 *   - Poll GET /api/terrain/tile-progress SSE during tile generation.
 *   - Write the metadata to state key 'terrain' (this module's only write).
 *   - Emit 'terrain:loaded' to unlock prerequisite-gated navigation buttons.
 *   - Add the raster-dem source and hillshade layer to the map canvas.
 *   - Set the 3D terrain source via the architectural exception
 *     api.map.setTerrainSource() (only terrain-loader receives this method).
 *
 * Isolation invariants observed:
 *   - No cross-module imports (MUST Rule 1).
 *   - All external access goes through the injected api object (MUST Rule 2).
 *   - Exactly { init(api) } exported (MUST Rule 3).
 *   - Only 'terrain' written; only declared events emitted (MUST Rules 4, 10).
 *   - Every watch() and map listener paired with unsubscribe in onUnmount (MUST 9, 15).
 */

// API_BASE is resolved inside init() from the execution environment to avoid
// module-level window.* access (D-329: isolation invariant — no globals outside init).

// ---------------------------------------------------------------------------
// Panel HTML template (mirrors panel.html — both files must stay in sync)
// ---------------------------------------------------------------------------

const PANEL_HTML = `
<div id="terrain-loader-panel" class="module-panel">
  <h2 class="panel-title">Load Terrain</h2>
  <div class="form-group">
    <label for="tl-dem-input" class="form-label">DEM file <span class="ext-hint">(.tif / .tiff)</span></label>
    <input type="file" id="tl-dem-input" accept=".tif,.tiff" class="file-input">
  </div>
  <div class="form-group">
    <label for="tl-dsm-input" class="form-label">DSM file <span class="ext-hint">(optional)</span></label>
    <input type="file" id="tl-dsm-input" accept=".tif,.tiff" class="file-input">
  </div>
  <div id="tl-crs-display" class="field-display" hidden>
    <span class="field-label">CRS:</span>
    <span id="tl-crs-value" class="field-value">—</span>
  </div>
  <div id="tl-progress-section" class="progress-section" hidden>
    <p id="tl-status-msg" class="status-msg">Processing…</p>
    <progress id="tl-progress-bar" class="progress-bar" max="100" value="0"></progress>
  </div>
  <div id="tl-summary" class="summary-section" hidden>
    <h3 class="summary-title">Loaded Terrain</h3>
    <div class="summary-row"><span class="summary-label">CRS EPSG:</span><span id="tl-sum-crs" class="summary-value">—</span></div>
    <div class="summary-row"><span class="summary-label">Resolution:</span><span id="tl-sum-res" class="summary-value">—</span></div>
    <div class="summary-row"><span class="summary-label">Bounds (WGS84):</span><span id="tl-sum-bounds" class="summary-value">—</span></div>
    <div class="summary-row"><span class="summary-label">Tiles:</span><span id="tl-sum-tiles" class="summary-value">—</span></div>
  </div>
  <p id="tl-error-msg" class="error-msg" hidden></p>
</div>
`;

// ---------------------------------------------------------------------------
// Map layer constants
// ---------------------------------------------------------------------------

const SOURCE_ID = 'terrain-loader:terrain-dem';
const HILLSHADE_LAYER_ID = 'terrain-loader:hillshade';

// ---------------------------------------------------------------------------
// Module entry point (MUST Rule 3: exactly { init(api) } exported)
// ---------------------------------------------------------------------------

export function init(api) {
  console.log('[terrain-loader]: init');

  // Resolve API base URL inside init() to satisfy Invariant 1 (no module-level
  // window.* access — D-329).  Empty string ('') for Node.js test environments.
  const apiBase =
    typeof window !== 'undefined' && window.location
      ? window.location.origin
      : '';

  // Build panel DOM from template
  const tmp = document.createElement('div');
  tmp.innerHTML = PANEL_HTML;
  const panel = tmp.firstElementChild;

  api.panel.mount(panel);

  // Wire DEM file input — async load triggered by user file selection
  const demInput = panel.querySelector('#tl-dem-input');
  const dsmInput = panel.querySelector('#tl-dsm-input');

  function handleDemChange() {
    const demFile = demInput.files && demInput.files[0];
    if (!demFile) return;
    const dsmFile = (dsmInput.files && dsmInput.files[0]) || null;
    _loadTerrain(api, panel, demFile, dsmFile, apiBase).catch((err) => {
      console.error('[terrain-loader] Unhandled terrain load error:', err);
    });
  }

  demInput.addEventListener('change', handleDemChange);

  // Initial read — render summary if terrain already loaded (e.g. after remount).
  // Map layer operations are also re-applied so the canvas stays consistent.
  // This is an approved one-time initial read; reactive updates go through watch().
  const existing = api.state.get('terrain'); // initial read
  if (existing) {
    _updateSummary(panel, existing);
    _applyMapLayers(api, existing, apiBase);
  }

  // Reactive summary — all future terrain state changes re-render the summary
  // (MUST Rule 8: all UI that reacts to state changes driven by watch).
  const unwatchTerrain = api.state.watch('terrain', (terrain) => {
    _updateSummary(panel, terrain);
  });

  // Cleanup on deactivation (MUST Rules 9 and 15)
  api.panel.onUnmount(() => {
    demInput.removeEventListener('change', handleDemChange);
    unwatchTerrain(); // paired with api.state.watch above (MUST Rule 9)
    _cleanupMapLayers(api);
  });
}

// ---------------------------------------------------------------------------
// Terrain loading pipeline
// ---------------------------------------------------------------------------

/**
 * POST the selected DEM (and optional DSM) to /api/terrain/load.
 * Polls SSE tile-progress, then writes state and adds map layers.
 *
 * @param {object} api - injected module API
 * @param {HTMLElement} panel - the mounted panel element
 * @param {File} demFile - selected DEM GeoTIFF
 * @param {File|null} dsmFile - optional DSM GeoTIFF
 * @param {string} apiBase - API base URL (resolved inside init — D-329)
 * @returns {Promise<void>}
 */
async function _loadTerrain(api, panel, demFile, dsmFile, apiBase) {
  const progressSection = panel.querySelector('#tl-progress-section');
  const statusMsg = panel.querySelector('#tl-status-msg');
  const progressBar = panel.querySelector('#tl-progress-bar');
  const errorMsg = panel.querySelector('#tl-error-msg');
  const summarySection = panel.querySelector('#tl-summary');

  // Reset UI state
  if (progressSection) progressSection.hidden = false;
  if (summarySection) summarySection.hidden = true;
  if (errorMsg) { errorMsg.hidden = true; errorMsg.textContent = ''; }
  if (statusMsg) statusMsg.textContent = 'Uploading terrain file…';
  if (progressBar) progressBar.value = 0;

  try {
    // Build multipart form
    const formData = new FormData();
    formData.append('dem_file', demFile);
    if (dsmFile) formData.append('dsm_file', dsmFile);

    // POST to backend
    const resp = await fetch(`${apiBase}/api/terrain/load`, {
      method: 'POST',
      body: formData,
    });

    if (!resp.ok) {
      let errDetail = `Server error ${resp.status}`;
      try {
        const body = await resp.json();
        errDetail = body.detail || body.error || errDetail;
      } catch {
        // ignore JSON parse failure on error response
      }
      throw new Error(errDetail);
    }

    const metadata = await resp.json();

    // Poll tile generation progress
    if (statusMsg) statusMsg.textContent = 'Generating terrain tiles…';
    await _pollTileProgress(panel, apiBase);

    // Write terrain state — watch() callback updates summary (MUST Rule 8).
    // Do NOT call api.state.get('terrain') after this set (MUST Rule 7).
    api.state.set('terrain', metadata);

    // Emit terrain:loaded — unlocks prerequisite-gated module buttons
    api.bus.emit('terrain:loaded', {});

    // Apply map layers using the local metadata variable (not re-read from state)
    _applyMapLayers(api, metadata, apiBase);

    // Fly to terrain bounds
    if (metadata.bounds_wgs84) {
      const [west, south, east, north] = metadata.bounds_wgs84;
      api.map.fitBounds([[west, south], [east, north]], { padding: 40 });
    }

    if (progressSection) progressSection.hidden = true;

  } catch (err) {
    console.error('[terrain-loader] Failed to load terrain:', err);
    if (progressSection) progressSection.hidden = true;
    if (errorMsg) {
      errorMsg.hidden = false;
      errorMsg.textContent = `Error: ${err.message}`;
    }
  }
}

// ---------------------------------------------------------------------------
// Tile progress SSE
// ---------------------------------------------------------------------------

/**
 * Subscribe to GET /api/terrain/tile-progress SSE and resolve when complete.
 *
 * @param {HTMLElement} panel
 * @param {string} apiBase - API base URL (resolved inside init — D-329)
 * @returns {Promise<void>}
 */
function _pollTileProgress(panel, apiBase) {
  return new Promise((resolve, reject) => {
    const progressBar = panel.querySelector('#tl-progress-bar');
    const statusMsg = panel.querySelector('#tl-status-msg');

    const es = new EventSource(`${apiBase}/api/terrain/tile-progress`);

    es.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // ignore malformed SSE event
      }

      if (data.type === 'progress') {
        const pct = data.pct ?? 0;
        if (progressBar) progressBar.value = pct;
        if (statusMsg) statusMsg.textContent = `Generating tiles… ${pct}%`;
      } else if (data.type === 'complete') {
        if (progressBar) progressBar.value = 100;
        if (statusMsg) statusMsg.textContent = 'Tiles ready.';
        es.close();
        resolve();
      } else if (data.type === 'error') {
        es.close();
        reject(new Error(data.message || 'Tile generation failed'));
      }
    };

    es.onerror = () => {
      es.close();
      reject(new Error('SSE connection error during tile generation'));
    };
  });
}

// ---------------------------------------------------------------------------
// Map layer operations
// ---------------------------------------------------------------------------

/**
 * Add the raster-dem source, set 3D terrain, and add the hillshade layer.
 * Cleans up existing layers first to handle remount safely.
 *
 * Note: map layer operations are NOT driven by api.state.watch because they
 * are imperative calls — re-adding a source that already exists would throw.
 * Instead they are called explicitly after set() and on initial read.
 *
 * @param {object} api - injected module API
 * @param {object} terrain - terrain metadata from state
 * @param {string} apiBase - API base URL (resolved inside init — D-329)
 */
function _applyMapLayers(api, terrain, apiBase) {
  if (!terrain || !terrain.tile_url_template) return;

  // Remove any existing layers before (re-)adding, so remount is idempotent
  _cleanupMapLayers(api);

  const tileUrl = apiBase + terrain.tile_url_template;

  // Add raster-dem source (MUST Rule 13: ID prefixed with layer_id_prefix)
  api.map.addSource(SOURCE_ID, {
    type: 'raster-dem',
    tiles: [tileUrl],
    tileSize: 256,
    minzoom: terrain.terrain_min_zoom,
    maxzoom: terrain.terrain_max_zoom,
    encoding: 'terrarium',
  });

  // Set 3D terrain canvas via architectural exception method (S14.3-3).
  // setTerrainSource is available ONLY on the terrain-loader's map proxy.
  // MUST Rule 14 permits this specific exception; all other modules must not
  // call setTerrain() or obtain the raw map reference.
  if (typeof api.map.setTerrainSource === 'function') {
    api.map.setTerrainSource(SOURCE_ID);
  }

  // Add hillshade layer for depth cues (MUST Rule 13: prefixed ID)
  api.map.addLayer({
    id: HILLSHADE_LAYER_ID,
    type: 'hillshade',
    source: SOURCE_ID,
    paint: {
      'hillshade-shadow-color': '#473B24',
      'hillshade-exaggeration': 0.5,
    },
  });
}

/**
 * Remove the hillshade layer and terrain-dem source from the map canvas.
 * Also clears the 3D terrain property if setTerrainSource is available.
 * Called in onUnmount (MUST Rule 15: all map layers cleaned up).
 *
 * @param {object} api - injected module API
 */
function _cleanupMapLayers(api) {
  // Remove hillshade layer
  try {
    if (api.map.getLayer(HILLSHADE_LAYER_ID)) {
      api.map.removeLayer(HILLSHADE_LAYER_ID);
    }
  } catch (err) {
    console.warn('[terrain-loader] removeLayer failed:', err);
  }

  // Remove raster-dem source and clear 3D terrain canvas together.
  // setTerrainSource(null) is only called when the source actually existed —
  // this avoids a spurious null-clear when _cleanupMapLayers is called before
  // any layers have been added (e.g. on the first call inside _applyMapLayers).
  try {
    if (api.map.getSource(SOURCE_ID)) {
      api.map.removeSource(SOURCE_ID);
      if (typeof api.map.setTerrainSource === 'function') {
        api.map.setTerrainSource(null);
      }
    }
  } catch (err) {
    console.warn('[terrain-loader] removeSource / setTerrainSource(null) failed:', err);
  }
}

// ---------------------------------------------------------------------------
// Panel summary rendering
// ---------------------------------------------------------------------------

/**
 * Update the panel summary section from terrain state.
 * Called from the api.state.watch('terrain') callback.
 *
 * @param {HTMLElement} panel
 * @param {object|null} terrain
 */
function _updateSummary(panel, terrain) {
  const summarySection = panel.querySelector('#tl-summary');
  if (!summarySection) return;

  if (!terrain) {
    summarySection.hidden = true;
    return;
  }

  summarySection.hidden = false;

  const crsDisplay = panel.querySelector('#tl-crs-display');
  if (crsDisplay) crsDisplay.hidden = false;

  const crsValue = panel.querySelector('#tl-crs-value');
  if (crsValue) crsValue.textContent = terrain.crs_epsg ? `EPSG:${terrain.crs_epsg}` : 'Unknown';

  const sumCrs = panel.querySelector('#tl-sum-crs');
  if (sumCrs) sumCrs.textContent = terrain.crs_epsg ? `EPSG:${terrain.crs_epsg}` : 'Unknown';

  const sumRes = panel.querySelector('#tl-sum-res');
  if (sumRes) {
    sumRes.textContent = terrain.resolution_m != null
      ? `${terrain.resolution_m.toFixed(1)} m`
      : '—';
  }

  const sumBounds = panel.querySelector('#tl-sum-bounds');
  if (sumBounds && Array.isArray(terrain.bounds_wgs84)) {
    const [w, s, e, n] = terrain.bounds_wgs84;
    sumBounds.textContent =
      `${s.toFixed(4)}°N, ${w.toFixed(4)}°E  →  ${n.toFixed(4)}°N, ${e.toFixed(4)}°E`;
  }

  const sumTiles = panel.querySelector('#tl-sum-tiles');
  if (sumTiles) {
    sumTiles.textContent = terrain.terrain_tile_count != null
      ? `${terrain.terrain_tile_count} tiles (zoom ${terrain.terrain_min_zoom}–${terrain.terrain_max_zoom})`
      : '—';
  }
}
