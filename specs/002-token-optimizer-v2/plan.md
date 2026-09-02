# Implementation Plan: Token Optimizer v2 — Extensible Provider Dispatch, User Dashboard & Model Routing

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-token-optimizer-v2/spec.md`

## Summary

Extend the Token Optimizer platform into a three-part v2 release:
1. **Hybrid Provider Dispatch** — four-way dispatch (native openai/anthropic/google, parameterized
   openai_compatible, and a generic declarative template interpreter) replaces the current
   string-switch in `dispatch_llm_call`.
2. **Schema & Admin API Expansion** — model capability tags, provider implementation_type, phase
   default requirements, and phase CRUD admin routes; MongoDB is reset so all new fields are
   required with no defaults.
3. **React SPA Rewrite** — Vite + React Router replaces the two-file HTML frontend; splits into a
   User Dashboard (/keys, /project, /estimate, /optimize, /discover) and an Admin Dashboard
   (/admin/providers, /admin/models, /admin/pricing, /admin/rules, /admin/phases).

The backend async/motor/httpx/FastAPI stack and all existing deterministic calculation endpoints
(/extract, /estimate, /optimize, /discover-optimizations) are preserved unchanged in behavior.
The new /route-model endpoint and GET /providers/{id}/models are additive. The shared-secret auth
pattern is extended to cover the new route-model endpoint; admin routes continue using their
existing Bearer auth.

## Technical Context

**Language/Version**: Python 3.11 (backend, unchanged); Node.js 20 LTS (frontend build)

**Primary Dependencies**:
- Backend: FastAPI, motor (async MongoDB), httpx.AsyncClient, pydantic v2, uvicorn (all unchanged)
- Frontend: Vite 5, React 18, React Router v6, no added state management library

**Storage**: MongoDB Atlas — full reset before v2 seeding; no backward-compatible field migrations

**Testing**:
- Backend: pytest + pytest-asyncio (existing); httpx stub transports for adapter tests
- Frontend: no test framework specified; routing/component behavior validated via quickstart scenarios

**Target Platform**: Linux server (backend), browser SPA (frontend); deployed separately over HTTPS

**Project Type**: Web service (backend REST API) + SPA (frontend)

**Performance Goals**: No change to existing p95 targets; /route-model is a Mongo read + O(n)
ranking across active models for one provider (n ≤ ~50), negligible latency impact

**Constraints**:
- Backend MUST remain fully stateless; no server-side session or user state
- All new document fields are REQUIRED; MongoDB is reset, no optional-with-defaults
- Admin dashboard MUST NOT handle or display user-supplied API keys
- Adapter template and openai_compatible base_url MUST be HTTPS-only and SSRF-guarded

**Scale/Scope**: Single-team codebase; incremental extension of existing repo

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Deterministic Calculation & LLM-Assisted Extraction Only | ✅ PASS | /route-model performs zero LLM calls. /estimate and /optimize unchanged. |
| II. Stateless Compute Layer with Centralized Config | ✅ PASS | No server-side user sessions added. MongoDB is the sole config authority. User keys remain client-side only. |
| III. Bring-Your-Own-Key Execution Pattern | ✅ PASS | Keys stored in localStorage only. API key UI moves to User Dashboard. Admin routes have no key input fields. Model restriction on /extract enforced at provider scope. |
| IV. Reproducibility Over Cleverness | ✅ PASS | Pricing calc engine untouched. /route-model is explicitly non-reproducible per Principle IX scope note. |
| V. Multiplicative & Capped Optimization Claims | ✅ PASS | Optimization engine untouched. |
| VI. Shared Secret Security & TLS Transport Boundary | ✅ PASS | Shared secret extended to /route-model. No new auth mechanism introduced. |
| VII. Distinct Advisory vs. Computed Recommendations | ✅ PASS | Optimization response structure untouched. |
| VIII. Hybrid Provider Dispatch | ✅ PASS | native keys are developer-shipped and fixed; openai_compatible base_url is admin-configurable; template is declarative only; no code execution of admin input. |
| IX. Model Capability Tagging & Best-Fit Routing | ✅ PASS | Four required enum tags on every model. Phase default requirements drive routing. Result is non-reproducible by design. |
| X. Client-Declared, Non-Authoritative Plan Tiers | ✅ PASS | Plan filter lives in a frontend config constant, never persisted to MongoDB, never enforced by backend. |

**No constitution violations. No complexity justification required.**

## Project Structure

### Documentation (this feature)

```text
specs/002-token-optimizer-v2/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── backend-api.md
│   └── frontend-routes.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── scripts/
│   └── seed.py                  # MODIFY — add implementation_type fields, capability
│                                #   tags on models, phase default requirements;
│                                #   add DeepSeek as openai_compatible row
├── src/
│   ├── schemas.py               # MODIFY — ModelIn/Out + tags; ProviderIn/Out +
│   │                            #   implementation_type + AdapterTemplate sub-schema;
│   │                            #   PhaseIn/Out + default req fields
│   ├── repository.py            # MODIFY — add update_phase(), set_phase_active_status(),
│   │                            #   get_active_models_by_provider()
│   ├── llm_adapters.py          # MODIFY — add call_openai_compatible(); add template
│   │                            #   interpreter (_substitute, _extract_path); rewrite
│   │                            #   dispatch_llm_call as 3-way switch on implementation_type
│   ├── routing.py               # NEW — pure best-fit routing function
│   ├── validators.py            # NEW — HTTPS + SSRF URL validator (reusable)
│   ├── main.py                  # MODIFY — add GET /providers/{id}/models;
│   │                            #   add POST /route-model
│   └── admin_api/
│       └── routes.py            # MODIFY — extend ProviderIn to use new schemas;
│                                #   add PATCH /admin/providers/{id} for full update;
│                                #   add GET/POST/PATCH /admin/phases phase CRUD
└── tests/
    ├── unit/
    │   ├── test_calc_engine.py  # UNCHANGED
    │   ├── test_routing.py      # NEW — routing function unit tests (no network/DB)
    │   └── test_adapters.py     # NEW — call_openai_compatible + template interpreter
    │                            #   tests using stub httpx transports
    └── integration/
        └── test_endpoints.py    # MODIFY — extend concurrency test; add mid-test
                                 #   provider-add scenario

