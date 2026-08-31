import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
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

@patch("src.main.dispatch_llm_call", new_callable=AsyncMock)
def test_extract_endpoint(mock_llm):
    # Mock LLM return value
    mock_llm.return_value = """
    {
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
          "confidence": "high"
        }
      ],
      "extraction_notes": "Extracted development phase details."
    }
    """
    
    body = {
        "project_description": "Build a weather application.",
        "document_summaries": [],
        "provider": "openai",
        "model_id": "gpt-4o",
        "api_key": "mock_key"
    }
    
    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "mock_key"
    }
    response = client.post("/extract", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["phases"]) == 1
    assert res_data["phases"][0]["phase"] == "development"
    assert res_data["phases"][0]["base_input_tokens"] == 10000
    assert res_data["extraction_notes"] == "Extracted development phase details."

@pytest.mark.asyncio
async def test_estimate_endpoint():
    # Setup mock active model pricing in DB
    db_model = {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "pricing": {
            "input_per_1m": 5.0,
            "output_per_1m": 15.0,
            "cached_input_per_1m": 2.5,
            "batch_input_per_1m": 2.5,
            "batch_output_per_1m": 7.5
        },
        "pricing_version": 2,
        "effective_from": datetime.utcnow()
    }
    db_conn.db.models.find_one = AsyncMock(return_value=db_model)
    
    # Mock phases collection for AMS flags
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[
        {"phase_id": "development", "ams_classified": False},
        {"phase_id": "ams_run_support", "ams_classified": True}
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
                "source": "llm_extracted"
            }
        ],
        "ams_config": {
            "runs_per_year": 100,
            "annual_growth_rate": 0.1,
            "horizon_years": 3
        }
    }
    
    headers = {"X-Shared-Secret": settings.application_secret}
    response = client.post("/estimate", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    
    # Check pricing snapshot is embedded
    assert "pricing_snapshot" in res_data
    assert res_data["pricing_snapshot"]["models"][0]["model_id"] == "gpt-4o"
    
    # Verify cost calculations
    # total input = 10000 + 20000 + 5000 = 35000
    # cacheable context = 20000 * 0.5 = 10000
    # non-cacheable = 35000 - 10000 = 25000
    # raw input cost = (25000/1M)*5 + (10000/1M)*2.5 = 0.125 + 0.025 = 0.150
    # output cost = (10000/1M)*15 = 0.150
    # total single cost = 0.15 + 0.15 = 0.30
    # total for 2 calls = 0.60
    assert float(res_data["project_total_cost"]) == 0.60
    assert len(res_data["phase_results"]) == 1
    assert res_data["phase_results"][0]["phase"] == "development"
    assert float(res_data["phase_results"][0]["phase_cost"]) == 0.60

@pytest.mark.asyncio
async def test_optimize_endpoint():
    # Setup mock rules in DB
    mock_rules = [
        {
            "rule_id": "context_pruning",
            "version": 1,
            "category": "context_pruning",
            "condition": {
                "field": "context_input_tokens_ratio",
                "operator": ">=",
                "threshold": 0.3
            },
            "token_pool": "input",
            "savings_percentage": {"expected": 0.20},
            "max_reduction": 0.50,
            "affected_phases": ["*"],
            "active": True
        }
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_rules)
    db_conn.db.optimizer_rules.find.return_value = mock_cursor

    # Stacker Request Body
    body = {
        "pricing_snapshot": {
            "resolved_at": datetime.utcnow().isoformat(),
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
                    "pricing_version": 2,
                    "effective_from": datetime.utcnow().isoformat()
                }
            ]
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
                "annualized": {}
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
                "source": "llm_extracted"
            }
        ]
    }

    headers = {"X-Shared-Secret": settings.application_secret}
    response = client.post("/optimize", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    
    # Verify optimizer savings triggered
    assert len(res_data["phase_optimizations"]) == 1
    assert res_data["phase_optimizations"][0]["phase"] == "development"
    assert len(res_data["phase_optimizations"][0]["triggered_rules"]) == 1
    assert res_data["phase_optimizations"][0]["triggered_rules"][0]["rule_id"] == "context_pruning"
    
    # Assert advisory coding recommendations are separated
    assert len(res_data["advisory_recommendations"]) == 1
    assert res_data["advisory_recommendations"][0]["category"] == "agentic_coding_tools"

@patch("src.main.dispatch_llm_call", new_callable=AsyncMock)
def test_discover_optimizations_endpoint(mock_llm):
    # Mock LLM advisor return
    mock_llm.return_value = """
    {
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
          "estimated_savings": {
            "low_percent": 0.10,
            "expected_percent": 0.20,
            "high_percent": 0.30
          },
          "confidence": "high",
          "assumptions": ["Shared context fits window."],
          "evidence": ["Tested in 2 projects."],
          "implementation_effort": "medium",
          "risk": "Minor loss of detail.",
          "dependencies": [],
          "overlap_with_existing_rules": "",
          "included_in_official_savings": false
        }
      ],
      "unquantified_opportunities": [
        {
          "name": "KG Knowledge Base Summarization",
          "description": "Expose summarizations for AMS Knowledge bases.",
          "rationale": "Saves Repeating context lookup cost."
        }
      ]
    }
    """
    
    # Discovery Payload
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
                        "input_per_1m": 5.0,
                        "output_per_1m": 15.0,
                        "cached_input_per_1m": 2.5,
                        "batch_input_per_1m": 2.5,
                        "batch_output_per_1m": 7.5
                    },
                    "pricing_version": 2,
                    "effective_from": datetime.utcnow().isoformat()
                }
            ]
        },
        "estimate_result": {
            "pricing_snapshot": {
                "resolved_at": datetime.utcnow().isoformat(),
                "models": []
            },
            "phase_results": [],
            "project_total_cost": 0.60,
            "ams_multi_year_total_cost": 0.0
        },
        "optimize_result": {
            "phase_optimizations": [],
            "total_savings_amount": 0.12,
            "total_savings_percentage": 0.20,
            "advisory_recommendations": []
        },
        "active_rules": []
    }
    
    headers = {
        "X-Shared-Secret": settings.application_secret,
        "X-Provider-Key": "my_provider_api_key_123"
    }
    
    response = client.post("/discover-optimizations", json=body, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["ai_strategies"]) == 1
    assert res_data["ai_strategies"][0]["strategy_id"] == "custom_agent_compaction"
    assert res_data["ai_strategies"][0]["included_in_official_savings"] is False
    assert len(res_data["unquantified_opportunities"]) == 1
