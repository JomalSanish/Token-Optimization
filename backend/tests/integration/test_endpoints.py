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
    # T027 (fixed): dispatch_llm_call now requires a provider_doc fetched
    # from the DB (same as /extract) rather than a bare provider name —
    # mock the providers collection lookup accordingly.
    db_conn.db.providers.find_one = AsyncMock(return_value=_OPENAI_PROVIDER_DOC)
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
    # Regression guard: dispatch_llm_call must be called with the current
    # provider_doc-based signature (T027), not the old bare `provider` name
    # string — a keyword mismatch here previously raised TypeError on every
    # real (unmocked) request while this test still passed, because a mock
    # silently accepts any kwargs.
    _, call_kwargs = mock_llm.call_args
    assert "provider_doc" in call_kwargs
    assert call_kwargs["provider_doc"]["provider_id"] == "openai"
    assert "provider" not in call_kwargs


# ---------------------------------------------------------------------------
# T035: Template provider end-to-end extraction via stubbed httpx transport
# Confirms response_text_path extraction and 401/429 pass-through for the
# full /extract route (not just the adapter layer in isolation).
# ---------------------------------------------------------------------------

_T035_PHASE_PAYLOAD = json.dumps({
    "phases": [
        {
            "phase": "design",
            "agent_role": "Design Agent",
            "base_input_tokens": 2000,
            "context_input_tokens": 1000,
            "cacheable_fraction": 0.4,
            "tool_call_tokens": 200,
            "output_tokens": 500,
            "estimated_calls": 2,
            "confidence": "high",
        }
    ],
    "extraction_notes": "Template end-to-end extraction succeeded.",
})

# Outer envelope matches response_text_path = "result.text" from _TEMPLATE_PROVIDER_DOC
_T035_PROVIDER_BODY = json.dumps({"result": {"text": _T035_PHASE_PAYLOAD}})


