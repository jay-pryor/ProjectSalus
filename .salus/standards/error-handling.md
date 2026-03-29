# Error Handling Standard — Salus

> Applies to: all `src/salus/` modules, especially `ingest/`, `engine/`, and `report/`

## MUST Rules

1. **Never swallow exceptions silently.** Every `except` block must either: re-raise, log with a message, or return an explicit error value (not None without documentation).

2. **Bare `except:` is forbidden.** Always name the exception class: `except FileNotFoundError`, `except rasterio.errors.RasterioIOError`, etc.

3. **File not found** — `load_dem()` and any function accepting a file path MUST raise `FileNotFoundError` with the path in the message if the file does not exist.

4. **GDAL/rasterio errors** — Catch specific rasterio exceptions, not bare `Exception`. Log the path and operation that failed.

5. **Shape mismatches** — When two arrays must match in shape (DEM + DSM, viewshed + DEM), raise `ValueError` with a message that includes both shapes: `f"DSM shape {dsm.shape} does not match DEM shape {dem.shape}"`.

6. **ImportError for optional deps** — The GDAL fallback (`except ImportError`) is the only approved use of catch-and-fallback. All other ImportErrors should propagate.

7. **NumPy NaN/inf** — If a computation can produce NaN or inf (division, log, sqrt), document it in the docstring and handle the output: either clip, raise, or return a masked array.

8. **Observer out of bounds** — If observer position is outside the DEM extent, raise `ValueError` with the coordinates and extent.

## SHOULD Rules

1. Use `pathlib.Path` for all file path handling — not raw strings passed to `open()` or rasterio.
2. Validate inputs at module boundaries (public API functions), not deep inside private helpers.
3. Exception messages should include the values that caused the failure, not just the type.

## Key Patterns

```python
# CORRECT: specific exception, informative message
if not path.exists():
    raise FileNotFoundError(f"DEM file not found: {path}")

# CORRECT: named exception with re-raise
try:
    with rasterio.open(path) as src:
        data = src.read(1)
except rasterio.errors.RasterioIOError as exc:
    raise RuntimeError(f"Failed to read DEM from {path}") from exc

# WRONG: silent swallow
try:
    result = compute_viewshed(site, x, y)
except Exception:
    pass  # NEVER DO THIS

# WRONG: bare except
try:
    ds = gdal.Open(path)
except:  # noqa — NEVER
    ds = None
```
