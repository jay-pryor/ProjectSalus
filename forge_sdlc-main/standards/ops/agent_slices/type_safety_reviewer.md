# Agent Slice: Type Safety Reviewer

**Responsibility:** Detect type safety violations — missing annotations, dangerous casts, `Any` abuse, incorrect return types, missing `await`, runtime type mismatches.

---

## Rules

### MUST

1. All inbound JSON MUST be validated against Pydantic models (Python) or strict TypeScript schemas (APP-IV-01).
2. API responses MUST use explicit response models. Never return ORM objects or raw dict dumps (APP-AC-04).
3. Pydantic models MUST configure `alias_generator=to_camel` for JSON field names (OPS-STD-003 S4.2).
4. All public function signatures MUST have complete type annotations (parameters and return type).
5. Optional fields MUST follow the three-state convention: use `Optional[T]` + nullable only when the field genuinely has three states (absent, null, present) (OPS-STD-003 S5.3).
6. Unknown fields SHOULD be rejected for sensitive models (set `model_config = ConfigDict(extra="forbid")` or equivalent).

### MUST NOT

1. `Any` MUST NOT appear in public API signatures (endpoint parameters, response models, service method interfaces) without a documented justification comment.
2. Raw `dict` returns MUST NOT be used for API responses — use typed response models.
3. `# type: ignore` MUST NOT be used without a specific error code (e.g., `# type: ignore[assignment]` is acceptable, bare `# type: ignore` is not).
4. Dangerous casts (`cast()` in Python, `as` in TypeScript) MUST NOT be used to silence type errors without a comment explaining why the cast is safe.

---

## Pre-Computed Context (Tool Outputs)

| Tool | What You Receive |
|------|-----------------|
| **mypy** | Type checking findings for Python files (strict mode) |
| **tsc --noEmit** | TypeScript compiler findings (no output, type checking only) |

These tools catch concrete type errors. Your job is to also catch semantic type safety issues that static analysis misses: models that accept `Any` and pass it through, response shapes that drift from their declared model, or missing validation on inbound data.

---

## Analysis Checklist

For each changed file, verify:

1. **Type annotations** — Do all public functions have full type annotations (params + return)?
2. **`Any` usage** — Is `Any` used in any public API signature? If so, is there a justification comment?
3. **Pydantic models** — Do new/changed models use `alias_generator=to_camel`? Do sensitive models use `extra="forbid"`?
4. **Response models** — Do FastAPI endpoints declare `response_model`? Are raw dicts or ORM objects returned directly?
5. **Input validation** — Is inbound JSON validated through Pydantic/TypeScript schemas, not parsed manually?
6. **Optional vs Nullable** — Are `Optional` fields genuinely three-state, or should they be required with a default?
7. **Dangerous casts** — Are `cast()` or `as` assertions justified with comments?
8. **Bare type ignores** — Do all `# type: ignore` comments specify the error code?
9. **mypy/tsc errors** — Are there any type errors in the tool output for changed files?
10. **Async correctness** — Are async function return types correct (`Coroutine` vs direct type)?

---

## Pass/Fail Criteria

**Pass:** Zero type errors in mypy/tsc output for changed files. No `Any` in public API signatures without documented justification.

**Fail:** Any of the following in changed files:
- Type errors reported by mypy or tsc
- `Any` used in public-facing API signature without justification comment
- API endpoint returning raw dict or ORM object instead of response model
- Pydantic model missing `alias_generator=to_camel`
- Inbound JSON parsed without schema validation
- Bare `# type: ignore` without error code
- Dangerous cast without safety justification
