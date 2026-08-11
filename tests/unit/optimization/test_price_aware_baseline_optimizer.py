"""Tests for the deterministic price-only baseline optimizer."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from math import inf, nan
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
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationSolution,
    OptimizationSolutionBoundary,
    OptimizationSolveOutput,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)


def make_problem(
    points: tuple[ForecastPoint, ...],
    objectives: tuple[OptimizationObjective, ...] = (
        OptimizationObjective("energy_cost", "minimize"),
    ),
    *,
    soc: float = 0.5,
) -> OptimizationProblem:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=soc,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=9.0,
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
    return OptimizationProblem(
        context,
        ForecastHorizon(points),
        OptimizationObjectiveCollection(objectives),
    )


def point(
    hour: int, price: float | None, *, pv: float = 2.0, load: float = 4.0
) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, hour, tzinfo=UTC),
        pv_power_kw=pv,
        load_power_kw=load,
        electricity_price_cny_per_kwh=price,
    )


def make_optimizer() -> PriceAwareBaselineOptimizer:
    return PriceAwareBaselineOptimizer(
        PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, 2.5)
    )


def test_configuration_is_frozen_slotted_and_validated() -> None:
    configuration = PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, 2.5)

    assert [
        field.name for field in fields(PriceAwareBaselineOptimizationConfiguration)
    ] == [
        "low_price_threshold_cny_per_kwh",
        "high_price_threshold_cny_per_kwh",
        "requested_power_kw",
    ]
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).requested_power_kw = 1.0


@pytest.mark.parametrize(
    "low_price,high_price,power",
    [
        (0.8, 0.3, 1.0),
        (0.3, 0.3, 1.0),
        (nan, 0.8, 1.0),
        (0.3, inf, 1.0),
        (0.3, 0.8, 0.0),
        (0.3, 0.8, -1.0),
    ],
)
def test_configuration_rejects_invalid_thresholds_and_power(
    low_price: float,
    high_price: float,
    power: float,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        PriceAwareBaselineOptimizationConfiguration(low_price, high_price, power)


def test_solution_output_is_frozen_slotted_and_requires_exact_result_identity() -> None:
    problem = make_problem(())
    output = make_optimizer().solve_with_solution(problem)
    reconstructed_result = type(output.result)(problem, output.result.outcome)
    reconstructed_solution = OptimizationSolution(reconstructed_result, ())

    assert [field.name for field in fields(OptimizationSolveOutput)] == [
        "result",
        "solution",
    ]
    assert output.result.source_problem is problem
    assert output.solution.source_result is output.result
    assert not hasattr(output, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, output).result = output.result
    with pytest.raises(ValueError, match="identity"):
        OptimizationSolveOutput(output.result, reconstructed_solution)


def test_solution_boundary_is_abstract_empty_slotted_and_explicit() -> None:
    signature = inspect.signature(OptimizationSolutionBoundary.solve_with_solution)
    hints = get_type_hints(OptimizationSolutionBoundary.solve_with_solution)

    assert issubclass(OptimizationSolutionBoundary, ABC)
    assert inspect.isabstract(OptimizationSolutionBoundary)
    assert OptimizationSolutionBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "problem"]
    assert hints == {"problem": OptimizationProblem, "return": OptimizationSolveOutput}
    with pytest.raises(TypeError):
        OptimizationSolutionBoundary()  # type: ignore[abstract]


@pytest.mark.parametrize(
    ("price", "action", "power"),
    [
        (0.3, "charge", 2.5),
        (0.8, "discharge", 2.5),
        (0.5, "idle", 0.0),
        (None, "idle", 0.0),
    ],
)
def test_price_classification_includes_threshold_equality(
    price: float | None,
    action: str,
    power: float,
) -> None:
    problem = make_problem((point(1, price),))
    output = make_optimizer().solve_with_solution(problem)
    step = output.solution.steps[0]

    assert output.result.outcome == "optimal"
    assert step.intent.action == action
    assert step.requested_power_kw == power
    assert step.timestamp is problem.forecast_horizon.points[0].timestamp


def test_multiple_points_preserve_caller_order_and_are_price_only() -> None:
    first_problem = make_problem(
        (point(1, 0.2, pv=0.0, load=100.0), point(2, 0.9, pv=99.0, load=0.0)),
        soc=0.01,
    )
    second_problem = make_problem(
        (point(1, 0.2, pv=99.0, load=0.0), point(2, 0.9, pv=0.0, load=100.0)),
        soc=0.99,
    )

    first = make_optimizer().solve_with_solution(first_problem)
    second = make_optimizer().solve_with_solution(second_problem)

    assert [step.intent.action for step in first.solution.steps] == [
        "charge",
        "discharge",
    ]
    assert [step.timestamp for step in first.solution.steps] == [
        point.timestamp for point in first_problem.forecast_horizon.points
    ]
    assert [
        (step.intent.action, step.requested_power_kw) for step in first.solution.steps
    ] == [
        (step.intent.action, step.requested_power_kw) for step in second.solution.steps
    ]


def test_empty_supported_horizon_is_optimal_with_no_invented_step() -> None:
    output = make_optimizer().solve_with_solution(make_problem(()))

    assert output.result.outcome == "optimal"
    assert output.solution.steps == ()


@pytest.mark.parametrize(
    "objectives",
    [
        (OptimizationObjective("peak", "minimize"),),
        (OptimizationObjective("energy_cost", "maximize"),),
        (
            OptimizationObjective("energy_cost", "minimize"),
            OptimizationObjective("other", "minimize"),
        ),
    ],
)
def test_unsupported_or_ambiguous_objectives_are_unavailable(
    objectives: tuple[OptimizationObjective, ...],
) -> None:
    problem = make_problem((point(1, 0.2),), objectives)
    output = make_optimizer().solve_with_solution(problem)

    assert output.result.outcome == "unavailable"
    assert output.solution.source_result is output.result
    assert output.solution.steps == ()


def test_concrete_optimizer_is_frozen_slotted_and_rejects_invalid_problem() -> None:
    optimizer = make_optimizer()

    assert not hasattr(optimizer, "__dict__")
    with pytest.raises(TypeError, match="problem"):
        optimizer.solve_with_solution(cast(Any, object()))


def test_new_modules_have_no_solver_or_execution_dependencies() -> None:
    package_path = Path(optimization.__file__).parent
    forbidden_roots = {
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
    }
    for module_name in ("solution_boundary.py", "price_aware_baseline.py"):
        tree = ast.parse((package_path / module_name).read_text(encoding="utf-8"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or module.split(".", maxsplit=1)[0] not in forbidden_roots
            for module in imported_modules
        )


def test_public_api_exports_price_aware_solution_optimization_contracts() -> None:
    for name in (
        "OptimizationSolutionBoundary",
        "OptimizationSolveOutput",
        "PriceAwareBaselineOptimizationConfiguration",
        "PriceAwareBaselineOptimizer",
    ):
        assert name in optimization.__all__
