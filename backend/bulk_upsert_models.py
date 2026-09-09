"""
bulk_upsert_models.py

Bulk-upserts the Sep 2026 rate-card spreadsheet, plus the two Gemini Flash
models from the pricing-page screenshots (non-free / paid tier), into the
`providers` and `models` collections of the token_optimizer MongoDB Atlas
database used by the AI Cost Estimation Platform.

WHAT THIS DOES
  - Upserts models on the unique (provider, model_id) key:
      * New (provider, model_id) -> inserted fresh.
      * Existing (provider, model_id) -> pricing is updated ONLY IF it
        actually changed, and a pricing_history record is written for
        the change (bumps pricing_version, keeps the old numbers).
  - Adds the new providers referenced by the spreadsheet that don't
    exist yet (xai, ibm, cursor, nex_agi, minimax, moonshot,
    inclusionai) as implementation_type="template" with a PLACEHOLDER
    adapter_template. These are NOT wired to real APIs -- fill in the
    real request_url / headers / body / response paths in the admin
    panel (or edit PROVIDERS below) before routing live traffic to
    them. openai / anthropic / google / deepseek already exist and are
    left untouched.
  - Gemini 3.7 Flash and Gemini 3.6 Flash use the PAID (non-free) tier
    pricing, current-through-Dec-31-2026 column from the screenshots
    (today's date is inside that window).

ASSUMPTIONS -- you asked me to infer reasonable defaults, so I did.
Review anything you care about before trusting it blindly:

  1. Non-token pricing rows (Moderation, Web search, Audio, Whisper)
     don't actually bill per-million-tokens. Per your instruction they
     are force-fit into input_per_1m / output_per_1m anyway (the raw
     $/minute or $/1000-calls number is stored as-is in those fields).
     `pricing.non_standard_unit` records what the number really means
     ("minute", "1000 calls", "request") so it isn't silently misread
     as a token price later.
  2. complexity_tier / reasoning_complexity / output_quality /
     primary_use / context_window / capabilities aren't in the
     spreadsheet or screenshots at all -- every value below is an
     inferred guess based on the model's name/category, not a
     verified fact. Re-tag anything that matters via the admin UI.
  3. batch_input_per_1m / batch_output_per_1m are schema-required but
     absent from the spreadsheet -- defaulted to 50% of the standard
     input/output rate (mirrors OpenAI's real published batch
     discount; applied here uniformly as a placeholder for every
     provider).
  4. cached_input_per_1m: used as given when the spreadsheet has a
     value; defaulted to 25% of input_per_1m where it's blank/"-".
  5. "Cache Write $/1M" isn't part of the existing schema. Stored as
     an additive `pricing.cache_write_per_1m` field (null when not
     given by the sheet). If your Pydantic response/request models use
     `extra="forbid"`, add this field there or it'll reject on read.
  6. Per-call/monthly-quota surcharges (Gemini Search/Maps grounding,
     OpenAI's web-search tool) are stored as an additive top-level
     `additional_costs` list -- informational only, the pricing
     calculator doesn't consume it today.
  7. New "template" provider docs use an obviously-fake placeholder
     adapter_template (request_url ends in /REPLACE_ME) so nobody
     mistakes them for working integrations.

Usage:
    pip install motor python-dotenv --break-system-packages
    MONGODB_URI="mongodb+srv://..." MONGODB_DATABASE="token_optimizer" \\
        python bulk_upsert_models.py
    # add --dry-run to print what would happen without writing anything
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "token_optimizer")
DRY_RUN = "--dry-run" in sys.argv
CHANGED_BY = "bulk_upsert_models.py (Sep 2026 rate card)"


def D(x):
    """None-safe Decimal-ish float wrapper (Mongo stores these as doubles unless
    you configure Decimal128 codecs; left as float to match the existing seed.py)."""
    return None if x is None else round(float(x), 6)


# ---------------------------------------------------------------------------
# New providers referenced by the spreadsheet that aren't seeded yet.
# implementation_type="template" with a PLACEHOLDER adapter_template.
# ---------------------------------------------------------------------------
NEW_PROVIDERS = [
    {"provider_id": "xai", "display_name": "xAI"},
    {"provider_id": "ibm", "display_name": "IBM"},
    {"provider_id": "cursor", "display_name": "Cursor"},
    {"provider_id": "nex_agi", "display_name": "Nex AGI"},
    {"provider_id": "minimax", "display_name": "MiniMax"},
    {"provider_id": "moonshot", "display_name": "Moonshot AI"},
    {"provider_id": "inclusionai", "display_name": "InclusionAI"},
]


def placeholder_provider_doc(provider_id, display_name, now):
    return {
        "provider_id": provider_id,
        "display_name": display_name,
        "active": False,  # left inactive until a real adapter is filled in
        "implementation_type": "template",
        "adapter_template": {
            "request_url": f"https://REPLACE_ME.{provider_id}.example/v1/chat/completions",
            "http_method": "POST",
            "header_template": {"Authorization": "Bearer {api_key}"},
            "body_template": {"model": "{model_id}", "messages": [
                {"role": "system", "content": "{system_prompt}"},
                {"role": "user", "content": "{user_prompt}"},
            ]},
            "response_text_path": "choices[0].message.content",
            "error_message_path": "error.message",
        },
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Model rows. Each: provider, model_id, display_name, input, output,
# cached (None -> defaulted to 25% of input), cache_write (None -> omitted),
# context_window, capabilities, complexity_tier, reasoning_complexity,
# output_quality, primary_use, non_standard_unit (None for normal token
# pricing), additional_costs (optional list of strings).
# ---------------------------------------------------------------------------
MODELS = [
    # ---------------- OpenAI: Cyber ----------------
    dict(provider="openai", model_id="gpt-5.6-sol", display_name="GPT-5.6 Sol (Short Context)",
         input=5.00, output=30.00, cached=0.50, cache_write=6.25, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["reasoning", "code-generation"]),
    dict(provider="openai", model_id="gpt-5.6-sol-long", display_name="GPT-5.6 Sol (Long Context)",
         input=10.00, output=45.00, cached=1.00, cache_write=12.50, context_window=1000000,
         capabilities=["text", "tool_use", "long_context"], complexity_tier="complex",
         reasoning_complexity="multi-step", output_quality="high-fidelity",
         primary_use=["reasoning", "code-generation", "long-context"]),
    dict(provider="openai", model_id="gpt-5.6-cyber", display_name="GPT-5.6 Cyber",
         input=12.50, output=75.00, cached=1.25, cache_write=15.63, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="frontier", reasoning_complexity="deep-reasoning",
         output_quality="expert-grade", primary_use=["reasoning", "code-generation"]),
    dict(provider="openai", model_id="gpt-5.5-cyber", display_name="GPT-5.5 Cyber",
         input=12.50, output=75.00, cached=1.25, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="frontier", reasoning_complexity="deep-reasoning",
         output_quality="expert-grade", primary_use=["reasoning", "code-generation"]),

    # ---------------- OpenAI: ChatGPT ----------------
    dict(provider="openai", model_id="chat-latest", display_name="ChatGPT (chat-latest)",
         input=5.00, output=30.00, cached=0.50, cache_write=None, context_window=128000,
         capabilities=["text", "vision"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["instruction-following", "summarization"]),
    dict(provider="openai", model_id="gpt-5.3-chat-latest", display_name="GPT-5.3 Chat Latest",
         input=1.75, output=14.00, cached=0.18, cache_write=None, context_window=128000,
         capabilities=["text", "vision"], complexity_tier="moderate", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["instruction-following", "summarization"]),
    dict(provider="openai", model_id="gpt-5.2-chat-latest", display_name="GPT-5.2 Chat Latest",
         input=1.75, output=14.00, cached=0.18, cache_write=None, context_window=128000,
         capabilities=["text", "vision"], complexity_tier="moderate", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["instruction-following", "summarization"]),

    # ---------------- OpenAI: Codex ----------------
    dict(provider="openai", model_id="gpt-5.3-codex", display_name="GPT-5.3 Codex",
         input=1.75, output=14.00, cached=0.18, cache_write=None, context_window=200000,
         capabilities=["text", "tool_use"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["code-generation"]),
    dict(provider="openai", model_id="gpt-5.3-codex-fast", display_name="GPT-5.3 Codex Fast",
         input=3.50, output=28.00, cached=0.35, cache_write=None, context_window=200000,
         capabilities=["text", "tool_use"], complexity_tier="complex", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["code-generation"]),

    # ---------------- OpenAI: Search ----------------
    dict(provider="openai", model_id="gpt-5-search-api", display_name="GPT-5 Search API",
         input=1.25, output=10.00, cached=0.13, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="moderate", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["extraction", "summarization"],
         additional_costs=["$10.00 per 1,000 tool calls"]),

    # ---------------- OpenAI: Embeddings (not token-generation models; output N/A) ----------------
    dict(provider="openai", model_id="text-embedding-3-small", display_name="Text Embedding 3 Small",
         input=0.02, output=0.0, cached=0.0, cache_write=None, context_window=8191,
         capabilities=["embedding"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["classification"]),
    dict(provider="openai", model_id="text-embedding-3-large", display_name="Text Embedding 3 Large",
         input=0.13, output=0.0, cached=0.0, cache_write=None, context_window=8191,
         capabilities=["embedding"], complexity_tier="moderate", reasoning_complexity="direct",
         output_quality="high-fidelity", primary_use=["classification"]),
    dict(provider="openai", model_id="text-embedding-ada-002", display_name="Text Embedding Ada 002",
         input=0.10, output=0.0, cached=0.0, cache_write=None, context_window=8191,
         capabilities=["embedding"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["classification"]),

    # ---------------- OpenAI: Moderation (free) ----------------
    dict(provider="openai", model_id="omni-moderation-latest", display_name="Omni Moderation Latest",
         input=0.0, output=0.0, cached=0.0, cache_write=None, context_window=32768,
         capabilities=["text", "vision"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["classification"],
         non_standard_unit="request (free)"),

    # ---------------- OpenAI: Web search tool surcharge (not a model) ----------------
    dict(provider="openai", model_id="web-search-tool-surcharge", display_name="Web Search Tool (all models)",
         input=10.00, output=0.0, cached=None, cache_write=None, context_window=0,
         capabilities=["tool_use"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["extraction"],
         non_standard_unit="1000 calls"),

    # ---------------- OpenAI: Audio ----------------
    dict(provider="openai", model_id="gpt-realtime-translate", display_name="GPT Realtime Translate",
         input=0.03, output=0.03, cached=0.03, cache_write=None, context_window=0,
         capabilities=["audio"], complexity_tier="moderate", reasoning_complexity="direct",
         output_quality="standard", primary_use=["extraction"],
         non_standard_unit="minute"),
    dict(provider="openai", model_id="gpt-live-transcribe", display_name="GPT Live Transcribe",
         input=0.02, output=0.02, cached=0.02, cache_write=None, context_window=0,
         capabilities=["audio"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["extraction"],
         non_standard_unit="minute"),
    dict(provider="openai", model_id="whisper", display_name="Whisper (Transcription)",
         input=0.01, output=0.01, cached=0.01, cache_write=None, context_window=0,
         capabilities=["audio"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["extraction"],
         non_standard_unit="minute"),

    # ---------------- Anthropic ----------------
    dict(provider="anthropic", model_id="claude-fable-5-1", display_name="Claude Fable 5",
         input=10.00, output=50.00, cached=None, cache_write=None, context_window=200000,
         capabilities=["text", "vision", "tool_use"], complexity_tier="frontier",
         reasoning_complexity="deep-reasoning", output_quality="expert-grade",
         primary_use=["reasoning", "code-generation", "instruction-following"]),
    dict(provider="anthropic", model_id="claude-sonnet-4-5", display_name="Claude Sonnet 4.5",
         input=3.00, output=15.00, cached=None, cache_write=None, context_window=200000,
         capabilities=["text", "vision", "tool_use"], complexity_tier="complex",
         reasoning_complexity="multi-step", output_quality="high-fidelity",
         primary_use=["extraction", "reasoning", "code-generation"]),
    dict(provider="anthropic", model_id="claude-sonnet-4-6", display_name="Claude Sonnet 4.6",
         input=3.00, output=15.00, cached=None, cache_write=None, context_window=200000,
         capabilities=["text", "vision", "tool_use"], complexity_tier="complex",
         reasoning_complexity="multi-step", output_quality="high-fidelity",
         primary_use=["extraction", "reasoning", "code-generation"]),

    # ---------------- xAI ----------------
    dict(provider="xai", model_id="grok-4", display_name="Grok 4",
         input=2.00, output=6.00, cached=0.50, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["reasoning", "instruction-following"]),

    # ---------------- IBM ----------------
    dict(provider="ibm", model_id="granite-4.1-8b", display_name="Granite 4.1 8B",
         input=0.05, output=0.10, cached=0.05, cache_write=None, context_window=32000,
         capabilities=["text"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="standard", primary_use=["classification", "summarization"]),

    # ---------------- Nex AGI ----------------
    dict(provider="nex_agi", model_id="nex-n2-mini", display_name="Nex-N2-Mini",
         input=0.02, output=0.10, cached=0.0, cache_write=None, context_window=32000,
         capabilities=["text"], complexity_tier="simple", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["classification", "instruction-following"]),

    # ---------------- OpenAI: misc (existing models -- pricing updates) ----------------
    dict(provider="openai", model_id="gpt-4o", display_name="GPT-4o (Standard)",
         input=2.50, output=10.00, cached=None, cache_write=None, context_window=128000,
         capabilities=["text", "vision", "tool_use"], complexity_tier="complex",
         reasoning_complexity="multi-step", output_quality="high-fidelity",
         primary_use=["extraction", "reasoning", "instruction-following"]),
    dict(provider="openai", model_id="gpt-4o-mini", display_name="GPT-4o Mini (Cost-Efficient)",
         input=0.15, output=0.60, cached=None, cache_write=None, context_window=128000,
         capabilities=["text", "vision", "tool_use"], complexity_tier="moderate",
         reasoning_complexity="single-step", output_quality="standard",
         primary_use=["classification", "summarization", "instruction-following"]),
    dict(provider="openai", model_id="gpt-4.5-0227", display_name="GPT-4.5 (0227)",
         input=75.00, output=150.00, cached=37.50, cache_write=None, context_window=128000,
         capabilities=["text", "vision"], complexity_tier="frontier", reasoning_complexity="deep-reasoning",
         output_quality="expert-grade", primary_use=["reasoning", "code-generation"]),
    dict(provider="openai", model_id="o1-pro", display_name="o1-pro",
         input=150.00, output=600.00, cached=75.00, cache_write=None, context_window=200000,
         capabilities=["text", "tool_use"], complexity_tier="frontier", reasoning_complexity="deep-reasoning",
         output_quality="expert-grade", primary_use=["reasoning"]),

    # ---------------- Cursor ----------------
    dict(provider="cursor", model_id="composer-2.5-fast", display_name="Composer 2.5 Fast",
         input=3.00, output=15.00, cached=0.50, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["code-generation"]),

    # ---------------- DeepSeek ----------------
    dict(provider="deepseek", model_id="deepseek-v4-pro", display_name="DeepSeek V4 Pro",
         input=0.44, output=0.87, cached=0.0, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="moderate", reasoning_complexity="multi-step",
         output_quality="standard", primary_use=["code-generation", "reasoning"]),
    dict(provider="deepseek", model_id="deepseek-v4-flash", display_name="DeepSeek V4 Flash",
         input=0.14, output=0.28, cached=0.0, cache_write=None, context_window=128000,
         capabilities=["text", "tool_use"], complexity_tier="moderate", reasoning_complexity="single-step",
         output_quality="standard", primary_use=["classification", "summarization"]),

    # ---------------- MiniMax ----------------
    dict(provider="minimax", model_id="minimax-m2.7", display_name="MiniMax M2.7",
         input=0.30, output=1.20, cached=0.05, cache_write=None, context_window=205000,
         capabilities=["text", "long_context"], complexity_tier="moderate", reasoning_complexity="multi-step",
         output_quality="standard", primary_use=["long-context", "reasoning"]),

    # ---------------- Moonshot AI ----------------
    dict(provider="moonshot", model_id="kimi-k2.6", display_name="Kimi K2.6",
         input=0.95, output=4.00, cached=0.16, cache_write=None, context_window=256000,
         capabilities=["text", "long_context"], complexity_tier="complex", reasoning_complexity="multi-step",
         output_quality="high-fidelity", primary_use=["long-context", "reasoning"]),

    # ---------------- InclusionAI ----------------
    dict(provider="inclusionai", model_id="ling-2.6-flash", display_name="Ling 2.6 Flash",
         input=0.01, output=0.03, cached=0.0, cache_write=None, context_window=262000,
         capabilities=["text", "long_context"], complexity_tier="simple", reasoning_complexity="direct",
         output_quality="draft", primary_use=["classification", "long-context"]),

    # ---------------- Google Gemini (screenshots, non-free/paid tier, through Dec 31 2026) ----------------
    dict(provider="google", model_id="gemini-3.7-flash", display_name="Gemini 3.7 Flash",
         input=0.75, output=3.75, cached=0.075, cache_write=None, context_window=1048576,
         capabilities=["text", "vision", "tool_use"], complexity_tier="moderate",
         reasoning_complexity="multi-step", output_quality="standard",
         primary_use=["code-generation", "instruction-following"],
         additional_costs=[
             "Grounding with Google Search: 5,000 free requests/month (shared across Gemini 3.x), then $14/1,000 requests",
             "Grounding with Google Maps: 5,000 free prompts/month (shared across Gemini 3), then $14/1,000 queries",
             "Context caching storage: $0.50/1,000,000 tokens/hour through Dec 31 2026 ($1.00 from Jan 1 2027)",
         ]),
    dict(provider="google", model_id="gemini-3.6-flash", display_name="Gemini 3.6 Flash",
         input=0.75, output=3.75, cached=0.075, cache_write=None, context_window=1048576,
         capabilities=["text", "vision", "tool_use", "multimodal"], complexity_tier="moderate",
         reasoning_complexity="single-step", output_quality="standard",
         primary_use=["summarization", "instruction-following", "multimodal"],
         additional_costs=[
             "Grounding with Google Search: 5,000 free prompts/month (shared across Gemini 3), then $14/1,000 queries",
             "Grounding with Google Maps: 5,000 free prompts/month (shared across Gemini 3), then $14/1,000 queries",
             "Context caching storage: $0.50/1,000,000 tokens/hour through Dec 31 2026 ($1.00 from Jan 1 2027)",
         ]),
]


def build_pricing(row):
    input_per_1m = D(row["input"])
    output_per_1m = D(row["output"])
    cached = row.get("cached")
    cached_input_per_1m = D(cached) if cached is not None else D(round(input_per_1m * 0.25, 6))
    pricing = {
        "input_per_1m": input_per_1m,
        "output_per_1m": output_per_1m,
        "cached_input_per_1m": cached_input_per_1m,
        "batch_input_per_1m": D(round(input_per_1m * 0.5, 6)),
        "batch_output_per_1m": D(round(output_per_1m * 0.5, 6)),
        "cache_write_per_1m": D(row.get("cache_write")),
    }
    if row.get("non_standard_unit"):
        pricing["non_standard_unit"] = row["non_standard_unit"]
    return pricing


def pricing_changed(existing_pricing, new_pricing):
    keys = ("input_per_1m", "output_per_1m", "cached_input_per_1m",
            "batch_input_per_1m", "batch_output_per_1m")
    return any(D(existing_pricing.get(k)) != D(new_pricing.get(k)) for k in keys)


async def run():
    if not MONGODB_URI:
        print("MONGODB_URI is not set. Export it (and optionally MONGODB_DATABASE) first.")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    now = datetime.now(timezone.utc)

    print(f"Target database: {MONGODB_DATABASE}  (dry-run={DRY_RUN})")

    # --- 1. New providers -------------------------------------------------
    existing_provider_ids = {p["provider_id"] async for p in db.providers.find({}, {"provider_id": 1})}
    added_providers = 0
    for p in NEW_PROVIDERS:
        if p["provider_id"] in existing_provider_ids:
            continue
        doc = placeholder_provider_doc(p["provider_id"], p["display_name"], now)
        print(f"  [provider] insert (template placeholder): {p['provider_id']}")
        if not DRY_RUN:
            await db.providers.insert_one(doc)
        added_providers += 1
    print(f"Providers added: {added_providers}")

    # --- 2. Models ----------------------------------------------------------
    inserted, updated, unchanged = 0, 0, 0
    for row in MODELS:
        provider = row["provider"]
        model_id = row["model_id"]
        new_pricing = build_pricing(row)

        doc_fields = {
            "provider": provider,
            "model_id": model_id,
            "display_name": row["display_name"],
            "pricing": new_pricing,
            "context_window": row["context_window"],
            "capabilities": row["capabilities"],
            "active": True,
            "complexity_tier": row["complexity_tier"],
            "reasoning_complexity": row["reasoning_complexity"],
            "output_quality": row["output_quality"],
            "primary_use": row["primary_use"],
            "effective_from": now,
            "updated_at": now,
        }
        if row.get("additional_costs"):
            doc_fields["additional_costs"] = row["additional_costs"]

        existing = await db.models.find_one({"provider": provider, "model_id": model_id})

        if existing is None:
            doc_fields["pricing_version"] = 1
            doc_fields["created_at"] = now
            print(f"  [model] insert: {provider}/{model_id}")
            if not DRY_RUN:
                await db.models.insert_one(doc_fields)
            inserted += 1
            continue

        if pricing_changed(existing.get("pricing", {}), new_pricing):
            new_version = existing.get("pricing_version", 1) + 1
            doc_fields["pricing_version"] = new_version
            print(f"  [model] update pricing: {provider}/{model_id} "
                  f"(v{existing.get('pricing_version', 1)} -> v{new_version})")
            if not DRY_RUN:
                await db.models.update_one(
                    {"_id": existing["_id"]},
                    {"$set": doc_fields},
                )
                await db.pricing_history.insert_one({
                    "model_id": model_id,
                    "provider": provider,
                    "previous_pricing": existing.get("pricing", {}),
                    "new_pricing": new_pricing,
                    "pricing_version": new_version,
                    "changed_by": CHANGED_BY,
                    "changed_at": now,
                    "reason": "Bulk upload from Sep 2026 rate-card spreadsheet / Gemini pricing screenshots",
                })
            updated += 1
        else:
            unchanged += 1

    print(f"\nModels inserted: {inserted}, updated: {updated}, unchanged: {unchanged}")
    client.close()


if __name__ == "__main__":
    asyncio.run(run())
