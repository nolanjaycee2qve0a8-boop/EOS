"""Tests for deterministic mapping from solved values to EOS control plans."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

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
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
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
    required = CapabilityDescriptor("optimization", "Required capability.")
    available = CapabilityDescriptor("optimization", "Available capability.")
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


def make_solution(result: OptimizationResult) -> OptimizationSolution:
    return OptimizationSolution(
        result,
        (
            OptimizationSolutionStep(
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                DecisionIntent("charge"),
                1.5,
            ),
            OptimizationSolutionStep(
                datetime(2026, 1, 1, 2, tzinfo=UTC),
                DecisionIntent("discharge"),
                2.0,
            ),
            OptimizationSolutionStep(
                datetime(2026, 1, 1, 3, tzinfo=UTC),
                DecisionIntent("idle"),
                0.0,
            ),
        ),
    )


def test_solution_aware_input_is_frozen_slotted_and_keeps_exact_solution() -> None:
    solution = make_solution(make_result())
    construction_input = OptimizationSolutionControlPlanConstructionInput(solution)

    assert [
        field.name for field in fields(OptimizationSolutionControlPlanConstructionInput)
    ] == ["solution"]
    assert construction_input.solution is solution
    assert not hasattr(construction_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, construction_input).solution = solution


def test_solution_aware_input_rejects_invalid_solution_type() -> None:
    with pytest.raises(TypeError, match="solution"):
        OptimizationSolutionControlPlanConstructionInput(cast(Any, object()))


def test_solution_aware_boundary_is_abstract_empty_slotted_and_explicit() -> None:
    signature = inspect.signature(
        OptimizationSolutionControlPlanConstructionBoundary.construct
    )
    hints = get_type_hints(
        OptimizationSolutionControlPlanConstructionBoundary.construct
    )

    assert issubclass(OptimizationSolutionControlPlanConstructionBoundary, ABC)
    assert inspect.isabstract(OptimizationSolutionControlPlanConstructionBoundary)
    assert OptimizationSolutionControlPlanConstructionBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "construction_input"]
    assert hints == {
        "construction_input": OptimizationSolutionControlPlanConstructionInput,
        "return": OptimizationControlPlan,
    }
    with pytest.raises(TypeError):
        OptimizationSolutionControlPlanConstructionBoundary()  # type: ignore[abstract]


def test_builder_maps_each_solution_step_without_reordering_or_modification() -> None:
    result = make_result()
    solution = make_solution(result)
    plan = OptimizationSolutionControlPlanBuilder().construct(
        OptimizationSolutionControlPlanConstructionInput(solution)
    )

    assert plan.source_result is result
    assert len(plan.steps) == len(solution.steps)
    for solution_step, control_step in zip(solution.steps, plan.steps, strict=True):
        assert control_step.timestamp is solution_step.timestamp
        assert control_step.intent is solution_step.intent
        assert control_step.requested_power_kw == solution_step.requested_power_kw


def test_builder_preserves_empty_solution_without_default_idle_step() -> None:
    result = make_result()
    solution = OptimizationSolution(result, ())

    plan = OptimizationSolutionControlPlanBuilder().construct(
        OptimizationSolutionControlPlanConstructionInput(solution)
    )

    assert plan.source_result is result
    assert plan.steps == ()


def test_builder_preserves_caller_solution_result_not_reconstructed_value() -> None:
    result = make_result()
    reconstructed_result = OptimizationResult(result.source_problem, result.outcome)
    solution = make_solution(result)

    plan = OptimizationSolutionControlPlanBuilder().construct(
        OptimizationSolutionControlPlanConstructionInput(solution)
    )

    assert plan.source_result is solution.source_result
    assert plan.source_result is not reconstructed_result


def test_builder_is_stateless_and_rejects_invalid_input() -> None:
    builder = OptimizationSolutionControlPlanBuilder()

    assert not hasattr(builder, "__dict__")
    with pytest.raises(TypeError, match="construction_input"):
        builder.construct(cast(Any, object()))


def test_solution_control_plan_module_has_no_solver_or_execution_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "solution_control_plan.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "optimization.control_plan",
        "optimization.solution",
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


def test_public_api_exports_solution_control_plan_contracts() -> None:
    assert optimization.OptimizationSolutionControlPlanBuilder is (
        OptimizationSolutionControlPlanBuilder
    )
    for name in (
        "OptimizationSolutionControlPlanBuilder",
        "OptimizationSolutionControlPlanConstructionBoundary",
        "OptimizationSolutionControlPlanConstructionInput",
    ):
        assert name in optimization.__all__
