# Research: Token Optimizer v2

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03

No NEEDS CLARIFICATION items were raised in the Technical Context — the user explicitly specified
the full tech stack, behavioral rules, and architectural constraints. This document records the
design decisions made from codebase inspection and the stated constraints.

---

## Decision 1: Dispatch Architecture — Three-Way Switch on `implementation_type`

**Decision**: Replace `dispatch_llm_call`'s string-switch on `provider` (openai/anthropic/google)
with a three-way switch on the provider document's `implementation_type` field:
- `native` → call matching static function in `LLMAdapter` class by `native_key`
- `openai_compatible` → call new `call_openai_compatible(base_url, ...)` wrapper
- `template` → call new `_dispatch_template(adapter_template, ...)` interpreter

**Rationale**: The current dispatcher couples provider identity to call path. The new dispatch
reads the stored implementation_type from the MongoDB provider document, enabling zero-code-deploy
addition of any `openai_compatible` or `template` provider. Native functions remain
developer-authored and code-reviewed — the dispatch table is a fixed dict, not admin-configurable.

**Alternatives considered**:
- Keep string-switch and add `deepseek`/`groq` cases: rejected — each new provider requires a
  code deploy; violates the spec's admin-only-onboarding success criterion.
- Full plugin/dynamic import system: rejected — opens RCE surface; violates Principle VIII.

---

## Decision 2: Template Interpreter — Substitution-Only, No Eval

**Decision**: The template interpreter performs only `str.format_map`-style literal token
substitution for `{model_id}`, `{api_key}`, `{system_prompt}`, `{user_prompt}` in the URL,
headers, and body strings. A dot-path extractor with `[n]` array-index support (e.g.,
`choices[0].message.content`) traverses the parsed JSON response. No `eval`, no `exec`, no
templating engine that supports expressions.

**Rationale**: Principle VIII explicitly prohibits admin-submitted code execution. The substitution
tokens are a fixed, hard-coded set — admins cannot inject new tokens or expressions.

**Alternatives considered**:
- Jinja2 template engine: rejected — supports arbitrary expressions including `exec()` bypasses;
  violates Principle VIII even if the macro set is restricted.
- JSONPath library (e.g., `jsonpath-ng`): viable, but a simple recursive dot-path traverser is
  sufficient for the known access patterns and adds no dependency.

---

## Decision 3: SSRF Guard — Synchronous DNS Resolution at Save Time

**Decision**: `validators.py` contains a reusable `validate_provider_url(url: str) -> None`
function that:
1. Rejects non-HTTPS schemes immediately (no DNS lookup needed).
2. Calls `socket.getaddrinfo(host, None)` synchronously to resolve the hostname and checks every
   resolved IP against private/loopback/link-local ranges using the `ipaddress` stdlib module.
3. Raises `ValueError` on any violation; the admin route converts this to HTTP 422.

**Rationale**: DNS-time validation is the standard SSRF mitigation for admin-submitted URLs.
The stdlib `ipaddress` module covers all RFC-1918, RFC-4193, loopback, and link-local ranges
without adding dependencies. Synchronous resolution is acceptable in the admin save path (not
a hot path).

**Alternatives considered**:
- Async DNS resolution via `aiodns`: not needed; admin save is low-frequency and acceptable
  latency for a one-time validation call.
- Allowlist approach (only known provider domains): too restrictive — declarative template
  providers by design point at third-party endpoints unknown at developer time.

---

## Decision 4: Routing Algorithm — Ordinal Score + Cheapest Tiebreak

**Decision**: The routing function in `routing.py` operates as a pure function:
```
best_fit_model(phase_doc, active_models) -> model_doc
```
Ordinal maps (0–3):
- `complexity_tier`: simple=0, moderate=1, complex=2, frontier=3
- `reasoning_complexity`: direct=0, single-step=1, multi-step=2, deep-reasoning=3
- `output_quality`: draft=0, standard=1, high-fidelity=2, expert-grade=3

Pass 1 — candidates meeting or exceeding ALL three requirements. Among these, select lowest
blended rate: `(input_per_1m + output_per_1m) / 2`.

Pass 2 (fallback) — if Pass 1 is empty, select the model with the smallest sum of absolute
ordinal distances across all three dimensions, tie-broken by blended rate, then by `model_id`
lexicographic order for full determinism within a fixed catalog.

**Rationale**: Per Principle IX, the platform optimizes for best-fit at call time; the algorithm
is simple, O(n) in the number of active models for the provider, and has no side effects that
could couple it to the pricing engine.

**Alternatives considered**:
- Weighted scoring (different weights per dimension): more complex, no user requirement for
  differential weighting; adds ambiguity in the fallback case.
- Cache routing results in Redis/memory: rejected per Principle IX — routing is explicitly
  non-reproducible across catalog changes.

---

## Decision 5: Frontend Scaffold — Vite + React Router v6

**Decision**: Use `npm create vite@latest frontend -- --template react` to scaffold the frontend
in-place (replacing the current HTML-file frontend). React Router v6 with nested routes:
- `/` → redirect to `/keys`
- `/keys`, `/project`, `/estimate`, `/optimize`, `/discover` under `<UserLayout>`
- `/admin/providers`, `/admin/models`, `/admin/pricing`, `/admin/rules`, `/admin/phases`
  under `<AdminLayout>`

No Redux, Zustand, or other state libraries — all server-relevant state is request-scoped;
localStorage service handles client persistence as today.

**Rationale**: User specified Vite + React Router in the plan request. Vite gives fast HMR with
no config overhead. React Router v6 nested routes map cleanly to the two-area dashboard spec.
The existing `apiKeysService` pattern is kept, just generalized to dynamic provider IDs.

**Alternatives considered**:
- Next.js: rejected — adds server-side rendering complexity that conflicts with the stateless
  constitution and the no-SSR constraint.
- Create React App: effectively deprecated; Vite is the current standard.

---

## Decision 6: `GET /providers/{id}/models` — New Public Endpoint

**Decision**: Add `GET /providers/{id}/models` to `main.py` (not under `/admin`) protected by
the shared-secret dependency. Returns active models for the given provider_id. This is the
endpoint the /project page calls to populate the model dropdown after provider selection.

**Rationale**: The existing `GET /models` returns all active models across all providers —
insufficient for the key-scoped model picker requirement. A provider-scoped endpoint avoids
client-side filtering of all models (which could expose model names from providers the user
doesn't hold a key for, even if they can't use them).

---

## Decision 7: Phase CRUD — Extend Existing Repository Methods

**Decision**: Add `update_phase(phase_id, update_doc)` and `set_phase_active_status(phase_id,
active)` to `CatalogRepository`. The existing `get_phases()`, `get_phase_by_id()`, and
`create_phase()` are already present. Phase admin routes mirror the model/provider pattern.

**Rationale**: The repository already has `get_phases` and `create_phase` but no update or
activate/deactivate methods. Adding them follows the established pattern exactly — no design
novelty required.

---

## Decision 8: Seed Script — Replace, Not Upsert

**Decision**: The v2 seed script (`scripts/seed.py`) drops and recreates collections before
inserting seed documents. All seed model documents include the four new required capability tags;
all seed provider documents include `implementation_type`; all seed phase documents include the
three new default requirement fields. DeepSeek is seeded as an `openai_compatible` provider with
`base_url: "https://api.deepseek.com/v1"`.

**Rationale**: The constitution specifies a full MongoDB reset for v2. Upsert semantics would
silently leave old documents without required fields, which contradicts the "all new fields are
required" rule. Drop-and-recreate is safe given the explicitly stated reset policy.
