"""Tests for the immutable battery constraint implementation."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from typing import Any, cast, get_type_hints

import pytest

from kernel.decision import (
    BatteryConstraintImplementation,
    DecisionConstraintBoundary,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import battery_constraint as battery_constraint_module


def make_constraint(
    *,
    soc: float = 0.5,
    reserve_soc: float = 0.2,
    max_charge_power_kw: float = 10.0,
    max_discharge_power_kw: float = 8.0,
) -> BatteryConstraintImplementation:
    return BatteryConstraintImplementation(
        soc=soc,
        reserve_soc=reserve_soc,
        max_charge_power_kw=max_charge_power_kw,
        max_discharge_power_kw=max_discharge_power_kw,
    )


def test_implementation_preserves_constraint_boundary_contract() -> None:
    assert issubclass(
        BatteryConstraintImplementation,
        DecisionConstraintBoundary,
    )
    parameters = list(
        inspect.signature(BatteryConstraintImplementation.evaluate).parameters
    )
    hints = get_type_hints(BatteryConstraintImplementation.evaluate)

    assert parameters == ["self", "intent"]
    assert hints == {
        "intent": DecisionIntent,
        "return": FeasibleDecisionIntent,
    }


def test_full_battery_blocks_charging_without_mutating_source() -> None:
    intent = DecisionIntent(5.0)

    result = make_constraint(soc=1.0).evaluate(intent)

    assert intent.battery_power_intent_kw == 5.0
    assert result.intent is not intent
    assert result.intent.battery_power_intent_kw == 0.0


@pytest.mark.parametrize("soc", [0.2, 0.1])
def test_reserve_soc_blocks_discharging(soc: float) -> None:
    intent = DecisionIntent(-5.0)

    result = make_constraint(soc=soc, reserve_soc=0.2).evaluate(intent)

    assert result.intent is not intent
    assert result.intent.battery_power_intent_kw == 0.0
    assert intent.battery_power_intent_kw == -5.0


def test_charge_power_is_clipped_to_maximum() -> None:
    intent = DecisionIntent(12.0)

    result = make_constraint(max_charge_power_kw=10.0).evaluate(intent)

    assert result.intent is not intent
    assert result.intent.battery_power_intent_kw == 10.0
    assert intent.battery_power_intent_kw == 12.0


def test_discharge_power_is_clipped_to_maximum_magnitude() -> None:
    intent = DecisionIntent(-12.0)

    result = make_constraint(max_discharge_power_kw=8.0).evaluate(intent)

    assert result.intent is not intent
    assert result.intent.battery_power_intent_kw == -8.0
    assert intent.battery_power_intent_kw == -12.0


@pytest.mark.parametrize("power_kw", [5.0, -5.0])
def test_unmodified_power_preserves_exact_intent_identity(power_kw: float) -> None:
    intent = DecisionIntent(power_kw)

    result = make_constraint().evaluate(intent)

    assert result.intent is intent


def test_zero_intent_preserves_exact_identity() -> None:
    intent = DecisionIntent(0.0)

    result = make_constraint(soc=1.0, reserve_soc=1.0).evaluate(intent)

    assert result.intent is intent
    assert result.intent.battery_power_intent_kw == 0.0


def test_zero_power_limits_block_matching_direction() -> None:
    charging = DecisionIntent(1.0)
    discharging = DecisionIntent(-1.0)
    constraint = make_constraint(
        max_charge_power_kw=0.0,
        max_discharge_power_kw=0.0,
    )

    charge_result = constraint.evaluate(charging)
    discharge_result = constraint.evaluate(discharging)

    assert charge_result.intent.battery_power_intent_kw == 0.0
    assert discharge_result.intent.battery_power_intent_kw == 0.0
    assert charge_result.intent is not charging
    assert discharge_result.intent is not discharging


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("soc", -0.01),
        ("soc", 1.01),
        ("reserve_soc", -0.01),
        ("reserve_soc", 1.01),
        ("max_charge_power_kw", -0.01),
        ("max_discharge_power_kw", -0.01),
        ("soc", nan),
        ("reserve_soc", inf),
        ("max_charge_power_kw", nan),
        ("max_discharge_power_kw", inf),
    ],
)
def test_invalid_constraint_fact_values_are_rejected(
    field_name: str,
    value: float,
) -> None:
    values = {
        "soc": 0.5,
        "reserve_soc": 0.2,
        "max_charge_power_kw": 10.0,
        "max_discharge_power_kw": 8.0,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        BatteryConstraintImplementation(**values)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("soc", True),
        ("reserve_soc", "0.2"),
        ("max_charge_power_kw", False),
        ("max_discharge_power_kw", object()),
    ],
)
def test_invalid_constraint_fact_types_are_rejected(
    field_name: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "soc": 0.5,
        "reserve_soc": 0.2,
        "max_charge_power_kw": 10.0,
        "max_discharge_power_kw": 8.0,
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=field_name):
        BatteryConstraintImplementation(
            soc=cast(float, values["soc"]),
            reserve_soc=cast(float, values["reserve_soc"]),
            max_charge_power_kw=cast(float, values["max_charge_power_kw"]),
            max_discharge_power_kw=cast(
                float,
                values["max_discharge_power_kw"],
            ),
        )


def test_invalid_intent_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="intent"):
        make_constraint().evaluate(cast(DecisionIntent, object()))


def test_constraint_facts_are_frozen_slotted_and_scalar() -> None:
    constraint = make_constraint()

    assert cast(Any, BatteryConstraintImplementation).__dataclass_params__.frozen
    assert BatteryConstraintImplementation.__slots__ == (
        "soc",
        "reserve_soc",
        "max_charge_power_kw",
        "max_discharge_power_kw",
    )
    assert not hasattr(constraint, "__dict__")
    assert [field.name for field in fields(constraint)] == [
        "soc",
        "reserve_soc",
        "max_charge_power_kw",
        "max_discharge_power_kw",
    ]
    assert all(
        isinstance(getattr(constraint, field.name), float)
        for field in fields(constraint)
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, constraint).soc = 0.8


def test_constraint_owns_no_history_cache_runtime_or_device_state() -> None:
    constraint = make_constraint()

    for forbidden in (
        "history",
        "cache",
        "runtime",
        "policy",
        "dispatcher",
        "device",
        "commands",
        "events",
    ):
        assert not hasattr(constraint, forbidden)


def test_module_has_only_decision_boundary_dependencies() -> None:
    tree = ast.parse(inspect.getsource(battery_constraint_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.constraint",
        "kernel.decision.intent",
        "kernel.decision.validation",
    }


def test_public_import_works() -> None:
    assert BatteryConstraintImplementation.__name__ == (
        "BatteryConstraintImplementation"
    )
