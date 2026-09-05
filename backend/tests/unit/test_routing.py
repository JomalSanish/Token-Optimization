"""
test_routing.py — Unit tests for src.routing.best_fit_model

Tests run with no network or DB — all inputs are plain dicts.
These lock down the two-pass routing algorithm before any endpoint wires it up.

Coverage:
  (a) Exact match — Pass 1 returns cheapest qualifying model
  (b) No-match fallback — Pass 2 when all models are BELOW the requirement
      on at least one dimension
  (c) Overkill fallback — Pass 2 when all models EXCEED the requirement on
      all dimensions (they qualify for Pass 1, so actually tests exact match)
      → separate test for a model that misses exactly one dimension
  (d) Tie-break — cheapest blended rate wins; then lexicographic model_id
  (e) Empty list → None
"""
import pytest
from decimal import Decimal

from src.routing import best_fit_model, _blended_rate, _ordinal_distance, _meets_all


# ---------------------------------------------------------------------------
# Helpers — minimal model/phase factory functions
# ---------------------------------------------------------------------------

def make_model(
    model_id: str,
    complexity_tier: str,
    reasoning_complexity: str,
    output_quality: str,
    input_per_1m: str = "5.00",
    output_per_1m: str = "15.00",
) -> dict:
    return {
        "model_id": model_id,
        "display_name": model_id.upper(),
        "complexity_tier": complexity_tier,
        "reasoning_complexity": reasoning_complexity,
        "output_quality": output_quality,
        "pricing": {
            "input_per_1m": input_per_1m,
            "output_per_1m": output_per_1m,
        },
    }


def make_phase(
    complexity_tier: str,
    reasoning_complexity: str,
    output_quality: str,
) -> dict:
    return {
        "default_complexity_tier": complexity_tier,
        "default_reasoning_complexity": reasoning_complexity,
        "default_output_quality": output_quality,
    }


# ---------------------------------------------------------------------------
# Helpers unit tests (_blended_rate, _ordinal_distance, _meets_all)
# ---------------------------------------------------------------------------

class TestBlendedRate:
    def test_basic(self):
        m = make_model("m", "simple", "direct", "draft", input_per_1m="5.00", output_per_1m="15.00")
        assert _blended_rate(m) == Decimal("10.00")

    def test_rounds_half_up(self):
        m = make_model("m", "simple", "direct", "draft", input_per_1m="1.00", output_per_1m="2.00")
        # (1 + 2) / 2 = 1.5
        assert _blended_rate(m) == Decimal("1.50")

    def test_missing_pricing_defaults_to_zero(self):
        assert _blended_rate({}) == Decimal("0.00")


class TestOrdinalDistance:
    def test_zero_when_exact(self):
        m = make_model("m", "complex", "multi-step", "high-fidelity")
        p = make_phase("complex", "multi-step", "high-fidelity")
        assert _ordinal_distance(m, p) == 0

    def test_one_dimension_below(self):
        # model is one tier below on complexity only
        m = make_model("m", "moderate", "multi-step", "high-fidelity")
        p = make_phase("complex", "multi-step", "high-fidelity")
        assert _ordinal_distance(m, p) == 1

    def test_two_dimensions_away(self):
        m = make_model("m", "simple", "direct", "high-fidelity")
        p = make_phase("complex", "multi-step", "high-fidelity")
        # complexity: |0-2| = 2, reasoning: |0-2| = 2, quality: |2-2| = 0
        assert _ordinal_distance(m, p) == 4

    def test_above_requirement_counts_as_distance(self):
        # Ordinal distance is absolute — exceeding also increases distance
        m = make_model("m", "frontier", "deep-reasoning", "expert-grade")
        p = make_phase("simple", "direct", "draft")
        # |3-0| + |3-0| + |3-0| = 9
        assert _ordinal_distance(m, p) == 9


class TestMeetsAll:
    def test_exact_meets(self):
        m = make_model("m", "complex", "multi-step", "high-fidelity")
        p = make_phase("complex", "multi-step", "high-fidelity")
        assert _meets_all(m, p) is True

    def test_exceeds_all_meets(self):
        m = make_model("m", "frontier", "deep-reasoning", "expert-grade")
        p = make_phase("simple", "direct", "draft")
        assert _meets_all(m, p) is True

    def test_one_below_fails(self):
        m = make_model("m", "moderate", "multi-step", "high-fidelity")
        p = make_phase("complex", "multi-step", "high-fidelity")
        assert _meets_all(m, p) is False

    def test_all_below_fails(self):
        m = make_model("m", "simple", "direct", "draft")
        p = make_phase("complex", "multi-step", "high-fidelity")
        assert _meets_all(m, p) is False


