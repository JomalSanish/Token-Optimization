from fastapi import APIRouter, Depends, HTTPException, status, Query
from src.admin_api.auth import validate_admin_auth
from src.repository import CatalogRepository
from src.validators import validate_provider_url
from src.schemas import (
    ModelIn, ModelOut, ModelPricing, ModelUpdate, ProviderIn, ProviderOut,
    OptimizerRuleIn, OptimizerRuleOut, PricingHistoryOut,
    PhaseIn, PhaseOut, PhaseUpdate, ProviderUpdate,
)
from pydantic import ValidationError
from typing import List, Dict, Any
from datetime import datetime
from decimal import Decimal

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

# T031: Capability tag partial update — separate PATCH route so the existing
# pricing-update path (/models/{model_id}/pricing) stays unchanged.
# Accepts a ModelUpdate body; only fields present in the request are applied.
# Enum validation is enforced by ModelUpdate's model_validator so invalid
# values automatically produce a 422 before this handler runs.
@admin_router.patch("/models/{model_id}/tags", response_model=ModelOut)
async def update_model_tags(
    model_id: str,
    update: ModelUpdate,
    provider: str = Query(..., description="Provider owning the model ID"),
):
    """Partial update for model capability tag fields.

    Only fields present in the request body are written; omitted fields are
    left unchanged.  All four capability tags are validated against their
    fixed enum sets — an invalid value returns 422 automatically.
    """
    # Verify the model exists under the given provider.
    provider_model = await repo.get_model_by_provider_and_id(provider, model_id)
    if not provider_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{provider}/{model_id}' not found."
        )
    mutable_fields = update.model_dump(exclude_unset=True)
    if not mutable_fields:
        # Nothing to update — return the existing document unchanged.
        return provider_model
    updated = await repo.update_model(provider, model_id, mutable_fields)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model capability tags."
        )
    return updated


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
    # T023: SSRF-validate base_url / adapter_template.request_url before saving.
    if provider.implementation_type == "openai_compatible" and provider.base_url:
        try:
            validate_provider_url(provider.base_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"base_url validation failed: {exc}",
            )
    if provider.implementation_type == "template" and provider.adapter_template:
        try:
            validate_provider_url(provider.adapter_template.request_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"adapter_template.request_url validation failed: {exc}",
            )
    existing = await repo.get_provider_by_id(provider.provider_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.provider_id}' already exists."
        )
    return await repo.create_provider(provider.model_dump())


# T024 (fixed): Partial provider update, per the API contract ("Request body:
# any subset of ProviderIn fields, including {"active": false} to
# deactivate."). Only fields actually present in the request are written.
# provider_id is not a field on ProviderUpdate, so it can never be changed.
#
# Because native/openai_compatible/template have conditional-required fields
# (enforced by ProviderIn's model_validator), a partial PATCH can't be
# validated in isolation — sending just {"active": false} must not trip a
# "base_url is required" error about fields the caller never touched. So we
# merge the submitted subset onto the *existing* document first, then
# validate the merged result against the full ProviderIn schema. Only fields
# actually submitted are sent to the DB write.
@admin_router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, provider: ProviderUpdate):
    existing = await repo.get_provider_by_id(provider_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found."
        )
    submitted_fields = provider.model_dump(exclude_unset=True)
    if not submitted_fields:
        # Nothing to update — return the existing document unchanged.
        return existing

    # Merge onto the existing document (existing values for anything not
    # submitted) and re-validate as a full ProviderIn for cross-field
    # consistency (e.g. implementation_type vs. its required sub-fields).
    merged = {**existing, **submitted_fields}
    try:
        validated = ProviderIn(**{
            k: v for k, v in merged.items()
            if k in ProviderIn.model_fields
        })
    except ValidationError as exc:
        # include_context=False: pydantic's default errors() embeds the raw
        # exception object (e.g. the ValueError raised by a model_validator)
        # in each error's "ctx", which is not JSON-serializable and would
        # otherwise crash FastAPI's own exception handler while trying to
        # build this very 422 response.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_context=False, include_url=False),
        )

    # SSRF-validate any URL present on the merged (post-update) document —
    # not just on newly-submitted fields, since e.g. changing
    # implementation_type to "openai_compatible" without resending base_url
    # would otherwise leave an unvalidated pre-existing base_url in effect.
    if validated.implementation_type == "openai_compatible" and validated.base_url:
        try:
            validate_provider_url(validated.base_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"base_url validation failed: {exc}",
            )
    if validated.implementation_type == "template" and validated.adapter_template:
        try:
            validate_provider_url(validated.adapter_template.request_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"adapter_template.request_url validation failed: {exc}",
            )

    updated = await repo.update_provider(provider_id, submitted_fields)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update provider."
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


# --- ADMIN PHASES ---

# T020: List all phases, ordered by sort_order (ascending, handled by repo).
@admin_router.get("/phases", response_model=List[PhaseOut])
async def get_all_phases():
    return await repo.get_phases()


# T021: Create a new phase.  All three default requirement fields are enforced
# by PhaseIn's model_validator — Pydantic will return 422 before this handler
# runs if any required field is missing or contains an invalid enum value.
# Uses the default 200 status code, matching the API contract ("Response 200:
# Created phase document") and the convention already used by every other
# admin create endpoint in this file (/models, /providers, /optimizer-rules).
@admin_router.post("/phases", response_model=PhaseOut)
async def create_phase(phase: PhaseIn):
    existing = await repo.get_phase_by_id(phase.phase_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phase '{phase.phase_id}' already exists."
        )
    phase_dict = phase.model_dump()
    if "default_cacheable_fraction" in phase_dict and isinstance(phase_dict["default_cacheable_fraction"], Decimal):
        phase_dict["default_cacheable_fraction"] = float(phase_dict["default_cacheable_fraction"])
    return await repo.create_phase(phase_dict)


# T022: Partial update of a phase, per the API contract ("Updates a phase
# (partial update). phase_id cannot be changed. Request body: Any subset of
# mutable phase fields"). The request body is a PhaseUpdate — every field is
# optional, so a caller may PATCH just `{"name": "..."}` or just
# `{"sort_order": 3}` without resending the rest of the document. Only fields
# actually present in the request (`exclude_unset=True`) are written, so
# omitted fields are left untouched rather than being misread as "clear this
# field". phase_id is not a field on PhaseUpdate at all, so it can never be
# changed via PATCH regardless of what the caller sends. sort_order IS
# mutable via PATCH per the contract.
@admin_router.patch("/phases/{phase_id}", response_model=PhaseOut)
async def update_phase(phase_id: str, phase: PhaseUpdate):
    existing = await repo.get_phase_by_id(phase_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phase '{phase_id}' not found."
        )
    mutable_fields = {
        k: (float(v) if isinstance(v, Decimal) else v)
        for k, v in phase.model_dump(exclude_unset=True).items()
    }
    if not mutable_fields:
        # Nothing to update — return the existing document unchanged rather
        # than issuing a no-op DB write.
        return existing
    updated = await repo.update_phase(phase_id, mutable_fields)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update phase."
        )
    return updated
