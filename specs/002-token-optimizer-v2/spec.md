# Feature Specification: Token Optimizer v2 — Extensible Provider Dispatch, User Dashboard & Model Routing

**Feature Branch**: `002-token-optimizer-v2`

**Created**: 2026-09-03

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Admin Registers a New OpenAI-Compatible Provider (Priority: P1)

An administrator opens the Admin Dashboard and creates a new provider record for
DeepSeek. The admin selects "OpenAI-compatible" as the implementation type, enters
DeepSeek's API base URL, and saves. No code is deployed. A user who holds a
DeepSeek API key immediately sees DeepSeek in the provider picker on the User
Dashboard and can select DeepSeek models for extraction.

**Why this priority**: This is the flagship extensibility story — it validates the
entire hybrid dispatch pipeline end-to-end and demonstrates the zero-code-deploy
promise for compatible providers. All other provider stories depend on this
infrastructure being sound.

**Independent Test**: An admin can add a new OpenAI-compatible provider via the
Admin Dashboard, and a user with a valid key for that provider can run a successful
extraction using a model from that provider — without any backend code changes.

**Acceptance Scenarios**:

1. **Given** the Admin Dashboard has no DeepSeek provider, **When** the admin
   submits a valid openai_compatible provider form with DeepSeek's base URL,
   **Then** the provider appears in the active provider list and the system
   validates the URL is HTTPS and not a private/loopback address before saving.

2. **Given** a saved openai_compatible DeepSeek provider, **When** a user enters
   their DeepSeek API key on the /keys page and navigates to /project, **Then** the
   provider picker shows DeepSeek and the model dropdown is populated exclusively
   with active DeepSeek models.

3. **Given** the user selects a DeepSeek model and submits a project description,
   **When** the extraction request is processed, **Then** the system dispatches
   the LLM call using the OpenAI-compatible call path with DeepSeek's base URL
   and the key is never stored server-side.

4. **Given** an admin attempts to save an openai_compatible provider with an HTTP
   (non-HTTPS) URL or a URL that resolves to a private IP range, **Then** the save
   is rejected with a clear error message identifying the SSRF-guard violation.

---

### User Story 2 — Admin Registers a Declarative Template Provider (Priority: P2)

An administrator onboards a provider with a genuinely novel request/response shape
(e.g., Cohere) using the Admin Dashboard's "Template" option. The admin fills in
the base URL, HTTP method, header template, body template, and the dot-paths for
extracting the response text and error message. Once saved, the provider becomes
available to users the same way as native providers.

**Why this priority**: This validates the declarative escape-hatch for the long
tail of providers. Without it, providers that don't share OpenAI's schema are
simply unavailable — blocking platform openness.

**Independent Test**: An admin can describe a novel provider entirely through form
fields and a user can immediately use that provider for extraction — without
writing or deploying any code.

**Acceptance Scenarios**:

1. **Given** the admin selects "template" as implementation type, **When** they
   fill in all required adapter fields and save, **Then** the record is persisted
   with all adapter template fields intact.

2. **Given** a saved template provider, **When** a user selects it and triggers
   extraction, **Then** the generic dispatcher substitutes `{model_id}`,
   `{api_key}`, `{system_prompt}`, `{user_prompt}` into the stored template and
   calls the provider endpoint, returning the extracted text from `response_path`.

3. **Given** a non-2xx response from the provider, **When** the dispatcher reads
   the `error_path` field, **Then** the error message is surfaced to the user
   alongside the appropriate status code mapping.

4. **Given** an admin attempts to supply any executable code, script, or expression
   in any template field, **Then** the system stores only the literal static
   template (no execution) and the field is treated as a plain string — the
   platform's limitation is documented, not a code-execution path.

---

### User Story 3 — User Manages API Keys in the User Dashboard (Priority: P2)

A user opens the User Dashboard, navigates to /keys, and adds a labelled API key
for one or more active providers. The keys are stored in the browser only. The
user can remove a key at any time. The Admin Dashboard has no visibility into
these keys.

**Why this priority**: Key management in the User Dashboard is a prerequisite for
the extraction flow (Story 1). The admin isolation rule is a security requirement
from the constitution.

