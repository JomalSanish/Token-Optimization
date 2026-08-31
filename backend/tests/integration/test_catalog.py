import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime
from src.repository import CatalogRepository

@pytest.mark.asyncio
async def test_get_active_models():
    # Setup mock database and cursor
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    
    mock_models_list = [
        {"model_id": "gpt-4o", "provider": "openai", "active": True, "display_name": "GPT-4o"},
        {"model_id": "gemini-1.5-flash", "provider": "google", "active": True, "display_name": "Gemini 1.5"}
    ]
    
    # Mock to_list on cursor
    mock_cursor.to_list = AsyncMock(return_value=mock_models_list)
    mock_db.models.find.return_value = mock_cursor
    
    repo = CatalogRepository(db=mock_db)
    active_models = await repo.get_active_models()
    
    assert len(active_models) == 2
    assert active_models[0]["model_id"] == "gpt-4o"
    mock_db.models.find.assert_called_once_with({"active": True})

@pytest.mark.asyncio
async def test_update_model_pricing():
    mock_db = MagicMock()
    
    # Existing model state
    old_model = {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "pricing": {
            "input_per_1m": Decimal("5.0"),
            "output_per_1m": Decimal("15.0"),
            "cached_input_per_1m": Decimal("2.5"),
            "batch_input_per_1m": Decimal("2.5"),
            "batch_output_per_1m": Decimal("7.5")
        },
        "pricing_version": 1,
        "active": True
    }
    
    new_pricing = {
        "input_per_1m": Decimal("6.0"),
        "output_per_1m": Decimal("18.0"),
        "cached_input_per_1m": Decimal("3.0"),
        "batch_input_per_1m": Decimal("3.0"),
        "batch_output_per_1m": Decimal("9.0")
    }
    
    updated_model = {
        **old_model,
        "pricing": new_pricing,
        "pricing_version": 2
    }
    
    # Mock queries
    mock_db.models.find_one = AsyncMock(return_value=old_model)
    mock_db.pricing_history.insert_one = AsyncMock()
    mock_db.models.find_one_and_update = AsyncMock(return_value=updated_model)
    
    repo = CatalogRepository(db=mock_db)
    res = await repo.update_model_pricing(
        provider="openai",
        model_id="gpt-4o",
        new_pricing_dict=new_pricing,
        reason="Price adjustment",
        changed_by="admin_1"
    )
    
    assert res is not None
    assert res["pricing_version"] == 2
    assert res["pricing"]["input_per_1m"] == Decimal("6.0")
    
    # Verify pricing history was inserted
    mock_db.pricing_history.insert_one.assert_called_once()
    history_call_args = mock_db.pricing_history.insert_one.call_args[0][0]
    assert history_call_args["model_id"] == "gpt-4o"
    assert history_call_args["pricing_version"] == 2
    assert history_call_args["previous_pricing"]["input_per_1m"] == Decimal("5.0")
    assert history_call_args["new_pricing"]["input_per_1m"] == Decimal("6.0")
    assert history_call_args["changed_by"] == "admin_1"
