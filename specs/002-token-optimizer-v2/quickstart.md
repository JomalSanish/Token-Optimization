# Quickstart Validation Guide: Token Optimizer v2

**Branch**: `002-token-optimizer-v2` | **Date**: 2026-09-03

This guide describes how to validate the feature end-to-end after implementation.
It is a run guide, not an implementation guide. Full API contracts are in
`contracts/backend-api.md` and `contracts/frontend-routes.md`.

---

## Prerequisites

- MongoDB Atlas cluster reset and empty (v2.0.0 reset policy applies).
- Backend `.env` populated: `MONGODB_URI`, `APPLICATION_SECRET`, `ADMIN_AUTH_SECRET`, `CORS_ORIGINS`.
- `CORS_ORIGINS` includes the frontend dev server origin (e.g. `http://localhost:5173`).

---

## Step 1: Reset and Seed Database

```bash
# From backend/
python scripts/seed.py
```

**Expected output**:
- Collections dropped and recreated.
- 4 providers inserted: openai (native), anthropic (native), google (native), deepseek (openai_compatible).
- Models inserted with all four capability tags populated.
- Phases inserted with all three default requirement fields populated.

**Verify**:
```bash
# Using mongosh or Compass — check that a model document has the new fields:
db.models.findOne({model_id: "gpt-4o"})
# → should include complexity_tier, reasoning_complexity, output_quality, primary_use

# Check providers:
db.providers.findOne({provider_id: "deepseek"})
# → should include implementation_type: "openai_compatible", base_url: "https://api.deepseek.com/v1"

# Check phases:
db.phases.findOne({phase_id: "requirement"})
# → should include default_complexity_tier, default_reasoning_complexity, default_output_quality
```

---

## Step 2: Start the Backend

```bash
# From backend/
uvicorn src.main:app --reload --port 8000
```

**Expected**: Server starts with no config errors.

---

## Step 3: Validate New Public Endpoints

```bash
# GET /providers — active provider list
curl -H "X-App-Secret: $APP_SECRET" http://localhost:8000/providers
# → JSON array with 4 providers; each has implementation_type; deepseek has base_url

# GET /providers/openai/models — scoped model list
curl -H "X-App-Secret: $APP_SECRET" http://localhost:8000/providers/openai/models
# → JSON array of active OpenAI models with all four capability tags

# GET /providers/deepseek/models — should return DeepSeek models (if seeded)
curl -H "X-App-Secret: $APP_SECRET" http://localhost:8000/providers/deepseek/models
```

---

## Step 4: Validate Admin Provider CRUD (including openai_compatible and template)

```bash
# POST /admin/providers — add a new openai_compatible provider (e.g. Groq)
curl -X POST http://localhost:8000/admin/providers \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"provider_id":"groq","display_name":"Groq","active":true,
       "implementation_type":"openai_compatible",
       "base_url":"https://api.groq.com/openai/v1"}'
# → 200 with provider doc; provider immediately appears in GET /providers

# POST /admin/providers — reject private IP (SSRF guard)
curl -X POST http://localhost:8000/admin/providers \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"provider_id":"bad","display_name":"Bad","active":true,
       "implementation_type":"openai_compatible",
       "base_url":"http://192.168.1.1/v1"}'
# → 422 validation error (non-HTTPS + private IP range)

# POST /admin/providers — add a template provider
curl -X POST http://localhost:8000/admin/providers \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "provider_id": "cohere",
  "display_name": "Cohere",
  "active": true,
  "implementation_type": "template",
  "adapter_template": {
    "request_url": "https://api.cohere.ai/v2/chat",
    "http_method": "POST",
    "header_template": {"Authorization": "Bearer {api_key}", "Content-Type": "application/json"},
    "body_template": {"model": "{model_id}", "messages": [{"role": "user", "content": "{user_prompt}"}]},
    "response_text_path": "message.content[0].text",
    "error_message_path": "message"
  }
}
JSON
# → 200
```

---

## Step 5: Validate Model Capability Tags (Admin)

