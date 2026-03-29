# Documentation Standard

> Purpose: Public API documentation coverage
> Loaded for: All Python source files (non-test)

## MUST Rules

1. All public classes must have docstrings
2. All public functions with >3 parameters must have docstrings
3. Module-level docstring required for all modules

## SHOULD Rules

1. Use Google or NumPy docstring style consistently
2. Include type info in docstrings for complex return types
3. README.md must be accurate and up-to-date

## Key Pattern

```python
def process(item: Item, config: Config) -> Result:
    """Process an item using the given configuration.

    Parameters
    ----------
    item : Item
        The item to process.
    config : Config
        Processing configuration.
    """
```

## Verification

- No public class without docstring
- README last-modified date < 30 days (for active projects)
