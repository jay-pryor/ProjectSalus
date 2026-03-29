# Standards Rules

## Applicable Standards

Standards are loaded dynamically based on project type:

### Python Projects
- error-handling, testing, logging, type-safety, api-design
- database, security, dependency-management, configuration, documentation

### Frontend Projects (additional)
- typescript-safety, component-testing, api-client-contracts
- error-boundaries, frontend-design-system

### Fullstack Projects
- All Python + all Frontend standards

## Checking Standards

Run `forge check standards` after implementation to verify compliance.
Run `forge check standards --file PATH` for specific files.

## Severity Levels

- **must** — Violations block completion
- **should** — Warnings, should be addressed but don't block
