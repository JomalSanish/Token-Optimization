# Quickstart Validation Guide: Token Cost Estimator and Optimizer

This document provides step-by-step instructions to run, verify, and test the Token Cost Estimator and Optimizer platform.

## Prerequisites

- Python 3.11+
- MongoDB Atlas cluster (configured with collection structures defined in the [Data Model](file:///c:/Users/gauth/OneDrive/Documents/Token/token-optimizer/specs/001-token-cost-estimator/data-model.md))
- A local or system environment variable `MONGODB_URI` containing the MongoDB Atlas connection string, `MONGODB_DATABASE` containing the target database name, `APPLICATION_SECRET` containing the shared application secret, and `ADMIN_AUTH_SECRET` for administrative route authentication.

---

## 🛠️ Step 1: Backend Setup

Navigate to the `backend/` directory, create a virtual environment, and install dependencies:

```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install fastapi uvicorn motor httpx pydantic pytest pytest-asyncio
```

---

## 🧪 Step 2: Running Automated Tests

To verify that the calculation engine is pure and deterministic, run the pytest suite. This verifies the multiplicative compounding optimizer rules, caching math, and confidence ratings:

```bash
# Run all tests
pytest

# Run only unit tests verifying the pure cost calculations and capped optimizer compounding
pytest tests/unit/test_calc_engine.py
```

### Key Mathematical Verification Scenarios

You can verify the calculations match the worked example in the [Implementation Plan](file:///c:/Users/gauth/OneDrive/Documents/Token/token-optimizer/specs/001-token-cost-estimator/plan.md#calc-engine-design):
- **Scenario**: A phase has 100,000 input tokens and triggers a 30% reduction rule (`context_pruning`) and a 40% reduction rule (`caching`).
- **Expected Outcome**: Combined savings should compute to $1 - (1 - 0.3) \times (1 - 0.4) = 58\%$, and the optimized input count becomes 42,000 tokens. The test suite verifies this exact behavior.

---

## 🚀 Step 3: Running the Application Locally

Start the async backend dev server:

```bash
# Load environment secrets and run backend server
$env:MONGODB_URI="mongodb+srv://..."
$env:MONGODB_DATABASE="token_optimizer"
$env:ADMIN_AUTH_SECRET="test_admin_auth_secret_456"
$env:APPLICATION_SECRET="test_shared_app_secret_123"
$env:CORS_ORIGINS="*"

uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Verify that the interactive API documentation loads at: `http://127.0.0.1:8000/docs`

---

## 🛰️ Step 4: Validating Endpoint Contracts

You can use standard CLI tools (like `curl` or `Invoke-RestMethod` in PowerShell) to query endpoints and confirm compliance with [contracts](file:///c:/Users/gauth/OneDrive/Documents/Token/token-optimizer/specs/001-token-cost-estimator/contracts/):

### 1. Retrieve Models Catalog (Normal User)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/models" -Method Get -Headers @{ "X-Shared-Secret" = "frontend_backend_secret" }
```

### 2. Extract Phase Estimates (Transient Request)
```powershell
$body = @{
  project_description = "Build a simple weather dashboard displaying forecasts."
  document_summaries = @()
  provider = "openai"
  model_id = "gpt-4o"
  api_key = "sk-..." # Relayed only, never persisted
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/extract" -Method Post -Body $body -ContentType "application/json" -Headers @{ "X-Shared-Secret" = "frontend_backend_secret" }
```
