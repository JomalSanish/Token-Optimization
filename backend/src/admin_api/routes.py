from fastapi import APIRouter, Depends, HTTPException, status, Query
from src.admin_api.auth import validate_admin_auth
from src.repository import CatalogRepository
from src.schemas import (
    ModelIn, ModelOut, ModelPricing, ProviderIn, ProviderOut,
    OptimizerRuleIn, OptimizerRuleOut, PricingHistoryOut
)
from typing import List, Dict, Any
from datetime import datetime

admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(validate_admin_auth)],
    tags=["admin"]
)

repo = CatalogRepository()

# Helper to find model by id and get its provider
async def get_provider_for_model(model_id: str) -> str:
    model_doc = await repo.db.models.find_one({"model_id": model_id})
    if not model_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found."
        )
    return model_doc["provider"]


# --- ADMIN MODELS ---

@admin_router.get("/models", response_model=List[ModelOut])
async def get_all_models():
    models = await repo.get_all_models()
    return models

@admin_router.post("/models", response_model=ModelOut)
async def create_model(model: ModelIn):
    # Check if duplicate (provider, model_id) exists
    existing = await repo.get_model_by_provider_and_id(model.provider, model.model_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model with id '{model.model_id}' under provider '{model.provider}' already exists."
        )
    model_dict = model.model_dump()
    return await repo.create_model(model_dict)

@admin_router.patch("/models/{model_id}", response_model=ModelOut)
async def update_model_pricing(
    model_id: str,
    pricing: ModelPricing,
    provider: str = Query(..., description="Provider owning the model ID"),
    reason: str = "Pricing updated by administrator",
    admin_id: str = "admin_user"
):
    # Require the provider because model IDs are only unique within a provider.
    provider_model = await repo.get_model_by_provider_and_id(provider, model_id)
    if not provider_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{provider}/{model_id}' not found."
        )
    pricing_dict = pricing.model_dump()
    updated = await repo.update_model_pricing(
        provider=provider,
        model_id=model_id,
        new_pricing_dict=pricing_dict,
        reason=reason,
        changed_by=admin_id
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model pricing."
        )
    return updated

@admin_router.post("/models/{model_id}/activate", response_model=ModelOut)
async def activate_model(model_id: str):
    provider = await get_provider_for_model(model_id)
    updated = await repo.set_model_active_status(provider, model_id, active=True)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate model."
        )
    return updated

@admin_router.post("/models/{model_id}/deactivate", response_model=ModelOut)
async def deactivate_model(model_id: str):
    provider = await get_provider_for_model(model_id)
    updated = await repo.set_model_active_status(provider, model_id, active=False)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate model."
        )
    return updated

@admin_router.get("/models/{model_id}/pricing-history", response_model=List[PricingHistoryOut])
async def get_model_pricing_history(model_id: str):
    # Verify model exists
    await get_provider_for_model(model_id)
    history = await repo.get_pricing_history(model_id)
    return history


# --- ADMIN PROVIDERS ---

@admin_router.get("/providers", response_model=List[ProviderOut])
async def get_all_providers():
    return await repo.get_all_providers()

@admin_router.post("/providers", response_model=ProviderOut)
async def create_provider(provider: ProviderIn):
    existing = await repo.get_provider_by_id(provider.provider_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.provider_id}' already exists."
        )
    return await repo.create_provider(provider.model_dump())

@admin_router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider_status(provider_id: str, active: bool):
    existing = await repo.get_provider_by_id(provider_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found."
        )
    updated = await repo.set_provider_active_status(provider_id, active)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update provider status."
        )
    return updated


# --- ADMIN OPTIMIZER RULES ---

@admin_router.get("/optimizer-rules", response_model=List[OptimizerRuleOut])
async def get_all_rules():
    return await repo.get_all_rules()

@admin_router.post("/optimizer-rules", response_model=OptimizerRuleOut)
async def create_optimizer_rule(rule: OptimizerRuleIn):
    # Verify unique (rule_id, version)
    existing = await repo.get_rule_by_id_and_version(rule.rule_id, rule.version)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Optimizer rule '{rule.rule_id}' with version '{rule.version}' already exists."
        )
    return await repo.create_rule(rule.model_dump())

@admin_router.patch("/optimizer-rules/{rule_id}", response_model=OptimizerRuleOut)
async def update_optimizer_rule(
    rule_id: str,
    update_data: Dict[str, Any]
):
    # Retrieve active version to update
    rule_doc = await repo.db.optimizer_rules.find_one({"rule_id": rule_id})
    if not rule_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found."
        )
        
    # Prevent modifying rule_id or version keys directly
    clean_update = {k: v for k, v in update_data.items() if k not in ["_id", "rule_id", "version"]}
    clean_update["updated_at"] = datetime.utcnow()
    
    updated = await repo.db.optimizer_rules.find_one_and_update(
        {"rule_id": rule_id},
        {"$set": clean_update},
        return_document=True
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update optimizer rule."
        )
    return updated

@admin_router.post("/optimizer-rules/{rule_id}/activate", response_model=OptimizerRuleOut)
async def activate_rule(rule_id: str):
    # Update active status for all versions
    updated = await repo.set_rule_active_status(rule_id, active=True)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found."
        )
    return updated

@admin_router.post("/optimizer-rules/{rule_id}/deactivate", response_model=OptimizerRuleOut)
async def deactivate_rule(rule_id: str):
    # Update active status for all versions
    updated = await repo.set_rule_active_status(rule_id, active=False)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found."
        )
    return updated
