/**
 * report-configurator/index.js — Report Configurator Module (S14.13).
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Presents a configuration form for the customer PDF report.  Writes form
 * state to `report_config` on every change and reacts to external state
 * updates via watch().  Captures the current map view as a PNG and POSTs
 * everything to /api/report, triggering a browser download of the returned
 * PDF binary.
 *
 * Reads:       sim_results, placements, zones, threat_corridors, report_config
 * Writes:      report_config
 * Emits:       report:generated
 * Subscribes:  (none)
 * Map sources: (none)
 * Map layers:  (none)
 */

// ---------------------------------------------------------------------------
// Sanitisation preview helpers — mirrors sanitise.py logic for client-side preview
// ---------------------------------------------------------------------------

const _RANGE_BANDS = [
  { label: 'Short range', upper: 500 },
  { label: 'Medium range', upper: 2000 },
  { label: 'Long range', upper: Infinity },
];

function _rangeBand(valueM) {
  for (const { label, upper } of _RANGE_BANDS) {
    if (valueM <= upper) return label;
  }
  return 'Long range';
}

// Sample rows shown in the sanitisation preview for Redacted / Full levels.
// These are illustrative examples that mirror sanitise.py's transformation rules.
function _buildPreviewRows(level) {
  if (level === 'none' || level === 'minimal') return null;
  const rows = [
    { field: 'position_lat',      before: '51.2345', after: '51.23' },
    { field: 'max_range_m',       before: '3500',    after: `'${_rangeBand(3500)}'` },
    { field: 'sensor_name',       before: 'Radar-1', after: 'Sensor-1' },
    { field: 'bearing_deg',       before: '135',     after: '[removed]' },
    { field: 'height_override_m', before: '10',      after: '[removed]' },
  ];
  if (level === 'full') {
    rows.push(
      { field: 'path_wgs84',       before: '[present]', after: '[removed]' },
      { field: 'available_time_s', before: '12.3',      after: '[removed]' },
    );
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REPORT_SECTIONS = [
  'Executive Summary', 'Site Overview', 'Coverage Analysis', 'Gap Analysis',
  'Threat Analysis', 'Kill Chain', 'Saturation', 'Comparison',
  'Recommendations', 'Assumptions', 'Appendix',
];

const SANITISATION_LEVELS = [
  { value: 'none',     label: 'None',     desc: 'All data preserved. For internal use only.' },
  { value: 'minimal',  label: 'Minimal',  desc: 'Coordinates rounded to 4 d.p. Specifications intact.' },
  { value: 'redacted', label: 'Redacted', desc: 'Sensor names and ranges generalised. Coordinates rounded.' },
  { value: 'full',     label: 'Full',     desc: 'All of Redacted, plus corridor paths and timing removed.' },
];

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirrors — updated by watch(), used in the POST body (D-379)
  let latestSimResults      = null;
  let latestPlacements      = null;
  let latestZones           = null;
  let latestThreatCorridors = null;
  let latestReportConfig    = null;   // D-379: cache report_config instead of get() at POST time

  // Local module state
  let capturedMapView    = null;
  let capturedLogoDataUrl = null;    // D-376: stores logo as serialisable data URL

  // Guards against the re-entrant watch→set cycle (D-380):
  // when _updateForm is updating DOM from state, _writeConfig must not re-emit.
  let _suppressWrite = false;

  // Tracks preview rows so they can be cleared and rebuilt without DOM children iteration
  const _previewRows = [];

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------
  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0;display:flex;flex-direction:column;height:100%';

  const heading = document.createElement('div');
  heading.textContent = 'Report Configurator';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0;flex-shrink:0';
  panel.appendChild(heading);

  // ---- Configuration form section ----
  const formSection = document.createElement('div');
  formSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';

  function _sectionLabel(text) {
    const el = document.createElement('div');
    el.textContent = text;
    el.style.cssText =
      'font-size:11px;color:#8888aa;margin-bottom:4px;font-weight:600;' +
      'text-transform:uppercase;letter-spacing:0.06em';
    return el;
  }

  // Client name
  formSection.appendChild(_sectionLabel('Client Name'));

  const nameInput = document.createElement('input');
  nameInput.setAttribute('type', 'text');
  nameInput.setAttribute('data-testid', 'client-name-input');
  nameInput.setAttribute('placeholder', 'Enter client name\u2026');
  nameInput.style.cssText =
    'width:100%;box-sizing:border-box;padding:5px 8px;background:#12121e;' +
    'border:1px solid #2a2a4a;border-radius:3px;color:#e0e0e0;font-size:13px;margin-bottom:10px';
  formSection.appendChild(nameInput);

  // Logo upload
  formSection.appendChild(_sectionLabel('Client Logo'));

  const logoInput = document.createElement('input');
  logoInput.setAttribute('type', 'file');
  logoInput.setAttribute('accept', 'image/*');
  logoInput.setAttribute('data-testid', 'logo-input');
  logoInput.style.cssText = 'width:100%;font-size:12px;color:#aaa;margin-bottom:10px';
  formSection.appendChild(logoInput);

  // Sanitisation level
  formSection.appendChild(_sectionLabel('Sanitisation Level'));

  const sanitSelect = document.createElement('select');
  sanitSelect.setAttribute('data-testid', 'sanitisation-select');
  sanitSelect.style.cssText =
    'width:100%;padding:5px 8px;background:#12121e;border:1px solid #2a2a4a;' +
    'border-radius:3px;color:#e0e0e0;font-size:13px;margin-bottom:4px';
  for (const { value, label } of SANITISATION_LEVELS) {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    sanitSelect.appendChild(opt);
  }
  formSection.appendChild(sanitSelect);

  const sanitDesc = document.createElement('div');
  sanitDesc.setAttribute('data-testid', 'sanitisation-desc');
  sanitDesc.style.cssText = 'font-size:11px;color:#666;margin-bottom:10px;font-style:italic';
  formSection.appendChild(sanitDesc);

  // Report sections checklist
  formSection.appendChild(_sectionLabel('Report Sections'));

  const sectionCheckboxes = {};
  for (const section of REPORT_SECTIONS) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:4px';

    const cb = document.createElement('input');
    cb.setAttribute('type', 'checkbox');
    const sectionKey = section.toLowerCase().replace(/ /g, '_');
    cb.setAttribute('data-testid', `section-${sectionKey}`);
    cb.checked = true;

    const lbl = document.createElement('label');
    lbl.textContent = section;
    lbl.style.cssText = 'font-size:12px;color:#ccc;cursor:pointer';

    row.append(cb, lbl);
    formSection.appendChild(row);
    sectionCheckboxes[section] = cb;
  }

  panel.appendChild(formSection);

  // ---- Sanitisation preview section ----
  const previewSection = document.createElement('div');
  previewSection.setAttribute('data-testid', 'sanitisation-preview');
  previewSection.style.cssText =
    'display:none;padding:8px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';
  previewSection.style.display = 'none'; // explicit for mock DOM compatibility

  const previewHeading = document.createElement('div');
  previewHeading.textContent = 'Sanitisation Preview';
  previewHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  previewSection.appendChild(previewHeading);

  const previewTable = document.createElement('table');
  previewTable.setAttribute('data-testid', 'preview-table');
  previewTable.style.cssText =
    'border-collapse:collapse;width:100%;font-size:11px;font-family:monospace';

  const previewHeaderRow = document.createElement('tr');
  for (const h of ['Field', 'Before', 'After']) {
    const th = document.createElement('th');
    th.textContent = h;
    th.style.cssText =
      'text-align:left;padding:2px 6px;color:#8888aa;font-weight:600;border-bottom:1px solid #2a2a4a';
    previewHeaderRow.appendChild(th);
  }
  previewTable.appendChild(previewHeaderRow);
  previewSection.appendChild(previewTable);
  panel.appendChild(previewSection);

  // ---- Map capture section ----
  const captureSection = document.createElement('div');
  captureSection.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30;flex-shrink:0';

  captureSection.appendChild(_sectionLabel('Map View'));

  const captureBtn = document.createElement('button');
  captureBtn.textContent = 'Capture Map View';
  captureBtn.setAttribute('data-testid', 'capture-btn');
  captureBtn.style.cssText =
    'width:100%;padding:6px 14px;background:#12121e;color:#ccc;' +
    'border:1px solid #2a2a4a;border-radius:3px;cursor:pointer;font-size:12px;margin-bottom:8px';
  captureSection.appendChild(captureBtn);

  const captureStatus = document.createElement('div');
  captureStatus.setAttribute('data-testid', 'capture-status');
  captureStatus.style.cssText = 'display:none;font-size:11px;padding:2px 0;margin-bottom:4px';
  captureStatus.style.display = 'none'; // explicit for mock DOM compatibility
  captureSection.appendChild(captureStatus);

  const thumbnailWrap = document.createElement('div');
  thumbnailWrap.setAttribute('data-testid', 'thumbnail-wrap');
  thumbnailWrap.style.cssText = 'display:none;margin-top:4px';
  thumbnailWrap.style.display = 'none'; // explicit for mock DOM compatibility

  const thumbnail = document.createElement('img');
  thumbnail.setAttribute('data-testid', 'map-thumbnail');
  thumbnail.style.cssText =
    'width:100%;border:1px solid #2a2a4a;border-radius:3px;max-height:80px;object-fit:cover';
  thumbnailWrap.appendChild(thumbnail);
  captureSection.appendChild(thumbnailWrap);
  panel.appendChild(captureSection);

  // ---- Generate section ----
  const generateSection = document.createElement('div');
  generateSection.style.cssText = 'padding:10px 12px;flex-shrink:0';

  const generateBtn = document.createElement('button');
  generateBtn.textContent = 'Generate Report';
  generateBtn.setAttribute('data-testid', 'generate-btn');
  generateBtn.style.cssText =
    'width:100%;padding:8px 14px;background:#0f3460;color:#fff;' +
    'border:1px solid #2266aa;border-radius:3px;cursor:pointer;font-size:13px;font-weight:600;margin-bottom:8px';
  generateSection.appendChild(generateBtn);

  const spinner = document.createElement('div');
  spinner.setAttribute('data-testid', 'generate-spinner');
  spinner.textContent = 'Generating report\u2026';
  spinner.style.cssText = 'display:none;font-size:12px;color:#aaa;text-align:center;padding:4px';
  spinner.style.display = 'none'; // explicit for mock DOM compatibility
  generateSection.appendChild(spinner);

  const statusEl = document.createElement('div');
  statusEl.setAttribute('data-testid', 'generate-status');
  statusEl.style.cssText = 'display:none;font-size:12px;padding:4px 0';
  statusEl.style.display = 'none'; // explicit for mock DOM compatibility
  generateSection.appendChild(statusEl);

  panel.appendChild(generateSection);

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function _currentConfig() {
    const include_modules = {};
    for (const [name, cb] of Object.entries(sectionCheckboxes)) {
      include_modules[name] = cb.checked;
    }
    return {
      client_name:    nameInput.value,
      logo_path:      capturedLogoDataUrl,   // D-376: data URL or null
      sanitise_level: sanitSelect.value,
      include_modules,
    };
  }

  function _writeConfig() {
    if (_suppressWrite) return;   // D-380: guard against re-entrant watch→set cycle
    api.state.set('report_config', _currentConfig());
  }

  function _updateSanitDescription(level) {
    const entry = SANITISATION_LEVELS.find(l => l.value === level);
    sanitDesc.textContent = entry ? entry.desc : '';
  }

  function _updatePreview(level) {
    for (const row of _previewRows) {
      previewTable.removeChild(row);
    }
    _previewRows.length = 0;

    const rows = _buildPreviewRows(level);
    if (!rows) {
      previewSection.style.display = 'none';
      return;
    }
    previewSection.style.display = 'block';
    for (const { field, before, after } of rows) {
      const tr = document.createElement('tr');
      for (const val of [field, before, after]) {
        const td = document.createElement('td');
        td.textContent = val;
        td.style.cssText =
          'padding:2px 6px;color:' + (val === '[removed]' ? '#f87171' : '#aaa');
        tr.appendChild(td);
      }
      previewTable.appendChild(tr);
      _previewRows.push(tr);
    }
  }

  // Update form DOM from a config object — sets _suppressWrite to prevent
  // the re-entrant watch→set cycle (D-380). Does NOT call _writeConfig itself.
  function _updateForm(config) {
    if (!config || typeof config !== 'object') return;
    _suppressWrite = true;
    try {
      if (typeof config.client_name === 'string') nameInput.value = config.client_name;
      const logoVal = config.logo_path ?? config.logo;
      if (typeof logoVal === 'string') capturedLogoDataUrl = logoVal;
      else if (logoVal === null) capturedLogoDataUrl = null;
      const sanitLevel = config.sanitise_level ?? config.sanitisation_level;
      if (typeof sanitLevel === 'string') {
        sanitSelect.value = sanitLevel;
        _updateSanitDescription(sanitLevel);
        _updatePreview(sanitLevel);
      }
      const modulesObj = config.include_modules ?? config.sections;
      if (modulesObj && typeof modulesObj === 'object') {
        for (const [name, cb] of Object.entries(sectionCheckboxes)) {
          if (typeof modulesObj[name] === 'boolean') cb.checked = modulesObj[name];
        }
      }
    } finally {
      _suppressWrite = false;
    }
  }

  // -------------------------------------------------------------------------
  // Form event listeners — each input change writes the full config to state
  // -------------------------------------------------------------------------

  nameInput.addEventListener('input', _writeConfig);

  // D-376: Read logo file as a serialisable data URL before writing to state
  logoInput.addEventListener('change', () => {
    const file = logoInput.files?.[0] ?? null;
    if (!file) {
      capturedLogoDataUrl = null;
      _writeConfig();
      return;
    }
    if (typeof FileReader === 'undefined') {
      // FileReader unavailable in this environment — logo not stored
      capturedLogoDataUrl = null;
      _writeConfig();
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      capturedLogoDataUrl = typeof e.target?.result === 'string' ? e.target.result : null;
      _writeConfig();
    };
    reader.onerror = () => {
      console.warn('[report-configurator] failed to read logo file');
      capturedLogoDataUrl = null;
      _writeConfig();
    };
    reader.readAsDataURL(file);
  });

  sanitSelect.addEventListener('change', () => {
    _updateSanitDescription(sanitSelect.value);
    _updatePreview(sanitSelect.value);
    _writeConfig();
  });

  for (const cb of Object.values(sectionCheckboxes)) {
    cb.addEventListener('change', _writeConfig);
  }

  // -------------------------------------------------------------------------
  // Capture map view
  // -------------------------------------------------------------------------

  captureBtn.addEventListener('click', () => {
    try {
      const canvas = api.map.getCanvas();
      const dataUrl = canvas.toDataURL('image/png');
      capturedMapView = dataUrl;
      thumbnail.src = dataUrl;
      thumbnailWrap.style.display = 'block';
      captureStatus.style.display = 'none';
    } catch (err) {
      // D-377: surface capture failure so operator knows the map view is missing
      console.warn('[report-configurator] map capture failed:', err.message);
      capturedMapView = null;
      captureStatus.textContent = '\u26a0 Map capture failed \u2014 report will not include a map figure.';
      captureStatus.style.color = '#fcd34d';
      captureStatus.style.display = 'block';
    }
  });

  // -------------------------------------------------------------------------
  // Generate report (async)
  // -------------------------------------------------------------------------

  async function _generateReport() {
    generateBtn.disabled = true;
    spinner.style.display = 'block';
    statusEl.style.display = 'none';

    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = `salus-report-${dateStr}.pdf`;

    try {
      const response = await fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report_config:    latestReportConfig,   // D-379: use cached mirror, not get()
          sim_results:      latestSimResults,
          placements:       latestPlacements,
          zones:            latestZones,
          threat_corridors: latestThreatCorridors,
          map_screenshot:   capturedMapView,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: HTTP ${response.status}`);
      }

      const blob = await response.blob();

      // D-378: reject an empty response body before the download fires
      if (blob.size === 0) {
        throw new Error('Server returned an empty response \u2014 report generation may have failed.');
      }

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      panel.appendChild(a);
      a.click();
      panel.removeChild(a);
      // Defer revoke one tick so the browser download manager can begin reading the URL
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);

      spinner.style.display = 'none';
      statusEl.textContent = '\u2713 Report downloaded: ' + filename;
      statusEl.style.color = '#4ade80';
      statusEl.style.display = 'block';

      api.bus.emit('report:generated', { filename });
    } catch (err) {
      spinner.style.display = 'none';
      statusEl.textContent = '\u2717 ' + err.message;
      statusEl.style.color = '#f87171';
      statusEl.style.display = 'block';
    } finally {
      generateBtn.disabled = false;
    }
  }

  generateBtn.addEventListener('click', () => {
    _generateReport().catch((err) => {
      console.error('[report-configurator] unhandled error in _generateReport:', err);
    });
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestSimResults      = api.state.get('sim_results');       // OK: initial render only
  latestPlacements      = api.state.get('placements');        // OK: initial render only
  latestZones           = api.state.get('zones');             // OK: initial render only
  latestThreatCorridors = api.state.get('threat_corridors');  // OK: initial render only
  latestReportConfig    = api.state.get('report_config');     // OK: initial render only (D-379)

  sanitSelect.value = 'none';
  _updateSanitDescription('none');

  const initialConfig = latestReportConfig;
  if (initialConfig) _updateForm(initialConfig);

  api.panel.mount(panel);

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('sim_results',      (v) => { latestSimResults      = v; }));
  unsubs.push(api.state.watch('placements',       (v) => { latestPlacements      = v; }));
  unsubs.push(api.state.watch('zones',            (v) => { latestZones           = v; }));
  unsubs.push(api.state.watch('threat_corridors', (v) => { latestThreatCorridors = v; }));
  unsubs.push(api.state.watch('report_config',    (v) => {
    latestReportConfig = v;       // D-379: keep mirror current
    _updateForm(v);
  }));

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
  });
}
