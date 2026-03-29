# Security Standard — Salus

> Applies to: file I/O, path handling, external data ingestion, CLI argument handling

## Context

Salus processes externally-sourced files (GeoTIFFs, YAML sensor configs) and writes output files (PNGs, PDFs). The attack surface is file path traversal and malformed geospatial data. There is no network surface, authentication, or database in this version.

## MUST Rules

1. **Path traversal prevention.** Never use user-supplied strings directly as file paths without resolving them:
   ```python
   # CORRECT
   path = Path(user_input).resolve()

   # WRONG
   with open(user_input) as f: ...
   ```

2. **Output paths must be validated.** Before writing output (PNG, PDF), verify the parent directory exists and is writable. Do not create arbitrary directories from user input.

3. **No `eval()`, `exec()`, or `subprocess` with user input.** These are not expected in Salus. If added, they require explicit review.

4. **Secrets never in source.** API keys, credentials, or sensitive config must never appear in source files. Use environment variables. The `.gitignore` must include patterns for `.env` files.

5. **GeoTIFF validation.** When opening a rasterio dataset, validate that band count and dtype are within expected ranges before reading. Malformed GeoTIFFs should raise a clean error, not crash with an internal exception.

6. **DSM/DEM size limits.** Enforce a maximum raster size before loading into memory to prevent DoS via enormous input files:
   ```python
   MAX_CELLS = 50_000 * 50_000  # ~2.5 billion cells — adjust based on hardware
   if rows * cols > MAX_CELLS:
       raise ValueError(f"Raster too large: {rows}x{cols} exceeds {MAX_CELLS} cell limit")
   ```

## SHOULD Rules

1. Use `pathlib.Path` throughout — not `os.path` string operations.
2. Log a WARNING when processing an unusually large raster (> 10_000 x 10_000 cells).
3. Document assumptions about input CRS and coordinate units in docstrings.

## Key Pattern

```python
def load_dem(path: str | Path, dsm_path: str | Path | None = None) -> SiteModel:
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"DEM not found: {path}")
    if not path.suffix.lower() in (".tif", ".tiff", ".img"):
        raise ValueError(f"Unsupported DEM format: {path.suffix}")
    # ... proceed
```
