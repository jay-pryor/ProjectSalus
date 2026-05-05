#!/usr/bin/env bash
# deploy-minimal.sh — Build the minimal Salus viewer package (S14.14-3).
#
# Copies only the files needed for the minimal (no-backend) deployment:
#   - Terrain Loader module
#   - Coverage Viewer module
#   - Shell infrastructure (index.html, shell.js, state.js, bus.js, ...)
#   - Vendor assets (MapLibreGL)
#   - A pre-generated viewer_data.js (must be supplied as $VIEWER_DATA_JS)
#
# Usage:
#   deploy-minimal.sh <output-dir> [viewer_data.js]
#
# Arguments:
#   output-dir      Directory to write the package into (created if absent).
#   viewer_data.js  Path to a pre-generated viewer_data.js file.
#                   If omitted, the script checks for ./viewer_data.js.
#
# The resulting directory is self-contained and can be served by any static
# HTTP server (Python's http.server, nginx, etc.) without a FastAPI backend.
#
# Example:
#   ./deploy-minimal.sh /tmp/salus-minimal viewer_output/viewer_data.js

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTERFACE_DIR="$SCRIPT_DIR"
STATIC_DIR="$(cd "$SCRIPT_DIR/../static" && pwd)"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <output-dir> [viewer_data.js]" >&2
  exit 1
fi

OUTPUT_DIR="$(realpath "$1")"

VIEWER_DATA_JS=""
if [[ $# -ge 2 ]]; then
  VIEWER_DATA_JS="$(realpath "$2")"
elif [[ -f "./viewer_data.js" ]]; then
  VIEWER_DATA_JS="$(realpath "./viewer_data.js")"
fi

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

echo "[deploy-minimal] Output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/static/vendor"
mkdir -p "$OUTPUT_DIR/modules/terrain-loader"
mkdir -p "$OUTPUT_DIR/modules/coverage-viewer"

# ---------------------------------------------------------------------------
# Shell infrastructure
# ---------------------------------------------------------------------------

SHELL_FILES=(
  index.html
  shell.js
  style.css
  state.js
  state-schema.js
  bus.js
  map-proxy.js
  mode-manager.js
  registry.js
)

for f in "${SHELL_FILES[@]}"; do
  cp "$INTERFACE_DIR/$f" "$OUTPUT_DIR/$f"
  echo "[deploy-minimal] Copied $f"
done

# Modules index — only terrain-loader and coverage-viewer
python3 -c "
import json
with open('$INTERFACE_DIR/modules/index.json') as fh:
    full = json.load(fh)
minimal = [m for m in full if m in ('terrain-loader', 'coverage-viewer')]
with open('$OUTPUT_DIR/modules/index.json', 'w') as fh:
    json.dump(minimal, fh)
print('[deploy-minimal] Wrote modules/index.json:', minimal)
"

# Module directories
for mod in terrain-loader coverage-viewer; do
  cp -r "$INTERFACE_DIR/modules/$mod/." "$OUTPUT_DIR/modules/$mod/"
  echo "[deploy-minimal] Copied modules/$mod/"
done

# ---------------------------------------------------------------------------
# Vendor assets
# ---------------------------------------------------------------------------

cp -r "$STATIC_DIR/vendor/." "$OUTPUT_DIR/static/vendor/"
echo "[deploy-minimal] Copied static/vendor/"

# ---------------------------------------------------------------------------
# viewer_data.js (pre-generated scenario data)
# ---------------------------------------------------------------------------

if [[ -n "$VIEWER_DATA_JS" ]]; then
  if [[ ! -f "$VIEWER_DATA_JS" ]]; then
    echo "[deploy-minimal] ERROR: viewer_data.js not found at $VIEWER_DATA_JS" >&2
    exit 1
  fi
  cp "$VIEWER_DATA_JS" "$OUTPUT_DIR/viewer_data.js"
  echo "[deploy-minimal] Copied viewer_data.js from $VIEWER_DATA_JS"
else
  echo "[deploy-minimal] WARNING: No viewer_data.js supplied. The viewer will start" >&2
  echo "[deploy-minimal] with empty sensor/effector libraries. Supply a pre-generated" >&2
  echo "[deploy-minimal] viewer_data.js to make the minimal deployment useful." >&2
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "[deploy-minimal] Package written to: $OUTPUT_DIR"
echo "[deploy-minimal] Serve with:"
echo "    python3 -m http.server 8080 --directory $OUTPUT_DIR"
echo "    then open http://localhost:8080/index.html"
