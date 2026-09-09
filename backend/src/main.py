from fastapi import FastAPI, Depends, status, HTTPException, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.database import connect_to_mongo, close_mongo_connection
from src.middleware import validate_shared_secret
from src.repository import CatalogRepository
from src.admin_api.routes import admin_router
from src.schemas import ModelOut, OptimizerRuleOut, ProviderPublicOut, RouteModelRequest, RouteModelResponse
from src.routing import best_fit_model
from pymongo.errors import PyMongoError
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="Token Optimizer API",
    description="Stateless cost estimation and optimization engine for LLM tokens.",
    version="1.0.0"
)

# Startup & Shutdown lifecycle hooks
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

# CORS configuration
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if settings.app_env.lower() not in {"development", "dev", "local", "test"} and "*" in origins:
    raise RuntimeError(
        "CORS_ORIGINS must be an explicit comma-separated origin list outside local development."
    )
if not origins:
    raise RuntimeError("CORS_ORIGINS must contain at least one explicit origin.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Centralized Error Handlers
@app.exception_handler(PyMongoError)
async def mongodb_exception_handler(request, exc):
    logger.error(f"Authoritative MongoDB database error: {str(exc)}")
    # Principle 2 / Acceptance Criteria 11: Fail safely with 503 instead of falling back to stale/user data
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authoritative configuration database is currently unavailable. Calculation aborted."
    )

# Register protected admin sub-router
app.include_router(admin_router)

# --- NORMAL ENDPOINTS (Protected by Shared Secret Header) ---

@app.get(
    "/models",
    response_model=List[ModelOut],
    tags=["catalog"]
)
async def get_active_models():
    """
    Public, read-only active model catalog used by the regular Dashboard.
    No administrative operations are exposed through this endpoint.
    """
    repo = CatalogRepository()
    try:
        models = await repo.get_active_models()
        return models
    except PyMongoError as e:
        logger.error(f"Database error during active models fetch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoritative configuration database is currently unavailable."
        )


@app.get(
    "/optimizer-rules",
    response_model=List[OptimizerRuleOut],
    tags=["catalog"]
)
async def get_active_optimizer_rules():
    """
    Public, read-only optimizer thresholds used by the regular Dashboard.
    Administrative rule mutations remain under /admin/*.
    """
    repo = CatalogRepository()
    try:
        return await repo.get_active_rules()
    except PyMongoError as e:
        logger.error(f"Database error during active optimizer rules fetch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoritative configuration database is currently unavailable."
        )


# T025: Public active-provider catalog — uses ProviderPublicOut so native_key
# and adapter_template internals are stripped at the FastAPI response-model layer.
@app.get(
    "/providers",
    response_model=List[ProviderPublicOut],
    dependencies=[Depends(validate_shared_secret)],
    tags=["catalog"]
)
async def get_active_providers():
    """
    Public, read-only active provider catalog.
    Returns only fields safe for external consumption; native_key and
    adapter_template are excluded by the ProviderPublicOut response model.
    """
    repo = CatalogRepository()
    try:
        return await repo.get_active_providers()
    except PyMongoError as e:
        logger.error(f"Database error during active providers fetch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoritative configuration database is currently unavailable."
        )


# T026: Models scoped to a single provider.
@app.get(
    "/providers/{provider_id}/models",
    response_model=List[ModelOut],
    dependencies=[Depends(validate_shared_secret)],
    tags=["catalog"]
)
async def get_provider_models(provider_id: str):
    """
    Returns active models for the given provider.
    Raises 404 if the provider_id is not found in the DB at all.
    Returns an empty list if the provider exists but has no active models.
    """
    repo = CatalogRepository()
    try:
        provider = await repo.get_provider_by_id(provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{provider_id}' not found."
            )
        return await repo.get_active_models_by_provider(provider_id)
    except HTTPException:
        raise
    except PyMongoError as e:
        logger.error(f"Database error during provider models fetch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoritative configuration database is currently unavailable."
        )


