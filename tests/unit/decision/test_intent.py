"""Tests for the immutable DecisionIntent boundary."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from math import inf, nan
from typing import Any, cast

import pytest

from kernel.decision import DecisionIntent
from kernel.decision import intent as intent_module


@pytest.mark.parametrize(
    ("power_kw", "expected"),
    [
        (25, 25.0),
        (-25, -25.0),
        (0, 0.0),
    ],
)
def test_battery_power_intent_accepts_finite_signed_kw(
    power_kw: float,
    expected: float,
) -> None:
    assert DecisionIntent(power_kw).battery_power_intent_kw == expected


@pytest.mark.parametrize("value", [True, "25", None])
def test_battery_power_intent_rejects_non_numeric_values(value: object) -> None:
    with pytest.raises(TypeError, match="battery_power_intent_kw"):
        DecisionIntent(cast(float, value))


@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_battery_power_intent_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="battery_power_intent_kw"):
        DecisionIntent(value)


def test_decision_intent_is_frozen_and_slotted() -> None:
    intent = DecisionIntent(0.0)

    assert is_dataclass(intent)
    assert cast(Any, DecisionIntent).__dataclass_params__.frozen
    assert DecisionIntent.__slots__ == ("battery_power_intent_kw",)
    assert not hasattr(intent, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, intent).battery_power_intent_kw = 1.0


def test_decision_intent_has_only_one_immutable_numeric_field() -> None:
    intent = DecisionIntent(0.0)

    assert [field.name for field in fields(intent)] == ["battery_power_intent_kw"]
    assert not hasattr(intent, "commands")
    assert not hasattr(intent, "events")
    assert not hasattr(intent, "cache")
    assert not hasattr(intent, "history")


def test_unit_sign_range_and_scaling_contract_is_explicit() -> None:
    contract = DecisionIntent.__doc__

    assert contract is not None
    for term in (
        "kilowatts",
        "literal",
        "unscaled",
        "Positive",
        "charging",
        "negative",
        "discharging",
        "zero",
        "idle",
        "finite",
    ):
        assert term in contract


def test_intent_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(intent_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.validation",
    }
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert forbidden not in imported_modules
