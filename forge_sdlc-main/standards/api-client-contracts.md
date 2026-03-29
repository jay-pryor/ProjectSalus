# API Client Contracts Standard

> Purpose: Type-safe API clients, response validation
> Loaded for: TypeScript files in api/, services/, clients/

## MUST Rules

1. All API calls must use typed request/response interfaces
2. Error responses must be handled (not silently ignored)
3. API client functions must validate response shapes

## SHOULD Rules

1. Use a shared API client wrapper (not raw fetch)
2. Include request/response type exports for consumers
3. Use response interceptors for common error handling

## Key Pattern

```typescript
async function getItem(id: string): Promise<ApiResponse<Item>> {
  const response = await apiClient.get<Item>(`/api/v1/items/${id}`);
  return response.data;
}
```

## Verification

- No raw fetch() without typed response in api/ files
- All API functions have typed return values
