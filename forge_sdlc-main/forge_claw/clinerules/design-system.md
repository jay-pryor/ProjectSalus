# Design System Rules

## Purpose

This file is a symlink target for project-specific design system rules.
When `forge init` detects a frontend project, it creates a symlink from
the project's `.clinerules/design-system.md` to the project's design
system documentation.

## Default Rules (when no project design system exists)

- Use CSS variables for colors, fonts, and spacing
- Follow the project's existing component patterns
- Use semantic HTML elements
- Ensure all interactive elements have accessible names
- Use responsive units (rem, %, vh/vw) over fixed px
