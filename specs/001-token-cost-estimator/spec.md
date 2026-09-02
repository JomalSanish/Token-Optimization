# Feature Specification: Token Cost Estimator and Optimizer

**Feature Branch**: `001-token-cost-estimator`

**Created**: 2026-08-24

**Status**: Draft

**Input**: User description: "Build a web platform that estimates and optimizes LLM token usage and cost across software delivery lifecycle phases..."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Interactive Estimation & Phase Cost Calculation (Priority: P1)

As a software delivery manager, I want to paste my project description, select an LLM provider, supply my own API key, and receive an editable per-phase estimation of token usage and costs so that I can forecast our AI tool costs and run what-if scenarios.

**Why this priority**: This is the core workflow of the platform. Without the ability to run estimates, view costs, and adjust inputs, the platform has no utility.

**Independent Test**: Can be fully tested by providing a simple project text description, selecting a mock provider, providing a dummy key, and verifying that the backend returns the phase estimation table and accurately calculates costs.

**Acceptance Scenarios**:

1. **Given** a user is on the Dashboard tab, **When** they paste a project description, select a provider (e.g., OpenAI), enter their provider API key, and click "Get Token Estimate", **Then** the backend extracts and returns a 10-row lifecycle phase table populated with estimated input, context, tool, and output token counts, low/medium/high confidence level tags, and assigned model IDs.
2. **Given** the extracted phase estimation table, **When** the user edits a cell (e.g., changes the development phase output tokens from 5,000 to 10,000) or changes the model assigned to a phase, **Then** that row's source is updated to "user-edited", preventing subsequent "Get Token Estimate" runs from overwriting that row's manually adjusted values.
3. **Given** the user-edited phase configuration, **When** the user clicks "Submit" to compute final costs, **Then** the calculation engine executes the formulas using active model pricing resolved from MongoDB, applies the deterministic optimizer rules, and renders:
   - Base cost vs. optimized cost per phase.
   - Active optimizer levers triggered per phase.
   - Total dollar and percentage savings (using multiplicative stacking rules).
   - An annual recurring rollup for AMS-classified phases.
   - A coding-tool advisory section (Development phase only) visually separated from computed savings.

---

### User Story 2 - Model, Provider, & Optimizer Rules Management (Priority: P2)

As a platform administrator, I want to manage the available models, providers, and optimization rule thresholds in a central catalog so that calculations are always based on authoritative metadata and pricing.

**Why this priority**: Governs the database inputs that the calculation engine relies upon. If administrators cannot update prices or thresholds, the calculator becomes outdated as provider models change.

**Independent Test**: Can be tested by calling the admin CRUD endpoints (GET/POST/PUT/DELETE) for models, providers, and rules, and verifying that changes are recorded in the database, pricing history logs are created, and future calculations automatically use the updated values.

**Acceptance Scenarios**:

1. **Given** an administrator updates a model's input pricing via the API, **When** the update is submitted, **Then** the system increments the model's `pricing_version`, inserts a record in `pricing_history` detailing the change, and marks the previous pricing version as inactive.
2. **Given** the administrator modifies an optimizer rule's condition threshold (e.g., changing the prompt caching trigger from context ratio > 0.5 to > 0.3), **When** a user subsequently submits an estimate, **Then** the calculation engine automatically applies the rule under the new threshold.

---

### User Story 3 - Dynamic AI Optimization Discovery (Priority: P3)

As a delivery architect, I want the system to analyze my project configuration beyond deterministic rules to discover novel optimization strategies and estimate their potential savings.

**Why this priority**: Enhances the product with advanced, contextual AI suggestions while ensuring they do not compromise the credibility of the primary, contract-bound calculation engine.

**Independent Test**: Can be tested by calling the `POST /discover-optimizations` endpoint with a phase configuration, verifying that the LLM returns structured strategy objects containing estimated savings and rationale, and confirming these savings are shown separately in the UI and never added to the primary savings total.

**Acceptance Scenarios**:

1. **Given** a generated project estimate, **When** the user views the optimization panel, **Then** the backend requests dynamic suggestions from the LLM, displaying the results under "AI-Estimated Potential" and "Unquantified Opportunities" distinct from the primary "Deterministic Savings" section.

---

### Edge Cases

- **MongoDB Catalog Unavailability**: If the MongoDB database is unreachable, backend cost calculations MUST fail gracefully with a descriptive error message rather than resorting to client-supplied or hardcoded prices.
- **Key Exhaustion and Pool Failures**: If a user-supplied API key is exhausted or invalid during extraction or discovery, the backend MUST return a specific error code indicating the key failure, prompting the client to rotate to the next key in their client-side pool.
- **Rule Stacking Capping**: If the compounded savings percentage of multiple stacked rules exceeds the specified `max_reduction` ceiling for a token pool, the final calculation MUST apply the cap exactly, logging the capping event.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Extraction -> Edit -> Submit Lifecycle Flow
- **FR-001**: The system MUST implement a three-step lifecycle for cost estimation:
  1. **Extraction**: Accepts user inputs (description, doc summaries, API key) and uses the LLM to populate a transient phase configuration.
  2. **Edit**: Allows the user to overwrite any cell in the UI phase table.
  3. **Submit**: Submits the final phase configuration to the stateless backend for deterministic cost calculation.
