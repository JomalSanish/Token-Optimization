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


# ---------------------------------------------------------------------------
# T036: GET / POST / PATCH /admin/phases integration tests
# ---------------------------------------------------------------------------

_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.admin_auth_secret}"}

# Minimal valid phase document (all three new requirement fields present)
_PHASE_DOC = {
    "phase_id": "requirement",
    "name": "Requirements",
    "sort_order": 1,
    "default_agent_role": "Requirements Analyst",
    "default_cacheable_fraction": 0.4,
    "ams_classified": False,
    "default_complexity_tier": "moderate",
    "default_reasoning_complexity": "single-step",
    "default_output_quality": "standard",
}


def test_get_admin_phases_returns_seeded_phases():
    """T036: GET /admin/phases returns all phases with the three new requirement fields."""
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[_PHASE_DOC])
    db_conn.db.phases.find.return_value = mock_cursor

    response = client.get("/admin/phases", headers=_ADMIN_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    phase = data[0]
    assert phase["phase_id"] == "requirement"
    # Confirm all three new default requirement fields are present in the response
    assert "default_complexity_tier" in phase
    assert "default_reasoning_complexity" in phase
    assert "default_output_quality" in phase
    assert phase["default_complexity_tier"] == "moderate"
    assert phase["default_reasoning_complexity"] == "single-step"
    assert phase["default_output_quality"] == "standard"


def test_post_admin_phases_missing_required_field_returns_422():
    """T036: POST /admin/phases with missing default_output_quality returns 422
    with the field name in the error detail."""
    payload = dict(_PHASE_DOC)
    del payload["default_output_quality"]  # omit one required field

    response = client.post("/admin/phases", json=payload, headers=_ADMIN_HEADERS)
    assert response.status_code == 422, (
        f"Expected 422, got {response.status_code}: {response.text}"
    )
    detail_str = str(response.json().get("detail", ""))
    assert "default_output_quality" in detail_str, (
        f"Expected 'default_output_quality' in 422 detail, got: {detail_str}"
    )


def test_post_admin_phases_missing_complexity_tier_returns_422():
    """T036: POST /admin/phases with missing default_complexity_tier returns 422."""
    payload = dict(_PHASE_DOC)
    del payload["default_complexity_tier"]

    response = client.post("/admin/phases", json=payload, headers=_ADMIN_HEADERS)
    assert response.status_code == 422
    detail_str = str(response.json().get("detail", ""))
    assert "default_complexity_tier" in detail_str


def test_post_admin_phases_duplicate_phase_id_returns_400():
    """T036: POST /admin/phases with a duplicate phase_id returns 400."""
    # Simulate the phase already existing
    db_conn.db.phases.find_one = AsyncMock(return_value=_PHASE_DOC)

    response = client.post("/admin/phases", json=_PHASE_DOC, headers=_ADMIN_HEADERS)
    assert response.status_code == 400, (
        f"Expected 400 for duplicate phase_id, got {response.status_code}: {response.text}"
    )
    assert "already exists" in response.json()["detail"]


def test_post_admin_phases_success():
    """T036: POST /admin/phases with all required fields creates successfully."""
    # Phase does not yet exist (find_one returns None)
    db_conn.db.phases.find_one = AsyncMock(return_value=None)
    db_conn.db.phases.insert_one = AsyncMock(return_value=MagicMock())

    response = client.post("/admin/phases", json=_PHASE_DOC, headers=_ADMIN_HEADERS)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["phase_id"] == "requirement"
    assert data["default_complexity_tier"] == "moderate"


def test_patch_admin_phases_updates_sort_order_and_enum_fields():
    """T036: PATCH /admin/phases/{phase_id} updates sort_order and enum fields in place."""
    updated_phase = {
        **_PHASE_DOC,
        "sort_order": 5,
        "default_complexity_tier": "complex",
        "default_reasoning_complexity": "multi-step",
    }
    # Phase exists
    db_conn.db.phases.find_one = AsyncMock(return_value=_PHASE_DOC)
    db_conn.db.phases.find_one_and_update = AsyncMock(return_value=updated_phase)

    patch_body = {
        "sort_order": 5,
        "default_complexity_tier": "complex",
        "default_reasoning_complexity": "multi-step",
    }
    response = client.patch(
        "/admin/phases/requirement", json=patch_body, headers=_ADMIN_HEADERS
    )
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["sort_order"] == 5
    assert data["default_complexity_tier"] == "complex"
    assert data["default_reasoning_complexity"] == "multi-step"


def test_patch_admin_phases_invalid_enum_value_returns_422():
    """T036: PATCH /admin/phases/{phase_id} with an invalid enum value returns 422."""
    db_conn.db.phases.find_one = AsyncMock(return_value=_PHASE_DOC)

    patch_body = {"default_complexity_tier": "ultra-mega-extreme"}  # not a valid value
    response = client.patch(
        "/admin/phases/requirement", json=patch_body, headers=_ADMIN_HEADERS
    )
    assert response.status_code == 422, (
        f"Expected 422 for invalid enum, got {response.status_code}: {response.text}"
    )


def test_patch_admin_phases_not_found_returns_404():
    """T036: PATCH /admin/phases/{phase_id} returns 404 if phase doesn't exist."""
    db_conn.db.phases.find_one = AsyncMock(return_value=None)

    patch_body = {"sort_order": 99}
    response = client.patch(
        "/admin/phases/does-not-exist", json=patch_body, headers=_ADMIN_HEADERS
    )
    assert response.status_code == 404, (
        f"Expected 404 for unknown phase, got {response.status_code}: {response.text}"
    )
