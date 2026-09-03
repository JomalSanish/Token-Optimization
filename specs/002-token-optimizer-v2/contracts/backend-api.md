# Backend API Contract: Token Optimizer v2

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03

All existing endpoints (`/extract`, `/estimate`, `/optimize`, `/discover-optimizations`,
`/models`, `/optimizer-rules`, and all `/admin/*` routes) are unchanged in their request/response
shapes. This document defines only the new and modified contracts.

Auth conventions (unchanged):
- Normal endpoints: `X-App-Secret: <APPLICATION_SECRET>` header required.
- Admin endpoints: `Authorization: Bearer <ADMIN_AUTH_SECRET>` required.
- Extraction endpoints additionally require: `X-Provider-Key: <user_api_key>` header.

---

## NEW: GET /providers

Returns active providers. Used by the User Dashboard to populate the provider picker on /keys
and /project.

**Auth**: `X-App-Secret` required.

**Response 200**:
```json
[
  {
    "provider_id": "openai",
    "display_name": "OpenAI",
    "active": true,
    "implementation_type": "native",
    "created_at": "2026-09-03T00:00:00Z",
    "updated_at": "2026-09-03T00:00:00Z"
  },
  {
    "provider_id": "deepseek",
    "display_name": "DeepSeek",
    "active": true,
    "implementation_type": "openai_compatible",
    "base_url": "https://api.deepseek.com/v1",
    "created_at": "2026-09-03T00:00:00Z",
    "updated_at": "2026-09-03T00:00:00Z"
  }
]
```

Note: `native_key` and `adapter_template` fields are NOT returned on this public endpoint —
these are internal dispatch details. This is enforced at the schema layer: the endpoint's
`response_model` is `ProviderPublicOut` (a distinct schema from the admin-facing `ProviderOut`),
not `ProviderOut` with fields manually stripped. The response includes only `provider_id`,
`display_name`, `active`, `implementation_type`, and (for `openai_compatible`) `base_url` for
display purposes.

---

## NEW: GET /providers/{provider_id}/models

Returns active models for a specific provider. Used by /project to populate the model dropdown.

**Auth**: `X-App-Secret` required.

**Path param**: `provider_id` — provider slug (e.g. `"openai"`)

**Response 200**:
```json
[
  {
    "provider": "openai",
    "model_id": "gpt-4o",
    "display_name": "GPT-4o (Standard)",
    "pricing": {
      "input_per_1m": "5.00",
      "output_per_1m": "15.00",
      "cached_input_per_1m": "2.50",
      "batch_input_per_1m": "2.50",
      "batch_output_per_1m": "7.50"
    },
    "pricing_version": 1,
    "context_window": 128000,
    "capabilities": ["text", "vision", "tool_use"],
    "active": true,
    "complexity_tier": "complex",
    "reasoning_complexity": "multi-step",
    "output_quality": "high-fidelity",
    "primary_use": ["extraction", "reasoning", "instruction-following"],
    "effective_from": "2026-09-03T00:00:00Z",
    "created_at": "2026-09-03T00:00:00Z",
    "updated_at": "2026-09-03T00:00:00Z"
  }
]
```

**Response 404**: Provider not found.

**Response 200 (empty array)**: Provider exists but has no active models.

---

## NEW: POST /route-model

Returns the best-fit active model for a given phase and provider, per the routing algorithm.

**Auth**: `X-App-Secret` required. No `X-Provider-Key` needed — no LLM call is made.

**Request body**:
```json
{
  "phase_id": "design",
  "provider_id": "openai"
}
```

**Response headers**: `Cache-Control: no-store` on every response from this endpoint (success and
error alike). Routing results are explicitly non-reproducible across admin catalog edits (see
constitution Principle IX) — a CDN or browser cache would silently serve a stale routing decision
otherwise.

**Response 200 (match found)**:
```json
{
  "phase_id": "design",
  "provider_id": "openai",
  "model_id": "gpt-4o",
  "display_name": "GPT-4o (Standard)",
  "match_type": "exact",
  "ordinal_distance": 0,
  "blended_rate": "10.00"
}
```

**Response 200 (no active models for this provider)**:
```json
{
  "phase_id": "design",
  "provider_id": "some-provider",
  "model_id": null,
  "display_name": null,
  "match_type": "none",
  "ordinal_distance": null,
  "blended_rate": null
}
```
This is a valid, expected outcome — the provider and phase both exist, the provider currently just
has no active models. It is intentionally a 200, not a 404: a 404 would conflate "this provider
doesn't exist" with "this provider has nothing active right now," which the frontend needs to
handle differently (the latter is not a broken request).

Fields:
- `match_type`: `"exact"` (model meets or exceeds all three requirements), `"nearest"` (fallback —
  no model fully meets requirements), or `"none"` (provider has zero active models).
