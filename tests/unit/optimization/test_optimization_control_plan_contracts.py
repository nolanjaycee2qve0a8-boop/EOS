"""Tests for immutable solver-independent optimization control plans."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationControlPlan,
    OptimizationControlStep,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)


def make_result() -> OptimizationResult:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=1.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("optimization", "Required test capability.")
    available = CapabilityDescriptor("optimization", "Available test capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("cost", "Describe cost without solving it."),
        ActiveCapabilityCollection(matches, (available,), ()),
    )
    context = EMSContext(source_context, composition, available)
    horizon = ForecastHorizon(
        (
            ForecastPoint(
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                pv_power_kw=1.0,
                load_power_kw=2.0,
            ),
        )
    )
    problem = OptimizationProblem(
        context,
        horizon,
        OptimizationObjectiveCollection((OptimizationObjective("cost", "minimize"),)),
    )
    return OptimizationResult(problem, "optimal")


def make_step(
    *,
    hour: int = 1,
    action: str = "charge",
    requested_power_kw: float = 1.0,
) -> OptimizationControlStep:
    return OptimizationControlStep(
        datetime(2026, 1, 1, hour, tzinfo=UTC),
        DecisionIntent(cast(Any, action)),
        requested_power_kw,
    )


@pytest.mark.parametrize(
    ("action", "requested_power_kw"),
    [("charge", 1.5), ("discharge", 2.0)],
)
def test_charge_and_discharge_steps_are_valid_immutable_slotted_contracts(
    action: str,
    requested_power_kw: float,
) -> None:
    step = make_step(action=action, requested_power_kw=requested_power_kw)

    assert [field.name for field in fields(OptimizationControlStep)] == [
        "timestamp",
        "intent",
        "requested_power_kw",
    ]
    assert step.intent.action == action
    assert step.requested_power_kw == requested_power_kw
    assert not hasattr(step, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, step).requested_power_kw = 0.0


def test_idle_step_requires_zero_power() -> None:
    step = make_step(action="idle", requested_power_kw=0.0)

    assert step.intent.action == "idle"
    assert step.requested_power_kw == 0.0
    with pytest.raises(ValueError, match="idle"):
        make_step(action="idle", requested_power_kw=1.0)


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("nan")])
def test_step_rejects_invalid_power_magnitude(value: float) -> None:
    with pytest.raises(ValueError, match="requested_power_kw"):
        make_step(requested_power_kw=value)


@pytest.mark.parametrize("action", ["charge", "discharge"])
def test_non_idle_steps_require_positive_power(action: str) -> None:
    with pytest.raises(ValueError, match="charge and discharge"):
        make_step(action=action, requested_power_kw=0.0)


def test_step_rejects_invalid_timestamp_or_intent() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OptimizationControlStep(
            datetime(2026, 1, 1, 1),
            DecisionIntent("charge"),
            1.0,
        )
    with pytest.raises(TypeError, match="intent"):
        OptimizationControlStep(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            cast(Any, object()),
            1.0,
        )


def test_plan_preserves_exact_result_tuple_and_step_identity_in_caller_order() -> None:
    result = make_result()
    first = make_step(hour=1, action="charge", requested_power_kw=1.0)
    second = make_step(hour=2, action="idle", requested_power_kw=0.0)
    steps = (first, second)

    plan = OptimizationControlPlan(result, steps)

    assert [field.name for field in fields(OptimizationControlPlan)] == [
        "source_result",
        "steps",
    ]
    assert plan.source_result is result
    assert plan.steps is steps
    assert plan.steps[0] is first
    assert plan.steps[1] is second
    assert not hasattr(plan, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, plan).steps = ()


def test_plan_accepts_empty_finite_sequence() -> None:
    result = make_result()
    supplied: tuple[OptimizationControlStep, ...] = ()

    plan = OptimizationControlPlan(result, supplied)

    assert plan.steps is supplied


def test_plan_rejects_non_tuple_invalid_steps_and_non_increasing_timestamps() -> None:
    result = make_result()
    first = make_step(hour=1)
    duplicate_time = make_step(hour=1, action="discharge", requested_power_kw=1.0)
    earlier = make_step(hour=0)

    with pytest.raises(TypeError, match="tuple"):
        OptimizationControlPlan(result, cast(Any, [first]))
    with pytest.raises(TypeError, match="OptimizationControlStep"):
        OptimizationControlPlan(result, cast(Any, (object(),)))
    with pytest.raises(ValueError, match="increasing"):
        OptimizationControlPlan(result, (first, duplicate_time))
    with pytest.raises(ValueError, match="increasing"):
        OptimizationControlPlan(result, (first, earlier))
    with pytest.raises(TypeError, match="source_result"):
        OptimizationControlPlan(cast(Any, object()), (first,))


def test_control_plan_module_has_no_execution_or_solver_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "control_plan.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "datetime",
        "decision_formation",
        "math",
        "optimization.model",
    }
    for forbidden_root in (
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "dispatch",
        "execution",
        "scipy",
        "cvxpy",
        "pulp",
        "pyomo",
        "ortools",
    ):
        assert forbidden_root not in imported_modules
