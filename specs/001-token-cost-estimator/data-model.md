# Data Model: Token Cost Estimator and Optimizer

## Centralized Configuration Collections

This document outlines the schema shapes, validation rules, and indexes for the MongoDB Atlas database.

### 1. `models` Collection
Stores the authoritative catalog of active LLM models and their current pricing configurations.

#### Schema
```json
{
  "_id": "ObjectId",
  "provider": "string (openai | google | anthropic)",
  "model_id": "string (canonical identifier, e.g. gpt-4o)",
  "display_name": "string",
  "pricing": {
    "input_per_1m": "decimal (USD per 1M input tokens)",
    "output_per_1m": "decimal (USD per 1M output tokens)",
    "cached_input_per_1m": "decimal (USD per 1M cached input tokens)",
    "batch_input_per_1m": "decimal (USD per 1M input tokens under batch API)",
    "batch_output_per_1m": "decimal (USD per 1M output tokens under batch API)"
  },
  "pricing_version": "integer (incremented on pricing update)",
  "context_window": "integer (max input tokens)",
  "capabilities": ["array of strings (text | vision | tool_use | ...)"],
  "active": "boolean",
  "effective_from": "ISO datetime",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

#### Validation Rules
- `provider` MUST be one of: `"openai"`, `"google"`, `"anthropic"`.
- All `pricing` sub-fields MUST be non-negative decimals.
- `pricing_version` MUST be a positive integer >= 1.
- `context_window` MUST be a positive integer.

#### Indexes
- **Unique Compound Index**: `{"provider": 1, "model_id": 1}` (Enforces that a provider cannot have duplicate canonical model definitions).
- **Index for Active Lookups**: `{"active": 1, "model_id": 1}` (Optimizes fetching active models during estimations).

---

### 2. `providers` Collection
Tracks supported providers and their active status.

#### Schema
```json
{
  "_id": "ObjectId",
  "provider_id": "string (openai | google | anthropic)",
  "display_name": "string",
  "active": "boolean",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

#### Validation Rules
- `provider_id` MUST be unique and match provider slugs.

#### Indexes
- **Unique Index**: `{"provider_id": 1}`

---

### 3. `pricing_history` Collection
Maintains an audit trail of all model pricing changes.

#### Schema
```json
{
  "_id": "ObjectId",
  "model_id": "string (references models.model_id)",
  "provider": "string",
  "previous_pricing": {
    "input_per_1m": "decimal",
    "output_per_1m": "decimal",
    "cached_input_per_1m": "decimal",
    "batch_input_per_1m": "decimal",
    "batch_output_per_1m": "decimal"
  },
  "new_pricing": {
    "input_per_1m": "decimal",
    "output_per_1m": "decimal",
    "cached_input_per_1m": "decimal",
    "batch_input_per_1m": "decimal",
    "batch_output_per_1m": "decimal"
  },
  "pricing_version": "integer (the version introduced by this change)",
  "changed_by": "string (admin user identifier)",
  "changed_at": "ISO datetime",
  "reason": "string (free-text description)"
}
```

#### Indexes
- **Compound Index**: `{"model_id": 1, "changed_at": -1}` (Optimizes querying audit history for a specific model).

---

### 4. `optimizer_rules` Collection
Stores administrator-configured deterministic optimization logic and thresholds.

#### Schema
```json
{
  "_id": "ObjectId",
  "rule_id": "string (stable identifier slug, e.g. context_caching)",
  "version": "integer",
  "name": "string",
  "description": "string",
  "category": "string (context_pruning | caching | model_routing | output_compression | batch_processing | kg_summarization | deterministic_fallback)",
  "condition": {
    "field": "string (e.g. context_input_tokens_ratio)",
    "operator": "string (>= | > | <= | < | ==)",
    "threshold": "decimal"
  },
  "token_pool": "string (input | output | both)",
  "savings_percentage": {
    "low": "decimal 0.0 - 1.0",
    "expected": "decimal 0.0 - 1.0",
    "high": "decimal 0.0 - 1.0"
  },
  "max_reduction": "decimal 0.0 - 1.0",
  "affected_phases": ["array of strings (phase IDs, or ['*'] for all phases)"],
  "active": "boolean",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

#### Validation Rules
- `savings_percentage` values MUST satisfy: $0 \le \text{low} \le \text{expected} \le \text{high} \le 1.0$.
- `max_reduction` MUST be between 0.0 and 1.0.

#### Indexes
- **Unique Compound Index**: `{"rule_id": 1, "version": 1}` (Ensures optimizer rules are versioned and immutable).

---

### 5. `phases` Collection
Seeded lifecycle reference data defining the lifecycle phases.

#### Schema
```json
{
  "_id": "ObjectId",
  "phase_id": "string (canonical phase slug, e.g. development)",
  "name": "string",
  "sort_order": "integer (defining display sequence)",
  "default_agent_role": "string",
  "default_cacheable_fraction": "decimal 0.0 - 1.0",
  "ams_classified": "boolean"
}
```

#### Indexes
- **Unique Index**: `{"phase_id": 1}`
- **Sort Index**: `{"sort_order": 1}`
