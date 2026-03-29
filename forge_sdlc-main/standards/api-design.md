# API Design Standard

> Purpose: REST conventions, response schemas, versioning
> Loaded for: Python files in routers/, endpoints/, api/

## MUST Rules

1. All API responses must use envelope wrapper with status field
2. Error responses must include detail and error_code
3. POST/PUT must validate request body with Pydantic model

## SHOULD Rules

1. Use versioned API paths (/api/v1/...)
2. Use consistent naming: plural nouns for collections
3. Return 201 for successful creation, 204 for deletion

## Key Pattern

```python
@router.post("/api/v1/items", status_code=201)
async def create_item(body: CreateItemRequest) -> ItemResponse:
    ...
```

## Verification

- All router files use Pydantic request/response models
- No raw dict returns in router handlers
