# Agent Slice: Silent Failure Hunter

**Responsibility:** Detect hidden failures — empty catch blocks, swallowed exceptions, unhandled Promise rejections, missing logging, ignored futures/awaitables, resource leaks.

---

## Rules

### MUST

1. All exceptions MUST be logged with a correlation ID before being handled or re-raised.
2. Production error responses MUST return generic messages with correlation IDs (APP-ERR-01).
3. Retry logic MUST use exponential backoff with jitter (OPS-STD-003 S7.5).
4. All error responses MUST use RFC 9457 Problem Details format (OPS-STD-003 S7.1).
5. Futures and awaitables MUST be awaited, or explicitly marked as fire-and-forget with an error callback attached.
6. Resource handles (files, connections, sessions) MUST use context managers or equivalent cleanup patterns.

### MUST NOT

1. Empty `except`/`catch` blocks are forbidden. Every handler MUST log or propagate.
2. Production error responses MUST NOT include stack traces or internal details (APP-ERR-01).
3. Exceptions MUST NOT be caught and silently discarded (e.g., `except: pass`, `catch (e) {}`).
4. Promise rejections MUST NOT go unhandled — attach `.catch()` or use `try/catch` in async functions.

---

## Pre-Computed Context (Tool Outputs)

| Tool | What You Receive |
|------|-----------------|
| **ruff** | Linting findings for Python files (includes bare-except warnings, unused exception variables) |
| **eslint** | Linting findings for JS/TS files (includes no-empty catch, no-floating-promises) |

Use these outputs as a starting point. They catch syntax-level issues but miss semantic problems (e.g., a catch block that logs but does not include the correlation ID, or a logged exception that is then silently swallowed upstream).

---

## Analysis Checklist

For each changed file, verify:

1. **Empty catch blocks** — Does every `except`/`catch` block contain meaningful handling (log + action)?
2. **Swallowed exceptions** — Is the original exception preserved in the log (not just a generic message)?
3. **Correlation IDs** — Does every error log include `correlation_id`, `request_id`, or equivalent trace context?
4. **Unhandled rejections** — Are all Promises either awaited or chained with `.catch()`?
5. **Unawaited coroutines** — Are all `async def` calls properly awaited? If fire-and-forget, is `asyncio.create_task()` used with an error callback?
6. **Resource leaks** — Are file handles, DB connections, HTTP sessions opened with `with`/`async with` or equivalent try-finally?
7. **Retry patterns** — Do retry loops use exponential backoff with jitter, not fixed delays?
8. **Error response format** — Do error responses follow RFC 9457 (type, title, status, detail, instance)?

---

## Pass/Fail Criteria

**Pass:** Zero instances of swallowed exceptions or missing error handling in changed files.

**Fail:** Any of the following in changed files:
- Empty catch block (`except: pass`, `catch (e) {}`, or catch with only a comment)
- Exception logged without correlation ID
- Unawaited future/coroutine without explicit fire-and-forget pattern
- Promise without `.catch()` or surrounding `try/catch`
- Resource opened without context manager or cleanup guarantee
- Error response missing RFC 9457 fields
