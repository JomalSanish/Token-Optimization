import pytest
import logging
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from src.main import app
from src.database import db_conn

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_db():
    db_conn.client = MagicMock()
    db_conn.db = MagicMock()
    yield
    db_conn.client = None
    db_conn.db = None

@patch("src.main.dispatch_llm_call", new_callable=AsyncMock)
def test_secrets_are_never_logged(mock_llm, caplog):
    # Setup log level to INFO to capture general prints
    caplog.set_level(logging.INFO)
    
    secret_app_key = "test_shared_app_secret_123"
    secret_provider_key = "my_super_secret_provider_api_key_xyz987"
    
    mock_llm.return_value = '{"ai_strategies": [], "unquantified_opportunities": []}'
    
    # Setup mock active model pricing in DB for snapshot validation
    db_model = {
        "provider": "openai",
        "model_id": "gpt-4o",
        "pricing": {
            "input_per_1m": 5.0,
            "output_per_1m": 15.0,
            "cached_input_per_1m": 2.5,
            "batch_input_per_1m": 2.5,
            "batch_output_per_1m": 7.5
        },
        "pricing_version": 1,
        "effective_from": "2026-08-24T21:00:00"
    }
    db_conn.db.models.find_one = AsyncMock(return_value=db_model)

    body = {
        "project_description": "Audit security test.",
        "document_summaries": [],
        "phases": [],
        "pricing_snapshot": {
            "resolved_at": "2026-08-24T21:00:00",
            "models": [
                {
                    "model_id": "gpt-4o",
                    "provider": "openai",
                    "pricing": {
                        "input_per_1m": 5.0,
                        "output_per_1m": 15.0,
                        "cached_input_per_1m": 2.5,
                        "batch_input_per_1m": 2.5,
                        "batch_output_per_1m": 7.5
                    },
                    "pricing_version": 1,
                    "effective_from": "2026-08-24T21:00:00"
                }
            ]
        },
        "estimate_result": {
            "pricing_snapshot": {"resolved_at": "2026-08-24T21:00:00", "models": []},
            "phase_results": [],
            "project_total_cost": 10.0,
            "ams_multi_year_total_cost": 0.0
        },
        "optimize_result": {
            "phase_optimizations": [],
            "total_savings_amount": 2.0,
            "total_savings_percentage": 0.20,
            "advisory_recommendations": []
        },
        "active_rules": []
    }
    
    headers = {
        "X-Shared-Secret": secret_app_key,
        "X-Provider-Key": secret_provider_key
    }
    
    response = client.post("/discover-optimizations", json=body, headers=headers)
    assert response.status_code == 200
    
    # Verify captured log output contains neither secret
    for record in caplog.records:
        message = record.getMessage()
        assert secret_provider_key not in message, "SECURITY VIOLATION: User API Key leaked in server log!"
        assert secret_app_key not in message, "SECURITY VIOLATION: Shared Application Secret leaked in server log!"
