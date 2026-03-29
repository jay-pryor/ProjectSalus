# Testing Standard — Salus

> Applies to: `tests/` directory, `conftest.py`, any file with `test_` prefix

## MUST Rules

1. Every test function must contain at least one `assert` or `pytest.raises`
2. Test names must describe the scenario: `test_ridge_blocks_visibility`, not `test_viewshed_2`
3. Do NOT use `MagicMock` with Pydantic models — construct real instances with keyword args
4. Fixtures that create rasterio files MUST use `tmp_path` (not a shared fixture path) to avoid test pollution
5. Use `pytest.approx` for floating-point comparisons: `assert result == pytest.approx(50.0)`
6. Tests for coverage percentage must use `>` not `>=` unless the boundary is explicitly meaningful
7. Every new source module in `src/salus/` must have a corresponding `tests/test_{module}.py`
8. `conftest.py` is the only place shared fixtures live — do not redefine fixtures in individual test files
9. Use `datetime.now(timezone.utc)` not `datetime.utcnow()` in any fixture producing timestamps
10. NumPy boolean array assertions: use `vis[r, c] is np.True_` for scalar checks, `np.all(array)` for full-array checks

## SHOULD Rules

1. Use `pytest.mark.parametrize` for testing multiple inputs to the same logic
2. Test file structure should mirror source: `test_terrain.py` tests `ingest/terrain.py`
3. Group related tests in a class (e.g. `class TestSiteModel`, `class TestLoadDem`)
4. DEM fixture sizes: use smallest DEM that exercises the behaviour (100x100 for flat, 200x200 for ridge)
5. Observer position in viewshed tests: place at row/col 50 of a 100x100 grid (centre) for predictable results

## Verification

```bash
pytest tests/ -v                                  # All tests pass
pytest tests/ --cov=src/salus --cov-fail-under=80  # Coverage >= 80%
pytest --tb=short -q                               # No collection errors
```