# ---------------------------------------------------------------------------
# (a) Pass 1 — Exact match: returns cheapest qualifying model
# ---------------------------------------------------------------------------

class TestPass1ExactMatch:
    def test_single_qualifying_model(self):
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("cheap-qualify", "complex", "multi-step", "high-fidelity",
                       input_per_1m="3.00", output_per_1m="9.00"),
            make_model("below-qualify", "simple", "direct", "draft",
                       input_per_1m="1.00", output_per_1m="2.00"),
        ]
        result = best_fit_model(phase, models)
        assert result is not None
        assert result["model_id"] == "cheap-qualify"
        assert result["_match_type"] == "exact"
        assert result["_ordinal_distance"] == 0

    def test_returns_cheapest_among_qualifying(self):
        """When multiple models qualify, the cheapest blended rate wins."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("expensive", "frontier", "deep-reasoning", "expert-grade",
                       input_per_1m="10.00", output_per_1m="30.00"),   # blended=20
            make_model("cheap", "complex", "multi-step", "high-fidelity",
                       input_per_1m="4.00", output_per_1m="12.00"),    # blended=8
            make_model("mid", "complex", "deep-reasoning", "expert-grade",
                       input_per_1m="6.00", output_per_1m="18.00"),    # blended=12
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "cheap"
        assert result["_match_type"] == "exact"
        assert result["_blended_rate"] == Decimal("8.00")

    def test_exact_match_blended_rate_is_correct(self):
        phase = make_phase("moderate", "single-step", "standard")
        models = [
            make_model("m1", "moderate", "single-step", "standard",
                       input_per_1m="5.00", output_per_1m="15.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["_blended_rate"] == Decimal("10.00")

    def test_overkill_model_qualifies_for_pass1(self):
        """A model that exceeds all requirements still qualifies for Pass 1
        (meets_all returns True when model ordinal >= phase ordinal)."""
        phase = make_phase("simple", "direct", "draft")
        models = [
            make_model("frontier-model", "frontier", "deep-reasoning", "expert-grade",
                       input_per_1m="10.00", output_per_1m="30.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["_match_type"] == "exact"
        assert result["model_id"] == "frontier-model"


# ---------------------------------------------------------------------------
# (b) Pass 2 — No-match fallback when all models are BELOW requirements
# ---------------------------------------------------------------------------

class TestPass2NearestFallback:
    def test_single_below_requirement_model(self):
        """Only one model, it falls short — must be returned as nearest."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("only-model", "simple", "direct", "draft",
                       input_per_1m="1.00", output_per_1m="2.00"),
        ]
        result = best_fit_model(phase, models)
        assert result is not None
        assert result["model_id"] == "only-model"
        assert result["_match_type"] == "nearest"
        # |0-2| + |0-2| + |0-2| = 6
        assert result["_ordinal_distance"] == 6

    def test_returns_closest_when_all_below(self):
        """Multiple models all below requirement — closest total distance wins."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            # distance: |1-2| + |2-2| + |2-2| = 1 (closest)
            make_model("close", "moderate", "multi-step", "high-fidelity",
                       input_per_1m="3.00", output_per_1m="9.00"),
            # distance: |0-2| + |0-2| + |0-2| = 6 (furthest)
            make_model("far", "simple", "direct", "draft",
                       input_per_1m="1.00", output_per_1m="2.00"),
            # distance: |1-2| + |1-2| + |1-2| = 3
            make_model("mid", "moderate", "single-step", "standard",
                       input_per_1m="2.00", output_per_1m="6.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "close"
        assert result["_match_type"] == "nearest"
        assert result["_ordinal_distance"] == 1

    def test_fallback_misses_exactly_one_dimension(self):
        """Model meets two of three dimensions but misses exactly one."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            # Meets complexity + reasoning but output_quality is one below
            make_model("almost", "complex", "multi-step", "standard",
                       input_per_1m="5.00", output_per_1m="15.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["_match_type"] == "nearest"
        # |2-2| + |2-2| + |1-2| = 1
        assert result["_ordinal_distance"] == 1


# ---------------------------------------------------------------------------
# (c) Pass 2 — fallback when all models exceed requirement (overkill)
#     In this scenario all models DO qualify for pass 1, so pass 2 never fires.
#     This tests a tricky setup: one dimension is below, rest are overkill.
# ---------------------------------------------------------------------------

class TestPass2OverkillMixedFallback:
    def test_mixed_overkill_and_one_miss_triggers_pass2(self):
        """When a model exceeds on 2 dimensions but misses on exactly 1,
        it does NOT qualify for pass 1. Pass 2 must select it if it is
        the nearest among all non-qualifying models."""
        phase = make_phase("complex", "deep-reasoning", "high-fidelity")
        models = [
            # Exceeds complexity + quality, but misses reasoning (single-step < deep-reasoning)
            make_model("partial-miss", "frontier", "single-step", "expert-grade",
                       input_per_1m="10.00", output_per_1m="30.00"),
            # Below on all three dimensions
            make_model("fully-below", "simple", "direct", "draft",
                       input_per_1m="1.00", output_per_1m="2.00"),
        ]
        result = best_fit_model(phase, models)
        # partial-miss: |3-2|+|1-3|+|3-2| = 1+2+1 = 4
        # fully-below:  |0-2|+|0-3|+|0-2| = 2+3+2 = 7
        assert result["_match_type"] == "nearest"
        assert result["model_id"] == "partial-miss"
        assert result["_ordinal_distance"] == 4


# ---------------------------------------------------------------------------
# (d) Tie-breaking — blended rate, then lexicographic model_id
# ---------------------------------------------------------------------------

class TestTieBreaking:
    def test_tie_break_by_blended_rate(self):
        """Two models with identical ordinal profile — cheaper wins."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("expensive", "complex", "multi-step", "high-fidelity",
                       input_per_1m="10.00", output_per_1m="20.00"),  # blended=15
            make_model("cheap", "complex", "multi-step", "high-fidelity",
                       input_per_1m="4.00", output_per_1m="8.00"),    # blended=6
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "cheap"

    def test_tie_break_by_model_id_when_same_rate(self):
        """Same ordinal profile AND same blended rate — lexicographically first model_id wins."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("zzz-model", "complex", "multi-step", "high-fidelity",
                       input_per_1m="5.00", output_per_1m="15.00"),
            make_model("aaa-model", "complex", "multi-step", "high-fidelity",
                       input_per_1m="5.00", output_per_1m="15.00"),
            make_model("mmm-model", "complex", "multi-step", "high-fidelity",
                       input_per_1m="5.00", output_per_1m="15.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "aaa-model"

    def test_tie_break_pass2_by_blended_rate(self):
        """Pass 2 tie: same ordinal distance, different blended rate."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            # Both miss complexity by 1 (moderate instead of complex), rest exact
            make_model("costly", "moderate", "multi-step", "high-fidelity",
                       input_per_1m="8.00", output_per_1m="16.00"),   # blended=12
            make_model("cheap", "moderate", "multi-step", "high-fidelity",
                       input_per_1m="2.00", output_per_1m="4.00"),    # blended=3
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "cheap"
        assert result["_match_type"] == "nearest"

    def test_tie_break_pass2_by_model_id(self):
        """Pass 2 tie: same distance AND same blended rate — lexicographic model_id."""
        phase = make_phase("complex", "multi-step", "high-fidelity")
        models = [
            make_model("z-model", "moderate", "multi-step", "high-fidelity",
                       input_per_1m="5.00", output_per_1m="15.00"),
            make_model("a-model", "moderate", "multi-step", "high-fidelity",
                       input_per_1m="5.00", output_per_1m="15.00"),
        ]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "a-model"
        assert result["_match_type"] == "nearest"


# ---------------------------------------------------------------------------
# (e) Empty model list → returns None
# ---------------------------------------------------------------------------

class TestEmptyList:
    def test_empty_returns_none(self):
        phase = make_phase("complex", "multi-step", "high-fidelity")
        result = best_fit_model(phase, [])
        assert result is None

    def test_result_contains_augmented_keys_for_exact(self):
        """Verify _match_type, _ordinal_distance, _blended_rate are present in result."""
        phase = make_phase("simple", "direct", "draft")
        models = [make_model("m", "simple", "direct", "draft")]
        result = best_fit_model(phase, models)
        assert "_match_type" in result
        assert "_ordinal_distance" in result
        assert "_blended_rate" in result

    def test_result_contains_augmented_keys_for_nearest(self):
        phase = make_phase("frontier", "deep-reasoning", "expert-grade")
        models = [make_model("m", "simple", "direct", "draft")]
        result = best_fit_model(phase, models)
        assert result["_match_type"] == "nearest"
        assert isinstance(result["_ordinal_distance"], int)
        assert result["_ordinal_distance"] > 0

    def test_original_model_fields_preserved(self):
        """The returned dict must include all original model fields (not just augmented ones)."""
        phase = make_phase("simple", "direct", "draft")
        models = [make_model("my-model", "simple", "direct", "draft",
                             input_per_1m="2.00", output_per_1m="4.00")]
        result = best_fit_model(phase, models)
        assert result["model_id"] == "my-model"
        assert "pricing" in result
        assert "complexity_tier" in result
