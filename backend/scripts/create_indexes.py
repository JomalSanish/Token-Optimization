import asyncio
import sys
import os
# Ensure root backend dir is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings

async def create_indexes():
    print("Connecting to MongoDB to establish indexes...")
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    
    # 1. models collection
    print("Creating models collection indexes...")
    # Unique compound index on (provider, model_id)
    models_res = await db.models.create_index(
        [("provider", 1), ("model_id", 1)],
        unique=True
    )
    print(f"Created index on models: {models_res}")
    
    # Index for active lookups
    models_active_res = await db.models.create_index(
        [("active", 1), ("model_id", 1)]
    )
    print(f"Created index on models active lookups: {models_active_res}")
    
    # 2. pricing_history collection
    print("Creating pricing_history collection indexes...")
    pricing_hist_res = await db.pricing_history.create_index(
        [("model_id", 1), ("changed_at", -1)]
    )
    print(f"Created index on pricing_history: {pricing_hist_res}")
    
    # 3. optimizer_rules collection
    print("Creating optimizer_rules collection indexes...")
    rules_res = await db.optimizer_rules.create_index(
        [("rule_id", 1), ("version", 1)],
        unique=True
    )
    print(f"Created index on optimizer_rules: {rules_res}")

    # 4. providers collection
    print("Creating providers collection indexes...")
    providers_res = await db.providers.create_index(
        [("provider_id", 1)],
        unique=True
    )
    print(f"Created index on providers: {providers_res}")
    
    # 5. phases collection
    print("Creating phases collection indexes...")
    phases_res = await db.phases.create_index(
        [("phase_id", 1)],
        unique=True
    )
    print(f"Created index on phases: {phases_res}")

    client.close()
    print("All indexes configured successfully.")

if __name__ == "__main__":
    asyncio.run(create_indexes())
