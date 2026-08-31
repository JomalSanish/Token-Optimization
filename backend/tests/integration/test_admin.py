import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from src.main import app
from src.database import db_conn
from src.config import settings

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_db():
    # Mock DatabaseConnection client to prevent actual connections during routing tests
    db_conn.client = MagicMock()
    db_conn.db = MagicMock()
    yield
    db_conn.client = None
    db_conn.db = None

def test_models_endpoint_shared_secret_protection():
    # 1. No shared secret header
    response = client.post("/estimate", json={})
    assert response.status_code == 422 # missing header field validation error
    
    # 2. Invalid shared secret header
    response = client.post("/estimate", json={}, headers={"X-Shared-Secret": "wrong_secret"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid application secret header."
    
    # 3. Valid shared secret header but database yields error
    # We stub repo call to raise PyMongoError
    from pymongo.errors import ConnectionFailure
    db_conn.db.models.find_one = AsyncMock(side_effect=ConnectionFailure("Atlas unreachable"))
    
    body = {
        "phases": [
            {
                "phase": "development",
                "agent_role": "Coding agent(s)",
                "base_input_tokens": 1000,
                "context_input_tokens": 1000,
                "cacheable_fraction": 0.5,
                "tool_call_tokens": 1000,
                "output_tokens": 1000,
                "estimated_calls": 1,
                "assigned_model_id": "gpt-4o",
                "assigned_provider": "openai",
                "source": "llm_extracted"
            }
        ],
        "ams_config": {
            "runs_per_year": 12,
            "annual_growth_rate": 0.1,
            "horizon_years": 3
        }
    }
    
    response = client.post("/estimate", json=body, headers={"X-Shared-Secret": settings.application_secret})
    assert response.status_code == 503
    assert "unreachable" in response.json()["detail"]

def test_admin_endpoint_bearer_token_protection():
    # 1. No admin credentials
    response = client.get("/admin/models")
    assert response.status_code == 401 # unauthorized without credentials
    
    # 2. Invalid Bearer Token
    response = client.get("/admin/models", headers={"Authorization": "Bearer wrong_admin_secret"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing administrator credentials."
    
    # 3. Valid Bearer Token (successful routing, mock database response)
    db_conn.db.models.find.return_value.to_list = AsyncMock(return_value=[])
    response = client.get("/admin/models", headers={"Authorization": f"Bearer {settings.admin_auth_secret}"})
    assert response.status_code == 200
    assert response.json() == []
