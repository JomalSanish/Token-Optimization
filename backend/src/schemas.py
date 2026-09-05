from pydantic import BaseModel, Field, ConfigDict, model_validator
from decimal import Decimal
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# Common Configuration for schemas to allow database compatibility
common_config = ConfigDict(
    populate_by_name=True,
    json_encoders={datetime: lambda v: v.isoformat()}
)

# 1. ModelPricing Schemas
class ModelPricing(BaseModel):
    input_per_1m: Decimal
    output_per_1m: Decimal
    cached_input_per_1m: Decimal
    batch_input_per_1m: Decimal
    batch_output_per_1m: Decimal
    
    model_config = common_config

# --- T007: Model capability tag enums (fixed sets — no free-text allowed) ---
COMPLEXITY_TIER_VALUES = {"simple", "moderate", "complex", "frontier"}
REASONING_COMPLEXITY_VALUES = {"direct", "single-step", "multi-step", "deep-reasoning"}
OUTPUT_QUALITY_VALUES = {"draft", "standard", "high-fidelity", "expert-grade"}
PRIMARY_USE_VALUES = {
    "extraction", "classification", "summarization", "code-generation",
    "reasoning", "instruction-following", "long-context", "multimodal"
}

class ModelIn(BaseModel):
    provider: str
    model_id: str
    display_name: str
    pricing: ModelPricing
    context_window: int
    capabilities: List[str]
    active: bool = True

    # --- NEW (T007): four required capability tags; all required, no defaults ---
    complexity_tier: str
    reasoning_complexity: str
    output_quality: str
    primary_use: List[str]  # non-empty list of PRIMARY_USE_VALUES

    model_config = common_config

    @model_validator(mode="after")
    def validate_capability_tags(self) -> "ModelIn":
        if self.complexity_tier not in COMPLEXITY_TIER_VALUES:
            raise ValueError(
                f"complexity_tier must be one of {sorted(COMPLEXITY_TIER_VALUES)}, "
                f"got '{self.complexity_tier}'"
            )
        if self.reasoning_complexity not in REASONING_COMPLEXITY_VALUES:
            raise ValueError(
                f"reasoning_complexity must be one of {sorted(REASONING_COMPLEXITY_VALUES)}, "
                f"got '{self.reasoning_complexity}'"
            )
        if self.output_quality not in OUTPUT_QUALITY_VALUES:
            raise ValueError(
                f"output_quality must be one of {sorted(OUTPUT_QUALITY_VALUES)}, "
                f"got '{self.output_quality}'"
            )
        if not self.primary_use:
            raise ValueError("primary_use must contain at least one value")
        invalid = set(self.primary_use) - PRIMARY_USE_VALUES
        if invalid:
            raise ValueError(
                f"primary_use contains invalid values: {sorted(invalid)}. "
                f"Allowed: {sorted(PRIMARY_USE_VALUES)}"
            )
        return self

class ModelOut(ModelIn):
    pricing_version: int = 1
    effective_from: datetime
    created_at: datetime
    updated_at: datetime
    
    model_config = common_config


# --- T005: AdapterTemplate sub-schema (used when implementation_type = "template") ---
class AdapterTemplate(BaseModel):
    """Declarative adapter configuration for novel-schema providers.

    All six fields are required. No code, scripts, or expressions may appear
    in any field — the generic dispatcher treats all values as static strings
    with only the four allowed placeholder tokens: {model_id}, {api_key},
    {system_prompt}, {user_prompt}.
    """
    request_url: str        # HTTPS URL, SSRF-validated at save time
    http_method: str        # e.g. "POST"
    header_template: Dict[str, str]   # header name → static value (may use {api_key})
    body_template: Dict[str, Any]     # JSON structure with optional placeholder refs
    response_text_path: str           # dot-path with [n] index support
    error_message_path: str           # dot-path to provider's error message field

    model_config = common_config


# --- T006: Provider implementation type enum ---
IMPLEMENTATION_TYPE_VALUES = {"native", "openai_compatible", "template"}
# Fixed backend-registered native implementation keys (developer-shipped only)
NATIVE_REGISTRY_KEYS = {"openai", "anthropic", "google"}

