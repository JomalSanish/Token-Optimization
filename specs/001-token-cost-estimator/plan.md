# Implementation Plan: Token Cost Estimator and Optimizer

**Branch**: `001-token-cost-estimator` | **Date**: 2026-08-24 | **Spec**: [spec.md](file:///c:/Users/gauth/OneDrive/Documents/Token/token-optimizer/specs/001-token-cost-estimator/spec.md)

**Input**: Feature specification from [`specs/001-token-cost-estimator/spec.md`](file:///c:/Users/gauth/OneDrive/Documents/Token/token-optimizer/specs/001-token-cost-estimator/spec.md)

## Summary

The Token Cost Estimator and Optimizer platform is a stateless web platform designed to forecast and optimize LLM token usage and pricing across 10 distinct software delivery lifecycle phases. 

The technical approach implements:
1. A fully async Python backend using FastAPI and the `motor` MongoDB driver.
2. A separate Single Page Application (SPA) frontend running client-side, using local storage for rotating user provider API keys.
3. Centralized configuration database (MongoDB Atlas) storing provider and model definitions, active pricing snapshots, and deterministic optimizer rules.
4. An isolated, pure mathematical calculation and rule engine to ensure 100% reproducibility and strict adherence to the multiplicative compounding stacking rules.

## Technical Context

**Language/Version**: Python 3.11+ (Backend) and Vanilla HTML5/CSS3/JavaScript (Frontend).

**Primary Dependencies**: 
- **Backend**: `fastapi`, `uvicorn`, `motor` (async MongoDB client), `httpx` (async HTTP requests to LLM providers), `pydantic` (data validation).
- **Testing**: `pytest`, `pytest-asyncio`.

**Storage**: MongoDB Atlas (authoritative store for catalogs, models, prices, pricing history, phases, and optimizer rules). No server-side session databases are permitted.

**Testing**: `pytest` covering calc engine functions, repository queries, and Mock API provider key relays.

**Target Platform**: Standalone Dockerized container deployment on Linux server with TLS 1.3 enabled.

**Project Type**: separated web-service (REST API backend + static HTML/JS frontend).

**Performance Goals**: p95 endpoint latency < 200ms under 10 concurrent requests.

**Constraints**:
- Absolute statelessness: Zero server-side user data persistence, session storage, or persistent API key files.
- BYOK security: Provider keys only reside client-side and are relayed through memory per request.
- Multiplicative compounding savings capped at database-defined thresholds.

**Scale/Scope**: Support at least 10 concurrent users with independent rotating key pools without cross-talk.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Deterministic calculations only**: **PASSED**. Calculation and optimization math is isolated in pure, testable helper functions. LLMs only extract JSON signals or draft narratives.
- **Stateless backend compute**: **PASSED**. No cookies, session tokens, or local caching of user-supplied data exists in the backend. 
- **Relayed-only BYOK model**: **PASSED**. API keys are relayed in request headers or body and immediately dispatched to providers via `httpx.AsyncClient`. They are never written to database or disk.
- **Strict calculation reproducibility**: **PASSED**. MongoDB pricing version history and active catalog lookups guarantee that calculations yield the same outputs given identical snapshots and parameters.
- **Multiplicative compounding and ceilings**: **PASSED**. Stacking math computes $1 - \prod(1 - S_i)$ and caps cost reductions at $\min(\text{max\_reduction})$.
- **Shared secret and TLS security boundary**: **PASSED**. Requests require validation against a shared secret header, and all routes are HTTPS-only. Logs are audited to filter out credentials.
- **Advisory separation**: **PASSED**. Advisory tool-adoption savings are visually and mathematically isolated from computed savings.

## Project Structure

### Documentation (this feature)

```text
specs/001-token-cost-estimator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output (JSON Schemas)
    ├── get_models.json
    ├── post_extract.json
    ├── post_estimate.json
    ├── post_optimize.json
    └── post_discover.json
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── main.py          # FastAPI application & route register
│   ├── config.py        # Environmental variables & shared secret validation
│   ├── database.py      # Async MongoDB motor client configuration
│   ├── repository.py    # Database repository logic
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── calc_engine.py   # Pure calculation logic (formulas)
│   ├── rules_engine.py  # Compounding rule logic
│   └── admin_api/       # Admin routes & credentials validation
└── tests/
    ├── unit/            # Calc/rules engine isolated unit tests
    ├── integration/     # Mock API server tests
    └── conftest.py      # pytest fixtures

frontend/
├── src/
│   ├── components/      # UI Dashboard, Management and Optimizer elements
│   ├── services/        # REST API calls and key rotation logic
│   └── app.js           # Core JS entrypoint
├── styles.css           # Vanilla CSS styles
└── index.html           # Main SPA HTML structure
```

**Structure Decision**: Separated `backend/` and `frontend/` directories to isolate the backend REST service from the frontend static client.

## Complexity Tracking

*No constitutional violations exist; all requirements are fully aligned. Thus, complexity tracking is blank.*
