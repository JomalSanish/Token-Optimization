# Tasks: Token Optimizer v2 — Extensible Provider Dispatch, User Dashboard & Model Routing

**Branch**: `002-token-optimizer-v2` | **Generated**: 2026-09-03
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

> **Ordering rationale**: Backend schema → validators → adapters + routing (+ their unit tests)
> → repository methods → admin phase CRUD → DB reset/reseed → public endpoints → integration
> tests → frontend scaffold → frontend services → user pages → admin pages → polish.
> The DB reset task is explicitly gated after all schemas are finalized (T018), and admin
> Phase CRUD is placed before /route-model so seeded phase data is available for routing tests.

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Scaffolding and configuration that everything else builds on.

- [X] T001 Scaffold Vite + React 18 project in `frontend/` using `npm create vite@latest . -- --template react` (replaces existing HTML frontend in-place); as part of this task, remove `frontend/styles.css`, `frontend/admin.html`, `frontend/index.html`, `frontend/src/app.js`, and `frontend/src/admin.js` so no orphaned legacy assets remain alongside the new scaffold — verify the working tree is clean (`git status`) before proceeding to T002
- [X] T002 Install React Router v6 dependency and verify `frontend/package.json` and `frontend/vite.config.js` are correct
- [X] T003 [P] Configure Vite dev proxy to `http://localhost:8000` so frontend API calls reach the backend during development in `frontend/vite.config.js`
- [X] T004 [P] Verify Python environment and `backend/requirements.txt` still resolves cleanly (no new backend dependencies required)

**Checkpoint**: Frontend scaffold boots at `http://localhost:5173`; backend boots unchanged at `http://localhost:8000`.

---

## Phase 2: Foundational — Backend Schema, Validators & Core Logic

**Purpose**: All new Python modules and schema changes that every subsequent backend task depends on.
No endpoint or seed work begins until this phase is complete.

> ⚠️ **CRITICAL**: Phases 3–5 (backend endpoints, DB reset, integration tests) MUST NOT begin
> until T005–T015 are complete. The seed script in Phase 3 will fail against an incomplete schema.

- [X] T005 Extend `backend/src/schemas.py` — add `AdapterTemplate` sub-schema (six required string fields: `request_url`, `http_method`, `header_template`, `body_template`, `response_text_path`, `error_message_path`)
- [X] T006 Extend `backend/src/schemas.py` — extend `ProviderIn`/`ProviderOut` with `implementation_type` (enum: `native | openai_compatible | template`), conditionally required `native_key`, `base_url`, and `adapter_template` fields; add pydantic `model_validator` enforcing which sub-fields are required per type
- [X] T007 Extend `backend/src/schemas.py` — add four required capability tag fields to `ModelIn`/`ModelOut`: `complexity_tier`, `reasoning_complexity`, `output_quality` (str enums), `primary_use` (list[str] enum); all required with no default
- [X] T008 Extend `backend/src/schemas.py` — add three required capability requirement fields to `PhaseIn`/`PhaseOut`: `default_complexity_tier`, `default_reasoning_complexity`, `default_output_quality`; all required with no default
- [X] T009 Create `backend/src/validators.py` — implement `validate_provider_url(url: str) -> None` that rejects non-HTTPS schemes and resolves hostname via `socket.getaddrinfo`, rejecting private/loopback/link-local address ranges using `ipaddress` stdlib; raises `ValueError` with a descriptive message on any violation
- [X] T010 Extend `backend/src/llm_adapters.py` — add `LLMAdapter.call_openai_compatible(base_url, model_id, api_key, system_prompt, user_prompt)` as a parameterized wrapper sharing the same request/response shape as `call_openai` but with a configurable base URL
- [X] T011 Extend `backend/src/llm_adapters.py` — add `_substitute(template_str, substitutions)` helper that replaces `{model_id}`, `{api_key}`, `{system_prompt}`, `{user_prompt}` via `str.format_map` (static substitution only, no eval/exec)
- [X] T012 Extend `backend/src/llm_adapters.py` — add `_extract_path(data, dot_path)` helper that traverses a parsed JSON dict via dot-path string with `[n]` array-index support (e.g. `choices[0].message.content`)
- [X] T013 Extend `backend/src/llm_adapters.py` — add `_dispatch_template(adapter_template, model_id, api_key, system_prompt, user_prompt)` async function using `_substitute` + `_extract_path` + `httpx.AsyncClient`; map 401/429 through, all other non-2xx to 502
- [X] T014 Extend `backend/src/llm_adapters.py` — rewrite `dispatch_llm_call` as a three-way switch on `provider_doc["implementation_type"]`: `native` → look up key in `NATIVE_REGISTRY` dict and call matching function; `openai_compatible` → `call_openai_compatible` with stored `base_url`; `template` → `_dispatch_template` with stored `adapter_template`
- [X] T015 Create `backend/src/routing.py` — implement pure function `best_fit_model(phase_doc: dict, active_models: list[dict]) -> dict` using ordinal ranking (simple=0…frontier=3, direct=0…deep-reasoning=3, draft=0…expert-grade=3); Pass 1: cheapest model meeting/exceeding all three requirements; Pass 2 fallback: smallest sum of absolute ordinal distances, tie-broken by blended rate then `model_id` lexicographic order