**Independent Test**: A user can add, label, and remove a provider API key from
the /keys screen; the key persists in the browser only and the admin panel exposes
no UI for viewing or collecting user keys.

**Acceptance Scenarios**:

1. **Given** a list of active providers fetched from the backend, **When** the user
   enters an API key and an optional label for a provider and saves, **Then** the
   key is stored in browser-local storage and confirmed with a success state — no
   network request is made to persist the key.

2. **Given** stored keys, **When** the user navigates to /project, **Then** only
   providers for which the user holds a key appear in the provider picker.

3. **Given** a user key is removed, **When** the user returns to /project, **Then**
   that provider no longer appears in the extraction provider picker.

4. **Given** the Admin Dashboard, **When** any admin-facing screen is visited,
   **Then** no field, endpoint, or display area exposes or references user-supplied
   provider keys.

---

### User Story 4 — Admin Tags Models with Capability Metadata (Priority: P2)

An admin opens the Models section of the Admin Dashboard, edits an existing model,
and sets its four capability tags using fixed dropdown menus: complexity_tier,
reasoning_complexity, output_quality, and primary_use (multi-select). There is no
free-text tag entry. The saved tags become the basis for best-fit routing.

**Why this priority**: Model capability tags are required for routing (Story 5) and
are mandatory fields on all model documents per the v2.0.0 constitution — they must
be present for any model to be valid.

**Independent Test**: An admin can set all four capability tags for a model and
save; the model appears with its tags when listed, and no model can be saved without
all four tags populated.

**Acceptance Scenarios**:

1. **Given** an admin edits a model, **When** they open any capability tag dropdown,
   **Then** only the fixed enum values for that tag are offered — no free-text
   input, no admin-added custom values.

2. **Given** all four tags are set and the admin saves, **Then** the model record
   stores the tags and they are reflected immediately in the model listing.

3. **Given** an admin attempts to save a model without all four tags populated,
   **Then** the save is rejected with a validation error identifying the missing
   fields.

4. **Given** a provider has models with differing tag values, **When** the routing
   endpoint is called for a phase under that provider, **Then** the response
   reflects the model whose tags best match the phase requirements.

---

### User Story 5 — Best-Fit Model is Suggested Per Phase on the Estimate Screen (Priority: P3)

On the /estimate screen, a user sees the phase table with per-phase assigned model
pickers. Clicking "Suggest model" for a phase and a provider calls the routing
endpoint and pre-fills the model picker with the best-fit result — which the user
can still override manually. Assigned models on the estimate screen are not limited
to the extraction provider.

**Why this priority**: This completes the capability tagging loop but can be
deferred without blocking earlier stories. The estimate screen remains usable
(with manual model selection) even if routing is not yet wired to the "Suggest"
action.

**Independent Test**: Clicking "Suggest model" for a phase returns a model
suggestion that matches the routing algorithm's output and pre-fills the picker;
the user can still select any other active model from any provider.

**Acceptance Scenarios**:

1. **Given** a phase with default capability requirements and a provider with
   tagged active models, **When** the user clicks "Suggest model", **Then** the
   picker is pre-filled with the cheapest model meeting or exceeding all three
   requirement dimensions.

2. **Given** no model meets the phase requirement, **When** the routing endpoint
   is called, **Then** it returns the model with the smallest aggregate ordinal
   distance across all three dimensions, tie-broken by cheapest cost.

3. **Given** the user accepts the suggestion, **When** the estimate is calculated,
   **Then** the assigned model is used for cost computation alongside the pricing
   snapshot — the routing choice is not re-derived during calculation.

4. **Given** the user overrides the suggestion with a different model, **Then**
   the override is preserved and used for all subsequent calculations until the
   user changes it again.

5. **Given** the full model catalog spans multiple providers, **When** the user
   opens the model picker for any phase, **Then** models are presented grouped by
   provider (provider name visible as a group header), not as one undifferentiated
   flat list.

---

### User Story 6 — Admin Manages Phases with Capability Requirements (Priority: P3)

