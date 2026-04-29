/**
 * scenario-comparison/_helpers.js — Pure parsing and validation utilities.
 *
 * Exported separately so tests can import them directly without violating the
 * architecture rule that index.js exports only { init }.
 */

/**
 * Extract the SALUS_DATA payload from a viewer_data.js text blob.
 * Returns the parsed object on success, or throws with a clear message.
 *
 * The expected format is:  window.SALUS_DATA={...};\n
 * We match non-greedy up to the last `};` and JSON.parse the inner literal.
 */
export function _parseScenarioJsText(text) {
  const match = /window\.SALUS_DATA\s*=\s*(\{[\s\S]*\})\s*;?\s*$/m.exec(text);
  if (!match) {
    throw new Error('File does not match the expected "window.SALUS_DATA={...}" format.');
  }
  return JSON.parse(match[1]);
}

/**
 * Parse scenario-B file contents based on filename extension.
 * Delegates to _parseScenarioJsText for .js, JSON.parse for .json.
 */
export function _parseScenarioFile(text, filename) {
  const lower = String(filename ?? '').toLowerCase();
  if (lower.endsWith('.js')) return _parseScenarioJsText(text);
  if (lower.endsWith('.json')) return JSON.parse(text);
  try {
    return JSON.parse(text);
  } catch (_) {
    return _parseScenarioJsText(text);
  }
}

/**
 * Validate a parsed scenario-B payload has the minimum fields required for
 * comparison.  Returns { ok: true } or { ok: false, reason: string }.
 */
export function _validateScenarioBPayload(obj) {
  if (obj == null || typeof obj !== 'object' || Array.isArray(obj)) {
    return { ok: false, reason: 'Payload is not a JSON object.' };
  }
  if (!obj.layers || typeof obj.layers !== 'object') {
    return { ok: false, reason: 'Missing "layers" object (expected a composite coverage layer).' };
  }
  if (!obj.layers.composite || typeof obj.layers.composite !== 'object') {
    return { ok: false, reason: 'Missing "layers.composite" FeatureCollection.' };
  }
  return { ok: true };
}

/**
 * Compute a rough longitude centroid for a GeoJSON feature.
 * Used only by the swipe filter to decide which side of the divider a feature
 * belongs to.
 */
export function _featureCentroidLng(feature) {
  const g = feature?.geometry;
  if (!g) return null;
  const coords = g.coordinates;
  if (coords == null) return null;

  const positions = [];
  function walk(node) {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number' && typeof node[1] === 'number') {
      positions.push(node);
      return;
    }
    for (const child of node) walk(child);
  }
  walk(coords);

  if (positions.length === 0) return null;
  let sum = 0;
  for (const p of positions) sum += p[0];
  return sum / positions.length;
}
