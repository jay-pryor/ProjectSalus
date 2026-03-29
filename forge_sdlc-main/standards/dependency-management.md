# Dependency Management Standard

> Purpose: Pinned versions, managed dependencies
> Loaded for: pyproject.toml, requirements*.txt

## MUST Rules

1. All production dependencies must have version constraints
2. Use pyproject.toml as canonical dependency source
3. Lock files must be committed (pip-compile or uv lock)

## SHOULD Rules

1. Pin to major.minor (e.g. >=1.2,<2.0) not exact
2. Separate dev dependencies from production
3. Run dependency audit quarterly

## Key Pattern

```toml
[project]
dependencies = [
    "fastapi>=0.100,<1.0",
    "httpx>=0.24,<1.0",
]
```

## Verification

- No unpinned dependencies in requirements.txt
- pyproject.toml has all dependency specs
