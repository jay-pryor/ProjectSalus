# Database Standard

> Purpose: Safe query patterns, migration safety
> Loaded for: Python files in models/, repositories/, migrations/

## MUST Rules

1. All queries must use parameterised statements (no f-strings in SQL)
2. Migrations must be reversible (include downgrade)
3. No DROP TABLE/COLUMN without explicit confirmation step

## SHOULD Rules

1. Use repository pattern — queries in repositories/ only
2. Use connection pooling
3. Migrations should be backward-compatible (additive)

## Key Pattern

```python
class ItemRepository:
    async def get_by_id(self, item_id: UUID) -> Item | None:
        return await self.session.get(Item, item_id)
```

## Verification

- Grep for `session.execute` outside repositories/ → zero matches
- Grep for f-string in .execute() calls → zero matches
