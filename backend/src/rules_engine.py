from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

def evaluate_condition(field_val: Decimal, operator: str, threshold: Decimal) -> bool:
    """Evaluates a comparison condition."""
    if operator == ">=":
        return field_val >= threshold
    elif operator == ">":
        return field_val > threshold
    elif operator == "<=":
        return field_val <= threshold
    elif operator == "<":
        return field_val < threshold
    elif operator == "==":
        return field_val == threshold
    return False

def get_row_field_value(row: Dict[str, Any], field: str) -> Decimal:
    """Extracts or computes a field value from a phase configuration row."""
    base_input = Decimal(str(row.get("base_input_tokens", 0)))
    context_input = Decimal(str(row.get("context_input_tokens", 0)))
    tool_calls = Decimal(str(row.get("tool_call_tokens", 0)))
    total_input = base_input + context_input + tool_calls
    
    if field == "context_input_tokens_ratio":
        if total_input == 0:
            return Decimal("0.0")
        return context_input / total_input
    elif field == "tool_call_tokens_ratio":
        if total_input == 0:
            return Decimal("0.0")
        return tool_calls / total_input
    elif field == "cacheable_fraction":
        return Decimal(str(row.get("cacheable_fraction", 0.0)))
    elif field == "output_tokens":
        return Decimal(str(row.get("output_tokens", 0)))
    elif field == "total_input_tokens":
        return total_input
    elif field in row:
        return Decimal(str(row[field]))
    return Decimal("0.0")

def match_rules_for_phase(
    row: Dict[str, Any],
    active_rules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Matches active rules against a phase row configuration."""
    triggered = []
    phase_id = row.get("phase")
    
    for rule in active_rules:
        # Check if phase is affected
        affected = rule.get("affected_phases", [])
        if "*" not in affected and phase_id not in affected:
            continue
            
        condition = rule.get("condition")
        if not condition:
            continue
            
        field = condition.get("field")
        operator = condition.get("operator")
        threshold = Decimal(str(condition.get("threshold", 0)))
        
        field_val = get_row_field_value(row, field)
        
        if evaluate_condition(field_val, operator, threshold):
            triggered.append(rule)
            
    return triggered

def calculate_compounded_reduction(
    triggered_rules: List[Dict[str, Any]],
    pool: str
) -> Dict[str, Decimal]:
    """
    Formula 7: Optimizer savings compounding and capping per token pool.
    Returns combined_reduction (decimal 0-1) and the applied max_reduction ceiling.
    """
    # Filter rules affecting this pool
    matching_rules = [
        r for r in triggered_rules
        if r.get("token_pool") == pool or r.get("token_pool") == "both"
    ]
    
    if not matching_rules:
        return {
            "reduction": Decimal("0.0"),
            "ceiling_applied": Decimal("1.0")
        }
        
    multiplier = Decimal("1.0")
    ceilings = []
    
    for rule in matching_rules:
        savings = Decimal(str(rule.get("savings_percentage", {}).get("expected", 0.0)))
        multiplier *= (Decimal("1.0") - savings)
        
        max_red = rule.get("max_reduction")
        if max_red is not None:
            ceilings.append(Decimal(str(max_red)))
            
    compounded_reduction = Decimal("1.0") - multiplier
    
    # Floor reduction at 0.0
    if compounded_reduction < 0:
        compounded_reduction = Decimal("0.0")
        
    # Apply ceiling if rules specified it
    applied_ceiling = Decimal("1.0")
    if ceilings:
        applied_ceiling = min(ceilings)
        if compounded_reduction > applied_ceiling:
            compounded_reduction = applied_ceiling
            
    return {
        "reduction": compounded_reduction,
        "ceiling_applied": applied_ceiling
    }
