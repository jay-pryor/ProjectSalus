# Security Standard

> Purpose: Input validation, secret handling, auth checks
> Loaded for: Python files in auth/, routers/, services/

## MUST Rules

1. No hardcoded secrets (passwords, API keys, tokens) in source
2. All user input must be validated before use
3. Auth middleware on all non-public endpoints
4. CORS origins must not use wildcard in production

## SHOULD Rules

1. Use HTTPS URLs for all external service calls
2. Sanitise error messages — no stack traces to clients
3. Rate limit public endpoints

## Key Pattern

```python
@router.get("/protected")
async def protected(user: User = Depends(get_current_user)):
    ...
```

## Verification

- detect-secrets scan passes with zero findings
- No `allow_origins=["*"]` in production config
