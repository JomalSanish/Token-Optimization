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

class ModelIn(BaseModel):
    provider: str
    model_id: str
    display_name: str
    pricing: ModelPricing
    context_window: int
    capabilities: List[str]
    active: bool = True
    
    model_config = common_config

class ModelOut(ModelIn):
    pricing_version: int = 1
    effective_from: datetime
    created_at: datetime
    updated_at: datetime
    
    model_config = common_config

# 2. Provider Schemas
class ProviderIn(BaseModel):
    provider_id: str
    display_name: str
    active: bool = True
    
    model_config = common_config

class ProviderOut(ProviderIn):
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

# 5. Phase Schema
class PhaseIn(BaseModel):
    phase_id: str
    name: str
    sort_order: int
    default_agent_role: str
    default_cacheable_fraction: Decimal
    ams_classified: bool
    
    model_config = common_config

class PhaseOut(PhaseIn):
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

