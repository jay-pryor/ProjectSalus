# Logging Standard — Salus

> Applies to: all `src/salus/` modules
> Current status: logging not yet implemented — this standard governs when it is added

## MUST Rules

1. **No `print()` in library code.** The `src/salus/` package is a library. Use the standard `logging` module. `print()` is only acceptable in `cli.py` for user-facing CLI output.

2. **Logger per module.** Each module that needs logging creates its own logger at module level:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

3. **Log level discipline:**
   - `DEBUG` — Detailed computation info (ray count, cell coordinates, intermediate values)
   - `INFO` — High-level operation progress (loading DEM, computing viewshed, saving map)
   - `WARNING` — Recoverable issues (GDAL unavailable, falling back to NumPy; nodata values found)
   - `ERROR` — Operation failed but execution continues
   - `CRITICAL` — Reserved for unrecoverable state

4. **GDAL fallback MUST log a WARNING.** The NumPy ray-marching fallback is significantly less accurate than GDAL. Callers must be aware:
   ```python
   logger.warning("GDAL not available — using NumPy ray-marching fallback (lower accuracy)")
   ```

5. **Long-running operations MUST log INFO at start and end:**
   ```python
   logger.info("Computing viewshed for observer at (%.1f, %.1f)", obs_x, obs_y)
   # ... computation ...
   logger.info("Viewshed complete: %.1f%% visible", 100 * visible.sum() / visible.size)
   ```

## SHOULD Rules

1. Include relevant numeric context in log messages (coordinates, shapes, percentages).
2. Do not log inside tight loops (e.g. per-ray in the NumPy viewshed) — log before and after.
3. CLI progress output (e.g. progress bars with Click) is separate from library logging and is acceptable.

## Key Pattern

```python
# Module-level logger
import logging
logger = logging.getLogger(__name__)

def load_dem(path: Path, dsm_path: Path | None = None) -> SiteModel:
    logger.info("Loading DEM from %s", path)
    # ...
    if dsm_path:
        logger.info("Loading DSM from %s", dsm_path)
    logger.debug("DEM shape: %s, resolution: %.2f m", site.dem.shape, site.resolution)
    return site
```
