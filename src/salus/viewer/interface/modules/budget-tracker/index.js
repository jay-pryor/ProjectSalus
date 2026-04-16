/**
 * budget-tracker/index.js — Procurement cost tracker and constraint setter.
 *
 * Architecture: docs/Technical/InterfaceArchitecture.md §2.6
 *
 * Reads:       placements, sensor_library, effector_library
 * Writes:      constraints
 * Emits:       constraint:updated
 * Subscribes:  placement:added, placement:removed
 *
 * This is a pure panel module — no map sources or layers are added.
 *
 * The constraints key is the integration point with the Optimiser module:
 *   { max_cost_aud, allowed_sensor_ids, max_sensors, max_effectors }
 * Written on every budget/limit input change and on init.
 */

/** Escape a value for RFC-4180 CSV output. */
function _csvField(v) {
  const s = String(v ?? '');
  return (s.includes(',') || s.includes('"') || s.includes('\n'))
    ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Format a number as a plain AUD string. */
function _fmtAud(n) {
  return `$${Number(n ?? 0).toLocaleString()}`;
}

/**
 * Build a lookup map from both libraries: name → { cost_aud, type, isEffector }.
 * Sensor library entries are marked isEffector:false; effector library entries true.
 */
function _buildLookupMap(sensorLib, effectorLib) {
  const map = new Map();
  function addLib(lib, isEffector) {
    if (!lib || typeof lib !== 'object' || Array.isArray(lib)) return;
    for (const items of Object.values(lib)) {
      // D-336: guard against non-array category values which would throw TypeError in for...of
      for (const item of (Array.isArray(items) ? items : [])) {
        if (item && item.name) {
          map.set(item.name, {
            // D-333: use Number() || 0 not ?? 0 — catches string cost_aud values that ?? passes
            cost_aud: Number(item.cost_aud) || 0,
            type: item.type ?? '',
            isEffector,
          });
        }
      }
    }
  }
  addLib(sensorLib, false);
  addLib(effectorLib, true);
  return map;
}

/**
 * Group placements into breakdown rows by sensor_name.
 * Returns array of { name, type, cost_aud, count, isEffector }.
 * Falls back to definition.name if sensor_name is absent.
 */
function _calcBreakdown(placements, lookupMap) {
  const byName = new Map();
  for (const p of (placements ?? [])) {
    const name = p.sensor_name ?? p.definition?.name ?? '(unknown)';
    if (!byName.has(name)) {
      const info = lookupMap.get(name) ?? {
        // D-333: Number() || 0 to handle string cost_aud from raw definition
        cost_aud: Number(p.definition?.cost_aud) || 0,
        type: p.definition?.type ?? '',
        isEffector: false,
      };
      byName.set(name, {
        name,
        type: info.type,
        cost_aud: info.cost_aud,
        count: 0,
        isEffector: info.isEffector,
      });
    }
    byName.get(name).count++;
  }
  return [...byName.values()];
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

export function init(api) {
  const unsubs = [];

  // Local mirrors — avoids cross-key get() inside watch() callbacks
  // (prevents stale reads if multiple keys update in rapid succession)
  let latestPlacements = null;
  let latestSensors = null;
  let latestEffectors = null;

  // Panel-level user inputs
  let budget = 0;       // AUD, 0 = no budget limit
  let maxSensors = null;    // null = unlimited
  let maxEffectors = null;  // null = unlimited

  // -------------------------------------------------------------------------
  // Panel DOM construction
  // -------------------------------------------------------------------------

  const panel = document.createElement('div');
  panel.style.cssText = 'overflow-y:auto;padding:0';

  // Heading
  const heading = document.createElement('div');
  heading.textContent = 'Budget Tracker';
  heading.style.cssText =
    'padding:10px 12px;font-size:14px;font-weight:600;' +
    'border-bottom:1px solid #252540;color:#e0e0e0';
  panel.appendChild(heading);

  // ---- Budget input ----
  const budgetRow = document.createElement('div');
  budgetRow.style.cssText = 'padding:10px 12px;border-bottom:1px solid #1e1e30';

  const budgetLabel = document.createElement('label');
  budgetLabel.textContent = 'Budget (AUD)';
  budgetLabel.style.cssText = 'font-size:12px;color:#aaa;display:block;margin-bottom:4px';
  budgetRow.appendChild(budgetLabel);

  const budgetInput = document.createElement('input');
  budgetInput.type = 'number';
  budgetInput.setAttribute('min', '0');
  budgetInput.setAttribute('placeholder', '0');
  budgetInput.setAttribute('data-testid', 'budget-input');
  budgetInput.style.cssText =
    'width:100%;box-sizing:border-box;padding:5px 8px;background:#0f0f1e;' +
    'border:1px solid #333;color:#e0e0e0;border-radius:3px;font-size:13px';
  budgetRow.appendChild(budgetInput);
  panel.appendChild(budgetRow);

  // ---- Progress bar ----
  const progressWrap = document.createElement('div');
  progressWrap.style.cssText =
    'margin:8px 12px 4px;background:#1e1e30;border-radius:3px;overflow:hidden;height:12px';

  const progressFill = document.createElement('div');
  progressFill.setAttribute('data-testid', 'budget-progress-fill');
  progressFill.style.cssText =
    'height:100%;width:0%;background:#22c55e;transition:width 0.2s,background 0.2s;border-radius:3px';
  progressWrap.appendChild(progressFill);
  panel.appendChild(progressWrap);

  const costLabel = document.createElement('div');
  costLabel.setAttribute('data-testid', 'cost-label');
  costLabel.style.cssText = 'padding:2px 12px 6px;font-size:12px;color:#aaa';
  costLabel.textContent = 'Cost: $0 / No budget set';
  panel.appendChild(costLabel);

  // ---- Over-budget warning banner ----
  const warningBanner = document.createElement('div');
  warningBanner.setAttribute('data-testid', 'over-budget-warning');
  warningBanner.style.cssText =
    'display:none;margin:4px 12px;padding:6px 10px;background:#7f1d1d;' +
    'color:#fca5a5;border-radius:3px;font-size:12px;font-weight:600';
  warningBanner.textContent = '\u26a0 Over budget';
  panel.appendChild(warningBanner);

  // ---- Constraint inputs: max sensors / max effectors ----
  const constraintsRow = document.createElement('div');
  constraintsRow.style.cssText =
    'padding:8px 12px;border-top:1px solid #1e1e30;border-bottom:1px solid #1e1e30;' +
    'display:flex;gap:12px;align-items:flex-start';

  function _makeConstraintField(labelText, testIdInput, testIdIndicator) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'flex:1';

    const lbl = document.createElement('label');
    lbl.textContent = labelText;
    lbl.style.cssText = 'font-size:11px;color:#aaa;display:block;margin-bottom:3px';

    const inp = document.createElement('input');
    inp.type = 'number';
    inp.setAttribute('min', '1');
    inp.setAttribute('placeholder', '\u2014');
    inp.setAttribute('data-testid', testIdInput);
    inp.style.cssText =
      'width:100%;box-sizing:border-box;padding:4px 6px;background:#0f0f1e;' +
      'border:1px solid #333;color:#e0e0e0;border-radius:3px;font-size:12px';

    const indicator = document.createElement('span');
    indicator.setAttribute('data-testid', testIdIndicator);
    indicator.style.cssText = 'font-size:11px;display:block;margin-top:2px;min-height:14px';

    wrap.append(lbl, inp, indicator);
    return { wrap, inp, indicator };
  }

  const {
    wrap: sensorsWrap,
    inp: maxSensorsInput,
    indicator: sensorIndicator,
  } = _makeConstraintField('Max sensors', 'max-sensors-input', 'sensor-limit-indicator');

  const {
    wrap: effectorsWrap,
    inp: maxEffectorsInput,
    indicator: effectorIndicator,
  } = _makeConstraintField('Max effectors', 'max-effectors-input', 'effector-limit-indicator');

  constraintsRow.append(sensorsWrap, effectorsWrap);
  panel.appendChild(constraintsRow);

  // ---- Breakdown table ----
  const tableWrap = document.createElement('div');
  tableWrap.style.cssText = 'padding:8px 12px';

  const tableHeading = document.createElement('div');
  tableHeading.textContent = 'Breakdown';
  tableHeading.style.cssText =
    'font-size:11px;font-weight:600;color:#8888aa;margin-bottom:6px;' +
    'text-transform:uppercase;letter-spacing:0.06em';
  tableWrap.appendChild(tableHeading);

  const table = document.createElement('table');
  table.style.cssText = 'border-collapse:collapse;width:100%;font-size:12px';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const col of ['Name', 'Type', 'Qty', 'Unit Cost', 'Subtotal']) {
    const th = document.createElement('th');
    th.textContent = col;
    th.style.cssText =
      'text-align:left;padding:2px 6px 4px;color:#6b7280;font-weight:600;white-space:nowrap';
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  panel.appendChild(tableWrap);

  // ---- CSV export button ----
  const csvBtn = document.createElement('button');
  csvBtn.textContent = 'Export BOM (CSV)';
  csvBtn.setAttribute('data-testid', 'csv-export-btn');
  csvBtn.style.cssText =
    'margin:4px 12px 12px;padding:5px 14px;background:#0f3460;color:#fff;' +
    'border:1px solid #2266aa;border-radius:3px;cursor:pointer;font-size:12px;display:block';
  panel.appendChild(csvBtn);

  // -------------------------------------------------------------------------
  // Constraint writer — called on any input change and on init
  // -------------------------------------------------------------------------

  function _writeConstraints() {
    api.state.set('constraints', {
      max_cost_aud: budget > 0 ? budget : null,
      allowed_sensor_ids: null,
      max_sensors: maxSensors,
      max_effectors: maxEffectors,
    });
    api.bus.emit('constraint:updated', {
      max_cost_aud: budget > 0 ? budget : null,
      max_sensors: maxSensors,
      max_effectors: maxEffectors,
    });
  }

  // -------------------------------------------------------------------------
  // Render — driven by placements + library data
  // -------------------------------------------------------------------------

  function _render() {
    const lookupMap = _buildLookupMap(latestSensors, latestEffectors);
    const rows = _calcBreakdown(latestPlacements, lookupMap);
    const totalCost = rows.reduce((sum, r) => sum + r.cost_aud * r.count, 0);
    const sensorCount = rows
      .filter(r => !r.isEffector)
      .reduce((sum, r) => sum + r.count, 0);
    const effectorCount = rows
      .filter(r => r.isEffector)
      .reduce((sum, r) => sum + r.count, 0);

    // Progress bar
    const pct = budget > 0 ? Math.min(100, (totalCost / budget) * 100) : 0;
    const overBudget = budget > 0 && totalCost > budget;
    progressFill.style.width = `${pct}%`;
    progressFill.style.background = overBudget ? '#ef4444' : '#22c55e';

    // Cost label
    const budgetStr = budget > 0 ? _fmtAud(budget) : 'No budget set';
    costLabel.textContent = `Cost: ${_fmtAud(totalCost)} / ${budgetStr}`;

    // Over-budget warning
    warningBanner.style.display = overBudget ? 'block' : 'none';

    // Validation indicators
    const sensorsOver = maxSensors != null && sensorCount > maxSensors;
    const effectorsOver = maxEffectors != null && effectorCount > maxEffectors;

    if (maxSensors != null || sensorCount > 0) {
      const limitStr = maxSensors != null ? `/${maxSensors}` : '';
      sensorIndicator.textContent = sensorsOver
        ? `\u26a0 ${sensorCount}${limitStr}`
        : `\u2713 ${sensorCount}${limitStr}`;
      sensorIndicator.style.color = sensorsOver ? '#ef4444' : '#22c55e';
    } else {
      sensorIndicator.textContent = '';
    }

    if (maxEffectors != null || effectorCount > 0) {
      const limitStr = maxEffectors != null ? `/${maxEffectors}` : '';
      effectorIndicator.textContent = effectorsOver
        ? `\u26a0 ${effectorCount}${limitStr}`
        : `\u2713 ${effectorCount}${limitStr}`;
      effectorIndicator.style.color = effectorsOver ? '#ef4444' : '#22c55e';
    } else {
      effectorIndicator.textContent = '';
    }

    // Rebuild breakdown tbody
    while (tbody.firstChild) {
      tbody.removeChild(tbody.firstChild);
    }

    if (rows.length === 0) {
      const emptyRow = document.createElement('tr');
      const emptyCell = document.createElement('td');
      emptyCell.textContent = 'No placements';
      emptyCell.setAttribute('colspan', '5');
      emptyCell.style.cssText = 'color:#6b7280;padding:8px 6px;font-style:italic';
      emptyRow.appendChild(emptyCell);
      tbody.appendChild(emptyRow);
    } else {
      for (const r of rows) {
        const tr = document.createElement('tr');
        const cells = [
          r.name,
          r.type || '\u2014',
          String(r.count),
          _fmtAud(r.cost_aud),
          _fmtAud(r.cost_aud * r.count),
        ];
        for (const val of cells) {
          const td = document.createElement('td');
          td.textContent = val;
          td.style.cssText = 'padding:2px 6px;border-bottom:1px solid #1e1e30';
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
    }
  }

  // -------------------------------------------------------------------------
  // CSV export
  // -------------------------------------------------------------------------

  function _buildCsv() {
    const lookupMap = _buildLookupMap(latestSensors, latestEffectors);
    const rows = _calcBreakdown(latestPlacements, lookupMap);
    const totalCost = rows.reduce((sum, r) => sum + r.cost_aud * r.count, 0);
    const lines = ['Sensor Name,Type,Quantity,Unit Cost (AUD),Line Total (AUD)'];
    for (const r of rows) {
      lines.push([
        _csvField(r.name),
        _csvField(r.type || ''),
        r.count,
        r.cost_aud,
        r.cost_aud * r.count,
      ].join(','));
    }
    lines.push(`,,,,${totalCost}`);
    return lines.join('\n');
  }

  csvBtn.addEventListener('click', () => {
    const csv = _buildCsv();
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    // D-337: append to panel before click to keep document.* access within module's own DOM scope
    const a = document.createElement('a');
    a.href = url;
    a.download = `salus-bom-${new Date().toISOString().slice(0, 10)}.csv`;
    panel.appendChild(a);
    a.click();
    panel.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // -------------------------------------------------------------------------
  // Input event handlers
  // -------------------------------------------------------------------------

  budgetInput.addEventListener('input', () => {
    // D-334: isFinite guard prevents Infinity from e.g. '1e9999' passing || 0 check
    const parsed = Number(budgetInput.value) || 0;
    budget = isFinite(parsed) ? parsed : 0;
    _render();
    _writeConstraints();
  });

  maxSensorsInput.addEventListener('input', () => {
    const v = Number(maxSensorsInput.value);
    maxSensors = (maxSensorsInput.value !== '' && v > 0) ? Math.floor(v) : null;
    _render();
    _writeConstraints();
  });

  maxEffectorsInput.addEventListener('input', () => {
    const v = Number(maxEffectorsInput.value);
    maxEffectors = (maxEffectorsInput.value !== '' && v > 0) ? Math.floor(v) : null;
    _render();
    _writeConstraints();
  });

  // -------------------------------------------------------------------------
  // Initial render — one-time get() is acceptable here per SHOULD rule 2
  // -------------------------------------------------------------------------
  latestPlacements = api.state.get('placements');      // OK: initial render only
  latestSensors = api.state.get('sensor_library');     // OK: initial render only
  latestEffectors = api.state.get('effector_library'); // OK: initial render only

  api.panel.mount(panel);
  _writeConstraints(); // write initial constraints so Optimiser has valid values on startup
  _render();

  // -------------------------------------------------------------------------
  // Reactive updates via watch()
  // All subsequent renders are driven here — no get() inside watch callbacks.
  // -------------------------------------------------------------------------
  unsubs.push(api.state.watch('placements', (placements) => {
    latestPlacements = placements;
    _render();
  }));

  unsubs.push(api.state.watch('sensor_library', (sensors) => {
    latestSensors = sensors;
    _render();
  }));

  unsubs.push(api.state.watch('effector_library', (effectors) => {
    latestEffectors = effectors;
    _render();
  }));

  // -------------------------------------------------------------------------
  // Bus subscriptions — idempotent recalculation, fires before state write
  // propagates for immediate UI responsiveness.
  // -------------------------------------------------------------------------
  unsubs.push(api.bus.on('placement:added', () => {
    _render();
  }));

  unsubs.push(api.bus.on('placement:removed', () => {
    _render();
  }));

  // -------------------------------------------------------------------------
  // Cleanup — all subscriptions removed in a single block
  // -------------------------------------------------------------------------
  api.panel.onUnmount(() => {
    // D-335: guard typeof to prevent mid-loop TypeError if any watch()/on() returned non-function
    unsubs.forEach(u => { if (typeof u === 'function') u(); });
  });
}
