"""Tests for deterministic battery SOC horizon projection contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from math import inf, nan
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import optimization
from decision_formation import DecisionIntent
from optimization import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    BatterySOCHorizonProjection,
    BatterySOCHorizonProjectionBoundary,
    BatterySOCHorizonProjectionInput,
    BatterySOCProjectionStep,
    DeterministicBatterySOCHorizonProjector,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolutionStep,
)
from tests.unit.optimization.test_battery_planning_contracts import make_problem


class MinimalProjectionBoundary(BatterySOCHorizonProjectionBoundary):
    """Test-only implementation that returns an empty projection."""

    __slots__ = ()

    def project(
        self,
        projection_input: BatterySOCHorizonProjectionInput,
    ) -> BatterySOCHorizonProjection:
        return BatterySOCHorizonProjection(projection_input, ())


def make_model(
    *,
    usable_capacity_kwh: float = 10.0,
    min_soc_fraction: float = 0.1,
    max_soc_fraction: float = 0.9,
    charge_efficiency: float = 0.9,
    discharge_efficiency: float = 0.9,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        usable_capacity_kwh=usable_capacity_kwh,
        min_soc_fraction=min_soc_fraction,
        max_soc_fraction=max_soc_fraction,
        max_charge_power_kw=3.0,
        max_discharge_power_kw=4.0,
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
    )


def make_projection_input(
    *,
    initial_soc_fraction: float = 0.5,
    model: BatteryOptimizationModel | None = None,
    steps: tuple[OptimizationSolutionStep, ...] | None = None,
    duration_seconds: float = 3600.0,
) -> BatterySOCHorizonProjectionInput:
    problem = make_problem()
    result = OptimizationResult(problem, "optimal")
    supplied_steps = steps
    if supplied_steps is None:
        supplied_steps = (
            OptimizationSolutionStep(
                datetime(2026, 1, 1, tzinfo=UTC),
                DecisionIntent("charge"),
                2.0,
            ),
        )
    return BatterySOCHorizonProjectionInput(
        BatteryOptimizationInput(
            problem,
            BatteryOptimizationState(initial_soc_fraction),
            model or make_model(),
        ),
        OptimizationSolution(result, supplied_steps),
        duration_seconds,
    )


def test_projection_input_is_frozen_slotted_and_preserves_exact_identities() -> None:
    projection_input = make_projection_input()

    assert [field.name for field in fields(BatterySOCHorizonProjectionInput)] == [
        "battery_input",
        "solution",
        "control_step_duration_seconds",
    ]
    assert (
        projection_input.solution.source_result.source_problem
        is projection_input.battery_input.problem
    )
    assert not hasattr(projection_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, projection_input).solution = projection_input.solution


@pytest.mark.parametrize("value", [0.0, -1.0, nan, inf, -inf, True])
def test_projection_input_rejects_invalid_duration(value: object) -> None:
    problem = make_problem()
    result = OptimizationResult(problem, "optimal")
    battery_input = BatteryOptimizationInput(
        problem, BatteryOptimizationState(0.5), make_model()
    )

    with pytest.raises((TypeError, ValueError), match="control_step_duration_seconds"):
        BatterySOCHorizonProjectionInput(
            battery_input,
            OptimizationSolution(result, ()),
            cast(Any, value),
        )


def test_projection_input_rejects_value_equal_but_reconstructed_problem_lineage() -> (
    None
):
    projection_input = make_projection_input()
    source_problem = projection_input.battery_input.problem
    reconstructed_problem = OptimizationProblem(
        source_problem.context,
        source_problem.forecast_horizon,
        source_problem.objectives,
    )
    reconstructed_result = OptimizationResult(reconstructed_problem, "optimal")

    with pytest.raises(ValueError, match="exact battery input problem identity"):
        BatterySOCHorizonProjectionInput(
            projection_input.battery_input,
            OptimizationSolution(reconstructed_result, ()),
            3600.0,
        )


def test_projection_step_is_frozen_slotted_and_allows_out_of_bound_soc_values() -> None:
    source_step = make_projection_input().solution.steps[0]
    projection_step = BatterySOCProjectionStep(source_step, 0.95, 1.08, 1.3)

    assert [field.name for field in fields(BatterySOCProjectionStep)] == [
        "source_step",
        "starting_soc_fraction",
        "ending_soc_fraction",
        "battery_energy_delta_kwh",
    ]
    assert projection_step.source_step is source_step
    assert projection_step.ending_soc_fraction == 1.08
    assert not hasattr(projection_step, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, projection_step).ending_soc_fraction = 0.5


@pytest.mark.parametrize("value", [nan, inf, -inf, True])
def test_projection_step_rejects_nonfinite_or_boolean_numbers(value: object) -> None:
    source_step = make_projection_input().solution.steps[0]

    with pytest.raises((TypeError, ValueError)):
        BatterySOCProjectionStep(source_step, cast(Any, value), 0.5, 0.0)


def test_projection_rejects_reconstructed_source_step_identity() -> None:
    projection_input = make_projection_input()
    source_step = projection_input.solution.steps[0]
    supplied_steps = (BatterySOCProjectionStep(source_step, 0.5, 0.68, 1.8),)
    projection = BatterySOCHorizonProjection(projection_input, supplied_steps)
    reconstructed_step = OptimizationSolutionStep(
        source_step.timestamp,
        source_step.intent,
        source_step.requested_power_kw,
    )

    assert [field.name for field in fields(BatterySOCHorizonProjection)] == [
        "source_input",
        "steps",
    ]
    assert projection.source_input is projection_input
    assert projection.steps is supplied_steps
    assert projection.steps[0] is supplied_steps[0]
    assert not hasattr(projection, "__dict__")
    with pytest.raises(ValueError, match="exact source step identity"):
        BatterySOCHorizonProjection(
            projection_input,
            (BatterySOCProjectionStep(reconstructed_step, 0.5, 0.68, 1.8),),
        )


def test_projection_boundary_is_abstract_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(BatterySOCHorizonProjectionBoundary.project)
    hints = get_type_hints(BatterySOCHorizonProjectionBoundary.project)

    assert issubclass(BatterySOCHorizonProjectionBoundary, ABC)
    assert inspect.isabstract(BatterySOCHorizonProjectionBoundary)
    assert BatterySOCHorizonProjectionBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "projection_input"]
    assert hints == {
        "projection_input": BatterySOCHorizonProjectionInput,
        "return": BatterySOCHorizonProjection,
    }
    with pytest.raises(TypeError):
        BatterySOCHorizonProjectionBoundary()  # type: ignore[abstract]


def test_minimal_boundary_is_stateless() -> None:
    boundary = MinimalProjectionBoundary()
    result = boundary.project(make_projection_input(steps=()))

    assert result.steps == ()
    assert MinimalProjectionBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")


def test_projector_charge_math_preserves_exact_lineage() -> None:
    projection_input = make_projection_input()
    projection = DeterministicBatterySOCHorizonProjector().project(projection_input)
    step = projection.steps[0]

    assert projection.source_input is projection_input
    assert step.source_step is projection_input.solution.steps[0]
    assert step.starting_soc_fraction == pytest.approx(0.5)
    assert step.battery_energy_delta_kwh == pytest.approx(1.8)
    assert step.ending_soc_fraction == pytest.approx(0.68)


def test_projector_discharge_math_uses_discharge_efficiency() -> None:
    steps = (
        OptimizationSolutionStep(
            datetime(2026, 1, 1, tzinfo=UTC),
            DecisionIntent("discharge"),
            1.8,
        ),
    )
    projection = DeterministicBatterySOCHorizonProjector().project(
        make_projection_input(steps=steps)
    )
    step = projection.steps[0]

    assert step.battery_energy_delta_kwh == pytest.approx(-2.0)
    assert step.ending_soc_fraction == pytest.approx(0.3)


def test_projector_preserves_caller_order_and_soc_continuity_without_limits() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    steps = (
        OptimizationSolutionStep(start, DecisionIntent("charge"), 5.0),
        OptimizationSolutionStep(
            start + timedelta(hours=1), DecisionIntent("idle"), 0.0
        ),
        OptimizationSolutionStep(
            start + timedelta(hours=2), DecisionIntent("discharge"), 9.0
        ),
    )
    projection_input = make_projection_input(
        initial_soc_fraction=0.95,
        model=make_model(max_soc_fraction=0.99),
        steps=steps,
    )
    projection = DeterministicBatterySOCHorizonProjector().project(projection_input)

    assert [step.source_step for step in projection.steps] == list(steps)
    assert projection.steps[0].source_step is steps[0]
    assert projection.steps[1].source_step is steps[1]
    assert projection.steps[2].source_step is steps[2]
    assert projection.steps[0].ending_soc_fraction == pytest.approx(1.4)
    assert projection.steps[1].starting_soc_fraction == pytest.approx(1.4)
    assert projection.steps[1].ending_soc_fraction == pytest.approx(1.4)
    assert projection.steps[2].starting_soc_fraction == pytest.approx(1.4)
    assert projection.steps[2].ending_soc_fraction == pytest.approx(0.4)


def test_projector_uses_explicit_duration_and_capacity_without_power_clipping() -> None:
    projection = DeterministicBatterySOCHorizonProjector().project(
        make_projection_input(
            model=make_model(usable_capacity_kwh=20.0, charge_efficiency=1.0),
            duration_seconds=1800.0,
            steps=(
                OptimizationSolutionStep(
                    datetime(2026, 1, 1, tzinfo=UTC),
                    DecisionIntent("charge"),
                    50.0,
                ),
            ),
        )
    )

    assert projection.steps[0].battery_energy_delta_kwh == pytest.approx(25.0)
    assert projection.steps[0].ending_soc_fraction == pytest.approx(1.75)


def test_projector_returns_empty_projection_for_empty_solution() -> None:
    projection_input = make_projection_input(steps=())
    projection = DeterministicBatterySOCHorizonProjector().project(projection_input)

    assert projection.source_input is projection_input
    assert projection.steps == ()


def test_projection_module_has_no_solver_or_execution_dependencies() -> None:
    module_path = Path(optimization.__file__).parent / "battery_soc_projection.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "math",
        "optimization.battery_planning",
        "optimization.solution",
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


def test_public_api_exports_soc_projection_contracts() -> None:
    assert optimization.BatterySOCHorizonProjection is BatterySOCHorizonProjection
    assert (
        optimization.BatterySOCHorizonProjectionBoundary
        is BatterySOCHorizonProjectionBoundary
    )
    assert (
        optimization.BatterySOCHorizonProjectionInput
        is BatterySOCHorizonProjectionInput
    )
    assert optimization.BatterySOCProjectionStep is BatterySOCProjectionStep
    assert (
        optimization.DeterministicBatterySOCHorizonProjector
        is DeterministicBatterySOCHorizonProjector
    )
