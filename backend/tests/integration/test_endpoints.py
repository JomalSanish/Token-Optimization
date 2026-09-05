import pytest
import json
import httpx
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from src.main import app
from src.database import db_conn
from src.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_db_and_auth():
    db_conn.client = MagicMock()
    db_conn.db = MagicMock()
    yield
    db_conn.client = None
    db_conn.db = None


# ---------------------------------------------------------------------------
# Shared stub provider documents
# ---------------------------------------------------------------------------

_OPENAI_PROVIDER_DOC = {
    "provider_id": "openai",
    "display_name": "OpenAI",
    "active": True,
    "implementation_type": "native",
    "native_key": "openai",
}

# Template provider — all six AdapterTemplate fields present.
# response_text_path = "result.text" so stubs wrap answers as
# {"result": {"text": "<llm json>"}}.
_TEMPLATE_PROVIDER_DOC = {
    "provider_id": "custom_llm",
    "display_name": "Custom LLM",
    "active": True,
    "implementation_type": "template",
    "adapter_template": {
        "request_url": "https://api.custom-llm.example.com/v1/generate",
        "http_method": "POST",
        "header_template": {
            "Authorization": "Bearer {api_key}",
            "Content-Type": "application/json",
        },
        "body_template": {
            "model": "{model_id}",
            "system": "{system_prompt}",
            "prompt": "{user_prompt}",
        },
        "response_text_path": "result.text",
        "error_message_path": "error.message",
    },
}

# ---------------------------------------------------------------------------
# Existing /extract smoke-test — fixed for T027 provider DB lookup
# ---------------------------------------------------------------------------

_EXTRACT_LLM_REPLY = json.dumps({
    "phases": [
        {
            "phase": "development",
            "agent_role": "Coding agent(s)",
            "base_input_tokens": 10000,
            "context_input_tokens": 20000,
            "cacheable_fraction": 0.5,
            "tool_call_tokens": 500,
            "output_tokens": 5000,
            "estimated_calls": 5,
            "confidence": "high",
        }
    ],
    "extraction_notes": "Extracted development phase details.",
})


@patch("src.main.dispatch_llm_call", new_callable=AsyncMock)
def test_extract_endpoint(mock_llm):
    # T027 added get_provider_by_id; mock the providers collection
    db_conn.db.providers.find_one = AsyncMock(return_value=_OPENAI_PROVIDER_DOC)
    mock_llm.return_value = _EXTRACT_LLM_REPLY
    body = {
        "project_description": "Build a weather application.",
        "document_summaries": [],
        "provider": "openai",
        "model_id": "gpt-4o",
    }
    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "mock_key",
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["phases"]) == 1
    assert res_data["phases"][0]["phase"] == "development"
    assert res_data["phases"][0]["base_input_tokens"] == 10000
    assert res_data["extraction_notes"] == "Extracted development phase details."

# ---------------------------------------------------------------------------
# T029-b: response_text_path extraction — pure unit test, no network / DB
# ---------------------------------------------------------------------------

def test_template_response_text_path_extraction():
    from src.llm_adapters import _extract_path

    # Simple nested dot-path
    nested = {"result": {"text": "The extracted LLM answer"}}
    assert _extract_path(nested, "result.text") == "The extracted LLM answer"

    # Array-index notation (OpenAI-shaped responses)
    openai_shaped = {"choices": [{"message": {"content": "OpenAI-style answer"}}]}
    assert _extract_path(openai_shaped, "choices[0].message.content") == "OpenAI-style answer"

    # Bad path must raise ValueError (mapped to 502 by _dispatch_template)
    with pytest.raises(ValueError, match="not found"):
        _extract_path(nested, "choices[0].message.content")

# ---------------------------------------------------------------------------
# T029-a: Token substitution round-trip via stubbed httpx.AsyncClient
# ---------------------------------------------------------------------------

