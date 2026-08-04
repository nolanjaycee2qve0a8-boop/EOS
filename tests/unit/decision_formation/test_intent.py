"""Tests for the Phase 5 semantic DecisionIntent contract."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from decision_formation import DecisionIntent
from decision_formation import intent as intent_module


@pytest.mark.parametrize("action", ["charge", "discharge", "idle"])
def test_decision_intent_accepts_exact_semantic_actions(action: str) -> None:
    intent = DecisionIntent(cast(Any, action))

    assert intent.action == action


@pytest.mark.parametrize("value", [True, 1, None, (), object()])
def test_decision_intent_rejects_non_string_action(value: object) -> None:
    with pytest.raises(TypeError, match="action"):
        DecisionIntent(cast(Any, value))


@pytest.mark.parametrize(
    "value",
    ["", " ", "Charge", "DISCHARGE", "standby", "charge "],
)
def test_decision_intent_rejects_unknown_or_normalized_action(value: str) -> None:
    with pytest.raises(ValueError, match="action"):
        DecisionIntent(cast(Any, value))


def test_decision_intent_is_frozen_slotted_and_field_complete() -> None:
    intent = DecisionIntent("idle")

    assert is_dataclass(intent)
    assert cast(Any, DecisionIntent).__dataclass_params__.frozen
    assert DecisionIntent.__slots__ == ("action",)
    assert [field.name for field in fields(DecisionIntent)] == ["action"]
    assert not hasattr(intent, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, intent).action = "charge"


def test_decision_intent_has_no_execution_or_analysis_state() -> None:
    intent = DecisionIntent("charge")

    for forbidden in (
        "command",
        "commands",
        "protocol",
        "runtime",
        "pcs",
        "bms",
        "constraint",
        "optimization",
        "power_kw",
        "battery_power_intent_kw",
        "cache",
        "history",
    ):
        assert not hasattr(intent, forbidden)


def test_contract_documents_action_and_command_separation() -> None:
    contract = DecisionIntent.__doc__

    assert contract is not None
    for term in (
        "charge",
        "discharge",
        "idle",
        "device power sign",
        "command",
        "protocol",
        "constraint",
        "optimization",
        "separate future",
        "boundary",
    ):
        assert term in contract


def test_intent_module_has_only_standard_library_dependencies() -> None:
    source = inspect.getsource(intent_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"dataclasses", "typing"}
