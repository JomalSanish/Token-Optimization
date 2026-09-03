"""
routing.py — Best-fit model routing for POST /route-model.

Constitution §IX: Routing results MUST NOT be cached — the endpoint must
fetch live data on every request so admin catalog changes take immediate effect.

This module is a pure function (no IO, no DB, no network) so it can be unit-tested
in isolation without mocking. All IO (fetching phase/model docs) is the caller's
responsibility and is performed in the endpoint handler (main.py).
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# ---------------------------------------------------------------------------
# Ordinal ranking tables
# ---------------------------------------------------------------------------
# Each table maps a valid enum string to its ordinal integer (0 = cheapest/simplest).
# Higher ordinal = more capable / more expensive.

COMPLEXITY_TIER_ORDINALS = {
    "simple": 0,
    "moderate": 1,
    "complex": 2,
    "frontier": 3,
}

REASONING_COMPLEXITY_ORDINALS = {
    "direct": 0,
    "single-step": 1,
    "multi-step": 2,
    "deep-reasoning": 3,
}

OUTPUT_QUALITY_ORDINALS = {
    "draft": 0,
    "standard": 1,
    "high-fidelity": 2,
    "expert-grade": 3,
}


def _blended_rate(model: dict) -> Decimal:
    """Compute (input_per_1m + output_per_1m) / 2 as a Decimal."""
    pricing = model.get("pricing", {})
    inp = Decimal(str(pricing.get("input_per_1m", "0")))
    out = Decimal(str(pricing.get("output_per_1m", "0")))
    return ((inp + out) / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ordinal_distance(model: dict, phase: dict) -> int:
    """Compute sum of absolute ordinal distances across all three dimensions.

    A distance of 0 means the model exactly meets the phase requirement on
    every dimension (or exceeds it, in which case the delta is still positive).
    For the nearest-neighbor pass, we want the minimum total distance, so we
    use the absolute value of the difference rather than a signed distance.

    Args:
        model: MongoDB model document (must contain capability tag fields).
        phase: MongoDB phase document (must contain default_* requirement fields).

    Returns:
        Total ordinal distance as a non-negative integer.
    """
    m_ct = COMPLEXITY_TIER_ORDINALS.get(model.get("complexity_tier", ""), 0)
    p_ct = COMPLEXITY_TIER_ORDINALS.get(phase.get("default_complexity_tier", ""), 0)

    m_rc = REASONING_COMPLEXITY_ORDINALS.get(model.get("reasoning_complexity", ""), 0)
    p_rc = REASONING_COMPLEXITY_ORDINALS.get(phase.get("default_reasoning_complexity", ""), 0)

    m_oq = OUTPUT_QUALITY_ORDINALS.get(model.get("output_quality", ""), 0)
    p_oq = OUTPUT_QUALITY_ORDINALS.get(phase.get("default_output_quality", ""), 0)

    return abs(m_ct - p_ct) + abs(m_rc - p_rc) + abs(m_oq - p_oq)


def _meets_all(model: dict, phase: dict) -> bool:
    """Return True if model meets or exceeds the phase requirement on all three dimensions."""
    m_ct = COMPLEXITY_TIER_ORDINALS.get(model.get("complexity_tier", ""), 0)
    p_ct = COMPLEXITY_TIER_ORDINALS.get(phase.get("default_complexity_tier", ""), 0)

    m_rc = REASONING_COMPLEXITY_ORDINALS.get(model.get("reasoning_complexity", ""), 0)
    p_rc = REASONING_COMPLEXITY_ORDINALS.get(phase.get("default_reasoning_complexity", ""), 0)

    m_oq = OUTPUT_QUALITY_ORDINALS.get(model.get("output_quality", ""), 0)
    p_oq = OUTPUT_QUALITY_ORDINALS.get(phase.get("default_output_quality", ""), 0)

    return m_ct >= p_ct and m_rc >= p_rc and m_oq >= p_oq


def best_fit_model(phase_doc: dict, active_models: list[dict]) -> Optional[dict]:
    """Find the best-fit active model for a given phase.

    Two-pass strategy (per spec.md FR-023 / FR-024):

    Pass 1 — Cheapest exact match:
        Return the cheapest (lowest blended rate) model that meets or exceeds
        the phase requirement on ALL three dimensions simultaneously.
        Tie-break by blended rate (ascending), then by model_id (lexicographic ascending).

    Pass 2 — Nearest-neighbour fallback:
        If no model passes Pass 1, return the model with the smallest sum of
        absolute ordinal distances across all three dimensions.
        Tie-break by blended rate (ascending), then by model_id (lexicographic ascending).

    Args:
        phase_doc:     MongoDB phase document with default_complexity_tier,
                       default_reasoning_complexity, default_output_quality fields.
        active_models: List of MongoDB model documents that are active and belong
                       to the requested provider. May be empty (caller handles that
                       case by returning RouteModelResponse(match_type="none")).

    Returns:
        A dict with the winning model document augmented with:
            "_match_type":       "exact" | "nearest"
            "_ordinal_distance": int (0 for exact matches)
            "_blended_rate":     Decimal
        Returns None if active_models is empty (caller should return "none" response).

    Note:
        This is a PURE function — no IO, no DB, no network. All data must be
        provided by the caller. Do not add caching here (constitution §IX).
    """
    if not active_models:
        return None

    # --- Pass 1: Cheapest model meeting all three requirements ---
    qualifying = [m for m in active_models if _meets_all(m, phase_doc)]
    if qualifying:
        winner = min(
            qualifying,
            key=lambda m: (_blended_rate(m), m.get("model_id", ""))
        )
        rate = _blended_rate(winner)
        return {
            **winner,
            "_match_type": "exact",
            "_ordinal_distance": 0,
            "_blended_rate": rate,
        }

    # --- Pass 2: Nearest-neighbour fallback ---
    winner = min(
        active_models,
        key=lambda m: (_ordinal_distance(m, phase_doc), _blended_rate(m), m.get("model_id", ""))
    )
    distance = _ordinal_distance(winner, phase_doc)
    rate = _blended_rate(winner)
    return {
        **winner,
        "_match_type": "nearest",
        "_ordinal_distance": distance,
        "_blended_rate": rate,
    }
