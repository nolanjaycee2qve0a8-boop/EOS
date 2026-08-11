"""Tests for solver-independent concrete optimization solution payloads."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from math import inf, nan
from pathlib import Path
from typing import Any, Literal, cast

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
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolutionStep,
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
    required = CapabilityDescriptor("mpc", "Required MPC capability.")
    available = CapabilityDescriptor("mpc", "Available MPC capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    context = EMSContext(
        source_context,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("cost", "Describe cost without solving it."),
            ActiveCapabilityCollection(matches, (available,), ()),
        ),
        available,
    )
    problem = OptimizationProblem(
        context,
        ForecastHorizon(
            (
                ForecastPoint(
                    datetime(2026, 1, 1, 1, tzinfo=UTC),
                    pv_power_kw=1.0,
                    load_power_kw=2.0,
                ),
            )
        ),
        OptimizationObjectiveCollection((OptimizationObjective("cost", "minimize"),)),
    )
    return OptimizationResult(problem, "optimal")


@pytest.mark.parametrize(
    ("action", "power"),
    [("charge", 1.0), ("discharge", 1.0), ("idle", 0.0)],
)
def test_solution_step_is_frozen_slotted_and_supports_semantic_actions(
    action: Literal["charge", "discharge", "idle"],
    power: float,
) -> None:
    step = OptimizationSolutionStep(
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        DecisionIntent(action),
        power,
    )

    assert [field.name for field in fields(OptimizationSolutionStep)] == [
        "timestamp",
        "intent",
        "requested_power_kw",
    ]
    assert not hasattr(step, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, step).requested_power_kw = power


@pytest.mark.parametrize("power", [-1.0, inf, nan, True])
def test_solution_step_rejects_negative_or_nonfinite_power(power: object) -> None:
    with pytest.raises((TypeError, ValueError), match="requested_power_kw"):
        OptimizationSolutionStep(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            DecisionIntent("charge"),
            cast(Any, power),
        )


@pytest.mark.parametrize(
    ("action", "power"),
    [("idle", 1.0), ("charge", 0.0), ("discharge", 0.0)],
)
def test_solution_step_rejects_invalid_action_power_semantics(
    action: Literal["charge", "discharge", "idle"],
    power: float,
) -> None:
    with pytest.raises(ValueError, match="require"):
        OptimizationSolutionStep(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            DecisionIntent(action),
            power,
        )


def test_solution_is_frozen_slotted_and_preserves_exact_result_tuple_and_steps() -> (
    None
):
    result = make_result()
    first = OptimizationSolutionStep(
        datetime(2026, 1, 1, 1, tzinfo=UTC), DecisionIntent("charge"), 1.0
    )
    second = OptimizationSolutionStep(
        datetime(2026, 1, 1, 2, tzinfo=UTC), DecisionIntent("idle"), 0.0
    )
    supplied_steps = (first, second)
    solution = OptimizationSolution(result, supplied_steps)

    assert [field.name for field in fields(OptimizationSolution)] == [
        "source_result",
        "steps",
    ]
    assert solution.source_result is result
    assert solution.steps is supplied_steps
    assert solution.steps[0] is first
    assert solution.steps[1] is second
    assert not hasattr(solution, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, solution).source_result = result


def test_solution_rejects_invalid_tuple_types_and_timestamp_ordering() -> None:
    result = make_result()
    first = OptimizationSolutionStep(
        datetime(2026, 1, 1, 2, tzinfo=UTC), DecisionIntent("charge"), 1.0
    )
    earlier = OptimizationSolutionStep(
        datetime(2026, 1, 1, 1, tzinfo=UTC), DecisionIntent("idle"), 0.0
    )

    with pytest.raises(TypeError, match="tuple"):
        OptimizationSolution(result, cast(Any, [first]))
    with pytest.raises(TypeError, match="OptimizationSolutionStep"):
        OptimizationSolution(result, cast(Any, (object(),)))
    with pytest.raises(ValueError, match="strictly increasing"):
        OptimizationSolution(result, (first, earlier))


def test_solution_source_provenance_is_exact_not_value_only() -> None:
    result = make_result()
    reconstructed_result = OptimizationResult(result.source_problem, result.outcome)
    solution = OptimizationSolution(result, ())

    assert solution.source_result is result
    assert solution.source_result is not reconstructed_result


def test_solution_module_has_no_solver_mpc_or_execution_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "solution.py"
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
        "ems_strategy",
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


def test_public_api_exports_solution_contracts() -> None:
    assert optimization.OptimizationSolution is OptimizationSolution
    assert optimization.OptimizationSolutionStep is OptimizationSolutionStep
    assert "OptimizationSolution" in optimization.__all__
    assert "OptimizationSolutionStep" in optimization.__all__