- **FR-002**: The backend estimation extraction endpoint MUST return a 10-row table corresponding to the seeded lifecycle phases: *Requirement, Design, Architecture, Development, Testing, Test Data Build, DevOps, AIOps, Data Pipeline, and AMS Run Support*.
- **FR-003**: The client-side application MUST support file uploads (diagrams, documents) by processing them locally (e.g., extracting page count or generating a brief text summary) and sending only the text metadata/summary to the backend. The raw files MUST NOT be sent to the backend.
- **FR-004**: Each row in the phase configuration table MUST track:
  - `phase_id` (string, stable identifier)
  - `agent_role` (string)
  - `base_input_tokens` (integer, low/high bounds)
  - `context_input_tokens` (integer, low/high bounds)
  - `cacheable_fraction` (decimal 0.0 - 1.0)
  - `tool_call_tokens` (integer, low/high bounds)
  - `output_tokens` (integer, low/high bounds)
  - `estimated_calls` (integer, number of LLM invocations)
  - `assigned_model_id` (string, model identifier from catalog)
  - `confidence` (string: "low", "medium", "high")
  - `source` (string: "LLM-extracted" or "user-edited")
- **FR-005**: If a row's `source` is flagged as `"user-edited"`, subsequent calls to the extraction endpoint MUST NOT overwrite the manually edited values for that row.
- **FR-006**: The calculation engine MUST reject or ignore any user-supplied pricing fields submitted in the request payload. Pricing MUST be resolved authoritatively by the backend from MongoDB Atlas collections.

#### Deterministic Optimizer Stacking Rules
- **FR-007**: When multiple optimization rules target the same token pool (input or output) in a phase, their savings percentages MUST compound multiplicatively.
- **FR-008**: The compounded multiplier for a token pool cost is defined as:
  $$\text{Compounded Multiplier} = \prod_{i=1}^{n} (1 - S_i)$$
  where $S_i$ is the savings percentage (as a decimal between 0 and 1) for each matching rule $i$.
- **FR-009**: The compounded savings percentage is defined as:
  $$\text{Compounded Savings} = 1 - \text{Compounded Multiplier}$$
- **FR-010**: The compounded savings percentage applied to a token pool in a phase MUST NOT exceed the `max_reduction` ceiling defined on the matching rules. If multiple matching rules specify `max_reduction`, the ceiling applied is the minimum of their `max_reduction` values:
  $$\text{Final Savings} = \min(\text{Compounded Savings}, \min_{i} (\text{max\_reduction}_i))$$
- **FR-011**: Savings percentages MUST NOT be combined using linear addition (e.g., Rule A with 20% savings and Rule B with 30% savings must result in exactly 44% combined savings, never 50%).
- **FR-012**: Recommendations requiring external tool adoption (e.g., adopting agentic coding skills, diff-based editors, batch APIs) are classified as *Advisory Recommendations*. Their estimated savings MUST NOT be folded into the computed savings totals. They MUST be displayed in a visually separate section.

#### AI Optimization Discovery
- **FR-013**: The system MUST expose a `POST /discover-optimizations` endpoint that analyzes the project description, extracted signals, and phase configurations to identify custom, context-specific optimization strategies.
- **FR-014**: Dynamic AI-discovered optimization savings percentages MUST NOT be added to the primary deterministic savings totals. They MUST be displayed separately in the UI as "AI-Estimated Potential" or "Unquantified Opportunities".
- **FR-015**: For each dynamic AI recommendation, the backend MUST validate that the estimated savings satisfy:
  $$0 \le \text{low\_percent} \le \text{expected\_percent} \le \text{high\_percent}$$
  If the LLM cannot confidently quantify the savings, it MUST return the recommendation as unquantified rather than inventing numbers.

### Key Entities

- **Model**: Represents an LLM model, its context window, capabilities, and pricing structure.
- **Provider**: Identifies LLM hosts (OpenAI, Google Gemini, Anthropic Claude) and their active status.
- **PricingHistory**: Records audit trail of model pricing updates.
- **OptimizerRule**: Configurable rule defining conditions under which a deterministic cost reduction applies to a phase's token pools.
- **LifecyclePhase**: Reference data defining the 10 lifecycle phases, their default configurations, and their AMS classification.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The backend cost calculation engine MUST complete deterministic calculations in under 200 milliseconds under a concurrent load of 10 requests.
- **SC-002**: 100% of calculations performed under identical phase configurations, pricing versions, and optimizer rule versions MUST yield identical, bit-for-bit cost and savings outputs (excluding dynamic AI discovery).
- **SC-003**: The user interface MUST enforce that advisory optimization recommendations and dynamic AI-discovered recommendations do not alter the primary cost totals, ensuring a 0% leakage rate between advisory/AI recommendations and deterministic calculations.
- **SC-004**: Stacking multiple optimization rules MUST compound using the multiplicative formula in 100% of cases, verified by automated unit tests.

---

## Assumptions

- **A-001**: Users have a client-side modern browser supporting `localStorage` for API key pool management.
- **A-002**: Database operations are read-heavy; model catalog and optimizer rules are updated infrequently by administrators.
- **A-003**: Network security is handled at the transport layer via TLS 1.3, ensuring raw API keys sent from the browser are protected in transit.
- **A-004**: The client application implements key rotation seamlessly when the backend reports quota limits or authorization failures.