**Checkpoint**: `backend/src/schemas.py`, `validators.py`, `llm_adapters.py`, `routing.py` all present and importable with no syntax errors.

---

## Phase 3: Foundational — Unit Tests for Core Logic

**Purpose**: Unit tests for T009–T015 before any endpoint wires them up. Tests run with no
network or DB — all IO is stubbed. These lock down the logic before it is called from endpoints.

- [X] T016 Create `backend/tests/unit/test_routing.py` — test `best_fit_model` in four cases (no network/DB): (a) exact match returns cheapest qualifying model; (b) no-match fallback when all models are below the requirement on at least one dimension; (c) no-match fallback when all models exceed the requirement; (d) tie-break by cheapest blended rate then lexicographic `model_id`
- [X] T017 [P] Create `backend/tests/unit/test_adapters.py` — test `call_openai_compatible` with a stubbed `httpx` transport returning a synthetic OpenAI-shaped response confirming `base_url` parameterization; test `_dispatch_template` with a stub transport returning a synthetic novel-REST-shaped response confirming `response_text_path` extraction; test `_extract_path` for nested dot-path and `[n]` array-index access; test `_substitute` for all four placeholder tokens; confirm no native-provider assumptions leak into the template path
- [X] T017A [Constitution: Testing Gates] Run `pytest --cov=src.calc_engine backend/tests/unit/test_calc_engine.py --cov-report=term-missing --cov-fail-under=100` and confirm the constitution's 100% unit-test-coverage gate for the pure calc-engine still passes unchanged after T014/T027's `dispatch_llm_call` signature change; `test_calc_engine.py` itself is not modified by this feature, but this task exists to prove that fact rather than assume it

**Checkpoint**: `pytest tests/unit/` passes including T016 and T017 (all existing `test_calc_engine.py` tests continue to pass unchanged); T017A confirms 100% calc-engine coverage holds.

---

## Phase 4: Foundational — Repository Methods, Schema Finalization & DB Reset

**Purpose**: Repository extension, then the DB reset/reseed. The seed script is gated here because
it depends on the fully-finalized schemas from T005–T008 (Phase 2) — reseeding against a
still-changing schema would need to be repeated.

- [X] T018 Extend `backend/src/repository.py` — add `get_active_models_by_provider(provider_id)`, `update_phase(phase_id, update_doc)`, and `set_phase_active_status(phase_id, active)` methods following existing patterns; add `update_provider(provider_id, update_doc)` for full provider edits
- [X] T019 Rewrite `backend/scripts/seed.py` to drop-and-recreate all collections before inserting seed data; add `implementation_type`, `native_key`/`base_url` to all four provider seed rows (openai/anthropic/google as `native`, deepseek as `openai_compatible` with `base_url: "https://api.deepseek.com/v1"`); add all four capability tags to every model seed row; add all three default requirement fields to every phase seed row; run `python scripts/seed.py` against the local dev DB and verify no errors

