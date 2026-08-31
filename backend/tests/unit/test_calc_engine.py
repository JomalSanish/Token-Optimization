import pytest
from decimal import Decimal
from src.calc_engine import (
    calculate_effective_input_tokens,
    calculate_cacheable_split,
    calculate_phase_raw_cost,
    calculate_ams_annualized_cost
)
from src.rules_engine import (
    evaluate_condition,
    get_row_field_value,
    match_rules_for_phase,
    calculate_compounded_reduction
)

def test_effective_input_tokens():
    res = calculate_effective_input_tokens(1000, 500, 100)
    assert res == 1600

def test_cacheable_split():
    # 1600 total tokens, 500 context, 0.4 cacheable fraction
    res = calculate_cacheable_split(1600, 500, 0.4)
    # cacheable context = 500 * 0.4 = 200
    # non-cacheable = 1600 - 200 = 1400
    assert res["cacheable_input_tokens"] == 200
    assert res["non_cacheable_input_tokens"] == 1400

def test_phase_raw_cost():
    pricing = {
        "input_per_1m": Decimal("10.0"),
        "output_per_1m": Decimal("30.0"),
        "cached_input_per_1m": Decimal("5.0"),
        "batch_input_per_1m": Decimal("5.0"),
        "batch_output_per_1m": Decimal("15.0")
    }
    
    # 1400 non-cacheable, 200 cacheable, 800 output, 10 calls
    # non-cacheable cost = (1400 / 1_000_000) * 10 = 0.014
    # cacheable cost = (200 / 1_000_000) * 5 = 0.001
    # output cost = (800 / 1_000_000) * 30 = 0.024
    # single run cost = 0.014 + 0.001 + 0.024 = 0.039
    # total cost for 10 calls = 0.039 * 10 = 0.39
    res = calculate_phase_raw_cost(1400, 200, 800, 10, pricing, use_batch=False)
    assert res["input_cost"] == Decimal("0.015")
    assert res["output_cost"] == Decimal("0.024")
    assert res["phase_cost"] == Decimal("0.39")
    
    # Verify batch discount calculations
    # non-cacheable batch cost = (1400 / 1_000_000) * 5 = 0.007
    # cacheable batch cost = (200 / 1_000_000) * 5 = 0.001
    # output batch cost = (800 / 1_000_000) * 15 = 0.012
    # total batch run cost = 0.007 + 0.001 + 0.012 = 0.020
    # total for 10 calls = 0.020 * 10 = 0.20
    res_batch = calculate_phase_raw_cost(1400, 200, 800, 10, pricing, use_batch=True)
    assert res_batch["input_cost"] == Decimal("0.008")
    assert res_batch["output_cost"] == Decimal("0.012")
    assert res_batch["phase_cost"] == Decimal("0.20")

def test_ams_annualized_cost():
    # phase cost = 0.39, runs/yr = 100, growth = 10% (0.1), horizon = 3 years
    # Year 1 base cost = 0.39 * 100 = 39.0
    # Year 2 cost = 39.0 * 1.1 = 42.9
    # Year 3 cost = 42.9 * 1.1 = 47.19
    # Total cost = 39.0 + 42.9 + 47.19 = 129.09
    res = calculate_ams_annualized_cost(Decimal("0.39"), 100, 0.1, 3)
    assert res["yearly_costs"]["year_1"] == Decimal("39.00")
    assert res["yearly_costs"]["year_2"] == Decimal("42.90")
    assert res["yearly_costs"]["year_3"] == Decimal("47.19")
    assert res["multi_year_total"] == Decimal("129.09")

def test_evaluate_condition():
    assert evaluate_condition(Decimal("0.6"), ">=", Decimal("0.5")) is True
    assert evaluate_condition(Decimal("0.4"), ">=", Decimal("0.5")) is False
    assert evaluate_condition(Decimal("0.5"), "==", Decimal("0.5")) is True

def test_row_field_value():
    row = {
        "base_input_tokens": 100,
        "context_input_tokens": 400,
        "tool_call_tokens": 500,
        "cacheable_fraction": 0.3,
        "output_tokens": 200
    }
    # total input = 1000
    # context ratio = 400 / 1000 = 0.4
    assert get_row_field_value(row, "context_input_tokens_ratio") == Decimal("0.4")
    assert get_row_field_value(row, "cacheable_fraction") == Decimal("0.3")
    assert get_row_field_value(row, "output_tokens") == Decimal("200")

def test_compounded_reduction():
    # Worked example: 100,000 raw input tokens
    # Triggers context_pruning (30% reduction) and caching (40% reduction)
    rules = [
        {
            "rule_id": "context_pruning",
            "token_pool": "input",
            "savings_percentage": {"expected": 0.30},
            "max_reduction": 0.65
        },
        {
            "rule_id": "caching",
            "token_pool": "input",
            "savings_percentage": {"expected": 0.40},
            "max_reduction": 0.65
        }
    ]
    
    # Combined expected reduction: 1 - (1-0.3)*(1-0.4) = 1 - 0.7*0.6 = 0.58 (58%)
    res = calculate_compounded_reduction(rules, "input")
    assert res["reduction"] == Decimal("0.58")
    assert res["ceiling_applied"] == Decimal("0.65")
    
    # Verify capping at rule max_reduction ceiling
    # If rule max_reduction is 50% (0.5), combined reduction of 58% should be capped at 50%
    rules_capped = [
        {
            "rule_id": "context_pruning",
            "token_pool": "input",
            "savings_percentage": {"expected": 0.30},
            "max_reduction": 0.50
        },
        {
            "rule_id": "caching",
            "token_pool": "input",
            "savings_percentage": {"expected": 0.40},
            "max_reduction": 0.50
        }
    ]
    res_capped = calculate_compounded_reduction(rules_capped, "input")
    assert res_capped["reduction"] == Decimal("0.50")
    assert res_capped["ceiling_applied"] == Decimal("0.50")