# 2. Provider Schemas
class ProviderIn(BaseModel):
    """Provider record schema.

    implementation_type is required. Conditional fields are validated by
    model_validator depending on the chosen type:
      - native: native_key must be present and in NATIVE_REGISTRY_KEYS
      - openai_compatible: base_url must be present (SSRF-validated at route layer)
      - template: adapter_template must be fully populated (SSRF-validated at route layer)
    """
    provider_id: str
    display_name: str
    active: bool = True

    # --- NEW (T006) ---
    implementation_type: str  # required; one of IMPLEMENTATION_TYPE_VALUES

    # Type-specific fields (conditionally required — enforced by model_validator below)
    native_key: Optional[str] = None          # required when implementation_type = "native"
    base_url: Optional[str] = None            # required when implementation_type = "openai_compatible"
    adapter_template: Optional[AdapterTemplate] = None  # required when type = "template"

    model_config = common_config

    @model_validator(mode="after")
    def validate_implementation_type(self) -> "ProviderIn":
        impl = self.implementation_type
        if impl not in IMPLEMENTATION_TYPE_VALUES:
            raise ValueError(
                f"implementation_type must be one of {sorted(IMPLEMENTATION_TYPE_VALUES)}, "
                f"got '{impl}'"
            )
        if impl == "native":
            if not self.native_key:
                raise ValueError(
                    "native_key is required when implementation_type is 'native'"
                )
            if self.native_key not in NATIVE_REGISTRY_KEYS:
                raise ValueError(
                    f"native_key '{self.native_key}' is not a registered native implementation. "
                    f"Valid keys: {sorted(NATIVE_REGISTRY_KEYS)}"
                )
        elif impl == "openai_compatible":
            if not self.base_url:
                raise ValueError(
                    "base_url is required when implementation_type is 'openai_compatible'"
                )
        elif impl == "template":
            if not self.adapter_template:
                raise ValueError(
                    "adapter_template is required when implementation_type is 'template'"
                )
        return self

class ProviderOut(ProviderIn):
    """Full provider document — used by admin routes only.

    Includes native_key and adapter_template internals. MUST NOT be used
    as the response_model for any public (non-admin) endpoint.
    """
    created_at: datetime
    updated_at: datetime

    model_config = common_config


# --- T024A: Public-safe provider view for GET /providers ---
class ProviderPublicOut(BaseModel):
    """Public provider view — excludes native_key and adapter_template.

    Used as response_model for GET /providers so internal dispatch details
    never leave the backend via the public endpoint.
    """
    provider_id: str
    display_name: str
    active: bool
    implementation_type: str
    base_url: Optional[str] = None  # present only for openai_compatible providers
    created_at: datetime
    updated_at: datetime

    model_config = common_config


# 3. PricingHistory Schema
class PricingHistoryOut(BaseModel):
    model_id: str
    provider: str
    previous_pricing: ModelPricing
    new_pricing: ModelPricing
    pricing_version: int
    changed_by: str
    changed_at: datetime
    reason: str
    
    model_config = common_config

# 4. OptimizerRule Schemas
class OptimizerRuleCondition(BaseModel):
    field: str
    operator: str
    threshold: Decimal
    
    model_config = common_config

class OptimizerRuleSavings(BaseModel):
    low: Decimal
    expected: Decimal
    high: Decimal
    
    model_config = common_config
    
    @model_validator(mode='after')
    def validate_bounds(self) -> 'OptimizerRuleSavings':
        if not (Decimal("0.0") <= self.low <= self.expected <= self.high <= Decimal("1.0")):
            raise ValueError("Rule savings must satisfy: 0 <= low <= expected <= high <= 1")
        return self

class OptimizerRuleIn(BaseModel):
    rule_id: str
    version: int
    name: str
    description: str
    category: str
    condition: OptimizerRuleCondition
    token_pool: str = Field(..., pattern="^(input|output|both)$")
    savings_percentage: OptimizerRuleSavings
    max_reduction: Decimal
    affected_phases: List[str]
    active: bool = True
    
    model_config = common_config

class OptimizerRuleOut(OptimizerRuleIn):
    created_at: datetime
    updated_at: datetime
    
    model_config = common_config


# --- T008: Phase capability requirement enums (same values as model tags) ---
PHASE_REQUIREMENT_FIELDS = {
    "default_complexity_tier": COMPLEXITY_TIER_VALUES,
    "default_reasoning_complexity": REASONING_COMPLEXITY_VALUES,
    "default_output_quality": OUTPUT_QUALITY_VALUES,
}