**Checkpoint**: `python backend/scripts/seed.py` runs cleanly; `db.providers.findOne({provider_id:"deepseek"})` returns a document with `implementation_type: "openai_compatible"` and `base_url`; `db.models.findOne()` includes all four capability tags; `db.phases.findOne()` includes all three default requirement fields.

---

## Phase 5: User Story 6 — Admin Phase CRUD Backend (Priority: P3, promoted for routing data)

**Goal**: Expose Phase CRUD via admin routes so the routing endpoint has real phase documents
to read. Placed before /route-model endpoint (T024) so integration tests can exercise routing
against real seeded phase data without mocking.

**Independent Test**: `GET /admin/phases` returns all seeded phases with the three new default
requirement fields; `POST /admin/phases` with a missing requirement field returns 422.

- [X] T020 [US6] Extend `backend/src/admin_api/routes.py` — add `GET /admin/phases` endpoint that calls `repo.get_phases()` returning `List[PhaseOut]`
- [X] T021 [US6] Extend `backend/src/admin_api/routes.py` — add `POST /admin/phases` endpoint validating `PhaseIn` (all three new required fields enforced by Pydantic) and calling `repo.create_phase()`; return 400 on duplicate `phase_id`
- [X] T022 [US6] Extend `backend/src/admin_api/routes.py` — add `PATCH /admin/phases/{phase_id}` endpoint calling `repo.update_phase()`; validate updated enum fields; return 404 if phase not found

**Checkpoint**: `GET /admin/phases` returns seeded phases; `POST /admin/phases` missing `default_output_quality` returns 422 with field name in error detail; `PATCH /admin/phases/{phase_id}` updates in place.

---

## Phase 6: User Story 1 — OpenAI-Compatible Provider Dispatch (Priority: P1)

**Goal**: Admin registers an openai_compatible provider (e.g. DeepSeek) via the Admin Dashboard;
a user with a key can immediately run extraction against it — zero backend code changes required.

**Independent Test**: POST `/admin/providers` with `implementation_type: "openai_compatible"` and a valid HTTPS `base_url` saves successfully; POST with an HTTP URL or private-IP URL returns 422; extraction against the new provider routes through `call_openai_compatible`.

### Backend — Provider Schema & SSRF Validation

- [ ] T023 [US1] Extend `backend/src/admin_api/routes.py` — update `POST /admin/providers` to use the new `ProviderIn` schema (T006); call `validate_provider_url` (T009) from `backend/src/validators.py` on `base_url` before saving; return 422 with descriptive error on SSRF violation or invalid `native_key`
- [ ] T024 [US1] Extend `backend/src/admin_api/routes.py` — add `PATCH /admin/providers/{provider_id}` endpoint for full provider updates (not just active status); call `validate_provider_url` on any updated URL; return 404 if not found

### Backend — Public Endpoints

- [ ] T024A [US1] Add `ProviderPublicOut` schema to `backend/src/schemas.py` — a variant of `ProviderOut` that excludes `native_key` and `adapter_template` (internal dispatch details never meant to leave the backend); include only `provider_id`, `display_name`, `active`, `implementation_type`, `base_url` (present only for `openai_compatible`), `created_at`, `updated_at`
- [ ] T025 [US1] Extend `backend/src/main.py` — add `GET /providers` endpoint (shared-secret protected) returning active providers using `ProviderPublicOut` as the `response_model`, so `native_key` and `adapter_template` are excluded at the FastAPI response-model layer rather than by convention
- [ ] T026 [US1] Extend `backend/src/main.py` — add `GET /providers/{provider_id}/models` endpoint (shared-secret protected) calling `repo.get_active_models_by_provider()`; return 404 if provider not found; return empty list if provider has no active models
- [ ] T027 [US1] Update `backend/src/main.py` `/extract` endpoint — change `dispatch_llm_call` call signature to pass the full provider document (fetched from DB by `provider_id`) instead of the provider name string, enabling the three-way implementation_type switch

