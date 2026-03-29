# TypeScript Safety Standard

> Purpose: Strict mode, no any, proper generics
> Loaded for: TypeScript/TSX files

## MUST Rules

1. No `any` type — use `unknown` or specific types
2. No `@ts-ignore` or `@ts-nocheck` directives
3. tsconfig.json must have `strict: true`
4. All exported functions must have explicit return types

## SHOULD Rules

1. Use discriminated unions for state management
2. Prefer `interface` over `type` for object shapes
3. Use generic constraints for reusable components

## Key Pattern

```typescript
interface ApiResponse<T> {
  data: T;
  status: "success" | "error";
  message?: string;
}
```

## Verification

- Grep for `: any` → zero matches (excluding generated code)
- tsconfig.json has strict: true
