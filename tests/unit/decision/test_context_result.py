"""Tests for the DecisionContextResult boundary."""

from dataclasses import fields, is_dataclass
from typing import Any, cast

import pytest

from kernel.decision import DecisionContextResult


def test_decision_context_result_is_frozen_and_slotted() -> None:
    result = DecisionContextResult()

    assert is_dataclass(result)
    assert cast(Any, DecisionContextResult).__dataclass_params__.frozen
    assert DecisionContextResult.__slots__ == ()
    assert not hasattr(result, "__dict__")


def test_initial_contract_has_no_mutable_or_execution_fields() -> None:
    result = DecisionContextResult()

    assert fields(result) == ()
    assert not hasattr(result, "commands")
    assert not hasattr(result, "events")
    assert not hasattr(result, "cache")
    assert not hasattr(result, "history")


def test_decision_context_result_cannot_gain_mutable_state() -> None:
    result = DecisionContextResult()

    with pytest.raises((AttributeError, TypeError)):
        cast(Any, result).commands = []


def test_public_import_uses_expected_type_name() -> None:
    assert DecisionContextResult.__name__ == "DecisionContextResult"