**Checkpoint**: `curl GET /providers` returns DeepSeek with `implementation_type: "openai_compatible"`; `GET /providers/deepseek/models` returns DeepSeek models; `POST /admin/providers` with `http://` URL returns 422; `POST /extract` with `provider: "deepseek"` dispatches via `call_openai_compatible`.

---

## Phase 7: User Story 2 — Declarative Template Provider Dispatch (Priority: P2)

**Goal**: Admin onboards a provider with a novel request/response shape using the full declarative
adapter template — no backend code changes required.

**Independent Test**: POST `/admin/providers` with `implementation_type: "template"` and all six adapter fields saves; extraction against that provider uses `_dispatch_template`; a missing adapter sub-field returns 422.

- [ ] T028 [US2] Extend `backend/src/admin_api/routes.py` `POST /admin/providers` — call `validate_provider_url` on `adapter_template.request_url` for template providers; enforce all six adapter sub-fields present (via Pydantic `AdapterTemplate` schema)
- [ ] T029 [US2] [TEST] Create/extend `backend/tests/integration/test_endpoints.py` — add an end-to-end test that POSTs a `template` provider, then calls `/extract` against it via a stubbed httpx transport, confirming: `{model_id}`, `{api_key}`, `{system_prompt}`, `{user_prompt}` are substituted from the live request into the stubbed transport's captured request; `response_text_path` correctly extracts the LLM reply from the stub's synthetic response; a stubbed 401/429 passes through unchanged and any other non-2xx maps to 502. This is a verification-only task — T027 (call-signature rewire) and T013 (`_dispatch_template`) already contain all the production code this test exercises; no new implementation code is expected here

**Checkpoint**: Saving a template provider with a missing `body_template` returns 422; extraction against a template provider with a synthetic stub returns the text from `response_text_path`.

---

## Phase 8: User Story 4 — Model Capability Tags Backend & Admin Route (Priority: P2)

**Goal**: Admin can set all four capability tags on any model; saves without all four fail.

**Independent Test**: `POST /admin/models` with all four tags succeeds; same request missing `complexity_tier` returns 422; `GET /admin/models` returns models with tag fields present.

- [ ] T030 [US4] Create `backend/tests/unit/test_model_tags.py` — pure unit test (no network, no DB, no `TestClient`) instantiating `ModelIn` directly: assert a payload missing `complexity_tier` (or any of the other three capability tag fields) raises Pydantic `ValidationError` with that field's name present in the error detail; assert a fully-populated payload validates successfully. This tests the schema in isolation — `POST /admin/models` returning 422 on the same missing field is a consequence of FastAPI enforcing this schema automatically and does not need its own route-level test beyond what T036's integration suite already covers for the admin routes generally
- [ ] T031 [US4] Update `backend/src/admin_api/routes.py` `PATCH /admin/models/{model_id}` — allow partial update of capability tag fields; validate enum values on update; return 422 for invalid enum values

**Checkpoint**: `POST /admin/models` missing `output_quality` returns 422 with `"output_quality"` in detail; `GET /admin/models` response includes all four tag fields on each model.

---

## Phase 9: User Story 5 — Best-Fit Routing Endpoint (Priority: P3)

**Goal**: POST `/route-model` returns a best-fit active model for a given phase and provider, or a
structured no-match response when the provider has no active models — never an error for that case.

**Independent Test**: `POST /route-model` with a valid phase/provider pair returns a model with `match_type`, `ordinal_distance`, and `blended_rate`; requesting a real phase/provider pair where the provider has zero active models returns 200 with `match_type: "none"`; requesting a nonexistent phase_id or provider_id returns 404.

