"""
seed.py — Drop-and-recreate all collections, then insert v2 seed data.

v2 schema requirements (all fields are REQUIRED — no document may be inserted
without them, per the constitution's MongoDB reset policy):

Providers:
  - implementation_type: "native" | "openai_compatible" | "template"
  - native_key: required when implementation_type = "native"
  - base_url: required when implementation_type = "openai_compatible"

Models:
  - complexity_tier: "simple" | "moderate" | "complex" | "frontier"
  - reasoning_complexity: "direct" | "single-step" | "multi-step" | "deep-reasoning"
  - output_quality: "draft" | "standard" | "high-fidelity" | "expert-grade"
  - primary_use: list from the allowed set

Phases:
  - default_complexity_tier (same enum as model.complexity_tier)
  - default_reasoning_complexity (same enum as model.reasoning_complexity)
  - default_output_quality (same enum as model.output_quality)

Usage:
  python backend/scripts/seed.py
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# Ensure root backend dir is in path so src.* imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings


async def seed_database():
    print("Connecting to MongoDB for seeding...")
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # DROP all collections first (full reset — not upsert)
    # ------------------------------------------------------------------
    print("Dropping existing collections...")
    for collection_name in ("providers", "models", "phases", "optimizer_rules", "pricing_history"):
        await db.drop_collection(collection_name)
        print(f"  Dropped: {collection_name}")

    # ------------------------------------------------------------------
    # 1. Seed Providers
    # ------------------------------------------------------------------
    print("Seeding providers collection...")
    providers = [
        {
            "provider_id": "openai",
            "display_name": "OpenAI",
            "active": True,
            "implementation_type": "native",
            "native_key": "openai",
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider_id": "anthropic",
            "display_name": "Anthropic Claude",
            "active": True,
            "implementation_type": "native",
            "native_key": "anthropic",
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider_id": "google",
            "display_name": "Google Gemini",
            "active": True,
            "implementation_type": "native",
            "native_key": "google",
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider_id": "deepseek",
            "display_name": "DeepSeek",
            "active": True,
            "implementation_type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "created_at": now,
            "updated_at": now,
        },
    ]
    if providers:
        await db.providers.insert_many(providers)
    print(f"  Inserted {len(providers)} providers.")

    # ------------------------------------------------------------------
    # 2. Seed Models  (all four capability tags required on every row)
    # ------------------------------------------------------------------
    print("Seeding models collection...")
    models = [
        # --- OpenAI ---
        {
            "provider": "openai",
            "model_id": "gpt-4o",
            "display_name": "GPT-4o (Standard)",
            "pricing": {
                "input_per_1m": 5.00,
                "output_per_1m": 15.00,
                "cached_input_per_1m": 2.50,
                "batch_input_per_1m": 2.50,
                "batch_output_per_1m": 7.50,
            },
            "pricing_version": 1,
            "context_window": 128000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "complex",
            "reasoning_complexity": "multi-step",
            "output_quality": "high-fidelity",
            "primary_use": ["extraction", "reasoning", "instruction-following"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "display_name": "GPT-4o Mini (Cost-Efficient)",
            "pricing": {
                "input_per_1m": 0.150,
                "output_per_1m": 0.600,
                "cached_input_per_1m": 0.075,
                "batch_input_per_1m": 0.075,
                "batch_output_per_1m": 0.300,
            },
            "pricing_version": 1,
            "context_window": 128000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "moderate",
            "reasoning_complexity": "single-step",
            "output_quality": "standard",
            "primary_use": ["classification", "summarization", "instruction-following"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        # --- Anthropic ---
        {
            "provider": "anthropic",
            "model_id": "claude-3-5-sonnet",
            "display_name": "Claude 3.5 Sonnet",
            "pricing": {
                "input_per_1m": 3.00,
                "output_per_1m": 15.00,
                "cached_input_per_1m": 1.50,
                "batch_input_per_1m": 1.50,
                "batch_output_per_1m": 7.50,
            },
            "pricing_version": 1,
            "context_window": 200000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "complex",
            "reasoning_complexity": "multi-step",
            "output_quality": "high-fidelity",
            "primary_use": ["extraction", "code-generation", "reasoning"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        # --- Google ---
        {
            "provider": "google",
            "model_id": "gemini-2.5-flash",
            "display_name": "Google Gemini 2.5 Flash",
            "pricing": {
                "input_per_1m": 0.075,
                "output_per_1m": 0.30,
                "cached_input_per_1m": 0.01875,
                "batch_input_per_1m": 0.0375,
                "batch_output_per_1m": 0.15,
            },
            "pricing_version": 1,
            "context_window": 1048576,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "moderate",
            "reasoning_complexity": "single-step",
            "output_quality": "standard",
            "primary_use": ["summarization", "classification", "long-context"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider": "google",
            "model_id": "gemini-2.5-pro",
            "display_name": "Google Gemini 2.5 Pro",
            "pricing": {
                "input_per_1m": 1.25,
                "output_per_1m": 5.00,
                "cached_input_per_1m": 0.3125,
                "batch_input_per_1m": 0.625,
                "batch_output_per_1m": 2.50,
            },
            "pricing_version": 1,
            "context_window": 2097152,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "complex",
            "reasoning_complexity": "multi-step",
            "output_quality": "high-fidelity",
            "primary_use": ["extraction", "reasoning", "long-context"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        # --- DeepSeek ---
        {
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "display_name": "DeepSeek Chat (V3)",
            "pricing": {
                "input_per_1m": 0.27,
                "output_per_1m": 1.10,
                "cached_input_per_1m": 0.07,
                "batch_input_per_1m": 0.135,
                "batch_output_per_1m": 0.55,
            },
            "pricing_version": 1,
            "context_window": 64000,
            "capabilities": ["text", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "moderate",
            "reasoning_complexity": "multi-step",
            "output_quality": "standard",
            "primary_use": ["code-generation", "instruction-following", "summarization"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
        {
            "provider": "deepseek",
            "model_id": "deepseek-reasoner",
            "display_name": "DeepSeek Reasoner (R1)",
            "pricing": {
                "input_per_1m": 0.55,
                "output_per_1m": 2.19,
                "cached_input_per_1m": 0.14,
                "batch_input_per_1m": 0.275,
                "batch_output_per_1m": 1.095,
            },
            "pricing_version": 1,
            "context_window": 64000,
            "capabilities": ["text", "tool_use"],
            "active": True,
            # v2 capability tags
            "complexity_tier": "complex",
            "reasoning_complexity": "deep-reasoning",
            "output_quality": "high-fidelity",
            "primary_use": ["reasoning", "code-generation", "instruction-following"],
            "effective_from": now,
            "created_at": now,
            "updated_at": now,
        },
    ]
    if models:
        await db.models.insert_many(models)
    print(f"  Inserted {len(models)} models.")

    # ------------------------------------------------------------------
    # 3. Seed Phases  (all three default requirement fields required)
    # ------------------------------------------------------------------
    print("Seeding phases collection...")
    phases = [
        {
            "phase_id": "requirement",
            "name": "Requirement",
            "sort_order": 1,
            "default_agent_role": "Requirements analyst agent",
            "default_cacheable_fraction": 0.8,
            "ams_classified": False,
            "default_complexity_tier": "moderate",
            "default_reasoning_complexity": "single-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "design",
            "name": "Design",
            "sort_order": 2,
            "default_agent_role": "UX/solution design agent",
            "default_cacheable_fraction": 0.7,
            "ams_classified": False,
            "default_complexity_tier": "moderate",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "architecture",
            "name": "Architecture",
            "sort_order": 3,
            "default_agent_role": "Architecture agent",
            "default_cacheable_fraction": 0.9,
            "ams_classified": False,
            "default_complexity_tier": "complex",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "high-fidelity",
        },
        {
            "phase_id": "development",
            "name": "Development",
            "sort_order": 4,
            "default_agent_role": "Coding agent(s)",
            "default_cacheable_fraction": 0.5,
            "ams_classified": False,
            "default_complexity_tier": "complex",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "high-fidelity",
        },
        {
            "phase_id": "testing",
            "name": "Testing",
            "sort_order": 5,
            "default_agent_role": "Test design agent",
            "default_cacheable_fraction": 0.6,
            "ams_classified": False,
            "default_complexity_tier": "moderate",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "test_data_build",
            "name": "Test Data Build",
            "sort_order": 6,
            "default_agent_role": "Data synthesis agent",
            "default_cacheable_fraction": 0.8,
            "ams_classified": False,
            "default_complexity_tier": "simple",
            "default_reasoning_complexity": "single-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "devops",
            "name": "DevOps",
            "sort_order": 7,
            "default_agent_role": "DevOps agent",
            "default_cacheable_fraction": 0.7,
            "ams_classified": False,
            "default_complexity_tier": "moderate",
            "default_reasoning_complexity": "single-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "aiops",
            "name": "AIOps",
            "sort_order": 8,
            "default_agent_role": "Ops/monitoring agent",
            "default_cacheable_fraction": 0.4,
            "ams_classified": True,
            "default_complexity_tier": "moderate",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "standard",
        },
        {
            "phase_id": "data_pipeline",
            "name": "Data Pipeline",
            "sort_order": 9,
            "default_agent_role": "Data engineering agent",
            "default_cacheable_fraction": 0.5,
            "ams_classified": True,
            "default_complexity_tier": "complex",
            "default_reasoning_complexity": "multi-step",
            "default_output_quality": "high-fidelity",
        },
        {
            "phase_id": "ams_run_support",
            "name": "AMS Run Support",
            "sort_order": 10,
            "default_agent_role": "Support agent",
            "default_cacheable_fraction": 0.8,
            "ams_classified": True,
            "default_complexity_tier": "simple",
            "default_reasoning_complexity": "direct",
            "default_output_quality": "standard",
        },
    ]
    if phases:
        await db.phases.insert_many(phases)
    print(f"  Inserted {len(phases)} phases.")

    # ------------------------------------------------------------------
    # 4. Seed Optimizer Rules  (unchanged from v1 — rules have no new fields)
    # ------------------------------------------------------------------
    print("Seeding optimizer_rules collection...")
    rules = [
        {
            "rule_id": "prompt_pruning",
            "version": 1,
            "name": "Context Pruning Optimizer",
            "description": "Prunes stale context tokens when context ratio is high.",
            "category": "context_pruning",
            "condition": {
                "field": "context_input_tokens_ratio",
                "operator": ">=",
                "threshold": 0.4,
            },
            "token_pool": "input",
            "savings_percentage": {"low": 0.15, "expected": 0.25, "high": 0.35},
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "rule_id": "context_caching",
            "version": 1,
            "name": "Context Caching Rule",
            "description": "Applies discount pricing for cached repeating inputs.",
            "category": "caching",
            "condition": {
                "field": "cacheable_fraction",
                "operator": ">=",
                "threshold": 0.5,
            },
            "token_pool": "input",
            "savings_percentage": {"low": 0.30, "expected": 0.40, "high": 0.50},
            "max_reduction": 0.60,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "rule_id": "batch_processing",
            "version": 1,
            "name": "Batch Discount Rule",
            "description": "Triggers 50% discount pricing for large asynchronous runs.",
            "category": "batch_processing",
            "condition": {
                "field": "total_input_tokens",
                "operator": ">=",
                "threshold": 50000,
            },
            "token_pool": "both",
            "savings_percentage": {"low": 0.50, "expected": 0.50, "high": 0.50},
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]
    if rules:
        await db.optimizer_rules.insert_many(rules)
    print(f"  Inserted {len(rules)} optimizer rules.")

    client.close()
    print("\nDatabase seeding completed successfully.")
    print("\nQuick-verification hints (run in mongosh):")
    print('  db.providers.findOne({provider_id:"deepseek"})   — expect implementation_type: "openai_compatible"')
    print('  db.models.findOne({provider:"deepseek"})          — expect complexity_tier, reasoning_complexity, ...')
    print('  db.phases.findOne({phase_id:"architecture"})      — expect default_complexity_tier: "complex"')


if __name__ == "__main__":
    asyncio.run(seed_database())