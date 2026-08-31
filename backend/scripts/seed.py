import asyncio
import sys
import os
from datetime import datetime, timezone

# Ensure root backend dir is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings

async def seed_database():
    print("Connecting to MongoDB for seeding...")
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    now = datetime.now(timezone.utc)

    # 1. Seed Providers
    print("Seeding providers collection...")
    providers = [
        {"provider_id": "openai", "display_name": "OpenAI", "active": True, "created_at": now, "updated_at": now},
        {"provider_id": "google", "display_name": "Google Gemini", "active": True, "created_at": now, "updated_at": now},
        {"provider_id": "anthropic", "display_name": "Anthropic Claude", "active": True, "created_at": now, "updated_at": now}
    ]
    for p in providers:
        await db.providers.replace_one({"provider_id": p["provider_id"]}, p, upsert=True)

    # 2. Seed Models
    print("Seeding models collection...")
    models = [
        {
            "provider": "openai",
            "model_id": "gpt-4o",
            "display_name": "GPT-4o (Standard)",
            "pricing": {
                "input_per_1m": 5.00,
                "output_per_1m": 15.00,
                "cached_input_per_1m": 2.50,
                "batch_input_per_1m": 2.50,
                "batch_output_per_1m": 7.50
            },
            "pricing_version": 1,
            "context_window": 128000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
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
                "batch_output_per_1m": 0.300
            },
            "pricing_version": 1,
            "context_window": 128000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
        },
        {
            "provider": "anthropic",
            "model_id": "claude-3-5-sonnet",
            "display_name": "Claude 3.5 Sonnet",
            "pricing": {
                "input_per_1m": 3.00,
                "output_per_1m": 15.00,
                "cached_input_per_1m": 1.50,
                "batch_input_per_1m": 1.50,
                "batch_output_per_1m": 7.50
            },
            "pricing_version": 1,
            "context_window": 200000,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
        },
        {
            "provider": "google",
            "model_id": "gemini-2.5-flash",
            "display_name": "Google Gemini 2.5 Flash",
            "pricing": {
                "input_per_1m": 0.075,
                "output_per_1m": 0.30,
                "cached_input_per_1m": 0.01875,
                "batch_input_per_1m": 0.0375,
                "batch_output_per_1m": 0.15
            },
            "pricing_version": 1,
            "context_window": 1048576,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
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
                "batch_output_per_1m": 2.50
            },
            "pricing_version": 1,
            "context_window": 2097152,
            "capabilities": ["text", "vision", "tool_use"],
            "active": True,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
        }
    ]
    for m in models:
        await db.models.replace_one({"provider": m["provider"], "model_id": m["model_id"]}, m, upsert=True)

    # 3. Seed Phases
    print("Seeding phases collection...")
    phases = [
        {"phase_id": "requirement", "name": "Requirement", "sort_order": 1, "default_agent_role": "Requirements analyst agent", "default_cacheable_fraction": 0.8, "ams_classified": False},
        {"phase_id": "design", "name": "Design", "sort_order": 2, "default_agent_role": "UX/solution design agent", "default_cacheable_fraction": 0.7, "ams_classified": False},
        {"phase_id": "architecture", "name": "Architecture", "sort_order": 3, "default_agent_role": "Architecture agent", "default_cacheable_fraction": 0.9, "ams_classified": False},
        {"phase_id": "development", "name": "Development", "sort_order": 4, "default_agent_role": "Coding agent(s)", "default_cacheable_fraction": 0.5, "ams_classified": False},
        {"phase_id": "testing", "name": "Testing", "sort_order": 5, "default_agent_role": "Test design agent", "default_cacheable_fraction": 0.6, "ams_classified": False},
        {"phase_id": "test_data_build", "name": "Test Data Build", "sort_order": 6, "default_agent_role": "Data synthesis agent", "default_cacheable_fraction": 0.8, "ams_classified": False},
        {"phase_id": "devops", "name": "DevOps", "sort_order": 7, "default_agent_role": "DevOps agent", "default_cacheable_fraction": 0.7, "ams_classified": False},
        {"phase_id": "aiops", "name": "AIOps", "sort_order": 8, "default_agent_role": "Ops/monitoring agent", "default_cacheable_fraction": 0.4, "ams_classified": True},
        {"phase_id": "data_pipeline", "name": "Data Pipeline", "sort_order": 9, "default_agent_role": "Data engineering agent", "default_cacheable_fraction": 0.5, "ams_classified": True},
        {"phase_id": "ams_run_support", "name": "AMS Run Support", "sort_order": 10, "default_agent_role": "Support agent", "default_cacheable_fraction": 0.8, "ams_classified": True}
    ]
    for ph in phases:
        await db.phases.replace_one({"phase_id": ph["phase_id"]}, ph, upsert=True)

    # 4. Seed Optimizer Rules
    print("Seeding optimizer rules collection...")
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
                "threshold": 0.4
            },
            "token_pool": "input",
            "savings_percentage": {
                "low": 0.15,
                "expected": 0.25,
                "high": 0.35
            },
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now
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
                "threshold": 0.5
            },
            "token_pool": "input",
            "savings_percentage": {
                "low": 0.30,
                "expected": 0.40,
                "high": 0.50
            },
            "max_reduction": 0.60,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now
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
                "threshold": 50000
            },
            "token_pool": "both",
            "savings_percentage": {
                "low": 0.50,
                "expected": 0.50,
                "high": 0.50
            },
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True,
            "created_at": now,
            "updated_at": now
        }
    ]
    for r in rules:
        await db.optimizer_rules.replace_one({"rule_id": r["rule_id"], "version": r["version"]}, r, upsert=True)

    client.close()
    print("Database seeding completed.")

if __name__ == "__main__":
    asyncio.run(seed_database())