An admin creates or edits a phase record through the Admin Dashboard's new Phases
section. Each phase has a sort order, name, default agent role, default cacheable
fraction, and three new required fields — default_complexity_tier,
default_reasoning_complexity, and default_output_quality — used to determine best-
fit model routing for that phase.

**Why this priority**: Phase CRUD is the last prerequisite for the routing story.
It can be deferred (phases pre-seeded via reset) but is required for full admin
self-service.

**Independent Test**: An admin can create a phase with all required fields through
the Admin Dashboard; the phase appears in the system and the routing endpoint
returns valid suggestions against it.

**Acceptance Scenarios**:

1. **Given** the admin creates a new phase, **When** they set a sort order, name,
   agent role, cacheable fraction, and all three default capability requirement
   fields, **Then** the phase is saved and appears in the phase list.

2. **Given** an admin attempts to save a phase without one of the three default
   capability requirement fields, **Then** the save is rejected with a clear
   validation error.

3. **Given** a saved phase, **When** a user calls "Suggest model" for that phase
   on the /estimate screen, **Then** the routing endpoint uses the phase's
   stored default requirements to rank available models.

---

### Edge Cases

- What happens when a provider has no active models? The model picker on /project
  shows an empty list with a message; the routing endpoint returns HTTP 200 with a
  structured `match_type: "none"` body (see FR-026) — deliberately not a 404 or any
  other error status, since "provider configured but temporarily has no active
  models" is an expected state, not a fault.
- What happens when the user's browser storage is cleared? All stored keys are
  lost; the user is shown an empty /keys screen and must re-enter them — no server-
  side recovery path exists per the stateless constitution.
- What happens when an admin retags a model after phase results already exist? The
  routing endpoint reflects the new tags immediately; previously assigned models in
  the user's local estimate state are not changed unless the user explicitly clicks
  "Suggest model" again.
- What happens when the template provider's endpoint returns an unexpected response
  structure (response_path not found)? The dispatcher returns a structured error;
  the user is shown a provider-configuration error message, not a raw stack trace.
- What happens when an admin tries to use an implementation_type not registered in
  the backend's native key list? The save is rejected with an error listing the
  valid native keys.
- What happens when two models tie on ordinal distance and cost in routing? The
  system selects deterministically (e.g., by lexicographic model_id order) to
  produce a consistent result for the same catalog state.

## Requirements *(mandatory)*

### Functional Requirements

**Provider Management**

- **FR-001**: The system MUST support three implementation types for providers:
  `native` (from a fixed backend-registered list), `openai_compatible` (parameterized
  with a `base_url`), and `template` (full declarative adapter).
- **FR-002**: The admin MUST be able to create, read, update, and deactivate
  provider records through the Admin Dashboard in a single atomic form, with
  implementation-type-appropriate fields shown or hidden dynamically.
- **FR-003**: The system MUST reject any provider save where `base_url` (for
  `openai_compatible` or `template`) is not HTTPS or resolves to a private,
  loopback, or link-local address range.
- **FR-004**: The `native` implementation_type MUST be restricted at save time to
  keys registered in the backend's fixed implementation list; admin-invented keys
  MUST be rejected.
- **FR-005**: Template adapter fields (request_url, http_method, header_template,
  body_template, response_text_path, error_message_path) MUST all be required when
  implementation_type is `template`.

**Model Management**

- **FR-006**: Every model record MUST carry four capability tags — `complexity_tier`,
  `reasoning_complexity`, `output_quality`, `primary_use` — each populated from a
  fixed enum; free-text or admin-added enum values MUST be rejected.
- **FR-007**: The system MUST reject any model save where any of the four capability
  tags is absent.
- **FR-008**: The admin MUST be able to set capability tags via fixed dropdown (or
  multi-select for `primary_use`) controls in the Admin Dashboard model form.

**Phase Management**

- **FR-009**: The system MUST expose full CRUD for the phases collection through the
  Admin Dashboard, including all existing phase fields and the three new required
  capability requirement fields (`default_complexity_tier`,
  `default_reasoning_complexity`, `default_output_quality`).