frontend/                        # REWRITE as React SPA (Vite + React Router)
├── package.json                 # NEW
├── vite.config.js               # NEW
├── index.html                   # NEW (Vite entry point)
└── src/
    ├── main.jsx                 # NEW — React root, Router setup
    ├── config/
    │   └── planTiers.js         # NEW — client-only plan tier → model filter config
    ├── services/
    │   ├── api.js               # NEW — centralized fetch wrapper (shared secret header)
    │   └── apiKeysService.js    # PORT from frontend/src/services/api_keys.js;
    │                            #   generalize to dynamic provider_id keys
    ├── layouts/
    │   ├── UserLayout.jsx       # NEW — sidebar + outlet for user routes
    │   └── AdminLayout.jsx      # NEW — sidebar + outlet for admin routes
    ├── pages/user/
    │   ├── KeysPage.jsx         # NEW — /keys
    │   ├── ProjectPage.jsx      # NEW — /project
    │   ├── EstimatePage.jsx     # NEW — /estimate (port from app.js)
    │   ├── OptimizePage.jsx     # NEW — /optimize (port from app.js)
    │   └── DiscoverPage.jsx     # NEW — /discover (port from app.js)
    └── pages/admin/
        ├── ProvidersPage.jsx    # NEW — /admin/providers (implementation_type switch)
        ├── ModelsPage.jsx       # NEW — /admin/models (incl. 4 capability dropdowns)
        ├── PricingPage.jsx      # NEW — /admin/pricing (port from admin.js)
        ├── RulesPage.jsx        # NEW — /admin/rules (port from admin.js)
        └── PhasesPage.jsx       # NEW — /admin/phases (new)
```

**Structure Decision**: Web application layout (backend + frontend) — existing layout
preserved; frontend directory is replaced in-place with the Vite React scaffold.