@patch("src.llm_adapters.httpx.AsyncClient")
def test_template_dispatch_token_substitution(mock_async_client_cls):
    db_conn.db.providers.find_one = AsyncMock(return_value=_TEMPLATE_PROVIDER_DOC)

    captured = {}

    # LLM reply wrapped to match response_text_path = "result.text"
    _inner = json.dumps({
        "phases": [
            {
                "phase": "requirement",
                "agent_role": "BA Agent",
                "base_input_tokens": 1000,
                "context_input_tokens": 500,
                "cacheable_fraction": 0.3,
                "tool_call_tokens": 100,
                "output_tokens": 200,
                "estimated_calls": 1,
                "confidence": "medium",
            }
        ],
        "extraction_notes": "Template provider extraction complete.",
    })
    provider_response_body = json.dumps({"result": {"text": _inner}})
    fake_response = httpx.Response(200, content=provider_response_body.encode())

    async def _intercept(method=None, url=None, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = dict(headers) if headers else {}
        captured["body"] = json
        return fake_response

    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.request = AsyncMock(side_effect=_intercept)
    mock_async_client_cls.return_value = mock_instance

    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "sk-test-key-12345",
    }
    body = {
        "project_description": "Build a data pipeline.",
        "document_summaries": [],
        "provider": "custom_llm",
        "model_id": "my-custom-model",
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    assert captured, "No outgoing HTTP request was captured"

    # {model_id} substituted into body_template["model"]
    assert captured["body"]["model"] == "my-custom-model", (
        f"{{model_id}} not substituted: {captured['body']}"
    )
    # {api_key} substituted into Authorization header
    auth = captured["headers"].get("Authorization", "")
    assert "sk-test-key-12345" in auth, (
        f"{{api_key}} not in Authorization: {captured['headers']}"
    )
    # {system_prompt} and {user_prompt} must be non-empty
    assert captured["body"].get("system"), "{system_prompt} empty or not substituted"
    assert captured["body"].get("prompt"), "{user_prompt} empty or not substituted"

    # response_text_path extraction check
    res_data = response.json()
    assert len(res_data["phases"]) == 1
    assert res_data["phases"][0]["phase"] == "requirement"
    assert res_data["extraction_notes"] == "Template provider extraction complete."

# ---------------------------------------------------------------------------
# T029-c: Non-2xx status code mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider_status,expected_app_status", [
    (401, 401),
    (429, 429),
    (500, 502),
    (503, 502),
    (400, 502),
])
@patch("src.llm_adapters.httpx.AsyncClient")
def test_template_error_status_mapping(mock_async_client_cls, provider_status, expected_app_status):
    db_conn.db.providers.find_one = AsyncMock(return_value=_TEMPLATE_PROVIDER_DOC)
    error_body = json.dumps({"error": {"message": f"Provider returned {provider_status}"}})
    fake_response = httpx.Response(provider_status, content=error_body.encode())

    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.request = AsyncMock(return_value=fake_response)
    mock_async_client_cls.return_value = mock_instance

    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "sk-test-key",
    }
    body = {
        "project_description": "Error mapping test.",
        "document_summaries": [],
        "provider": "custom_llm",
        "model_id": "my-model",
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == expected_app_status, (
        f"Provider {provider_status} -> expected {expected_app_status}, "
        f"got {response.status_code}. Body: {response.text}"
    )
    if expected_app_status in (401, 429):
        detail = response.json().get("detail", "")
        assert "Provider returned" in detail, (
            f"Expected provider error in 401/429 detail, got: {detail}"
        )

# ---------------------------------------------------------------------------
# Existing /estimate test (logic unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_estimate_endpoint():
    db_model = {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "pricing": {
            "input_per_1m": 5.0,
            "output_per_1m": 15.0,
            "cached_input_per_1m": 2.5,
            "batch_input_per_1m": 2.5,
            "batch_output_per_1m": 7.5,
        },
        "pricing_version": 2,
        "effective_from": datetime.utcnow(),
    }
    db_conn.db.models.find_one = AsyncMock(return_value=db_model)
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[
        {"phase_id": "development", "ams_classified": False},
        {"phase_id": "ams_run_support", "ams_classified": True},
    ])
    db_conn.db.phases.find.return_value = mock_cursor

    body = {
        "phases": [
            {
                "phase": "development",
                "agent_role": "Coding agent(s)",
                "base_input_tokens": 10000,
                "context_input_tokens": 20000,
                "cacheable_fraction": 0.5,
                "tool_call_tokens": 5000,
                "output_tokens": 10000,
                "estimated_calls": 2,
                "assigned_model_id": "gpt-4o",
                "assigned_provider": "openai",
                "source": "llm_extracted",
            }
        ],
        "ams_config": {"runs_per_year": 100, "annual_growth_rate": 0.1, "horizon_years": 3},
    }
    headers = {"X-Shared-Secret": settings.application_secret}
    response = client.post("/estimate", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert "pricing_snapshot" in res_data
    assert res_data["pricing_snapshot"]["models"][0]["model_id"] == "gpt-4o"
    assert float(res_data["project_total_cost"]) == 0.60
    assert len(res_data["phase_results"]) == 1
    assert res_data["phase_results"][0]["phase"] == "development"
    assert float(res_data["phase_results"][0]["phase_cost"]) == 0.60

# ---------------------------------------------------------------------------
# Existing /optimize test (logic unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_optimize_endpoint():
    mock_rules = [
        {
            "rule_id": "context_pruning",
            "version": 1,
            "category": "context_pruning",
            "condition": {"field": "context_input_tokens_ratio", "operator": ">=", "threshold": 0.3},
            "token_pool": "input",
            "savings_percentage": {"expected": 0.20},
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True,
        }
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_rules)
    db_conn.db.optimizer_rules.find.return_value = mock_cursor

    body = {
        "pricing_snapshot": {
            "resolved_at": datetime.utcnow().isoformat(),
            "models": [
                {
                    "model_id": "gpt-4o",
                    "provider": "openai",
                    "pricing": {
                        "input_per_1m": 5.0, "output_per_1m": 15.0,
                        "cached_input_per_1m": 2.5, "batch_input_per_1m": 2.5,
                        "batch_output_per_1m": 7.5,
                    },
                    "pricing_version": 2,
                    "effective_from": datetime.utcnow().isoformat(),
                }
            ],
        },
        "phase_results": [
            {
                "phase": "development",
                "effective_input_tokens": 35000,
                "cacheable_input_tokens": 10000,
                "output_tokens": 10000,
                "input_cost": 0.150,
                "output_cost": 0.150,
                "phase_cost": 0.600,
                "ams_classified": False,
                "annualized": {},
            }
        ],
        "phases": [
            {
                "phase": "development",
                "agent_role": "Coding agent(s)",
                "base_input_tokens": 10000,
                "context_input_tokens": 20000,
                "cacheable_fraction": 0.5,
                "tool_call_tokens": 5000,
                "output_tokens": 10000,
                "estimated_calls": 2,
                "assigned_model_id": "gpt-4o",
                "assigned_provider": "openai",
                "source": "llm_extracted",
            }
        ],
    }
    headers = {"X-Shared-Secret": settings.application_secret}
    response = client.post("/optimize", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["phase_optimizations"]) == 1
    assert res_data["phase_optimizations"][0]["phase"] == "development"
    assert len(res_data["phase_optimizations"][0]["triggered_rules"]) == 1
    assert res_data["phase_optimizations"][0]["triggered_rules"][0]["rule_id"] == "context_pruning"
    assert len(res_data["advisory_recommendations"]) == 1
    assert res_data["advisory_recommendations"][0]["category"] == "agentic_coding_tools"

_DISCOVER_LLM_REPLY = json.dumps({
    "ai_strategies": [
        {
            "strategy_id": "custom_agent_compaction",
            "name": "Agent Compaction Strategy",
            "category": "workflow_optimization",
            "affected_phases": ["development"],
            "affected_token_pool": "both",
            "description": "Consolidate coding agents to reduce redundant loops.",
            "rationale": "High turn count is causing prompt ballooning.",
            "mechanism": "Merge planning and generation turns.",
            "estimated_savings": {"low_percent": 0.10, "expected_percent": 0.20, "high_percent": 0.30},
            "confidence": "high",
            "assumptions": ["Shared context fits window."],
            "evidence": ["Tested in 2 projects."],
            "implementation_effort": "medium",
            "risk": "Minor loss of detail.",
            "dependencies": [],
            "overlap_with_existing_rules": "",
            "included_in_official_savings": False,
        }
    ],
    "unquantified_opportunities": [
        {
            "name": "KG Knowledge Base Summarization",
            "description": "Expose summarizations for AMS Knowledge bases.",
            "rationale": "Saves Repeating context lookup cost.",
        }
    ],
})


@patch("src.main.dispatch_llm_call", new_callable=AsyncMock)
def test_discover_optimizations_endpoint(mock_llm):
    mock_llm.return_value = _DISCOVER_LLM_REPLY
    body = {
        "project_description": "Build a weather application.",
        "document_summaries": [],
        "phases": [],
        "pricing_snapshot": {
            "resolved_at": datetime.utcnow().isoformat(),
            "models": [
                {
                    "model_id": "gpt-4o",
                    "provider": "openai",
                    "pricing": {
                        "input_per_1m": 5.0, "output_per_1m": 15.0,
                        "cached_input_per_1m": 2.5, "batch_input_per_1m": 2.5,
                        "batch_output_per_1m": 7.5,
                    },
                    "pricing_version": 2,
                    "effective_from": datetime.utcnow().isoformat(),
                }
            ],
        },
        "estimate_result": {
            "pricing_snapshot": {"resolved_at": datetime.utcnow().isoformat(), "models": []},
            "phase_results": [],
            "project_total_cost": 0.60,
            "ams_multi_year_total_cost": 0.0,
        },
        "optimize_result": {
            "phase_optimizations": [],
            "total_savings_amount": 0.12,
            "total_savings_percentage": 0.20,
            "advisory_recommendations": [],
        },
        "active_rules": [],
    }
    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "my_provider_api_key_123",
    }
    response = client.post("/discover-optimizations", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["ai_strategies"]) == 1
    assert res_data["ai_strategies"][0]["strategy_id"] == "custom_agent_compaction"
    assert res_data["ai_strategies"][0]["included_in_official_savings"] is False
    assert len(res_data["unquantified_opportunities"]) == 1