# T033: POST /route-model — best-fit model routing endpoint.
# Cache-Control: no-store is set on EVERY response (success, "none", and 404
# alike) per contracts/backend-api.md and constitution §IX: routing results
# MUST NOT be served from any cache because admin catalog edits must take
# immediate effect without a cache purge step.
@app.post(
    "/route-model",
    response_model=RouteModelResponse,
    dependencies=[Depends(validate_shared_secret)],
    tags=["routing"]
)
async def route_model(payload: RouteModelRequest, response: Response):
    """Return the best-fit active model for the given phase and provider.

    404 if phase_id or provider_id is not found in the DB.
    200 with match_type='none' if the provider exists but has zero active models.
    200 with match_type='exact' or 'nearest' otherwise.

    Cache-Control: no-store is always set so routing decisions are never
    served stale after an admin catalog change.
    """
    # Always stamp no-store regardless of the response outcome.
    response.headers["Cache-Control"] = "no-store"

    repo = CatalogRepository()
    try:
        # Fetch phase and provider; 404 if either is missing.
        #
        # NOTE: mutating `response.headers` above does NOT carry over to the
        # response FastAPI builds when an HTTPException is raised — the
        # exception handler constructs a fresh JSONResponse using only the
        # `headers=` kwarg passed to HTTPException itself. So Cache-Control
        # must be set explicitly on every HTTPException raised in this
        # endpoint, not just relied upon via the injected `response` object,
        # or 404s here would silently ship without it despite the comment
        # above and the contract's "every response... 404 alike" requirement.
        phase_doc = await repo.get_phase_by_id(payload.phase_id)
        if not phase_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Phase '{payload.phase_id}' not found.",
                headers={"Cache-Control": "no-store"},
            )

        provider_doc = await repo.get_provider_by_id(payload.provider_id)
        if not provider_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{payload.provider_id}' not found.",
                headers={"Cache-Control": "no-store"},
            )

        # Fetch the provider's active models.
        active_models = await repo.get_active_models_by_provider(payload.provider_id)

        # Provider exists but has no active models — valid, not an error (200).
        if not active_models:
            return RouteModelResponse(
                phase_id=payload.phase_id,
                provider_id=payload.provider_id,
                model_id=None,
                display_name=None,
                match_type="none",
                ordinal_distance=None,
                blended_rate=None,
            )

        # Run the pure best-fit routing algorithm.
        result = best_fit_model(phase_doc, active_models)
        if result is None:
            # best_fit_model returns None only when active_models is empty;
            # that path is already handled above, but guard defensively.
            return RouteModelResponse(
                phase_id=payload.phase_id,
                provider_id=payload.provider_id,
                model_id=None,
                display_name=None,
                match_type="none",
                ordinal_distance=None,
                blended_rate=None,
            )

        return RouteModelResponse(
            phase_id=payload.phase_id,
            provider_id=payload.provider_id,
            model_id=result["model_id"],
            display_name=result.get("display_name"),
            match_type=result["_match_type"],
            ordinal_distance=result["_ordinal_distance"],
            blended_rate=result["_blended_rate"],
        )

    except HTTPException:
        raise
    except PyMongoError as e:
        logger.error(f"Database error during route-model lookup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoritative configuration database is currently unavailable.",
            headers={"Cache-Control": "no-store"},
        )


# Import schemas for endpoints
from src.schemas import (
    ExtractRequest, ExtractResponse, ExtractedPhase,
    EstimateRequest, EstimateResponse, PricingSnapshot, PricingSnapshotModel, EstimatedPhaseResult,
    OptimizeRequest, OptimizeResponse, PhaseOptimization, TriggeredRule, AdvisoryRecommendation,
    DiscoverRequest, DiscoverResponse, AiStrategy, AiStrategySavings, UnquantifiedOpportunity
)
from src.llm_adapters import dispatch_llm_call
from src.calc_engine import (
    calculate_effective_input_tokens,
    calculate_cacheable_split,
    calculate_phase_raw_cost,
    calculate_ams_annualized_cost
)
from src.rules_engine import (
    match_rules_for_phase,
    calculate_compounded_reduction
)
import json
from datetime import datetime
from decimal import Decimal

