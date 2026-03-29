# Error Handling Standard

> Purpose: Ensure consistent, safe exception handling across Python code
> Loaded for: Python files in services/, routers/, endpoints/, auth/

## MUST Rules

1. Never use bare `except:` — always specify exception type
2. Never swallow exceptions silently — always re-raise, log, or convert
3. All API error responses must include structured error detail
4. Custom exceptions must inherit from a project base exception

## SHOULD Rules

1. Prefer specific exception types over `except Exception`
2. Use contextual error messages that aid debugging
3. Include the original exception via `from exc` when re-raising

## Key Pattern

```python
try:
    result = external_call()
except SpecificError as exc:
    logger.error("context", error=str(exc))
    raise DomainError("human message") from exc
```

## Verification

- Grep for bare `except:` → zero matches
- Grep for `except Exception` without `raise` in body → zero matches
