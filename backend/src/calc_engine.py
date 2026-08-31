from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Union

def to_decimal(value: Any) -> Decimal:
    """Helper to convert a value safely to Decimal."""
    if value is None:
        return Decimal("0.0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def calculate_effective_input_tokens(
    base_input_tokens: int,
    context_input_tokens: int,
    tool_call_tokens: int
) -> int:
    """Formula 1: Effective input tokens per phase row."""
    return base_input_tokens + context_input_tokens + tool_call_tokens

def calculate_cacheable_split(
    effective_input_tokens: int,
    context_input_tokens: int,
    cacheable_fraction: Union[float, Decimal]
) -> Dict[str, int]:
    """
    Formula 2: Cacheable/non-cacheable split of the context portion.
    Returns:
      {
        "cacheable_input_tokens": int,
        "non_cacheable_input_tokens": int
      }
    """
    fraction = to_decimal(cacheable_fraction)
    context_dec = Decimal(str(context_input_tokens))
    
    # Calculate cacheable tokens and round to nearest integer
    cacheable = int((context_dec * fraction).to_integral_value(rounding=ROUND_HALF_UP))
    non_cacheable = effective_input_tokens - cacheable
    
    # Ensure values are non-negative
    if cacheable < 0:
        cacheable = 0
    if non_cacheable < 0:
        non_cacheable = 0
        
    return {
        "cacheable_input_tokens": cacheable,
        "non_cacheable_input_tokens": non_cacheable
    }

def calculate_phase_raw_cost(
    non_cacheable_input_tokens: int,
    cacheable_input_tokens: int,
    output_tokens: int,
    estimated_calls: int,
    pricing: Dict[str, Any],
    use_batch: bool = False
) -> Dict[str, Decimal]:
    """
    Formula 3 & 4: Per-phase raw cost (pre-optimization) and batch discount.
    Returns input_cost, output_cost, and total phase_cost.
    """
    input_rate = to_decimal(pricing["batch_input_per_1m"] if use_batch else pricing["input_per_1m"])
    output_rate = to_decimal(pricing["batch_output_per_1m"] if use_batch else pricing["output_per_1m"])
    cached_input_rate = to_decimal(pricing["cached_input_per_1m"])
    
    million = Decimal("1000000")
    
    input_cost = (
        (Decimal(non_cacheable_input_tokens) / million) * input_rate +
        (Decimal(cacheable_input_tokens) / million) * cached_input_rate
    )
    
    output_cost = (Decimal(output_tokens) / million) * output_rate
    
    calls = Decimal(str(estimated_calls))
    phase_cost = (input_cost + output_cost) * calls
    
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "phase_cost": phase_cost
    }

def calculate_ams_annualized_cost(
    phase_cost: Decimal,
    runs_per_year: int,
    annual_growth_rate: Union[float, Decimal],
    horizon_years: int
) -> Dict[str, Any]:
    """
    Formula 6: AMS annualized cost (AMS-classified phases only).
    Returns yearly projections and total multi-year cost.
    """
    growth = to_decimal(annual_growth_rate)
    cost = to_decimal(phase_cost)
    runs = Decimal(str(runs_per_year))
    
    # Year 1 base annualized cost
    base_annual_cost = cost * runs
    
    yearly_costs: Dict[str, Decimal] = {}
    multi_year_total = Decimal("0.0")
    
    for year in range(1, horizon_years + 1):
        year_cost = base_annual_cost * ((Decimal("1.0") + growth) ** (year - 1))
        # Keep decimals accurate to 4 places
        year_cost = year_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        yearly_costs[f"year_{year}"] = year_cost
        multi_year_total += year_cost
        
    return {
        "yearly_costs": yearly_costs,
        "multi_year_total": multi_year_total
    }
