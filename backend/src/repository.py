from motor.motor_asyncio import AsyncIOMotorDatabase
from src.database import get_database
from typing import List, Dict, Any, Optional
from datetime import datetime

class CatalogRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self._db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is not None:
            return self._db
        return get_database()

    # --- MODELS ---

    async def get_active_models(self) -> List[Dict[str, Any]]:
        cursor = self.db.models.find({"active": True})
        return await cursor.to_list(length=100)

    async def get_all_models(self) -> List[Dict[str, Any]]:
        cursor = self.db.models.find()
        return await cursor.to_list(length=200)

    async def get_model_by_provider_and_id(self, provider: str, model_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.models.find_one({"provider": provider, "model_id": model_id})

    async def get_active_model_by_provider_and_id(
        self, provider: str, model_id: str
    ) -> Optional[Dict[str, Any]]:
        return await self.db.models.find_one(
            {"provider": provider, "model_id": model_id, "active": True}
        )

    # Backward-compatible alias for internal callers that have not yet migrated.
    async def get_active_model_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.models.find_one({"model_id": model_id, "active": True})

    async def get_active_models_by_provider(self, provider_id: str) -> List[Dict[str, Any]]:
        """Return all active models belonging to the given provider.

        Used by:
          - GET /providers/{provider_id}/models  (public endpoint)
          - POST /route-model                    (routing endpoint, caller passes provider_id)

        Returns an empty list (never raises 404) if the provider has no active models —
        callers handle the empty case by returning RouteModelResponse(match_type="none").
        """
        cursor = self.db.models.find({"provider": provider_id, "active": True})
        return await cursor.to_list(length=200)

    async def create_model(self, model_doc: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            **model_doc,
            "pricing_version": 1,
            "effective_from": now,
            "created_at": now,
            "updated_at": now
        }
        await self.db.models.insert_one(doc)
        return doc

    async def update_model_pricing(
        self,
        provider: str,
        model_id: str,
        new_pricing_dict: Dict[str, Any],
        reason: str,
        changed_by: str
    ) -> Optional[Dict[str, Any]]:
        # Fetch current model
        model = await self.get_model_by_provider_and_id(provider, model_id)
        if not model:
            return None
            
        now = datetime.utcnow()
        old_pricing = model["pricing"]
        new_version = model.get("pricing_version", 1) + 1
        
        # Write to pricing history
        history_doc = {
            "model_id": model_id,
            "provider": provider,
            "previous_pricing": old_pricing,
            "new_pricing": new_pricing_dict,
            "pricing_version": new_version,
            "changed_by": changed_by,
            "changed_at": now,
            "reason": reason
        }
        await self.db.pricing_history.insert_one(history_doc)
        
        # Update model
        updated = await self.db.models.find_one_and_update(
            {"provider": provider, "model_id": model_id},
            {
                "$set": {
                    "pricing": new_pricing_dict,
                    "pricing_version": new_version,
                    "effective_from": now,
                    "updated_at": now
                }
            },
            return_document=True
        )
        return updated

    async def set_model_active_status(self, provider: str, model_id: str, active: bool) -> Optional[Dict[str, Any]]:
        return await self.db.models.find_one_and_update(
            {"provider": provider, "model_id": model_id},
            {
                "$set": {
                    "active": active,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=True
        )

    async def get_pricing_history(self, model_id: str) -> List[Dict[str, Any]]:
        cursor = self.db.pricing_history.find({"model_id": model_id}).sort("changed_at", -1)
        return await cursor.to_list(length=100)


    # --- PROVIDERS ---

    async def get_active_providers(self) -> List[Dict[str, Any]]:
        cursor = self.db.providers.find({"active": True})
        return await cursor.to_list(length=50)

    async def get_all_providers(self) -> List[Dict[str, Any]]:
        cursor = self.db.providers.find()
        return await cursor.to_list(length=50)

    async def get_provider_by_id(self, provider_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.providers.find_one({"provider_id": provider_id})

    async def create_provider(self, provider_doc: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            **provider_doc,
            "created_at": now,
            "updated_at": now
        }
        await self.db.providers.insert_one(doc)
        return doc

    async def update_provider(
        self, provider_id: str, update_doc: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Perform a full field-level update on a provider document.

        *update_doc* should contain only the fields to overwrite (the caller
        builds this from the validated ProviderIn payload). `updated_at` is
        always refreshed automatically; `created_at` is never touched.

        Returns the updated document, or None if provider_id was not found.
        """
        update_doc["updated_at"] = datetime.utcnow()
        return await self.db.providers.find_one_and_update(
            {"provider_id": provider_id},
            {"$set": update_doc},
            return_document=True,
        )

    async def set_provider_active_status(self, provider_id: str, active: bool) -> Optional[Dict[str, Any]]:
        return await self.db.providers.find_one_and_update(
            {"provider_id": provider_id},
            {
                "$set": {
                    "active": active,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=True
        )


    # --- OPTIMIZER RULES ---

    async def get_active_rules(self) -> List[Dict[str, Any]]:
        cursor = self.db.optimizer_rules.find({"active": True})
        return await cursor.to_list(length=100)

    async def get_all_rules(self) -> List[Dict[str, Any]]:
        cursor = self.db.optimizer_rules.find()
        return await cursor.to_list(length=200)

    async def get_rule_by_id_and_version(self, rule_id: str, version: int) -> Optional[Dict[str, Any]]:
        return await self.db.optimizer_rules.find_one({"rule_id": rule_id, "version": version})

    async def create_rule(self, rule_doc: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow()
        doc = {
            **rule_doc,
            "created_at": now,
            "updated_at": now
        }
        await self.db.optimizer_rules.insert_one(doc)
        return doc

    async def set_rule_active_status(self, rule_id: str, active: bool) -> Optional[Dict[str, Any]]:
        # Update active flag across all versions of the rule_id
        await self.db.optimizer_rules.update_many(
            {"rule_id": rule_id},
            {
                "$set": {
                    "active": active,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return await self.db.optimizer_rules.find_one({"rule_id": rule_id})


    # --- LIFECYCLE PHASES ---

    async def get_phases(self) -> List[Dict[str, Any]]:
        cursor = self.db.phases.find().sort("sort_order", 1)
        return await cursor.to_list(length=50)

    async def get_phase_by_id(self, phase_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.phases.find_one({"phase_id": phase_id})

    async def create_phase(self, phase_doc: Dict[str, Any]) -> Dict[str, Any]:
        await self.db.phases.insert_one(phase_doc)
        return phase_doc

    async def update_phase(
        self, phase_id: str, update_doc: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Perform a field-level update on a phase document.

        *update_doc* contains only the fields to overwrite (built from the
        validated PhaseIn payload by the caller). Returns None if phase_id
        was not found.
        """
        return await self.db.phases.find_one_and_update(
            {"phase_id": phase_id},
            {"$set": update_doc},
            return_document=True,
        )

    async def set_phase_active_status(self, phase_id: str, active: bool) -> Optional[Dict[str, Any]]:
        """Activate or deactivate a phase by phase_id.

        Mirrors set_model_active_status / set_rule_active_status patterns.
        Returns the updated document, or None if not found.
        """
        return await self.db.phases.find_one_and_update(
            {"phase_id": phase_id},
            {"$set": {"active": active}},
            return_document=True,
        )
