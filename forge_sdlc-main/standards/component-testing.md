# Component Testing Standard

> Purpose: React Testing Library patterns, behavior-focused tests
> Loaded for: Test files (.test.tsx, .test.ts, .spec.tsx, .spec.ts)

## MUST Rules

1. Use React Testing Library (not Enzyme)
2. Test user behavior, not implementation details
3. No direct access to component state or instances

## SHOULD Rules

1. Use `screen` queries over destructured render results
2. Prefer `getByRole` over `getByTestId`
3. Use `userEvent` over `fireEvent` for interactions

## Key Pattern

```typescript
test("shows error when form is invalid", async () => {
  render(<Form />);
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(screen.getByRole("alert")).toHaveTextContent(/required/i);
});
```

## Verification

- No imports from enzyme
- No .instance() or .state() calls in tests