- **FR-010**: The system MUST reject any phase save where any of the three default
  capability requirement fields is absent.

**Provider Dispatch**

- **FR-011**: The dispatch layer MUST route a call to the appropriate native function,
  the parameterized OpenAI-compatible function, or the generic template interpreter
  based solely on the provider's stored `implementation_type`.
- **FR-012**: The generic template interpreter MUST substitute `{model_id}`,
  `{api_key}`, `{system_prompt}`, and `{user_prompt}` into the adapter template
  before calling the provider; it MUST NOT execute any code or expression found in
  the template.
- **FR-013**: The dispatch layer MUST map provider HTTP status 401 and 429 responses
  through directly; all other non-2xx responses MUST be mapped to a 502 response
  for the caller.
- **FR-014**: The backend MUST NOT log, cache, or persist user-supplied API keys at
  any point in the dispatch path.

**User Dashboard**

- **FR-015**: The User Dashboard MUST provide a /keys route where users can add, label,
  and remove provider API keys; storage MUST be browser-local only with no server-side
  write for key data.
- **FR-016**: The /project route MUST populate the provider picker only with providers
  for which the user holds a local key, and MUST restrict the model dropdown to active
  models belonging to the selected provider.
- **FR-017**: The /project route MUST include a client-side-only "Plan" selector that
  filters the model list against a static frontend configuration; this filtering MUST
  NOT be enforced by the backend or stored in the database.
- **FR-018**: The /estimate route MUST offer a model picker per phase that spans the
  full active model catalog across all providers (not limited to the extraction
  provider), because the estimate calculation requires no API key. The picker MUST
  visually group models by provider (not present as one flat list), so a catalog
  spanning many providers and models stays navigable.
- **FR-019**: The /estimate route MUST include a "Suggest model" action per phase that
  calls the routing endpoint and pre-fills the picker; the pre-fill MUST be
  user-overridable.
- **FR-020**: The /discover route MUST reuse the provider and model selected at
  extraction time for any discovery LLM call; no separate provider/model selector
  appears on this screen.
- **FR-021**: The Admin Dashboard MUST NOT present any field, display area, or
  endpoint that collects, stores, or displays user-supplied provider API keys.

**Best-Fit Model Routing**

- **FR-022**: The routing endpoint MUST accept a `phase_id` and a `provider_id` and
  return the best-fit active model from that provider for the phase.
- **FR-023**: Routing MUST prefer the cheapest model (by blended input/output rate)
  among models that meet or exceed the phase's default requirement on all three
  ordinal dimensions (complexity_tier, reasoning_complexity, output_quality).
- **FR-024**: When no model meets the requirement, routing MUST fall back to the model
  with the smallest aggregate ordinal distance across all three dimensions, tie-broken
  by cheapest cost, then by model_id lexicographically.
- **FR-025**: The routing endpoint MUST NOT cache its result or treat the response
  as reproducible across admin catalog changes (tags, pricing, active status).
- **FR-026**: The routing endpoint MUST return a valid HTTP 200 result for any
  phase/provider combination where both the phase and the provider exist — including
  a structured `match_type: "none"` response (not an HTTP error) when the provider
  exists but currently has zero active models. HTTP 404 is reserved for a `phase_id`
  or `provider_id` that does not exist at all.

**Deterministic Engine (unchanged)**

- **FR-027**: The /estimate and /optimize endpoints MUST continue to return identical
  results for identical phase configurations, model identifier sets, pricing database
  snapshots, and optimizer-rule versions, regardless of model tag changes.
- **FR-028**: All pricing computations MUST use the verified database pricing snapshot;
  user-supplied prices MUST NOT be accepted as authoritative.

### Key Entities *(include if feature involves data)*

- **Provider**: Represents an LLM provider. Attributes: `provider_id`, `display_name`,
  `active`, `implementation_type` (`native` | `openai_compatible` | `template`), and
  type-specific config fields (`native_key`, `base_url`, or the full adapter template
  sub-document). `implementation_type` is required; no provider can exist without it.

