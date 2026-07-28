"""Tests for the DecisionContextResult boundary."""

from dataclasses import fields, is_dataclass
from typing import Any, cast

import pytest

from kernel.decision import DecisionContextResult, DecisionIntent


def make_result() -> DecisionContextResult:
    return DecisionContextResult(DecisionIntent(0.0))


def test_decision_context_result_is_frozen_and_slotted() -> None:
    result = make_result()

    assert is_dataclass(result)
    assert cast(Any, DecisionContextResult).__dataclass_params__.frozen
    assert DecisionContextResult.__slots__ == ("intent",)
    assert not hasattr(result, "__dict__")


def test_initial_contract_has_no_mutable_or_execution_fields() -> None:
    result = make_result()

    assert [field.name for field in fields(result)] == ["intent"]
    assert not hasattr(result, "commands")
    assert not hasattr(result, "events")
    assert not hasattr(result, "cache")
    assert not hasattr(result, "history")


def test_decision_context_result_cannot_gain_mutable_state() -> None:
    result = make_result()

    with pytest.raises((AttributeError, TypeError)):
        cast(Any, result).commands = []


def test_public_import_uses_expected_type_name() -> None:
    assert DecisionContextResult.__name__ == "DecisionContextResult"


def test_result_preserves_exact_intent_identity() -> None:
    intent = DecisionIntent(25.0)

    result = DecisionContextResult(intent)

    assert result.intent is intent


def test_result_rejects_invalid_intent_type() -> None:
    with pytest.raises(TypeError, match="intent"):
        DecisionContextResult(cast(DecisionIntent, object()))
