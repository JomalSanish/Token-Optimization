import pytest
from pydantic import ValidationError
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from src.schemas import (
    ModelIn, ModelPricing,
    COMPLEXITY_TIER_VALUES,
    REASONING_COMPLEXITY_VALUES,
    OUTPUT_QUALITY_VALUES,
    PRIMARY_USE_VALUES,
)

# ---------------------------------------------------------------------------
# Shared minimal valid payload
# ---------------------------------------------------------------------------

_VALID_PRICING = dict(
    input_per_1m='5.00',
    output_per_1m='15.00',
    cached_input_per_1m='2.50',
    batch_input_per_1m='2.50',
    batch_output_per_1m='7.50',
)

_VALID_MODEL = dict(
    provider='openai',
    model_id='gpt-4o',
    display_name='GPT-4o',
    pricing=_VALID_PRICING,
    context_window=128000,
    capabilities=['text'],
    complexity_tier='complex',
    reasoning_complexity='multi-step',
    output_quality='high-fidelity',
    primary_use=['code-generation', 'reasoning'],
)


# ---------------------------------------------------------------------------
# T030: ModelIn capability tag schema unit tests
# ---------------------------------------------------------------------------

def test_fully_populated_model_validates():
    m = ModelIn(**_VALID_MODEL)
    assert m.complexity_tier == 'complex'
    assert m.reasoning_complexity == 'multi-step'
    assert m.output_quality == 'high-fidelity'
    assert 'code-generation' in m.primary_use


@pytest.mark.parametrize('missing_field', [
    'complexity_tier',
    'reasoning_complexity',
    'output_quality',
    'primary_use',
])
def test_missing_capability_tag_raises_validation_error(missing_field):
    payload = {k: v for k, v in _VALID_MODEL.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        ModelIn(**payload)
    errors = exc_info.value.errors()
    field_names = [e['loc'][-1] for e in errors]
    assert missing_field in field_names, (
        f'Expected {missing_field!r} in ValidationError field names, got {field_names}'
    )


@pytest.mark.parametrize('field,bad_value', [
    ('complexity_tier', 'ultra'),
    ('reasoning_complexity', 'quantum'),
    ('output_quality', 'perfect'),
    ('primary_use', ['does-not-exist']),
])
def test_invalid_capability_tag_value_raises_validation_error(field, bad_value):
    payload = {**_VALID_MODEL, field: bad_value}
    with pytest.raises(ValidationError) as exc_info:
        ModelIn(**payload)
    # The error must mention the offending value somewhere in the detail
    error_str = str(exc_info.value)
    bad_str = bad_value if isinstance(bad_value, str) else bad_value[0]
    assert bad_str in error_str or field in error_str, (
        f'Expected {bad_str!r} or {field!r} in ValidationError detail, got: {error_str}'
    )


def test_empty_primary_use_raises_validation_error():
    payload = {**_VALID_MODEL, 'primary_use': []}
    with pytest.raises(ValidationError) as exc_info:
        ModelIn(**payload)
    assert 'primary_use' in str(exc_info.value)


def test_all_complexity_tier_values_accepted():
    for tier in COMPLEXITY_TIER_VALUES:
        m = ModelIn(**{**_VALID_MODEL, 'complexity_tier': tier})
        assert m.complexity_tier == tier


def test_all_reasoning_complexity_values_accepted():
    for rc in REASONING_COMPLEXITY_VALUES:
        m = ModelIn(**{**_VALID_MODEL, 'reasoning_complexity': rc})
        assert m.reasoning_complexity == rc


def test_all_output_quality_values_accepted():
    for oq in OUTPUT_QUALITY_VALUES:
        m = ModelIn(**{**_VALID_MODEL, 'output_quality': oq})
        assert m.output_quality == oq


def test_all_primary_use_values_accepted_individually():
    for use in PRIMARY_USE_VALUES:
        m = ModelIn(**{**_VALID_MODEL, 'primary_use': [use]})
        assert use in m.primary_use