- [ ] T032 [US5] Add `RouteModelRequest` and `RouteModelResponse` Pydantic schemas to `backend/src/schemas.py`; `RouteModelResponse` includes an optional `model_id`/`display_name`/`match_type`/`ordinal_distance`/`blended_rate` set (all `None` when `match_type` is `"none"`)
- [ ] T033 [US5] Extend `backend/src/main.py` — add `POST /route-model` endpoint (shared-secret protected) using the schemas from T032: fetch phase doc and provider doc from DB, return 404 if EITHER is not found; fetch the provider's active models — if the provider exists but has zero active models, return **200** with `RouteModelResponse(match_type="none", model_id=None, ...)`, not 404 (a provider with no active models is a valid, expected state per spec.md's edge-case note, not an error condition); otherwise call `best_fit_model()` from `backend/src/routing.py` and return `match_type` `"exact"` or `"nearest"` per its result; set `Cache-Control: no-store` on every response from this endpoint (success, `"none"`, and 404 alike) per `contracts/backend-api.md`

**Checkpoint**: `POST /route-model {"phase_id":"requirement","provider_id":"openai"}` returns a model doc; `POST /route-model` against a real provider with zero active models returns 200 with `match_type: "none"`; `POST /route-model {"phase_id":"requirement","provider_id":"does-not-exist"}` returns 404.

---

## Phase 10: Integration Tests — Extended Backend Suite

**Purpose**: Extend the existing integration test suite to cover the new dispatch paths and concurrency behaviour with mid-test provider addition.

- [ ] T034 [Constitution: Concurrency & Key Relaying] Extend `backend/tests/integration/test_endpoints.py` — add a test that POSTs an `openai_compatible` provider (mocked httpx transport), then runs `GET /providers/{id}/models` and `POST /route-model` against it, confirming zero cross-request leakage across 10+ concurrent requests with independently rotating key pools; ALSO add a sibling test that fires 10+ concurrent `POST /extract` requests against a mix of `openai_compatible` and `template` providers (mocked httpx transports, distinct API keys per simulated user), confirming no key crosses between requests through the rewritten `dispatch_llm_call` three-way switch — the pre-existing key-isolation coverage for `/extract` was written against the old string-switch dispatch path and does not by itself prove the new path is safe
- [ ] T035 [P] Extend `backend/tests/integration/test_endpoints.py` — add a test that POSTs a `template` provider with a synthetic adapter, triggers `POST /extract` against it via a stubbed httpx transport, and confirms `response_text_path` extraction and 401/429 status pass-through
- [ ] T036 [P] Extend `backend/tests/integration/test_admin.py` — add tests for `GET/POST/PATCH /admin/phases`; confirm missing default requirement field returns 422; confirm PATCH updates sort_order and enum fields; confirm duplicate `phase_id` returns 400

**Checkpoint**: `pytest tests/integration/` passes all new and existing tests.

---

## Phase 11: User Story 3 — User Dashboard: API Keys Page (Priority: P2)

**Goal**: User navigates to `/keys` in the React SPA, adds/labels/removes provider API keys stored
in localStorage only. Admin area has no API key UI anywhere.

**Independent Test**: Adding a key for "deepseek" saves to localStorage with no network request; removing it removes it from localStorage; navigating to `/admin` has no key input field.

- [ ] T037 [US3] Create `frontend/src/services/apiKeysService.js` — port from old `api_keys.js`; generalize hardcoded `{openai:[], google:[], anthropic:[]}` default to a dynamic provider_id map; expose `getKeys()`, `addKey(provider_id, key, label)`, `removeKey(provider_id, keyId)`, `getActiveKey(provider_id)`, `markKeyExhausted(provider_id, keyId)`
- [ ] T038 [US3] Create `frontend/src/services/api.js` — centralized `apiFetch(path, options)` wrapper that injects `X-App-Secret` header from an env constant (`import.meta.env.VITE_APP_SECRET`) on every request
- [ ] T039 [US3] Create `frontend/src/layouts/UserLayout.jsx` — persistent left sidebar with nav links for API Keys (`/keys`), Project (`/project`), Estimate (`/estimate`), Optimize (`/optimize`), Discover (`/discover`); renders `<Outlet />` for child routes
- [ ] T040 [US3] Create `frontend/src/layouts/AdminLayout.jsx` — persistent left sidebar with nav links for Providers, Models, Pricing, Rules, Phases under `/admin/*`; renders `<Outlet />`; contains NO API key input fields, state, or references
- [ ] T041 [US3] Create `frontend/src/main.jsx` — React Router v6 `<BrowserRouter>` with nested routes: `/` redirect to `/keys`; user routes under `<UserLayout>`; admin routes under `<AdminLayout>`
- [ ] T042 [US3] Create `frontend/src/pages/user/KeysPage.jsx` — fetches active provider list from `GET /providers` on mount; renders one row per provider showing provider display name, an API key input, an optional label input, and an Add button; existing stored keys shown with a Remove button; all adds/removes call `apiKeysService` (localStorage only, no network write); admin layout link is NOT present on this page

