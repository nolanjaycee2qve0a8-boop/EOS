"""Tests for the Phase 6 battery simulation actuation contract."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import BatterySimulationActuation
from simulator import battery as battery_module


def make_feasible_decision(power_kw: float = 2.0) -> FeasibleDecisionIntent:
    return FeasibleDecisionIntent(DecisionIntent(power_kw))


def test_battery_actuation_preserves_exact_feasible_decision_identity() -> None:
    feasible_decision = make_feasible_decision()

    actuation = BatterySimulationActuation(feasible_decision, 2.0)

    assert actuation.source_feasible_decision is feasible_decision
    assert actuation.battery_power_kw == 2.0


@pytest.mark.parametrize(
    ("power_kw", "meaning"),
    [(2.5, "charging"), (-2.5, "discharging"), (0.0, "idle")],
)
def test_battery_actuation_accepts_explicit_signed_power_contract(
    power_kw: float,
    meaning: str,
) -> None:
    actuation = BatterySimulationActuation(make_feasible_decision(), power_kw)

    assert actuation.battery_power_kw == power_kw
    assert meaning in (BatterySimulationActuation.__doc__ or "")


def test_battery_actuation_does_not_derive_power_from_source() -> None:
    feasible_decision = make_feasible_decision(4.0)

    actuation = BatterySimulationActuation(feasible_decision, 1.5)

    assert actuation.source_feasible_decision is feasible_decision
    assert actuation.battery_power_kw == 1.5
    assert feasible_decision.intent.battery_power_intent_kw == 4.0


def test_battery_actuation_rejects_invalid_source_type() -> None:
    with pytest.raises(TypeError, match="source_feasible_decision"):
        BatterySimulationActuation(cast(Any, object()), 1.0)


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_battery_actuation_rejects_invalid_power_type(value: object) -> None:
    with pytest.raises(TypeError, match="battery_power_kw"):
        BatterySimulationActuation(make_feasible_decision(), cast(Any, value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_battery_actuation_rejects_non_finite_power(value: float) -> None:
    with pytest.raises(ValueError, match="battery_power_kw"):
        BatterySimulationActuation(make_feasible_decision(), value)


def test_battery_actuation_is_frozen_slotted_and_field_complete() -> None:
    feasible_decision = make_feasible_decision()
    actuation = BatterySimulationActuation(feasible_decision, 1.0)

    assert is_dataclass(BatterySimulationActuation)
    assert cast(Any, BatterySimulationActuation).__dataclass_params__.frozen
    assert BatterySimulationActuation.__slots__ == (
        "source_feasible_decision",
        "battery_power_kw",
    )
    assert [field.name for field in fields(BatterySimulationActuation)] == [
        "source_feasible_decision",
        "battery_power_kw",
    ]
    assert not hasattr(actuation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, actuation).battery_power_kw = 0.0


def test_battery_actuation_does_not_mutate_source_decision() -> None:
    feasible_decision = make_feasible_decision(3.0)
    original_intent = feasible_decision.intent

    BatterySimulationActuation(feasible_decision, 1.0)

    assert feasible_decision.intent is original_intent
    assert feasible_decision.intent.battery_power_intent_kw == 3.0


def test_battery_actuation_has_no_execution_or_state_ownership() -> None:
    actuation = BatterySimulationActuation(make_feasible_decision(), 1.0)

    for forbidden in (
        "command",
        "runtime",
        "device",
        "dispatcher",
        "state",
        "cache",
        "history",
        "timestamp",
        "uuid",
    ):
        assert not hasattr(actuation, forbidden)


def test_battery_module_has_only_contract_dependencies() -> None:
    tree = ast.parse(inspect.getsource(battery_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "kernel.decision.constraint",
        "simulator.core",
        "simulator.validation",
    }


def test_battery_actuation_defines_no_model_or_execution_method() -> None:
    public_methods = [
        name
        for name, member in inspect.getmembers(
            BatterySimulationActuation,
            inspect.isfunction,
        )
        if not name.startswith("__")
    ]

    assert public_methods == []