```bash
# POST /admin/models — missing capability tag should fail
curl -X POST http://localhost:8000/admin/models \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","model_id":"gpt-test","display_name":"Test",
       "pricing":{"input_per_1m":1,"output_per_1m":2,"cached_input_per_1m":0.5,
                  "batch_input_per_1m":0.5,"batch_output_per_1m":1},
       "context_window":8000,"capabilities":["text"],"active":true}'
# → 422: complexity_tier, reasoning_complexity, output_quality, primary_use all required

# POST /admin/models — with all four tags
curl -X POST http://localhost:8000/admin/models \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","model_id":"gpt-test","display_name":"Test",
       "pricing":{"input_per_1m":1,"output_per_1m":2,"cached_input_per_1m":0.5,
                  "batch_input_per_1m":0.5,"batch_output_per_1m":1},
       "context_window":8000,"capabilities":["text"],"active":true,
       "complexity_tier":"simple","reasoning_complexity":"direct",
       "output_quality":"draft","primary_use":["classification"]}'
# → 200
```

---

## Step 6: Validate Phase CRUD (Admin)

```bash
# GET /admin/phases
curl -H "Authorization: Bearer $ADMIN_SECRET" http://localhost:8000/admin/phases
# → array of phase docs, each with default_complexity_tier, default_reasoning_complexity, default_output_quality

# POST /admin/phases — missing a default requirement field should fail
curl -X POST http://localhost:8000/admin/phases \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"phase_id":"test_phase","name":"Test Phase","sort_order":99,
       "default_agent_role":"Agent","default_cacheable_fraction":0.3,"ams_classified":false,
       "default_complexity_tier":"simple","default_reasoning_complexity":"direct"}'
# → 422: default_output_quality is required
```

---

## Step 7: Validate /route-model

```bash
# POST /route-model — should return best-fit model
curl -X POST http://localhost:8000/route-model \
  -H "X-App-Secret: $APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"phase_id":"requirement","provider_id":"openai"}'
# → 200 with model_id, match_type ("exact" or "nearest"), ordinal_distance, blended_rate

# POST /route-model — provider with no active models → 404
curl -X POST http://localhost:8000/route-model \
  -H "X-App-Secret: $APP_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"phase_id":"requirement","provider_id":"groq"}'
# → 404 (groq has no models seeded yet)
```

---

## Step 8: Run Unit Tests

```bash
# From backend/
pytest tests/unit/ -v

# Expected: test_calc_engine.py (all passing, unchanged)
#           test_routing.py: exact match, no-match-fallback-above, no-match-fallback-below, tie-break-by-price
#           test_adapters.py: call_openai_compatible with stubbed response, template interpreter with synthetic shape
```

---

## Step 9: Run Integration Tests

```bash
pytest tests/integration/ -v

# Includes extended concurrency test:
# - 10+ concurrent requests with independently rotating key pools
# - Mid-test admin addition of a new provider, followed by requests against it
# - Verify no cross-request key leakage
```

---

## Step 10: Validate React Frontend

```bash
# From frontend/
npm install
npm run dev
# → Vite dev server at http://localhost:5173
```

**Validation scenarios** (manual browser walkthrough):

1. Navigate to `http://localhost:5173/keys` → User Dashboard shows sidebar; API Keys page loads.
   - Add a key for "OpenAI" → persists to localStorage; no network request.
   - Add a key for "DeepSeek" → persists; no network request.

2. Navigate to `/project` → Provider picker shows only OpenAI and DeepSeek (providers with keys).
   - Select OpenAI → model dropdown populates with OpenAI models only.
   - Select DeepSeek → model dropdown populates with DeepSeek models only.
   - Toggle "Plan" selector → model list filters client-side (observe no network call).

3. Navigate to `/estimate` → Phase table loads.
   - Per-phase model picker spans ALL providers (not just the extraction provider).
   - Click "Suggest model" on a phase → POST /route-model called; picker pre-fills.
   - Override suggestion → picker accepts the override.

4. Navigate to `/admin/providers` → Admin sidebar; Provider list.
   - Create an openai_compatible provider (e.g. Groq) → form shows only `base_url` field.
   - Create a template provider → form shows all six adapter template fields.
   - Attempt to save with HTTP URL → error shown before save.

5. Navigate to `/admin/models` → All four capability dropdowns visible on create form.
   - Attempt to save without a tag → validation error.

6. Navigate to `/admin/phases` → Phase list with default requirement fields.
   - Create a new phase → three dropdown fields required.

7. Confirm admin area has NO API key input fields anywhere.
