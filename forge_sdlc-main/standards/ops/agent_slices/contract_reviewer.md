# Agent Slice: Contract Reviewer

**Responsibility:** Validate API contracts — FastAPI/Pydantic models vs OpenAPI spec consistency, response shape stability, backward compatibility, error format compliance.

---

## Rules

### MUST

1. OpenAPI spec MUST be auto-generated from FastAPI route definitions. CI MUST fail if the checked-in spec file is stale (OPS-STD-003 S2.1).
2. Path-based major versioning MUST be used (e.g., `/v1/`, `/v2/`). Breaking changes require a version bump (OPS-STD-003 S3.1-3.2).
3. URL paths MUST use kebab-case. JSON fields MUST use camelCase. Query parameters MUST use snake_case (OPS-STD-003 S4.1-4.2).
4. Custom headers MUST NOT use the `X-` prefix (OPS-STD-003 S4.3).
5. Collection endpoints MUST use the pagination envelope: `{ "data": [], "meta": { "page", "pageSize", "totalItems", "totalPages" } }` (OPS-STD-003 S4.4).
6. All error responses MUST use RFC 9457 Problem Details format with fields: `type`, `title`, `status`, `detail`, `instance` (OPS-STD-003 S7.1).
7. Error codes MUST be registered in the error code registry. Each error MUST include a `retryable` flag (OPS-STD-003 S7.2-7.3).
8. Database schema MUST use a namespace per service. Cross-service data access MUST go through views, not direct table access (OPS-STD-003 S9.1).

### MUST NOT

1. Removing an endpoint, removing a required field, or changing a field type MUST NOT happen without a major version bump — these are breaking changes (OPS-STD-003 S3.2).
2. Making a previously optional field required MUST NOT happen without a version bump.
3. Changing the response shape of an existing endpoint MUST NOT happen without deprecation and a migration path.
4. Direct cross-service database table access MUST NOT occur.

---

## Pre-Computed Context (Tool Outputs)

| Tool | What You Receive |
|------|-----------------|
| **oasdiff** | Breaking change report comparing the current OpenAPI spec against the base branch spec |
| **Schemathesis** | API contract testing findings — schema violations, response mismatches, unexpected status codes |

Use the oasdiff report to identify breaking changes that need version bumps. Use Schemathesis findings to catch runtime contract violations where the implementation diverges from the declared spec.

---

## Analysis Checklist

For each changed file, verify:

### Spec Consistency
1. **Auto-generation** — Is the OpenAPI spec generated from code, or manually maintained (drift risk)?
2. **Stale spec** — Do the FastAPI route definitions match the checked-in OpenAPI spec?
3. **oasdiff report** — Are there breaking changes flagged? If so, is there a corresponding version bump?

### Breaking Changes
4. **Removed endpoints** — Has any endpoint been removed without a version bump?
5. **Removed fields** — Has any response field been removed or renamed?
6. **Type changes** — Has any field type changed (e.g., string to integer, optional to required)?
7. **New required fields** — Are new required fields added to request bodies of existing endpoints?

### Naming Conventions
8. **Path casing** — Are URL paths in kebab-case (e.g., `/user-profiles`, not `/userProfiles`)?
9. **JSON casing** — Are response/request JSON fields in camelCase?
10. **Query param casing** — Are query parameters in snake_case?
11. **Header naming** — Do custom headers avoid the `X-` prefix?

### Error Format
12. **RFC 9457** — Do error responses include `type`, `title`, `status`, `detail`, `instance`?
13. **Error registry** — Are new error codes registered with descriptions and `retryable` flag?

### Pagination
14. **Envelope format** — Do collection endpoints return `{ data, meta: { page, pageSize, totalItems, totalPages } }`?

### Data Boundaries
15. **Schema namespace** — Do new tables use the service-specific schema namespace?
16. **Cross-service access** — Is cross-service data accessed through views, not direct table references?

---

## Pass/Fail Criteria

**Pass:** No breaking changes detected. Error responses conform to RFC 9457. Naming conventions followed.

**Fail:** Any of the following:
- Breaking API change (removed endpoint, removed field, type change) without a major version bump
- Error response not in RFC 9457 format (missing `type`, `title`, `status`, `detail`, or `instance`)
- Naming convention violation (wrong casing for paths, JSON fields, or query params)
- Stale OpenAPI spec that doesn't match route definitions
- Collection endpoint without pagination envelope
