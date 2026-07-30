"""Tests for the immutable grid power limit constraint implementation."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from typing import Any, cast, get_type_hints

import pytest

from kernel.decision import (
    DecisionIntent,
    FeasibleDecisionIntent,
    GridConstraintBoundary,
    GridPowerLimitConstraintImplementation,
)
from kernel.decision import (
    grid_power_limit_constraint as grid_power_limit_constraint_module,
)


def make_constraint(
    *,
    grid_power_baseline_kw: float = 0.0,
    max_import_power_kw: float = 5.0,
    max_export_power_kw: float = 5.0,
) -> GridPowerLimitConstraintImplementation:
    return GridPowerLimitConstraintImplementation(
        grid_power_baseline_kw=grid_power_baseline_kw,
        max_import_power_kw=max_import_power_kw,
        max_export_power_kw=max_export_power_kw,
    )


def projected_grid_power_kw(
    constraint: GridPowerLimitConstraintImplementation,
    intent: DecisionIntent,
) -> float:
    return constraint.grid_power_baseline_kw + intent.battery_power_intent_kw


def test_implementation_preserves_grid_constraint_contract() -> None:
    assert issubclass(
        GridPowerLimitConstraintImplementation,
        GridConstraintBoundary,
    )
    parameters = list(
        inspect.signature(
            GridPowerLimitConstraintImplementation.evaluate,
        ).parameters
    )
    hints = get_type_hints(GridPowerLimitConstraintImplementation.evaluate)

    assert parameters == ["self", "intent"]
    assert hints == {
        "intent": DecisionIntent,
        "return": FeasibleDecisionIntent,
    }


def test_import_limit_clips_charging_intent_without_mutating_source() -> None:
    constraint = make_constraint(
        grid_power_baseline_kw=4.0,
        max_import_power_kw=5.0,
    )
    source_intent = DecisionIntent(3.0)

    result = constraint.evaluate(source_intent)

    assert source_intent.battery_power_intent_kw == 3.0
    assert result.intent is not source_intent
    assert result.intent.battery_power_intent_kw == 1.0
    assert projected_grid_power_kw(constraint, result.intent) == 5.0


def test_export_limit_clips_discharging_intent_without_mutating_source() -> None:
    constraint = make_constraint(
        grid_power_baseline_kw=-4.0,
        max_export_power_kw=5.0,
    )
    source_intent = DecisionIntent(-3.0)

    result = constraint.evaluate(source_intent)

    assert source_intent.battery_power_intent_kw == -3.0
    assert result.intent is not source_intent
    assert result.intent.battery_power_intent_kw == -1.0
    assert projected_grid_power_kw(constraint, result.intent) == -5.0


@pytest.mark.parametrize(
    ("baseline_kw", "intent_kw"),
    [
        (1.0, 2.0),
        (-1.0, -2.0),
        (5.0, 0.0),
        (-5.0, 0.0),
        (0.0, 0.0),
    ],
)
def test_intent_within_grid_limits_preserves_exact_identity(
    baseline_kw: float,
    intent_kw: float,
) -> None:
    constraint = make_constraint(grid_power_baseline_kw=baseline_kw)
    source_intent = DecisionIntent(intent_kw)

    result = constraint.evaluate(source_intent)

    assert result.intent is source_intent


def test_float_round_trip_does_not_replace_an_unadjusted_intent() -> None:
    constraint = make_constraint(grid_power_baseline_kw=0.1)
    source_intent = DecisionIntent(0.2)

    result = constraint.evaluate(source_intent)

    assert result.intent is source_intent


def test_constraint_can_correct_an_out_of_range_baseline() -> None:
    constraint = make_constraint(
        grid_power_baseline_kw=8.0,
        max_import_power_kw=5.0,
    )
    source_intent = DecisionIntent(0.0)

    result = constraint.evaluate(source_intent)

    assert result.intent is not source_intent
    assert result.intent.battery_power_intent_kw == -3.0
    assert projected_grid_power_kw(constraint, result.intent) == 5.0


def test_zero_limits_clamp_projected_grid_exchange_to_zero() -> None:
    constraint = make_constraint(
        grid_power_baseline_kw=2.0,
        max_import_power_kw=0.0,
        max_export_power_kw=0.0,
    )
    source_intent = DecisionIntent(3.0)

    result = constraint.evaluate(source_intent)

    assert result.intent.battery_power_intent_kw == -2.0
    assert projected_grid_power_kw(constraint, result.intent) == 0.0
    assert source_intent.battery_power_intent_kw == 3.0


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("max_import_power_kw", -0.01),
        ("max_export_power_kw", -0.01),
        ("grid_power_baseline_kw", nan),
        ("grid_power_baseline_kw", inf),
        ("max_import_power_kw", nan),
        ("max_export_power_kw", inf),
    ],
)
def test_invalid_grid_fact_values_are_rejected(
    field_name: str,
    value: float,
) -> None:
    values = {
        "grid_power_baseline_kw": 0.0,
        "max_import_power_kw": 5.0,
        "max_export_power_kw": 5.0,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        GridPowerLimitConstraintImplementation(**values)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("grid_power_baseline_kw", True),
        ("max_import_power_kw", False),
        ("max_export_power_kw", "5.0"),
    ],
)
def test_invalid_grid_fact_types_are_rejected(
    field_name: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "grid_power_baseline_kw": 0.0,
        "max_import_power_kw": 5.0,
        "max_export_power_kw": 5.0,
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=field_name):
        GridPowerLimitConstraintImplementation(
            grid_power_baseline_kw=cast(
                float,
                values["grid_power_baseline_kw"],
            ),
            max_import_power_kw=cast(
                float,
                values["max_import_power_kw"],
            ),
            max_export_power_kw=cast(
                float,
                values["max_export_power_kw"],
            ),
        )


def test_invalid_intent_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="intent"):
        make_constraint().evaluate(cast(DecisionIntent, object()))


def test_grid_facts_are_frozen_slotted_and_scalar() -> None:
    constraint = make_constraint()

    assert cast(
        Any,
        GridPowerLimitConstraintImplementation,
    ).__dataclass_params__.frozen
    assert GridPowerLimitConstraintImplementation.__slots__ == (
        "grid_power_baseline_kw",
        "max_import_power_kw",
        "max_export_power_kw",
    )
    assert not hasattr(constraint, "__dict__")
    assert [field.name for field in fields(constraint)] == [
        "grid_power_baseline_kw",
        "max_import_power_kw",
        "max_export_power_kw",
    ]
    assert all(
        isinstance(getattr(constraint, field.name), float)
        for field in fields(constraint)
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, constraint).grid_power_baseline_kw = 2.0


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
    tree = ast.parse(inspect.getsource(grid_power_limit_constraint_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.constraint",
        "kernel.decision.grid_constraint",
        "kernel.decision.intent",
        "kernel.decision.validation",
    }


def test_public_import_works() -> None:
    assert GridPowerLimitConstraintImplementation.__name__ == (
        "GridPowerLimitConstraintImplementation"
    )
