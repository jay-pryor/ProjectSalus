# Frontend Design System Standard

> Purpose: Design token usage, component consistency, accessibility
> Loaded for: TSX, CSS, SCSS files (non-test)

## MUST Rules

1. No hardcoded color values outside design token files
2. Typography must use design system scale (not arbitrary px)
3. Interactive elements must have accessible names

## SHOULD Rules

1. Use design tokens via CSS variables or theme object
2. Components should accept className prop for composition
3. Use semantic HTML elements (button, not div with onClick)

## Key Pattern

```css
/* Use theme tokens */
.button {
  color: var(--color-primary);
  font-size: var(--font-size-md);
}
```

## Verification

- Grep for hardcoded hex colors in components → zero matches
- All buttons and links have accessible text
