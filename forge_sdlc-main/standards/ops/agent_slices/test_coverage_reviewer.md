# Agent Slice: Test Coverage Reviewer

**Responsibility:** Identify critical code paths lacking tests — changed code with no new tests, missing assertions for failure states, fragile test patterns.

---

## Rules

### MUST

1. Every new endpoint MUST have at least one happy-path test and one error-path test.
2. Every new Pydantic model MUST have validation tests for required fields and type constraints.
3. Auth-protected endpoints MUST have tests for both authenticated and unauthenticated access.
4. Integration points (external API calls, DB operations) MUST have tests with mocked dependencies.
5. Coverage for changed files MUST meet the project threshold (default 80%, override via `forge.project.yaml`).
6. Test assertions MUST verify specific values or behaviors, not just that no exception was raised.

### MUST NOT

1. Tests MUST NOT depend on execution order or shared mutable state between test cases.
2. Tests MUST NOT make real network calls — external dependencies MUST be mocked or stubbed.
3. Tests MUST NOT use `time.sleep()` or fixed delays — use async test utilities or mock timers.
4. Tests MUST NOT assert only on status code without verifying the response body shape.
5. `pytest.mark.skip` or `@skip` MUST NOT be added without a linked issue or TODO comment explaining when it will be unskipped.

---

## Pre-Computed Context (Tool Outputs)

| Tool | What You Receive |
|------|-----------------|
| **pytest-cov** | Coverage report for Python — line-level coverage percentages per file, uncovered line ranges |
| **istanbul** | Coverage report for JS/TS — statement, branch, function, and line coverage per file |

Use coverage reports to identify changed files with low or zero coverage. Focus review effort on files where coverage dropped or new code has no corresponding tests.

---

## Analysis Checklist

For each changed file, verify:

### Test Existence
1. **Corresponding test file** — Does the changed source file have a matching test file (e.g., `service.py` -> `test_service.py`)?
2. **New endpoints** — Does every new API endpoint have at least one happy-path and one error-path test?
3. **New models** — Do new Pydantic/TypeScript models have validation tests for required fields and edge cases?

### Test Quality
4. **Meaningful assertions** — Do tests assert specific return values, response shapes, or state changes (not just `assert response.status_code == 200`)?
5. **Error path coverage** — Are failure scenarios tested (invalid input, unauthorized access, not found, conflict)?
6. **Auth tests** — Do auth-protected endpoints have tests for both valid and missing/invalid credentials?
7. **Edge cases** — Are boundary conditions tested (empty collections, max-length strings, null values)?

### Test Hygiene
8. **Mocked dependencies** — Are external API calls, DB operations, and third-party services properly mocked?
9. **No real network calls** — Do tests avoid hitting real endpoints?
10. **No sleep/delays** — Do tests avoid `time.sleep()` or fixed waits?
11. **No order dependency** — Can tests run in any order without failure?
12. **No skipped tests** — Are there new `@skip` or `pytest.mark.skip` decorators without linked issues?

### Coverage Metrics
13. **Coverage threshold** — Do changed files meet the project coverage threshold (default 80%)?
14. **Coverage delta** — Did coverage decrease for any changed file compared to the base branch?
15. **Uncovered critical paths** — Are error handlers, auth checks, and data validation paths covered?

---

## Pass/Fail Criteria

**Pass:** Changed files have corresponding test files. Coverage meets the project threshold. Critical paths (endpoints, auth, validation) are tested with both happy and error cases.

**Fail:** Any of the following:
- New endpoint with zero tests (no happy-path or error-path test)
- Coverage below the project threshold for changed files
- Auth-protected endpoint without unauthenticated access test
- New Pydantic model without validation tests
- Test that makes real network calls or uses `time.sleep()`
- Test that asserts only status code without verifying response body