**Checkpoint**: Navigate to `http://localhost:5173/keys`; add a "deepseek" key → appears in list; remove it → disappears; open DevTools Network — no write request to backend during add/remove.

---

## Phase 12: User Story 1 & 3 — User Dashboard: Project Page (Priority: P1)

**Goal**: User selects a provider (from keys they hold), sees only that provider's models, optionally
applies a client-side plan-tier filter, and triggers extraction.

**Independent Test**: Provider picker shows only providers with stored keys; model picker populates from `GET /providers/{id}/models`; plan-tier selector filters client-side with no network call; extraction POSTs to `/extract` with `X-Provider-Key` from localStorage.

- [ ] T043 [US1] Create `frontend/src/config/planTiers.js` — export `PLAN_TIERS` constant mapping tier name to `allowedComplexityTiers` array; this is the sole source of plan-tier data; not fetched from backend
- [ ] T044 [US1] Create `frontend/src/pages/user/ProjectPage.jsx` — reads stored keys from `apiKeysService`; renders provider picker populated only from providers for which a key exists; on provider selection calls `GET /providers/{id}/models` via `api.js`; renders model dropdown from the response; renders optional Plan tier `<select>` that filters the model list client-side using `PLAN_TIERS` (no network call on tier change); renders project description textarea and document upload; on submit calls `POST /extract` with `X-Provider-Key` header from `apiKeysService.getActiveKey(provider_id)`; stores extraction result in `sessionStorage["extractResult"]` and extraction context in `sessionStorage["extractionContext"]`

**Checkpoint**: Hold only an OpenAI key → only OpenAI appears in provider picker; change plan tier → model list filters without network call; add a DeepSeek key → DeepSeek appears in picker.

---

## Phase 13: User Story 5 — User Dashboard: Estimate Page (Priority: P3)

**Goal**: User edits phase table, assigns models across ALL providers (not limited to extraction
provider), and optionally clicks "Suggest model" per phase to call `/route-model`.

**Independent Test**: Phase model picker includes models from all providers; "Suggest model" calls `POST /route-model` and pre-fills the picker; override is preserved through to the estimate calculation.

- [ ] T045 [US5] Create `frontend/src/pages/user/EstimatePage.jsx` — loads phase data from `sessionStorage["extractResult"]` or defaults to manual entry; fetches full model catalog from `GET /models` (all providers, all active models); renders editable phase table with per-row assigned-model picker spanning all providers grouped by provider name; adds a "Suggest model" button per row that calls `POST /route-model {phase_id, provider_id}` and pre-fills the picker (user can still override); on estimate submit calls `POST /estimate`; stores result in `sessionStorage["estimateResult"]`

**Checkpoint**: Phase table model picker shows models from OpenAI AND Anthropic AND Google (not just the extraction provider); "Suggest model" pre-fills picker but user can immediately select a different model; resulting estimate uses the user's selected (possibly overridden) model.

---

## Phase 14: Existing User Flows — Optimize & Discover Pages

**Goal**: Port the existing optimize and discover flows into the React SPA routing shell.
No behavioral changes — these are UI migrations only.

