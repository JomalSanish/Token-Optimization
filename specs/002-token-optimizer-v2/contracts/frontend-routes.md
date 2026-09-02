# Frontend Route Contract: Token Optimizer v2

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03

The frontend is a React SPA scaffolded with Vite, using React Router v6 nested routes.
All routes are client-side only. The backend has no concept of frontend routes.

---

## Route Tree

```
/                         → redirect to /keys
│
├── <UserLayout>          (persistent sidebar: API Keys, Project, Estimate, Optimize, Discover)
│   ├── /keys             → KeysPage
│   ├── /project          → ProjectPage
│   ├── /estimate         → EstimatePage
│   ├── /optimize         → OptimizePage
│   └── /discover         → DiscoverPage
│
└── <AdminLayout>         (persistent sidebar: Providers, Models, Pricing, Rules, Phases)
    ├── /admin/providers  → ProvidersPage
    ├── /admin/models     → ModelsPage
    ├── /admin/pricing    → PricingPage
    ├── /admin/rules      → RulesPage
    └── /admin/phases     → PhasesPage
```

---

## Page Contracts

### /keys — KeysPage

**Purpose**: Add, label, and remove API keys per provider.

**Data sources**:
- `GET /providers` (backend) — list of active providers to show in picker
- `localStorage["apiKeys"]` — current stored keys

**State mutations**:
- Add key → writes to `localStorage` only; no backend call
- Remove key → writes to `localStorage` only; no backend call

**Key rule**: No network call persists a key. The admin layout has no access to this page or
its data.

---

### /project — ProjectPage

**Purpose**: Enter project description, upload documents, select provider + model for extraction,
optionally apply plan tier filter.

**Data sources**:
- `localStorage["apiKeys"]` — determines which providers appear in the provider picker
  (only providers with at least one non-exhausted key)
- `GET /providers/{provider_id}/models` (backend) — model list for the selected provider

**State mutations**:
- Provider selection → triggers model list fetch
- Plan tier selection → filters model list client-side using `PLAN_TIERS` config; NOT sent to backend
- "Extract" action → `POST /extract` with `X-Provider-Key` from `localStorage`

**Key rules**:
- Provider picker shows ONLY providers for which the user holds a key in localStorage.
- Model picker shows ONLY active models from the selected provider (the GET /providers/{id}/models response).
- Plan tier filter is applied client-side after the model list is fetched; it is a UI-only filter.

---

### /estimate — EstimatePage

**Purpose**: Edit phase table, assign models per phase, get cost estimate.

**Data sources**:
- Phase table state: from prior `/extract` response stored in sessionStorage/state, or manually entered
- `GET /models` (backend) — full active model catalog across all providers (for the per-phase model picker)
- `POST /route-model` (backend) — on "Suggest model" click per phase

**State mutations**:
- Edit phase fields → local state only
- Assign model per phase → local state; NOT sent to backend until estimate is requested
- "Suggest model" → `POST /route-model` → pre-fills picker (user can override)
- "Estimate" action → `POST /estimate`

**Key rules**:
- Per-phase model picker spans the FULL active catalog (all providers) — not limited to the extraction provider.
- No `X-Provider-Key` is required for the estimate flow.

---

### /optimize — OptimizePage

**Purpose**: Display optimizer output (triggered rules, savings, advisory recommendations).

**Data sources**:
- Prior `/estimate` response (from page state/sessionStorage)
- `POST /optimize` (backend)

**State mutations**:
- "Optimize" action → `POST /optimize` using the prior estimate snapshot

**Key rules**: No change to optimizer behavior or response shape.

---

### /discover — DiscoverPage

**Purpose**: AI-powered discovery of additional optimization opportunities.

**Data sources**:
- Prior estimate and optimize results (from page state/sessionStorage)
- Provider + model from extraction session (stored in sessionStorage)
- `POST /discover-optimizations` (backend)

**State mutations**:
- "Discover" action → `POST /discover-optimizations` with `X-Provider-Key` from localStorage
  using the same provider chosen at extraction time

**Key rules**:
- No separate provider/model picker on this screen.
- If no prior extraction session, the discover action is disabled.

---

### /admin/providers — ProvidersPage

**Purpose**: Full CRUD for providers.

**Data sources**: `GET /admin/providers`

**State mutations**:
- Create provider → `POST /admin/providers`; form fields change based on `implementation_type`:
  - `native`: shows `native_key` picker (populated from a frontend constant listing the fixed keys)
  - `openai_compatible`: shows `base_url` text field
  - `template`: shows all six adapter template fields
- Update provider status → `PATCH /admin/providers/{id}`

**Key rules**:
- No field on this page collects, displays, or references user-supplied API keys.
- `native_key` picker uses a static frontend list matching the backend's `NATIVE_REGISTRY`.

---

### /admin/models — ModelsPage

**Purpose**: Full CRUD for models including capability tags.

**Data sources**: `GET /admin/models`

**State mutations**:
- Create/update model → includes four required capability tag dropdowns
- Activate/deactivate → `POST /admin/models/{id}/activate|deactivate`
- Update pricing → `PATCH /admin/models/{id}`

**Key rules**:
- All four capability tag fields use `<select>` elements with only the fixed enum values.
- No free-text tag entry.

---

### /admin/phases — PhasesPage (NEW)

**Purpose**: Full CRUD for phases including default capability requirements.

**Data sources**: `GET /admin/phases`

**State mutations**:
- Create phase → `POST /admin/phases`; includes three required default capability dropdowns
- Edit phase → `PATCH /admin/phases/{id}`

---

### /admin/pricing — PricingPage
### /admin/rules — RulesPage

Ported from existing `admin.js/admin.html` — behavior and API calls unchanged.

---

## Persistent State Conventions

| Data | Storage | Lifetime |
|------|---------|----------|
| API keys (all providers) | `localStorage["apiKeys"]` | Until user removes |
| Plan tier selection | `localStorage["planTier"]` | Until user changes |
| Extraction result (phases) | `sessionStorage["extractResult"]` | Session |
| Estimate result | `sessionStorage["estimateResult"]` | Session |
| Optimize result | `sessionStorage["optimizeResult"]` | Session |
| Extraction provider + model | `sessionStorage["extractionContext"]` | Session |

No data is ever sent to the backend for storage. The backend is fully stateless.