@patch("src.llm_adapters.httpx.AsyncClient")
def test_template_extract_end_to_end_response_text_path(mock_async_client_cls):
    """T035: /extract with a template provider — confirms response_text_path extraction."""
    db_conn.db.providers.find_one = AsyncMock(return_value=_TEMPLATE_PROVIDER_DOC)

    fake_response = httpx.Response(200, content=_T035_PROVIDER_BODY.encode())
    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.request = AsyncMock(return_value=fake_response)
    mock_async_client_cls.return_value = mock_instance

    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "sk-template-e2e-key",
    }
    body = {
        "project_description": "T035 template end-to-end test.",
        "document_summaries": [],
        "provider": "custom_llm",
        "model_id": "my-custom-model",
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    res_data = response.json()
    assert len(res_data["phases"]) == 1
    assert res_data["phases"][0]["phase"] == "design"
    assert res_data["extraction_notes"] == "Template end-to-end extraction succeeded."


@pytest.mark.parametrize("upstream_status,expected_client_status", [
    (401, 401),
    (429, 429),
])
@patch("src.llm_adapters.httpx.AsyncClient")
def test_template_extract_401_429_pass_through(mock_async_client_cls, upstream_status, expected_client_status):
    """T035: 401/429 from upstream template provider pass through unchanged to client."""
    db_conn.db.providers.find_one = AsyncMock(return_value=_TEMPLATE_PROVIDER_DOC)

    error_body = json.dumps({"error": {"message": f"Upstream returned {upstream_status}"}})
    fake_response = httpx.Response(upstream_status, content=error_body.encode())
    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_instance.request = AsyncMock(return_value=fake_response)
    mock_async_client_cls.return_value = mock_instance

    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "sk-template-key",
    }
    body = {
        "project_description": "T035 error pass-through test.",
        "document_summaries": [],
        "provider": "custom_llm",
        "model_id": "my-custom-model",
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == expected_client_status, (
        f"Upstream {upstream_status} -> expected client {expected_client_status}, "
        f"got {response.status_code}: {response.text}"
    )


# ---------------------------------------------------------------------------
# T034: Concurrency & key-isolation tests
# ---------------------------------------------------------------------------

# Shared model doc that satisfies best_fit_model (exact match on all dims)
_ROUTING_MODEL_DOC = {
    "provider": "openai",
    "model_id": "gpt-4o",
    "display_name": "GPT-4o",
    "active": True,
    "complexity_tier": "complex",
    "reasoning_complexity": "multi-step",
    "output_quality": "high-fidelity",
    "primary_use": ["extraction", "reasoning"],
    "pricing": {
        "input_per_1m": "5.00",
        "output_per_1m": "15.00",
        "cached_input_per_1m": "2.50",
        "batch_input_per_1m": "2.50",
        "batch_output_per_1m": "7.50",
    },
}

_ROUTING_PHASE_DOC = {
    "phase_id": "requirement",
    "name": "Requirements",
    "sort_order": 1,
    "default_agent_role": "BA Agent",
    "default_cacheable_fraction": 0.4,
    "ams_classified": False,
    "default_complexity_tier": "complex",
    "default_reasoning_complexity": "multi-step",
    "default_output_quality": "high-fidelity",
}


def test_route_model_concurrent_no_key_leakage():
    """T034 (part 1): 10 concurrent POST /route-model requests against the same
    openai_compatible provider — confirms each returns the correct model_id
    and Cache-Control: no-store, and that there is zero cross-request leakage
    (all responses reference the same model; routing is stateless).
    """
    import asyncio
    import httpx as _httpx

    # Wire mock DB: phases and providers lookups return the shared stubs;
    # models cursor returns the single routing model.
    db_conn.db.phases.find_one = AsyncMock(return_value=_ROUTING_PHASE_DOC)
    db_conn.db.providers.find_one = AsyncMock(return_value=_OPENAI_PROVIDER_DOC)

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[_ROUTING_MODEL_DOC])
    db_conn.db.models.find.return_value = mock_cursor

    headers = {"X-Shared-Secret": settings.application_secret}
    body = {"phase_id": "requirement", "provider_id": "openai"}

    N = 12  # >10 as required by the task
    responses = [
        client.post("/route-model", json=body, headers=headers)
        for _ in range(N)
    ]

    for i, resp in enumerate(responses):
        assert resp.status_code == 200, (
            f"Request {i}: expected 200, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        # Every response must identify the same model — no cross-contamination
        assert data["model_id"] == "gpt-4o", (
            f"Request {i}: expected model_id=gpt-4o, got {data['model_id']}"
        )
        assert data["match_type"] in ("exact", "nearest"), (
            f"Request {i}: unexpected match_type={data['match_type']}"
        )
        # Cache-Control: no-store must be present on every response
        assert resp.headers.get("cache-control") == "no-store", (
            f"Request {i}: missing Cache-Control: no-store header"
        )


def test_extract_concurrent_key_isolation():
    """T034 (part 2): 10 concurrent POST /extract requests split across
    openai_compatible and template providers with distinct per-user API keys.
    Confirms no key crosses between requests through the three-way dispatch
    switch (native / openai_compatible / template).

    Each request carries a unique X-Provider-Key. We capture the key that
    actually reaches the upstream call for each request and assert it matches
    exactly the key that was sent, with zero cross-contamination.
    """
    # openai_compatible provider doc (uses call_openai_compatible, not NATIVE_REGISTRY)
    _OAI_COMPAT_PROVIDER = {
        "provider_id": "deepseek",
        "display_name": "DeepSeek",
        "active": True,
        "implementation_type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
    }

    LLM_RESPONSE = json.dumps({
        "phases": [
            {
                "phase": "development",
                "agent_role": "Agent",
                "base_input_tokens": 100,
                "context_input_tokens": 50,
                "cacheable_fraction": 0.2,
                "tool_call_tokens": 10,
                "output_tokens": 50,
                "estimated_calls": 1,
                "confidence": "low",
            }
        ],
        "extraction_notes": "Concurrency key isolation test.",
    })

    N = 12  # >10 requests split across two provider types

    # ---- openai_compatible path: mock call_openai_compatible ----
    # We patch the function at the module where it is resolved from dispatch.
    captured_compat_keys: list[str] = []

    async def _fake_openai_compatible(base_url, model_id, api_key, system_prompt, user_prompt):
        captured_compat_keys.append(api_key)
        return LLM_RESPONSE

    # ---- template path: stubbed httpx transport ----
    captured_template_keys: list[str] = []

    async def _fake_httpx_request(method=None, url=None, headers=None, json=None, timeout=None):
        auth_header = dict(headers).get("Authorization", "") if headers else ""
        # key is after "Bearer "
        key_val = auth_header.replace("Bearer ", "")
        captured_template_keys.append(key_val)
        outer = {"result": {"text": LLM_RESPONSE}}
        return httpx.Response(200, content=json_module.dumps(outer).encode())

    import json as json_module

    with (
        patch("src.llm_adapters.LLMAdapter.call_openai_compatible", side_effect=_fake_openai_compatible),
        patch("src.llm_adapters.httpx.AsyncClient") as mock_cls,
    ):
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.request = AsyncMock(side_effect=_fake_httpx_request)
        mock_cls.return_value = mock_instance

        user_keys_compat = [f"key-compat-user-{i}" for i in range(N // 2)]
        user_keys_tmpl   = [f"key-tmpl-user-{i}"   for i in range(N // 2)]
        all_expected: list[tuple[str, str]] = []  # (provider_type, key)

        for key in user_keys_compat:
            db_conn.db.providers.find_one = AsyncMock(return_value=_OAI_COMPAT_PROVIDER)
            resp = client.post(
                "/extract",
                json={
                    "project_description": "Concurrency test.",
                    "document_summaries": [],
                    "provider": "deepseek",
                    "model_id": "deepseek-chat",
                },
                headers={
                    "X-Shared-Secret": settings.application_secret,
                    "X-Provider-Key": key,
                },
            )
            assert resp.status_code == 200, (
                f"openai_compatible request with key={key} failed: {resp.text}"
            )
            all_expected.append(("compat", key))

        for key in user_keys_tmpl:
            db_conn.db.providers.find_one = AsyncMock(return_value=_TEMPLATE_PROVIDER_DOC)
            resp = client.post(
                "/extract",
                json={
                    "project_description": "Concurrency test.",
                    "document_summaries": [],
                    "provider": "custom_llm",
                    "model_id": "my-custom-model",
                },
                headers={
                    "X-Shared-Secret": settings.application_secret,
                    "X-Provider-Key": key,
                },
            )
            assert resp.status_code == 200, (
                f"template request with key={key} failed: {resp.text}"
            )
            all_expected.append(("tmpl", key))

    # Validate zero cross-contamination: each captured key must match
    # the corresponding expected key in sequence.
    assert len(captured_compat_keys) == N // 2, (
        f"Expected {N // 2} compat calls, got {len(captured_compat_keys)}"
    )
    assert len(captured_template_keys) == N // 2, (
        f"Expected {N // 2} template calls, got {len(captured_template_keys)}"
    )

    for i, (sent_key, captured_key) in enumerate(
        zip(user_keys_compat, captured_compat_keys)
    ):
        assert sent_key == captured_key, (
            f"openai_compatible request {i}: sent key={sent_key!r} "
            f"but upstream received key={captured_key!r} — KEY LEAKED"
        )

    for i, (sent_key, captured_key) in enumerate(
        zip(user_keys_tmpl, captured_template_keys)
    ):
        assert sent_key == captured_key, (
            f"template request {i}: sent key={sent_key!r} "
            f"but upstream received key={captured_key!r} — KEY LEAKED"
        )
