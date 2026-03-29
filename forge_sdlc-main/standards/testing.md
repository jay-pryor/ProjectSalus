# Testing Standard

> Purpose: Ensure test quality and coverage
> Loaded for: Python files in tests/

## MUST Rules

1. Every test file must have at least one `test_` function
2. Every test must contain at least one assert or pytest.raises
3. Test functions must have descriptive names indicating the scenario
4. Do NOT use MagicMock with Pydantic models — use real model instances
5. FastAPI test client: use `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`, NOT `httpx.AsyncClient(app=app)`
6. FastAPI test fixtures MUST override dependencies: `app.dependency_overrides[get_store] = lambda: test_store`
7. Timestamp assertions: use `>=` not `>` (in-memory ops can complete in same microsecond)
8. Use `datetime.now(timezone.utc)` in test fixtures, NOT `datetime.utcnow()`
9. Construct Pydantic models with keyword arguments matching the model definition exactly
10. Tests must import from the actual module paths, not guess at names

## SHOULD Rules

1. Use fixtures over module-level setup
2. Use parametrize for testing multiple inputs
3. Test file should match source file: `test_{module}.py`
4. Use `conftest.py` for shared fixtures — test files should import from conftest, not redefine

## Key Patterns

### FastAPI Test Client Setup
```python
import httpx
import pytest
from pipeline_test.api import app
from pipeline_test.store import TaskStore

@pytest.fixture
def store():
    return TaskStore()

@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
```

### Pydantic Model Construction
```python
# CORRECT: use keyword args matching model fields
task = TaskCreate(title="Test", description="Desc", priority=TaskPriority.NORMAL)

# WRONG: do NOT use dicts, MagicMock, or positional args
task = TaskCreate(**{"title": "Test"})  # fragile
task = MagicMock(spec=TaskCreate)  # breaks Pydantic validation
```

### Enum Usage
```python
# CORRECT: use enum members
TaskStatus.PENDING
TaskPriority.HIGH

# WRONG: do NOT use raw strings or integers
"pending"  # may not match enum value format
1  # enums are strings, not ints
```

## Verification

- Every source file in src/ has corresponding tests/test_{name}.py
- `pytest --tb=short` shows no collection errors or warnings
- All tests pass: `pytest -q` returns 0