- `ordinal_distance`: sum of absolute ordinal distances across all three dimensions (0 for exact,
  `null` for `"none"`).
- `blended_rate`: `(input_per_1m + output_per_1m) / 2` as a Decimal string (`null` for `"none"`).

**Response 404**: `phase_id` or `provider_id` does not exist at all. Reserved strictly for
unknown entities — not for a real provider that happens to have no active models (see above).

---

## MODIFIED: POST /admin/providers (ProviderIn schema extended)

**Auth**: `Authorization: Bearer` required.

**Request body (native)**:
```json
{
  "provider_id": "openai",
  "display_name": "OpenAI",
  "active": true,
  "implementation_type": "native",
  "native_key": "openai"
}
```

**Request body (openai_compatible)**:
```json
{
  "provider_id": "deepseek",
  "display_name": "DeepSeek",
  "active": true,
  "implementation_type": "openai_compatible",
  "base_url": "https://api.deepseek.com/v1"
}
```

**Request body (template)**:
```json
{
  "provider_id": "cohere",
  "display_name": "Cohere",
  "active": true,
  "implementation_type": "template",
  "adapter_template": {
    "request_url": "https://api.cohere.ai/v2/chat",
    "http_method": "POST",
    "header_template": {
      "Authorization": "Bearer {api_key}",
      "Content-Type": "application/json"
    },
    "body_template": {
      "model": "{model_id}",
      "messages": [
        { "role": "system", "content": "{system_prompt}" },
        { "role": "user",   "content": "{user_prompt}" }
      ]
    },
    "response_text_path": "message.content[0].text",
    "error_message_path": "message"
  }
}
```

**Response 200**: Full `ProviderOut` (includes all stored fields).

**Response 422**: Validation error — includes details for:
- Invalid `implementation_type` value.
- `native_key` not in the backend's registered key list.
- Non-HTTPS `base_url` or `request_url`.
- `base_url` / `request_url` resolving to a private/loopback/link-local IP.
- Missing required fields for the chosen `implementation_type`.

---

## NEW: PATCH /admin/providers/{provider_id}

Full provider update, including status changes.

**Auth**: `Authorization: Bearer` required.

**Request body**: any subset of `ProviderIn` fields, including `{"active": false}` to deactivate.

**Response 200**: Updated `ProviderOut`. **Response 404**: provider not found.

Note on pattern: models and optimizer rules expose separate `POST /activate` /
`POST /deactivate` sub-routes for status changes, but providers use a single `PATCH` with
`{"active": bool}` instead. This is a deliberate difference, not an oversight: provider status is
one field among several (`implementation_type`, `base_url`, adapter config) that can change
together in the same admin form save, whereas model/rule activation is a standalone action
elsewhere in their UIs. Do not add `POST /admin/providers/{id}/activate` — use `PATCH` for all
provider field changes including status.

---

## MODIFIED: POST /admin/models (ModelIn schema extended)

Four new required fields added to the existing contract. All other fields unchanged.

**New required fields in request body**:
```json
{
  "complexity_tier": "complex",
  "reasoning_complexity": "multi-step",
  "output_quality": "high-fidelity",
  "primary_use": ["extraction", "reasoning"]
}
```

**Response 422**: Missing or invalid enum value for any capability tag.

---

## NEW: GET /admin/phases

Returns all phases sorted by `sort_order`.

**Auth**: `Authorization: Bearer` required.

**Response 200**:
```json
[
  {
    "phase_id": "requirement",
    "name": "Requirements",
    "sort_order": 1,
    "default_agent_role": "Requirements Analyst",
    "default_cacheable_fraction": "0.40",
    "ams_classified": false,
    "default_complexity_tier": "moderate",
    "default_reasoning_complexity": "single-step",
    "default_output_quality": "standard"
  }
]
```

---

## NEW: POST /admin/phases

Creates a new phase.

**Auth**: `Authorization: Bearer` required.

**Request body**:
```json
{
  "phase_id": "new_phase",
  "name": "New Phase",
  "sort_order": 11,
  "default_agent_role": "Agent",
  "default_cacheable_fraction": "0.30",
  "ams_classified": false,
  "default_complexity_tier": "simple",
  "default_reasoning_complexity": "direct",
  "default_output_quality": "standard"
}
```

**Response 200**: Created phase document.
**Response 400**: Duplicate `phase_id`.
**Response 422**: Missing required fields.

---

## NEW: PATCH /admin/phases/{phase_id}

Updates a phase (partial update). `phase_id` cannot be changed.

**Auth**: `Authorization: Bearer` required.

**Request body**: Any subset of mutable phase fields (all validated against their enums).

**Response 200**: Updated phase document.
**Response 404**: Phase not found.
