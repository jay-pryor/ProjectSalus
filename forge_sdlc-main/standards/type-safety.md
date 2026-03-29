# Type Safety Standard

> Purpose: Enforce type hints and reduce Any usage
> Loaded for: Python files in services/, models/

## MUST Rules

1. All public functions must have return type annotations
2. All public function parameters must have type annotations
3. No use of `Any` without documented justification

## SHOULD Rules

1. Use Protocol for structural typing over ABC
2. Use TypeVar for generic functions
3. Use `from __future__ import annotations` for forward references

## Key Pattern

```python
def process_item(item: Item, config: Config) -> ProcessResult:
    ...
```

## Verification

- mypy or pyright passes with no errors
- Grep for `: Any` → verify each has a comment justifying usage
