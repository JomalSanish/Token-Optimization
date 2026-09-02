# Data Model: Token Optimizer v2

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03

All collections live in MongoDB Atlas. The instance is reset for v2.0.0 — all new fields are
REQUIRED on their documents; no optional-with-defaults migration is needed.

---

## Collection: `providers`

Stores one document per LLM provider. The `implementation_type` field determines which dispatch
path the backend uses and which additional fields are required.

```
providers document
├── provider_id          : str          — unique slug (e.g. "openai", "deepseek")
├── display_name         : str          — human-readable name
├── active               : bool         — whether visible to users
├── implementation_type  : str (enum)   — REQUIRED; one of: "native" | "openai_compatible" | "template"
│
│   [when implementation_type = "native"]
├── native_key           : str          — REQUIRED; must match a key in the backend's fixed
│                                         NATIVE_REGISTRY dict (e.g. "openai", "anthropic", "google")
│
│   [when implementation_type = "openai_compatible"]
├── base_url             : str          — REQUIRED; HTTPS URL, SSRF-validated at save time
│                                         (e.g. "https://api.deepseek.com/v1")
│
│   [when implementation_type = "template"]
├── adapter_template     : object       — REQUIRED sub-document:
│   ├── request_url          : str      — HTTPS URL with optional {model_id}; SSRF-validated
│   ├── http_method          : str      — e.g. "POST"
│   ├── header_template      : object   — map of header name → static template string
│   │                                     (may reference {api_key})
│   ├── body_template        : object   — JSON structure with optional references to
│   │                                     {model_id}, {system_prompt}, {user_prompt}
│   ├── response_text_path   : str      — dot-path with [n] index support (e.g. "choices[0].message.content")
│   └── error_message_path   : str      — dot-path for the provider's error message field
│
├── created_at           : datetime
└── updated_at           : datetime
```

**Validation rules**:
- `implementation_type` must be one of the three enum values; reject any other value.
- `native`: `native_key` must match a key registered in the backend's fixed `NATIVE_REGISTRY`;
  admin-invented keys are rejected at save time with a 422 listing valid keys.
- `openai_compatible`: `base_url` is required; must be HTTPS; must not resolve to private/
  loopback/link-local addresses.
- `template`: all six `adapter_template` sub-fields are required; `request_url` is SSRF-validated
  using the same validator as `openai_compatible.base_url`.

**Seed data** (v2.0.0 reset):
| provider_id | implementation_type | native_key / base_url |
|-------------|--------------------|-----------------------|
| openai      | native             | openai                |
| anthropic   | native             | anthropic             |
| google      | native             | google                |
| deepseek    | openai_compatible  | https://api.deepseek.com/v1 |

---

## Collection: `models`

Stores one document per model. All four capability tags are required for every document.

```
models document
├── provider             : str          — provider_id reference
├── model_id             : str          — unique within provider (e.g. "gpt-4o")
├── display_name         : str
├── pricing              : object
│   ├── input_per_1m         : Decimal
│   ├── output_per_1m        : Decimal
│   ├── cached_input_per_1m  : Decimal
│   ├── batch_input_per_1m   : Decimal
│   └── batch_output_per_1m  : Decimal
├── pricing_version      : int
├── effective_from       : datetime
├── context_window       : int
├── capabilities         : list[str]    — existing free-text list (e.g. ["text","vision"])
├── active               : bool
│
│   [NEW — all four required, no defaults]
├── complexity_tier      : str (enum)   — "simple" | "moderate" | "complex" | "frontier"
├── reasoning_complexity : str (enum)   — "direct" | "single-step" | "multi-step" | "deep-reasoning"
├── output_quality       : str (enum)   — "draft" | "standard" | "high-fidelity" | "expert-grade"
├── primary_use          : list[str]    — one or more of: "extraction" | "classification" |
│                                         "summarization" | "code-generation" | "reasoning" |
│                                         "instruction-following" | "long-context" | "multimodal"
│
├── created_at           : datetime
└── updated_at           : datetime
```

**Validation rules**:
- All four tag fields are required; reject any model save where any is absent.
- Enum values are fixed; admin UI offers only the listed values (no free-text entry).
- `primary_use` is a non-empty list; at least one value required.
- `(provider, model_id)` composite is unique.

**Routing ordinal mapping** (used by `routing.py`, not stored):
| Field               | Values in ordinal order (0→3)                                       |
|---------------------|---------------------------------------------------------------------|
| complexity_tier     | simple, moderate, complex, frontier                                 |
| reasoning_complexity| direct, single-step, multi-step, deep-reasoning                     |
| output_quality      | draft, standard, high-fidelity, expert-grade                        |

---

## Collection: `phases`

One document per workflow phase. Previously unexposed via admin routes; fully exposed in v2.

```
phases document
├── phase_id                    : str     — unique slug (e.g. "requirement", "design")
├── name                        : str     — display name
├── sort_order                  : int     — determines phase ordering in the estimate table
├── default_agent_role          : str     — pre-filled agent role for extraction
├── default_cacheable_fraction  : Decimal — pre-filled cacheable fraction (0.0–1.0)
├── ams_classified              : bool    — whether the phase counts in AMS annualized calc
│
│   [NEW — all three required, no defaults]
├── default_complexity_tier     : str (enum) — same enum as model.complexity_tier
├── default_reasoning_complexity: str (enum) — same enum as model.reasoning_complexity
└── default_output_quality      : str (enum) — same enum as model.output_quality
```

**Validation rules**:
- All three new default requirement fields are required; reject phase saves where any is absent.
- Enum values match the model capability tag enums exactly.
- `phase_id` is unique.

---

## Collection: `optimizer_rules`

Unchanged from v1. No new fields.

---

## Collection: `pricing_history`

Unchanged from v1. No new fields.

---

## Client-Side Only: User Key Records (localStorage)

Not stored in MongoDB. Kept in browser localStorage keyed by `"apiKeys"`.

```
localStorage["apiKeys"] = {
  "<provider_id>": [
    {
      id        : str      — client-generated unique id
      key       : str      — the raw API key (never sent to the backend except as X-Provider-Key header)
      label     : str      — user-supplied label
      exhausted : bool     — whether the key has hit a 429
      lastUsedAt: str|null — ISO timestamp
    },
    ...
  ],
  ...
}
```

The key object shape is generalized from the existing `api_keys.js` — the hardcoded
`{ openai: [], google: [], anthropic: [] }` default is replaced with a dynamic provider_id map.

---

## Client-Side Only: Plan Tier Config (frontend constant)

Not stored in MongoDB, not fetched from the backend.

```javascript
// src/config/planTiers.js
export const PLAN_TIERS = {
  free: {
    label: "Free",
    allowedComplexityTiers: ["simple", "moderate"]
  },
  pro: {
    label: "Pro",
    allowedComplexityTiers: ["simple", "moderate", "complex"]
  },
  enterprise: {
    label: "Enterprise",
    allowedComplexityTiers: ["simple", "moderate", "complex", "frontier"]
  }
}
```

Used only to filter the model list on the /project screen. Backend never reads or enforces this.

---

## MongoDB Index Requirements

Existing indexes remain. New indexes to create:
- `providers`: unique on `provider_id` (existing)
- `models`: compound unique on `(provider, model_id)` (existing); add single-field index on
  `provider` for the `GET /providers/{id}/models` query
- `phases`: unique on `phase_id` (existing); index on `sort_order`