# 5. Phase Schema
class PhaseIn(BaseModel):
    phase_id: str
    name: str
    sort_order: int
    default_agent_role: str
    default_cacheable_fraction: Decimal
    ams_classified: bool

    # --- NEW (T008): three required default capability requirement fields ---
    default_complexity_tier: str       # required; same enum as model.complexity_tier
    default_reasoning_complexity: str  # required; same enum as model.reasoning_complexity
    default_output_quality: str        # required; same enum as model.output_quality

    model_config = common_config

    @model_validator(mode="after")
    def validate_phase_requirements(self) -> "PhaseIn":
        checks = {
            "default_complexity_tier": (self.default_complexity_tier, COMPLEXITY_TIER_VALUES),
            "default_reasoning_complexity": (self.default_reasoning_complexity, REASONING_COMPLEXITY_VALUES),
            "default_output_quality": (self.default_output_quality, OUTPUT_QUALITY_VALUES),
        }
        for field_name, (value, allowed) in checks.items():
            if value not in allowed:
                raise ValueError(
                    f"{field_name} must be one of {sorted(allowed)}, got '{value}'"
                )
        return self

class PhaseOut(PhaseIn):
    model_config = common_config


# --- T022 fix: PATCH /admin/phases/{phase_id} is a partial update per the API
# contract ("Request body: Any subset of mutable phase fields"). phase_id is
# intentionally NOT a field here so it can never be changed via PATCH — any
# phase_id sent in the body is silently ignored rather than rejected. All
# other fields (including sort_order, which IS mutable per the contract) are
# optional; only fields actually present in the request are applied, via
# `.model_dump(exclude_unset=True)` at the call site.
class PhaseUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    default_agent_role: Optional[str] = None
    default_cacheable_fraction: Optional[Decimal] = None
    ams_classified: Optional[bool] = None
    default_complexity_tier: Optional[str] = None
    default_reasoning_complexity: Optional[str] = None
    default_output_quality: Optional[str] = None

    model_config = common_config

    @model_validator(mode="after")
    def validate_phase_requirements_if_present(self) -> "PhaseUpdate":
        checks = {
            "default_complexity_tier": (self.default_complexity_tier, COMPLEXITY_TIER_VALUES),
            "default_reasoning_complexity": (self.default_reasoning_complexity, REASONING_COMPLEXITY_VALUES),
            "default_output_quality": (self.default_output_quality, OUTPUT_QUALITY_VALUES),
        }
        for field_name, (value, allowed) in checks.items():
            if value is not None and value not in allowed:
                raise ValueError(
                    f"{field_name} must be one of {sorted(allowed)}, got '{value}'"
                )
        return self


# --- T032: Route-model request/response schemas ---
class RouteModelRequest(BaseModel):
    """Request body for POST /route-model."""
    phase_id: str
    provider_id: str

    model_config = common_config

class RouteModelResponse(BaseModel):
    """Response for POST /route-model.

    match_type values:
      "exact"   — model meets or exceeds all three requirement dimensions
      "nearest" — fallback; no model fully met requirements; closest returned
      "none"    — provider has zero active models (valid, not an error)

    All model-specific fields are None when match_type is "none".
    """
    phase_id: str
    provider_id: str
    model_id: Optional[str] = None
    display_name: Optional[str] = None
    match_type: str  # "exact" | "nearest" | "none"
    ordinal_distance: Optional[int] = None
    blended_rate: Optional[Decimal] = None

    model_config = common_config


# --- API ENDPOINTS SCHEMAS ---

# 1. /extract endpoint schemas
class DocumentSummary(BaseModel):
    filename: str
    page_count: int
    summary: str
    
    model_config = common_config

class ExtractRequest(BaseModel):
    project_description: str
    document_summaries: List[DocumentSummary]
    provider: str
    model_id: str
    
    model_config = common_config

class ExtractedPhase(BaseModel):
    phase: str
    agent_role: str
    base_input_tokens: int
    context_input_tokens: int
    cacheable_fraction: Decimal
    tool_call_tokens: int
    output_tokens: int
    estimated_calls: int
    confidence: str
    source: str = "llm_extracted"
    
    model_config = common_config

class ExtractResponse(BaseModel):
    phases: List[ExtractedPhase]
    extraction_notes: str
    
    model_config = common_config


