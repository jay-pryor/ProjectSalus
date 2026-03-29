# Configuration Standard

> Purpose: Env var handling, validated config
> Loaded for: Python files in config/, settings/

## MUST Rules

1. No hardcoded configuration values in source code
2. All env vars must have defaults or fail fast at startup
3. Validate config at startup, not at first use

## SHOULD Rules

1. Use a settings class (Pydantic BaseSettings) for typed config
2. Document all env vars in .env.example
3. Group related config into namespaced settings

## Key Pattern

```python
class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379"
    debug: bool = False
```

## Verification

- No raw os.environ.get() without validation wrapper
- .env.example exists and lists all required vars