- **Model**: Represents a specific LLM model available via a provider. Attributes:
  existing fields (provider reference, `model_id`, `display_name`, pricing, context
  window, capabilities, active status) plus four required capability tags:
  `complexity_tier`, `reasoning_complexity`, `output_quality`, `primary_use`.

- **Phase**: Represents a structured project workflow stage. Attributes: `phase_id`,
  `name`, `sort_order`, `default_agent_role`, `default_cacheable_fraction`,
  `ams_classified`, plus three new required fields: `default_complexity_tier`,
  `default_reasoning_complexity`, `default_output_quality`.

- **Adapter Template** (sub-document on a `template` provider): `request_url`,
  `http_method`, `header_template` (map), `body_template` (object), `response_text_path`
  (dot-path string), `error_message_path` (dot-path string). All six fields required.

- **User Key Record** (client-side only, never in MongoDB): `provider_id`,
  `display_label`, `api_key`. Lives in browser localStorage; no server representation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can onboard a new OpenAI-compatible provider
  (e.g., DeepSeek) entirely through the Admin Dashboard — without any code
  deployment — and it is immediately usable by a user who holds a key for it.

- **SC-002**: An administrator can onboard a provider with a non-OpenAI request/
  response shape entirely through the declarative template form — without any code
  deployment — and it is immediately usable for extraction.

- **SC-003**: A user who holds only an OpenAI key sees exclusively OpenAI models
  on the extraction model picker; after adding a second key, both providers appear
  without any page reload-based data refresh requiring admin involvement.

- **SC-004**: The routing endpoint returns a deterministic best-fit model for every
  phase/provider pair where at least one active model exists for the provider,
  including the fallback case where no model fully meets the phase requirement.

- **SC-005**: Running /estimate or /optimize with identical inputs before and after
  an admin retags a model produces identical cost outputs — tag changes affect only
  routing suggestions, not the pricing calculation engine.

- **SC-006**: All four model capability tags are enforced as required fields at
  write time; no model can be saved without all four populated, and the admin UI
  offers only the fixed enum values for each tag.

- **SC-007**: No API key supplied by a user via the /keys screen is persisted to
  the database, present in backend logs, or visible anywhere in the Admin Dashboard.

- **SC-008**: Attempting to save a provider with an HTTP (non-HTTPS) base URL or
  a base URL that resolves to a private IP range is rejected before the record is
  written to the database, with a user-legible error.

## Assumptions

- The MongoDB instance is being fully reset for v2.0.0; no backward-compatible
  handling for pre-existing documents without the new required fields is needed.
  New fields are required at write time, not optional with defaults.
- The fixed set of native implementation keys registered in the backend at v2.0.0
  launch is: `openai`, `anthropic`, `google`. The `openai_compatible` type is a
  fourth dispatch path, not a native key.
- DeepSeek, Groq, Mistral, Together, Perplexity, Fireworks, and OpenRouter are all
  served by the `openai_compatible` path — no separate code per provider.
- Seed data for the reset database includes OpenAI, Anthropic, and Google as
  `native` rows, and DeepSeek as an `openai_compatible` row — giving four ready-to-
  use providers from day one with no template configuration required.
- The ordinal ranking for routing dimensions uses the order listed in the
  constitution: complexity_tier (simple=0, moderate=1, complex=2, frontier=3);
  reasoning_complexity (direct=0, single-step=1, multi-step=2, deep-reasoning=3);
  output_quality (draft=0, standard=1, high-fidelity=2, expert-grade=3).
- "Blended input/output rate" for cost tie-breaking is defined as (input_price_per_1k
  + output_price_per_1k) / 2, using values already present in the model pricing
  document.
- The client-side "Plan" selector on /project is seeded via a static frontend
  configuration file (e.g., a constants or config module); it is not fetched from
  the backend and is not user-editable at runtime.
- The /discover route's LLM call uses the provider and model stored in the browser
  session from the extraction step; if no extraction has been run in the session the
  discovery call is disabled.
- The existing /estimate and /optimize endpoint contracts (request/response shapes,
  error codes, pricing snapshot semantics) are not changed by this feature.
- User-facing plan tiers are a UI-only filter and are never checked, stored, or
  referenced by the backend in any form.
