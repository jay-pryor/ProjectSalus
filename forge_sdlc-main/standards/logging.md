# Logging Standard

> Purpose: Enforce structured logging, no print statements
> Loaded for: All non-test Python files

## MUST Rules

1. No `print()` calls in production code
2. Use structured logging (structlog or logging with structured format)
3. Include context keys in log messages (user_id, request_id, etc.)

## SHOULD Rules

1. Use appropriate log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
2. Avoid logging sensitive data (passwords, tokens, PII)
3. Log at service boundaries (incoming/outgoing calls)

## Key Pattern

```python
import structlog
logger = structlog.get_logger()
logger.info("action_completed", user_id=uid, duration_ms=elapsed)
```

## Verification

- Grep for `print(` in non-test .py files → zero matches
- All log calls include at least one structured key
