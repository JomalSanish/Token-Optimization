# Token Optimizer v2 — Spec-Kit Prompt Pack

How to use this: run the commands in order inside your Spec-Kit-enabled repo. Paste
the prompt text under each command verbatim (edit anything in `[[double brackets]]`
first). Run `/speckit.analyze` after every phase, as you already do. This is a new
feature set on top of the existing `001-token-cost-estimator` — it becomes
`002-token-optimizer-v2`, it does not edit spec `001` in place.

Design decisions baked into these prompts (so you don't re-litigate them mid-run):
- No user accounts / no server-side auth change. Still fully stateless, still one
  shared secret for user endpoints and one for admin.
- Plan-tier model filtering is client-side and self-declared only — not backend data,
  not enforced.
- Provider calling logic is hybrid: a small set of popular providers get real,
  developer-shipped native code (like today), everything else uses a declarative
  adapter template stored in Mongo. Never admin-submitted code.
- Model routing (tag-based best-fit) is explicitly exempt from the reproducibility
  principle — only pricing calculation stays reproducible.
- Database is being wiped and reseeded, so every new field is mandatory, not optional.

---

## 1. `/speckit.constitution`

```
Amend the Token Optimizer constitution to a v2.0.0. This is a set of additive
principles and clarifications for a new feature phase (dynamic provider onboarding,
user-owned API keys, model capability tagging, and a React user dashboard). Do not
remove or weaken any existing principle unless explicitly told to below.

1. Amend Principle III (Bring-Your-Own-Key Execution Pattern):
   - Add: API key entry, storage, and provider/model selection for extraction MUST
     live in the user-facing dashboard, not the admin dashboard. The admin dashboard
     MUST NOT collect, store, or have any visibility into user-supplied provider keys.
   - Add: the model selected for the /extract call MUST be restricted to active
     models belonging to the provider the user just supplied a key for. This
     restriction applies ONLY to the /extract call. Once phase results exist, the
     user MAY reassign any active model from any provider to any phase — the platform
     does not require a key for models used only for deterministic phase-cost
     assignment, since /estimate and /optimize never call an LLM.

2. Add a new principle, "VIII. Hybrid Provider Dispatch: Native Code for Popular
   Providers, Declarative Templates for Everything Else":
   - Rule: The backend MAY ship real, developer-authored native implementations for
     a fixed, code-reviewed set of popular providers. At minimum this covers OpenAI,
     Anthropic, and Google/Gemini (their genuinely distinct request/response
     shapes), plus one parameterized "OpenAI-compatible" native implementation
     (configurable base_url) that covers DeepSeek and any other provider that
     mirrors the OpenAI chat-completions schema (e.g. Groq, Mistral, Together,
     Perplexity, Fireworks, OpenRouter) without needing separate code per provider.
   - Rule: Every other provider MUST be onboarded by storing a declarative adapter
     configuration in MongoDB (request URL template, HTTP method, header template,
     body template, response-text extraction path, error-message extraction path),
     interpreted by one generic dispatcher.
   - Rule: The backend MUST NOT execute admin-submitted code, scripts, or expressions
     of any kind to fulfill a provider call, regardless of dispatch path. A provider
     whose request/response shape matches neither a native implementation nor the
     declarative template is an accepted platform limitation, not a case requiring
     a code-execution escape hatch.
   - Rule: A provider record MUST declare its implementation_type
     (native | openai_compatible | template). native and openai_compatible MUST be
     restricted to a fixed, backend-exposed list of implementation keys the code
     actually registers (admin cannot invent a native key); openai_compatible MAY
     take an admin-supplied base_url override; template REQUIRES the full adapter
     template described above.
   - Rule: Adapter template and openai_compatible base URLs MUST be validated at
     save time (HTTPS only, reject requests that resolve to private/loopback/
     link-local address ranges) as an SSRF guard, since admins may point these at
     third-party endpoints unknown to the original developers.
   - Rationale: native code gives the best-tested behavior for the providers most
     users will actually pick, the OpenAI-compatible parameterization gets several
     more providers "for free" without per-provider code, and the declarative
     fallback keeps the platform open-ended without ever executing admin-supplied
     code. Closes the RCE surface identically to the pure-template approach while
     costing less quality on the providers that matter most.

3. Add a new principle, "IX. Model Capability Tagging & Best-Fit Routing":
   - Rule: Every model in the catalog MUST carry four admin-set capability tags,
     each a fixed dropdown enum with no admin-added values:
       - complexity_tier: simple | moderate | complex | frontier
       - reasoning_complexity: direct | single-step | multi-step | deep-reasoning
       - output_quality: draft | standard | high-fidelity | expert-grade
       - primary_use: one or more of extraction | classification | summarization |
         code-generation | reasoning | instruction-following | long-context |
         multimodal
   - Rule: Each phase MUST carry an admin-set default requirement for
     complexity_tier, reasoning_complexity, and output_quality, used to select the
     best-fit model for that phase within a given provider.
   - Rule: model routing/tag-based selection is explicitly EXEMPT from Principle IV
     (Reproducibility Over Cleverness). Re-running the same phase config after an
     admin retags a model MAY produce a different assigned model. Principle IV
     continues to apply, unmodified, to the pricing calculation engine itself —
     only routing/model-selection is exempted.
   - Rationale: the platform optimizes for the best-fit model available at the time
     of the request, not for byte-identical output across admin catalog changes.

4. Add a new principle, "X. Client-Declared, Non-Authoritative Plan Tiers":
   - Rule: any "plan" or "tier" concept used to filter which models a user sees MUST
     be implemented entirely client-side (frontend-only configuration), MUST NOT be
     stored in MongoDB, and MUST NOT be enforced by the backend in any way. It is a
     UI convenience only.
   - Rationale: consistent with Principle II/VI — introducing enforced plan
     entitlements would require server-side user identity, which is out of scope.

5. Amend "Technology Constraints & Architecture Standards" → Frontend Constraints:
   - Replace the existing frontend description with: the frontend is a React
     single-page application with client-side routing (e.g. React Router). It keeps
     two top-level areas: a User Dashboard (sidebar-navigated: API Keys, Project
     Details & Model Selection, Token Estimate, Optimization, AI Discovery) and an
     Admin Dashboard (Providers, Models, Pricing, Optimizer Rules, Phases). No
     server-side session state; localStorage remains the only persistence layer for
     user-side data (keys, project drafts, phase overrides, plan-tier selection).

6. Add to "Database & Secrets Management":
   - Note that the MongoDB instance is being reset for this version; all new fields
     introduced by this amendment (adapter templates, model tags, phase default
     tiers) are REQUIRED fields on their respective documents, not optional/
     migrated-with-defaults.

Bump to version 2.0.0 (principle additions + one amended principle = at least a
minor bump; treat as a documented, deliberate scope expansion). Regenerate the sync
impact report.
```

---

## 2. `/speckit.specify`

```
Create a new feature spec: 002-token-optimizer-v2.

## Summary
Rework the Token Optimizer platform's provider and model configuration to be
extensible — native code for the handful of providers that matter most, an
admin-only declarative template for everything else — move API key ownership from
the admin dashboard to a new multi-section user dashboard, add model capability
tagging with best-fit routing per phase, and rebuild the frontend as a routed React
SPA. Backend stays stateless per the constitution; MongoDB is being reset and
reseeded, so new fields are mandatory.

## In scope

### A. Admin Dashboard
Full CRUD, backed by MongoDB, for:
1. **Providers** — provider_id, display_name, active, implementation_type, and
   type-dependent config:
   - implementation_type = "native": pick from a fixed, backend-exposed list of
     registered native implementation keys (initially: openai, anthropic, google).
     No further config needed — the code already knows how to call it.
   - implementation_type = "openai_compatible": pick the openai_compatible native
     implementation and supply a base_url override (e.g. DeepSeek's endpoint, or
     Groq's, or Mistral's). Reuses the OpenAI request/response shape with a
     different host.
   - implementation_type = "template": full declarative adapter template required —
     base_url (with a {model_id} placeholder), http_method, headers (map of header
     name → template string; templates may reference {api_key}), body_template
     (JSON, may reference {model_id}, {system_prompt}, {user_prompt}), response_path
     (dot-path with array-index support, e.g. choices[0].message.content),
     error_path (dot-path for the provider's error message field).
   Provider creation is a single atomic form — implementation_type drives which
   fields are shown/required, but the record is saved as one unit either way.
   Reject non-HTTPS base_urls and base_urls that resolve to private/loopback/
   link-local addresses for both openai_compatible and template records.
2. **Models** — existing fields (provider, model_id, display_name, pricing,
   context_window, capabilities, active) plus four new mandatory fields, each a
   fixed-enum dropdown in the UI: complexity_tier, reasoning_complexity,
   output_quality, primary_use (multi-select). No free-text tag entry.
3. **Pricing** — retain existing versioned pricing update + pricing-history
   endpoints; surface in the new admin UI unchanged.
4. **Optimizer Rules** — retain existing CRUD, versioning, activate/deactivate;
   surface unchanged in the new admin UI.
5. **Phases** — NEW. CRUD for the phases collection (phase_id, name, sort_order,
   default_agent_role, default_cacheable_fraction, ams_classified — all already
   defined in schemas.py but currently unexposed via any admin route) plus three
   new mandatory fields: default_complexity_tier, default_reasoning_complexity,
   default_output_quality (same fixed enums as model tags). This is required for
   best-fit routing to have something to route against, and currently has no admin
   route despite repository-layer support already existing.

### B. Hybrid Provider Dispatch
Keep call_openai, call_anthropic, and call_gemini in llm_adapters.py largely as
they are today (native, developer-maintained code — this is where Gemini's
model-name-cleanup quirk etc. stays handled properly). Add:
- call_openai_compatible(base_url, model_id, api_key, system_prompt, user_prompt):
  same request/response shape as call_openai, but base_url is a parameter instead
  of hardcoded, so one function serves DeepSeek and any other OpenAI-schema
  provider an admin points at it.
- A generic template interpreter (new code, replacing nothing) for
  implementation_type = "template": loads the provider's adapter template from
  MongoDB, substitutes {model_id}, {api_key}, {system_prompt}, {user_prompt} into
  the url/headers/body, executes via httpx.AsyncClient, extracts response text via
  response_path or the error message via error_path on non-2xx.
- dispatch_llm_call becomes a three-way switch on the provider's
  implementation_type: native key → call the matching native function directly;
  openai_compatible → call_openai_compatible with the stored base_url; template →
  generic interpreter. All three paths preserve today's status-code mapping
  (401/429 passed through, everything else → 502).
Seed OpenAI, Anthropic, and Google as native provider rows (implementation_type =
native) and DeepSeek as an openai_compatible row with its real base_url — no
template needed for any of the four launch providers.

### C. User Dashboard (React, routed)
Sidebar with these routes, replacing the current two-tab layout:
1. **/keys — API Key Management.** Add/label/remove a key per provider (GET
   /providers for the active list). This is the current apiKeysService/localStorage
   behavior relocated out of admin.html into the user dashboard; no backend change
   to key handling itself (still never persisted server-side).
2. **/project — Project Details & Model Selection.** Text description, document
   upload, provider selection (only providers the user holds a key for), and a
   model dropdown scoped to GET /providers/{id}/models (active models under that
   provider only). Include an optional, purely client-side "Plan" selector that
   filters the model list against a static frontend-only mapping (plan → allowed
   model ids/tiers) — not backend data, not enforced, editable only by changing
   frontend config. This selection applies only to the /extract call.
3. **/estimate — Token Estimate.** Existing editable phase table (base/context
   input tokens, cacheable fraction, tool-call tokens, output tokens, estimated
   calls, confidence, source). Per-phase "assigned model" is no longer limited to
   the extraction-time provider — expose a full model picker grouped by provider
   across the whole active catalog, since /estimate performs no LLM call and needs
   no key for the assigned model. Include a "Suggest model" action per phase that
   calls the new routing endpoint (below) and pre-fills the pick, which the user
   can still override.
4. **/optimize — Optimization.** Existing optimizer output (per-phase triggered
   rules, combined reductions, savings) — no functional change, new UI shell only.
5. **/discover — AI Discovery & Coding-Tool Advisory.** Existing Step 4/Step 5
   behavior. The discovery LLM call reuses the same provider/model chosen at
   extraction time — it is not separately selectable on this screen.

### D. Best-Fit Model Routing
New endpoint (e.g. POST /route-model) that, given a phase_id and a provider_id,
returns the best-fit active model from that provider:
- Rank complexity_tier/reasoning_complexity/output_quality on their fixed 4-value
  ordinal scales (0–3 each, in the order listed in the constitution amendment).
- Prefer the cheapest model (by blended input/output rate) among models that meet
  or exceed the phase's default requirement on all three dimensions.
- If none meet the requirement, fall back to the model with the smallest total
  ordinal distance across all three dimensions from the requirement, regardless of
  whether that distance is above or below the requirement (nearest tier overall,
  not "nearest cheaper tier"). Tie-break by cheapest.
- This endpoint is explicitly non-reproducible across admin catalog edits, per
  constitution Principle IX — do not cache or snapshot its result the way pricing
  is snapshotted.
- Only considers models within the given provider — no cross-provider fallback;
  the user switches providers manually if the routed result is unsatisfactory.

## Out of scope (explicitly)
- Any server-side user account, login, session, or plan-entitlement enforcement.
- Admin-submitted executable code for provider calls.
- Reproducibility guarantees for routing/model-tag-based selection.
- Migrating old Mongo documents — the database is being dropped and reseeded, so
  no backward-compatible optional-field handling is needed for the new mandatory
  fields.

## Success criteria
- Admin can add DeepSeek purely through the admin UI as an openai_compatible
  provider (base_url only, zero backend code changes) and it's immediately usable
  from the user dashboard's key and model-selection screens.
- Admin can add a provider with a genuinely novel shape (e.g. Cohere, or any
  provider that is neither OpenAI-, Anthropic-, nor Gemini-shaped) purely through
  the admin UI using the full declarative template — no backend code changes —
  and it becomes usable the same way.
- A user with only an OpenAI key never sees Anthropic or Gemini models on the
  /project extraction screen, but can freely assign a Claude model to a phase on
  the /estimate screen.
- Existing /estimate and /optimize deterministic behavior and reproducibility
  guarantees are unchanged for identical pricing snapshots.
- Route-model endpoint returns a result for every phase/provider combination where
  the provider has at least one active model, even when no model meets the
  phase's stated requirement.
```

---

## 3. `/speckit.plan`

```
Generate the implementation plan for 002-token-optimizer-v2.

Backend (FastAPI, unchanged async/motor/httpx stack):
- Extend schemas.py: ModelIn/ModelOut gain complexity_tier, reasoning_complexity,
  output_quality (str enums), primary_use (list[str] enum) — all required, no
  default. ProviderIn/ProviderOut gain implementation_type (native |
  openai_compatible | template) plus a conditionally-required base_url (for
  openai_compatible) or AdapterTemplate sub-schema (for template). PhaseIn/PhaseOut
  gain default_complexity_tier, default_reasoning_complexity,
  default_output_quality — all required.
- New admin_api/routes.py phase endpoints (GET/POST/PATCH mirroring the existing
  model/provider pattern), wired to the existing repository.get_phases/
  create_phase plus new update/activate methods to add to repository.py.
- llm_adapters.py: keep call_openai/call_anthropic/call_gemini as-is; add
  call_openai_compatible(base_url, ...) as a thin parameterized wrapper around the
  same shape as call_openai; add a new generic template interpreter (small
  placeholder substitution helper + dot-path-with-[n]-index extractor) used only
  for implementation_type = "template". Rewrite dispatch_llm_call as a three-way
  switch on provider.implementation_type. Add a seed script updating scripts/ to
  insert OpenAI/Anthropic/Google as native rows and DeepSeek as an
  openai_compatible row.
- New src/routing.py (or similar): pure function taking (phase doc, provider's
  active models) → best-fit model, per the ranking/fallback rules in the spec. Unit
  test this in isolation like calc_engine.py already is.
- New endpoint in main.py: POST /route-model, protected by the existing shared-
  secret dependency, no LLM call involved (pure Mongo read + routing function).
- Update GET /providers/{id}/models (new or existing) to support the /project
  screen's provider-scoped model listing.
- Adapter template URL validation (HTTPS + private-IP-range rejection) as a
  reusable validator called from the provider create/update admin routes.

Frontend (React rewrite):
- Scaffold with your usual tooling (Vite + React Router, or your preferred stack —
  specify here if you have a house default); no framework-level state library
  required given everything server-relevant is stateless and everything
  client-relevant already lived in a single localStorage-backed service.
- Port apiKeysService.js logic into a /keys route/page largely as-is, just moved
  out of admin.js/admin.html.
- Build /project, /estimate, /optimize, /discover as routed pages sharing a layout
  with a persistent sidebar; port the existing app.js logic into these pages,
  splitting by concern (today it's one 20K file).
- Admin app becomes its own routed area (or separate app, your call) with pages
  for Providers (implementation_type switch driving which fields show — native
  key picker, base_url field, or full adapter template form), Models (incl. the
  four dropdowns), Pricing, Optimizer Rules, and the new Phases page.
- Preserve the shared-secret header and provider-key header behavior exactly as
  today; no new client-side auth is being introduced.

Testing:
- Extend calc-engine-style unit tests to cover the new routing function in
  isolation (no network/DB), covering: exact match, no-match-fallback-above,
  no-match-fallback-below, tie-break-by-price.
- Add adapter-template interpreter tests using a stub httpx transport, covering at
  least one synthetic "generic REST" shape to prove the interpreter isn't
  accidentally coupled to any native provider's quirks; separately test
  call_openai_compatible against a stubbed DeepSeek-shaped response to confirm the
  base_url parameterization doesn't leak assumptions from call_openai.
- Extend the existing concurrency integration test (10+ concurrent requests,
  independently rotating key pools) to include a request against a
  freshly-admin-added provider mid-test, confirming no cross-request leakage.

Constitution check: confirm the plan doesn't reintroduce server-side user identity,
doesn't store or execute admin-submitted code anywhere (native providers are
developer-shipped, code-reviewed, and fixed — not admin-editable beyond picking a
key or a base_url), and keeps pricing-calculation reproducibility untouched while
explicitly not attempting reproducibility for /route-model.
```

---

## 4. `/speckit.tasks`

```
Generate the task breakdown for 002-token-optimizer-v2 from the plan above.
Order tasks so that backend schema + adapter-template interpreter + routing
function (with their unit tests) land before the endpoints that depend on them,
and before any frontend work that consumes those endpoints. Keep the admin-side
Phase CRUD task early, since /route-model has no data to route against until
phase default tiers exist. Call out the database reset/reseed script as its own
task, gated to run only after all new required fields are finalized in schemas.py
— reseeding against a still-changing schema would need to be repeated.
```

---

## Notes for you, not for Spec-Kit

- DeepSeek's API is OpenAI-compatible (same chat-completions request/response
  shape, different host), so it doesn't need its own hand-written adapter — it
  rides the openai_compatible native path via a base_url override. The same is
  true of Groq, Mistral, Together, Perplexity, Fireworks, and OpenRouter, so that
  one parameterized function gets you most of the "few more" for free. If you
  later hit a provider that genuinely diverges (different auth scheme, different
  response envelope), that's exactly the case the declarative template exists for.
- I did not include a task for reproducibility-snapshotting model routing — you
  explicitly said routing changing over time is fine, so I left that requirement
  out entirely rather than writing it in and immediately contradicting it.
- Phase CRUD wasn't in your original ask; I added it because the routing feature
  is unbuildable without a place to store each phase's default tier requirement,
  and the repository layer already half-expects it (`get_phases`/`create_phase`
  exist with no route ever calling them).
- The "Plan" selector on /project is specified as frontend-only config (a plain
  JS/TS object mapping plan names to allowed models or tiers) rather than
  anything server-driven, per your answer — worth deciding where that mapping
  lives (checked into the repo vs. something you can tweak without a redeploy)
  when you get to `/speckit.plan` review, since the spec above doesn't pin that
  down.
