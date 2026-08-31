import pytest
import asyncio
import httpx
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from src.main import app
from src.database import db_conn
from src.config import settings

@pytest.mark.asyncio
async def test_concurrent_estimates():
    # Setup mock active model pricing in DB
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
    
    # We must patch the database client connection and routing layer for HTTP calls
    # To run test concurrently under asyncio, we can use httpx.AsyncClient with our app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        with pytest.MonkeyPatch.context() as mp:
            mock_db = MagicMock()
            mock_db.models.find_one = AsyncMock(return_value=db_model)
            
            mock_cursor = MagicMock()
            mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[
                {"phase_id": "development", "ams_classified": False}
            ])
            mock_db.phases.find.return_value = mock_cursor
            
            db_conn.db = mock_db
            
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
            
            headers = {"X-Shared-Secret": settings.application_secret}
            
            # Spawn 10 concurrent requests
            tasks = [
                client.post("/estimate", json=body, headers=headers)
                for _ in range(10)
            ]
            
            responses = await asyncio.gather(*tasks)
            
            # Assert all 10 completed successfully with status 200
            for r in responses:
                assert r.status_code == 200
                res_data = r.json()
                assert float(res_data["project_total_cost"]) == 0.30
