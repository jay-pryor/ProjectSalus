# Error Boundaries Standard

> Purpose: React error boundaries, fallback UI, error reporting
> Loaded for: React component files (.tsx)

## MUST Rules

1. App must have at least one ErrorBoundary wrapping routes
2. Error boundary must show user-friendly fallback UI
3. Errors caught by boundary must be reported (Sentry/logger)

## SHOULD Rules

1. Use granular error boundaries around independent features
2. Provide retry/recovery actions in fallback UI
3. Log component stack in error reports

## Key Pattern

```typescript
<ErrorBoundary fallback={<ErrorFallback />} onError={reportError}>
  <Routes />
</ErrorBoundary>
```

## Verification

- At least one ErrorBoundary component exists
- Error boundary includes error reporting call