# 2. /estimate endpoint schemas
class EstimatedPhaseConfig(BaseModel):
    phase: str
    agent_role: str
    base_input_tokens: int
    context_input_tokens: int
    cacheable_fraction: Decimal
    tool_call_tokens: int
    output_tokens: int
    estimated_calls: int
    assigned_model_id: str
    assigned_provider: str
    source: str
    
    model_config = common_config

class AmsConfig(BaseModel):
    runs_per_year: int
    annual_growth_rate: Decimal
    horizon_years: int
    
    model_config = common_config

class EstimateRequest(BaseModel):
    phases: List[EstimatedPhaseConfig]
    ams_config: AmsConfig
    
    model_config = common_config

class PricingSnapshotModel(BaseModel):
    model_id: str
    provider: str
    pricing: ModelPricing
    pricing_version: int
    effective_from: datetime
    
    model_config = common_config

class PricingSnapshot(BaseModel):
    resolved_at: datetime
    models: List[PricingSnapshotModel]
    
    model_config = common_config

class EstimatedPhaseResult(BaseModel):
    phase: str
    effective_input_tokens: int
    cacheable_input_tokens: int
    output_tokens: int
    input_cost: Decimal
    output_cost: Decimal
    phase_cost: Decimal
    ams_classified: bool
    annualized: Dict[str, Decimal]
    
    model_config = common_config

class EstimateResponse(BaseModel):
    pricing_snapshot: PricingSnapshot
    phase_results: List[EstimatedPhaseResult]
    project_total_cost: Decimal
    ams_multi_year_total_cost: Decimal
    
    model_config = common_config


# 3. /optimize endpoint schemas
class OptimizeRequest(BaseModel):
    pricing_snapshot: PricingSnapshot
    phase_results: List[EstimatedPhaseResult]
    phases: List[EstimatedPhaseConfig]
    
    model_config = common_config

class TriggeredRule(BaseModel):
    rule_id: str
    version: int
    pool: str
    reduction_applied: Decimal
    
    model_config = common_config

class PhaseOptimization(BaseModel):
    phase: str
    triggered_rules: List[TriggeredRule]
    combined_input_reduction: Decimal
    combined_output_reduction: Decimal
    optimized_phase_cost: Decimal
    savings_amount: Decimal
    savings_percentage: Decimal
    
    model_config = common_config

class AdvisoryRecommendation(BaseModel):
    category: str
    phase: str
    description: str
    note: str = "adoption-required, not included in totals above"
    
    model_config = common_config

class OptimizeResponse(BaseModel):
    phase_optimizations: List[PhaseOptimization]
    total_savings_amount: Decimal
    total_savings_percentage: Decimal
    advisory_recommendations: List[AdvisoryRecommendation]
    
    model_config = common_config


# 4. /discover-optimizations endpoint schemas
class DiscoverRequest(BaseModel):
    project_description: str
    document_summaries: List[DocumentSummary]
    phases: List[EstimatedPhaseConfig]
    pricing_snapshot: PricingSnapshot
    estimate_result: EstimateResponse
    optimize_result: OptimizeResponse
    active_rules: List[Dict[str, Any]]
    
    model_config = common_config

class AiStrategySavings(BaseModel):
    low_percent: Decimal
    expected_percent: Decimal
    high_percent: Decimal
    
    model_config = common_config
    
    @model_validator(mode='after')
    def validate_bounds(self) -> 'AiStrategySavings':
        if not (Decimal("0.0") <= self.low_percent <= self.expected_percent <= self.high_percent <= Decimal("1.0")):
            raise ValueError("AI strategy savings bounds must satisfy: 0 <= low <= expected <= high <= 1")
        return self

class AiStrategy(BaseModel):
    strategy_id: str
    name: str
    category: str
    affected_phases: List[str]
    affected_token_pool: str
    description: str
    rationale: str
    mechanism: str
    estimated_savings: AiStrategySavings
    confidence: str
    assumptions: List[str]
    evidence: List[str]
    implementation_effort: str
    risk: str
    dependencies: List[str]
    overlap_with_existing_rules: str
    included_in_official_savings: bool = False
    
    model_config = common_config

class UnquantifiedOpportunity(BaseModel):
    name: str
    description: str
    rationale: str
    
    model_config = common_config

class DiscoverResponse(BaseModel):
    ai_strategies: List[AiStrategy]
    unquantified_opportunities: List[UnquantifiedOpportunity]
    
    model_config = common_config