- [ ] T046 [P] Create `frontend/src/pages/user/OptimizePage.jsx` — port existing `/optimize` call and results display from `frontend/src/app.js`; reads `sessionStorage["estimateResult"]`; calls `POST /optimize`; stores result in `sessionStorage["optimizeResult"]`; renders per-phase triggered rules, savings, and advisory recommendations in their existing two-category split
- [ ] T047 [P] Create `frontend/src/pages/user/DiscoverPage.jsx` — port existing `/discover-optimizations` call from `frontend/src/app.js`; reads extraction context from `sessionStorage["extractionContext"]` for provider+model; disables the Discover action if no extraction context exists; calls `POST /discover-optimizations` with `X-Provider-Key` from `apiKeysService.getActiveKey(extractionContext.provider_id)`; no separate provider/model selector on this page

**Checkpoint**: Navigating to `/optimize` after estimate shows optimizer output; navigating to `/discover` without a prior extraction shows a disabled/empty state.

---

## Phase 15: User Story 1, 2, 4, 6 — Admin Dashboard Pages

**Goal**: React admin area with full CRUD for Providers (implementation_type switch form), Models
(four capability tag dropdowns), Pricing, Rules, and the new Phases page.

- [ ] T048 [US1] [US2] Create `frontend/src/pages/admin/ProvidersPage.jsx` — fetches `GET /admin/providers`; renders provider list with Add and Edit buttons; provider form shows `implementation_type` as a radio/select that dynamically shows/hides: native → `native_key` picker (static list from a frontend constant matching the backend's registered keys: `["openai","anthropic","google"]`); openai_compatible → `base_url` text field; template → all six adapter template fields; on save calls `POST /admin/providers`; on status toggle calls `PATCH /admin/providers/{id}`; NO API key input fields anywhere on this page
- [ ] T049 [US4] Create `frontend/src/pages/admin/ModelsPage.jsx` — fetches `GET /admin/models`; renders model list; model form includes four required capability tag fields as `<select>` elements with only the fixed enum values (no free-text); `primary_use` is a multi-select; on save calls `POST /admin/models`; on pricing update calls `PATCH /admin/models/{id}`; on activate/deactivate calls the activate/deactivate endpoints
- [ ] T050 [P] Create `frontend/src/pages/admin/PricingPage.jsx` — port existing pricing management UI from `frontend/src/admin.js`; no behavioral change
- [ ] T051 [P] Create `frontend/src/pages/admin/RulesPage.jsx` — port existing optimizer rules management UI from `frontend/src/admin.js`; no behavioral change
- [ ] T052 [US6] Create `frontend/src/pages/admin/PhasesPage.jsx` — fetches `GET /admin/phases`; renders phase list sorted by `sort_order`; phase form includes all phase fields plus three required default capability requirement dropdowns (`default_complexity_tier`, `default_reasoning_complexity`, `default_output_quality`) using the same fixed enums as model tags; on save calls `POST /admin/phases`; on edit calls `PATCH /admin/phases/{id}`

**Checkpoint**: Admin navigates to `/admin/providers`; selects "template" implementation type → all six adapter fields appear; selects "native" → only `native_key` picker shown; navigates to `/admin/models` → four capability dropdowns visible; navigates to `/admin/phases` → three default requirement dropdowns visible; no API key field exists anywhere in the admin area.

---

## Phase 16: Polish & Cross-Cutting Concerns

**Purpose**: Final wiring, edge-case handling, and validation guide run-through.

- [ ] T053 Add empty-state handling to `frontend/src/pages/user/ProjectPage.jsx` — show "No models available" message when `GET /providers/{id}/models` returns an empty array
- [ ] T054 [P] Add empty-state handling to `frontend/src/pages/user/KeysPage.jsx` — show "Add your first API key to get started" when localStorage has no keys
- [ ] T055 [P] Wire `frontend/src/main.jsx` root `/` redirect to `/keys` and add a 404 catch-all route
- [ ] T056 [P] Update `frontend/index.html` title and meta description to "Token Optimizer — User Dashboard"
- [ ] T057 Manually run through all ten validation scenarios in `specs/002-token-optimizer-v2/quickstart.md` and confirm each expected outcome matches; fix any discrepancies before marking complete
- [ ] T057A [Constitution: Pre-Commit Auditing] Add `.pre-commit-config.yaml` at repo root with a secret-scan hook (`gitleaks` or `detect-secrets`) covering both `backend/` and `frontend/`; run it once against the full working tree and resolve any findings before this feature is marked complete — the constitution requires this gate exist, and nothing in the current task list creates it

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1  (Setup)              → No dependencies; start immediately
Phase 2  (Schema + Core)      → Depends on Phase 1 completion
Phase 3  (Unit Tests)         → Depends on Phase 2 (tests the logic in T010–T015)
Phase 4  (Repo + DB Reset)    → Depends on Phase 2 (schema must be finalized before seeding)
Phase 5  (Admin Phase CRUD)   → Depends on Phase 4 (needs seeded phase data + updated schema)
Phase 6  (US1 Dispatch)       → Depends on Phases 3, 4, 5
Phase 7  (US2 Template)       → Depends on Phase 6 (template dispatch builds on same infra)
Phase 8  (US4 Model Tags)     → Depends on Phase 4 (schema must be stable)
Phase 9  (US5 Route Endpoint) → Depends on Phases 5, 6, 8 (needs phases, models with tags)
Phase 10 (Integration Tests)  → Depends on Phases 6, 7, 8, 9
Phase 11 (FE Keys Page)       → Depends on Phase 6 (GET /providers must exist)
Phase 12 (FE Project Page)    → Depends on Phases 11, 6 (GET /providers/{id}/models must exist)
Phase 13 (FE Estimate Page)   → Depends on Phases 9, 12 (POST /route-model must exist)
Phase 14 (FE Optimize/Disc.)  → Depends on Phase 12
Phase 15 (Admin Pages)        → Depends on Phases 5, 6, 7, 8, 9
Phase 16 (Polish)             → Depends on all prior phases
```

### User Story Completion Order

- **US6 (Phase CRUD backend)** — promoted to Phase 5 (data dependency for routing)
- **US1 (openai_compatible dispatch)** — Phase 6; P1 highest priority
- **US2 (template dispatch)** — Phase 7; builds directly on US1 infrastructure
- **US4 (model capability tags)** — Phase 8; feeds routing and admin UI
- **US3 (API keys UI)** — Phase 11; first frontend work, only needs GET /providers
- **US5 (routing endpoint + estimate page)** — Phases 9 + 13; last backend, last estimate UI

### Parallel Opportunities

Backend Phases 7, 8 can be worked in parallel once Phase 6 is complete (different files):
- Developer A: T028–T029 (template validation + extraction wiring)
- Developer B: T030–T031 (model tag admin routes)

Frontend Phases 11–15: Pages within the same phase marked `[P]` touch independent files:
- T046 `OptimizePage.jsx` and T047 `DiscoverPage.jsx` are independent
- T050 `PricingPage.jsx` and T051 `RulesPage.jsx` are independent

---

## Implementation Strategy

### MVP Scope (User Story 1 only — minimum to prove zero-code-deploy promise)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Schema + Core Logic)
3. Complete Phase 3 (Unit Tests)
4. Complete Phase 4 (Repo + DB Reset)
5. Complete Phase 5 (Admin Phase CRUD backend)
6. Complete Phase 6 (US1: openai_compatible dispatch + public endpoints)
7. Complete Phase 11 (Keys page)
8. Complete Phase 12 (Project page)
9. **VALIDATE**: Admin adds DeepSeek via Admin API; user with DeepSeek key runs extraction → confirmed via quickstart Step 7
10. Deploy/demo

### Incremental Delivery After MVP

- Add US2 (Phase 7) → template providers usable
- Add US4 (Phase 8) → model tags searchable
- Add US5 (Phases 9 + 13) → routing endpoint + estimate page suggest-model
- Add US3 full UI (Phase 11 already done; Phases 13–14 for optimize/discover)
- Add US6 admin UI (Phase 15 — PhasesPage)
- Polish (Phase 16)