# 1. /extract endpoint
@app.post(
    "/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(validate_shared_secret)],
    tags=["estimation"]
)
async def extract_project_signals(
    payload: ExtractRequest,
    x_provider_key: str = Header(..., alias="X-Provider-Key")
):
    """
    Calls the LLM using the provider key supplied in X-Provider-Key.
    The key is never accepted in the JSON body.
    """
    system_prompt = (
        "You are a stateless FinOps token estimation assistant. Analyze the project description "
        "and document summaries to extract estimated LLM token metrics for each of the 10 software "
        "delivery lifecycle phases: requirement, design, architecture, development, testing, "
        "test_data_build, devops, aiops, data_pipeline, ams_run_support.\n\n"
        "You MUST respond with a JSON object containing two keys:\n"
        "1. 'phases': An array of objects, one for each of the 10 phases. Each object must have keys:\n"
        "   - 'phase': string, matching the lowercase phase id slug (e.g., 'requirement')\n"
        "   - 'agent_role': string, the role description\n"
        "   - 'base_input_tokens': integer (0 or more)\n"
        "   - 'context_input_tokens': integer (0 or more)\n"
        "   - 'cacheable_fraction': decimal (between 0.0 and 1.0)\n"
        "   - 'tool_call_tokens': integer (0 or more)\n"
        "   - 'output_tokens': integer (0 or more)\n"
        "   - 'estimated_calls': integer (1 or more)\n"
        "   - 'confidence': string, one of: 'low', 'medium', 'high'\n"
        "2. 'extraction_notes': A markdown string explaining your estimation rationale and assumptions.\n\n"
        "Do NOT output anything other than raw, valid JSON. Ensure all keys exist."
    )
    
    docs_text = "\n".join([
        f"File: {d.filename}, Pages: {d.page_count}, Summary: {d.summary}"
        for d in payload.document_summaries
    ])
    user_prompt = (
        f"Project Description: {payload.project_description}\n\n"
        f"Supporting Documents Summary:\n{docs_text}"
    )
    
    try:
        # T027: Fetch the full provider document from DB and pass it to
        # dispatch_llm_call so the three-way implementation_type switch works
        # for openai_compatible and template providers (not just native).
        repo_inner = CatalogRepository()
        try:
            provider_doc = await repo_inner.get_provider_by_id(payload.provider)
        except PyMongoError as e:
            logger.error(f"Database error during provider lookup for extraction: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authoritative configuration database is currently unavailable."
            )
        if not provider_doc or not provider_doc.get("active", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider '{payload.provider}' not found or inactive."
            )

        response_text = await dispatch_llm_call(
            provider_doc=provider_doc,
            model_id=payload.model_id,
            api_key=x_provider_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        
        # Clean potential markdown wrappers
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        parsed = json.loads(clean_text)
        
        # Ensure all 10 phases are formatted correctly
        phases_list = []
        for p in parsed.get("phases", []):
            phases_list.append(ExtractedPhase(
                phase=p["phase"],
                agent_role=p.get("agent_role", "Agent"),
                base_input_tokens=int(p.get("base_input_tokens", 0)),
                context_input_tokens=int(p.get("context_input_tokens", 0)),
                cacheable_fraction=Decimal(str(p.get("cacheable_fraction", 0.0))),
                tool_call_tokens=int(p.get("tool_call_tokens", 0)),
                output_tokens=int(p.get("output_tokens", 0)),
                estimated_calls=max(1, int(p.get("estimated_calls", 1))),
                confidence=p.get("confidence", "medium"),
                source="llm_extracted"
            ))
            
        return ExtractResponse(
            phases=phases_list,
            extraction_notes=parsed.get("extraction_notes", "Estimation completed.")
        )
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM extraction response as JSON: {response_text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned invalid JSON structure: {str(e)}"
        )

# 2. /estimate endpoint
@app.post(
    "/estimate",
    response_model=EstimateResponse,
    dependencies=[Depends(validate_shared_secret)],
    tags=["estimation"]
)
async def estimate_costs(payload: EstimateRequest):
    """
    Resolves authoritative model pricing from MongoDB Atlas and runs
    the pure calculation cost engine asynchronously.
    """
    repo = CatalogRepository()
    
    # Step 1: Collect distinct provider/model pairs from the payload.
    # model_id is not globally unique; MongoDB uniqueness is (provider, model_id).
    distinct_models = list({
        (p.assigned_provider, p.assigned_model_id)
        for p in payload.phases
    })

    # Step 2: Resolve one MongoDB document per distinct provider/model pair.
    resolved_models: Dict[tuple[str, str], Dict[str, Any]] = {}
    for provider, model_id in distinct_models:
        try:
            model_doc = await repo.get_active_model_by_provider_and_id(provider, model_id)
        except PyMongoError as e:
            logger.error(f"Database unavailable during pricing lookup: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authoritative pricing database is currently unreachable. Estimation aborted."
            )

        if not model_doc:
            offending_phase = next(
                (p.phase for p in payload.phases
                 if p.assigned_provider == provider and p.assigned_model_id == model_id),
                "unknown"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assigned model '{provider}/{model_id}' in phase '{offending_phase}' is missing or inactive in the database."
            )
        resolved_models[(provider, model_id)] = model_doc

    # Step 3: Build Pricing Snapshot
    now = datetime.utcnow()
    snapshot_models = []
    for (provider, model_id), doc in resolved_models.items():
        snapshot_models.append(PricingSnapshotModel(
            model_id=model_id,
            provider=provider,
            pricing=doc["pricing"],
            pricing_version=doc.get("pricing_version", 1),
            effective_from=doc["effective_from"]
        ))
        
    pricing_snapshot = PricingSnapshot(
        resolved_at=now,
        models=snapshot_models
    )
    
    # Step 4: Resolve Phase classification variables (AMS-classified flag)
    # We query phases collection for matching metadata
    ams_flags: Dict[str, bool] = {}
    try:
        db_phases = await repo.get_phases()
        for p in db_phases:
            ams_flags[p["phase_id"]] = p.get("ams_classified", False)
    except PyMongoError as e:
        logger.error(f"Failed to fetch phases catalog metadata: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database failed to load lifecycle configuration metadata. Estimation aborted."
        )
        
    # Step 5: Execute calculations for each phase
    phase_results = []
    project_total_cost = Decimal("0.0")
    ams_multi_year_total_cost = Decimal("0.0")
    
    for phase_conf in payload.phases:
        model_doc = resolved_models[
            (phase_conf.assigned_provider, phase_conf.assigned_model_id)
        ]
        pricing = model_doc["pricing"]
        
        effective_in = calculate_effective_input_tokens(
            phase_conf.base_input_tokens,
            phase_conf.context_input_tokens,
            phase_conf.tool_call_tokens
        )
        
        splits = calculate_cacheable_split(
            effective_in,
            phase_conf.context_input_tokens,
            phase_conf.cacheable_fraction
        )
        
        costs = calculate_phase_raw_cost(
            non_cacheable_input_tokens=splits["non_cacheable_input_tokens"],
            cacheable_input_tokens=splits["cacheable_input_tokens"],
            output_tokens=phase_conf.output_tokens,
            estimated_calls=phase_conf.estimated_calls,
            pricing=pricing,
            use_batch=False
        )
        
        # Determine AMS classification
        is_ams = ams_flags.get(phase_conf.phase, False)
        
        # Calculate annualized projections if AMS
        annualized = {}
        if is_ams:
            ams_proj = calculate_ams_annualized_cost(
                costs["phase_cost"],
                payload.ams_config.runs_per_year,
                payload.ams_config.annual_growth_rate,
                payload.ams_config.horizon_years
            )
            annualized = ams_proj["yearly_costs"]
            ams_multi_year_total_cost += ams_proj["multi_year_total"]
        else:
            project_total_cost += costs["phase_cost"]
            
        phase_results.append(EstimatedPhaseResult(
            phase=phase_conf.phase,
            effective_input_tokens=effective_in,
            cacheable_input_tokens=splits["cacheable_input_tokens"],
            output_tokens=phase_conf.output_tokens,
            input_cost=costs["input_cost"],
            output_cost=costs["output_cost"],
            phase_cost=costs["phase_cost"],
            ams_classified=is_ams,
            annualized=annualized
        ))
        
    return EstimateResponse(
        pricing_snapshot=pricing_snapshot,
        phase_results=phase_results,
        project_total_cost=project_total_cost,
        ams_multi_year_total_cost=ams_multi_year_total_cost
    )

# 3. /optimize endpoint
@app.post(
    "/optimize",
    response_model=OptimizeResponse,
    dependencies=[Depends(validate_shared_secret)],
    tags=["optimization"]
)
async def optimize_estimates(payload: OptimizeRequest):
    """
    Applies active deterministic rules fetched from MongoDB Atlas at request time.
    Calculates compounded cost savings using the multiplicative capping stacking formula.
    """
    repo = CatalogRepository()
    
    # Step 1: Load active rules dynamically from MongoDB
    try:
        active_rules = await repo.get_active_rules()
    except PyMongoError as e:
        logger.error(f"Failed to fetch active rules from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Optimizer rules database is currently unreachable. Optimization aborted."
        )
        
    # Helper to convert pricing snapshot models back to lookup dictionary
    pricing_map = {
        (m.provider, m.model_id): m.pricing.model_dump()
        for m in payload.pricing_snapshot.models
    }
    
    phase_optimizations = []
    total_savings_amount = Decimal("0.0")
    advisory_recommendations = []
    
    # Map phase configurations for easy lookup
    original_phases_map = {p.phase: p for p in payload.phases}
    results_map = {r.phase: r for r in payload.phase_results}
    
    # Step 2: Loop through phases and evaluate rules
    for phase_id, phase_conf in original_phases_map.items():
        res = results_map.get(phase_id)
        if not res:
            continue
            
        pricing = pricing_map.get(
            (phase_conf.assigned_provider, phase_conf.assigned_model_id)
        )
        if not pricing:
            continue
            
        # Match optimizer rules
        phase_row_dict = phase_conf.model_dump()
        triggered_rules = match_rules_for_phase(phase_row_dict, active_rules)
        
        # Compound reductions for input and output pools
        input_red_res = calculate_compounded_reduction(triggered_rules, "input")
        output_red_res = calculate_compounded_reduction(triggered_rules, "output")
        
        input_reduction = input_red_res["reduction"]
        output_reduction = output_red_res["reduction"]
        
        # Check if batch processing is triggered
        use_batch = any(r.get("category") == "batch_processing" for r in triggered_rules)
        
        # Apply reductions to tokens
        optimized_non_cacheable_in = Decimal(str(res.effective_input_tokens - res.cacheable_input_tokens)) * (Decimal("1.0") - input_reduction)
        optimized_cacheable_in = Decimal(str(res.cacheable_input_tokens)) * (Decimal("1.0") - input_reduction)
        optimized_out = Decimal(str(res.output_tokens)) * (Decimal("1.0") - output_reduction)
        
        # Re-price using calculations
        costs = calculate_phase_raw_cost(
            non_cacheable_input_tokens=int(optimized_non_cacheable_in),
            cacheable_input_tokens=int(optimized_cacheable_in),
            output_tokens=int(optimized_out),
            estimated_calls=phase_conf.estimated_calls,
            pricing=pricing,
            use_batch=use_batch
        )
        
        optimized_cost = costs["phase_cost"]
        savings = res.phase_cost - optimized_cost
        if savings < 0:
            savings = Decimal("0.0")
            
        total_savings_amount += savings
        
        savings_pct = Decimal("0.0")
        if res.phase_cost > 0:
            savings_pct = savings / res.phase_cost
            
        # Compile triggered rules outputs
        triggered_outputs = []
        for r in triggered_rules:
            # Skip compiling batch rule as direct token reduction if it only applies batch pricing
            pool = r.get("token_pool", "input")
            red = Decimal(str(r.get("savings_percentage", {}).get("expected", 0.0)))
            triggered_outputs.append(TriggeredRule(
                rule_id=r["rule_id"],
                version=r.get("version", 1),
                pool=pool,
                reduction_applied=red
            ))
            
        phase_optimizations.append(PhaseOptimization(
            phase=phase_id,
            triggered_rules=triggered_outputs,
            combined_input_reduction=input_reduction,
            combined_output_reduction=output_reduction,
            optimized_phase_cost=optimized_cost,
            savings_amount=savings,
            savings_percentage=savings_pct
        ))
        
        # Capture advisory coding-tool recommendations (Development phase only)
        if phase_id == "development":
            advisory_recommendations.append(AdvisoryRecommendation(
                category="agentic_coding_tools",
                phase=phase_id,
                description="Adopt agentic coding patterns (diff-based editing and repository-aware context indexing) to decrease redundant generation.",
                note="adoption-required, not included in totals above"
            ))
            
    # Calculate global totals
    raw_total = sum(r.phase_cost for r in payload.phase_results)
    total_savings_pct = Decimal("0.0")
    if raw_total > 0:
        total_savings_pct = total_savings_amount / raw_total
        
    return OptimizeResponse(
        phase_optimizations=phase_optimizations,
        total_savings_amount=total_savings_amount,
        total_savings_percentage=total_savings_pct,
        advisory_recommendations=advisory_recommendations
    )

# 4. /discover-optimizations endpoint
@app.post(
    "/discover-optimizations",
    response_model=DiscoverResponse,
    dependencies=[Depends(validate_shared_secret)],
    tags=["optimization"]
)
async def discover_custom_optimizations(
    payload: DiscoverRequest,
    x_provider_key: str = Header(..., alias="X-Provider-Key")
):
    """
    LLM-assisted dynamic advisor. Returns novel recommendations and
    qualitative opportunities kept strictly separate from deterministic savings.
    """
    system_prompt = (
        "You are an expert AI FinOps optimization strategist. Analyze the project details, "
        "cost estimates, active rule definitions, and optimization configurations to discover "
        "novel, custom optimization actions that are NOT covered by current deterministic rules.\n\n"
        "You MUST respond with a JSON object containing two keys:\n"
        "1. 'ai_strategies': An array of objects. Each object represents a custom saving strategy and MUST have keys:\n"
        "   - 'strategy_id': string (slug)\n"
        "   - 'name': string\n"
        "   - 'category': string\n"
        "   - 'affected_phases': array of phase ids (e.g. ['development'])\n"
        "   - 'affected_token_pool': string ('input', 'output', 'both')\n"
        "   - 'description': string\n"
        "   - 'rationale': string\n"
        "   - 'mechanism': string\n"
        "   - 'estimated_savings': object with keys: 'low_percent', 'expected_percent', 'high_percent' (all decimals 0.0 - 1.0)\n"
        "   - 'confidence': string ('low', 'medium', 'high')\n"
        "   - 'assumptions': array of strings\n"
        "   - 'evidence': array of strings\n"
        "   - 'implementation_effort': string ('low', 'medium', 'high')\n"
        "   - 'risk': string\n"
        "   - 'dependencies': array of strings\n"
        "   - 'overlap_with_existing_rules': string (referencing active rules if any)\n"
        "   - 'included_in_official_savings': boolean (MUST be false)\n"
        "2. 'unquantified_opportunities': An array of objects representing qualitative advice. Keys:\n"
        "   - 'name': string\n"
        "   - 'description': string\n"
        "   - 'rationale': string\n\n"
        "Do NOT output anything other than raw, valid JSON. Ensure savings bounds satisfy: 0 <= low <= expected <= high <= 1."
    )
    
    # Pass user key and relay request
    active_rules_list = ",".join([r.get("rule_id", "rule") for r in payload.active_rules])
    user_prompt = (
        f"Project Description: {payload.project_description}\n\n"
        f"Active Deterministic Rules: [{active_rules_list}]\n"
        f"Raw total cost: {payload.estimate_result.project_total_cost} USD\n"
        f"Compounded savings achieved: {payload.optimize_result.total_savings_amount} USD\n"
    )
    
    # Determine provider and model for the advisor run:
    # Prefer explicit provider and model_id from payload (e.g. from extraction context),
    # otherwise fall back to matching or first model in pricing_snapshot.
    target_provider = payload.provider
    target_model_id = payload.model_id

    if not target_provider or not target_model_id:
        if not payload.pricing_snapshot.models:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pricing snapshot contains no active models to execute the discovery request."
            )
        matched_model = None
        if target_provider:
            for m in payload.pricing_snapshot.models:
                if m.provider == target_provider:
                    matched_model = m
                    break
        if not matched_model:
            matched_model = payload.pricing_snapshot.models[0]
            
        target_provider = target_provider or matched_model.provider
        target_model_id = target_model_id or matched_model.model_id

    try:
        repo_inner = CatalogRepository()
        try:
            provider_doc = await repo_inner.get_provider_by_id(target_provider)
        except PyMongoError as e:
            logger.error(f"Database error during provider lookup for discovery: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authoritative configuration database is currently unavailable."
            )
        if not provider_doc or not provider_doc.get("active", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider '{target_provider}' not found or inactive."
            )

        response_text = await dispatch_llm_call(
            provider_doc=provider_doc,
            model_id=target_model_id,
            api_key=x_provider_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        parsed = json.loads(clean_text)
        
        strategies = []
        for s in parsed.get("ai_strategies", []):
            savings = s.get("estimated_savings", {})
            low = Decimal(str(savings.get("low_percent", 0.0)))
            expected = Decimal(str(savings.get("expected_percent", 0.0)))
            high = Decimal(str(savings.get("high_percent", 0.0)))
            
            # Enforce constraints: 0 <= low <= expected <= high <= 1.0
            if not (Decimal("0.0") <= low <= expected <= high <= Decimal("1.0")):
                low = expected = high = Decimal("0.0")
                
            strategies.append(AiStrategy(
                strategy_id=s["strategy_id"],
                name=s["name"],
                category=s.get("category", "custom"),
                affected_phases=s.get("affected_phases", []),
                affected_token_pool=s.get("affected_token_pool", "input"),
                description=s.get("description", ""),
                rationale=s.get("rationale", ""),
                mechanism=s.get("mechanism", ""),
                estimated_savings=AiStrategySavings(
                    low_percent=low,
                    expected_percent=expected,
                    high_percent=high
                ),
                confidence=s.get("confidence", "medium"),
                assumptions=s.get("assumptions", []),
                evidence=s.get("evidence", []),
                implementation_effort=s.get("implementation_effort", "medium"),
                risk=s.get("risk", ""),
                dependencies=s.get("dependencies", []),
                overlap_with_existing_rules=s.get("overlap_with_existing_rules", ""),
                included_in_official_savings=False # Hardcoded constraint
            ))
            
        unquantified = []
        for o in parsed.get("unquantified_opportunities", []):
            unquantified.append(UnquantifiedOpportunity(
                name=o["name"],
                description=o.get("description", ""),
                rationale=o.get("rationale", "")
            ))
            
        return DiscoverResponse(
            ai_strategies=strategies,
            unquantified_opportunities=unquantified
        )
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM discovery response: {response_text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI returned invalid JSON structure: {str(e)}"
        )


