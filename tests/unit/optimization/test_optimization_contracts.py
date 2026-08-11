"""Tests for solver-independent EOS optimization contracts."""

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
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationBoundary,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)


class MinimalOptimizationBoundary(OptimizationBoundary):
    """Test-only boundary implementation without a numerical solver."""

    __slots__ = ()

    def solve(self, problem: OptimizationProblem) -> OptimizationResult:
        if not isinstance(problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        return OptimizationResult(problem, "unavailable")


def make_context() -> EMSContext:
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
    required_collection = RequiredCapabilityCollection((required,))
    available_collection = AvailableCapabilityCollection((available,))
    matches = CapabilityMatchCollection(
        required_collection,
        available_collection,
        (CapabilityMatch(required, available),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("cost", "Describe cost without solving it."),
        active,
    )
    return EMSContext(source_context, composition, available)


def make_horizon() -> tuple[ForecastHorizon, tuple[ForecastPoint, ...]]:
    points = (
        ForecastPoint(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            pv_power_kw=1.0,
            load_power_kw=2.0,
            electricity_price_cny_per_kwh=0.4,
        ),
        ForecastPoint(
            datetime(2026, 1, 1, 2, tzinfo=UTC),
            pv_power_kw=0.0,
            load_power_kw=3.0,
            electricity_price_cny_per_kwh=0.9,
        ),
    )
    return ForecastHorizon(points), points


def make_problem() -> tuple[
    OptimizationProblem,
    EMSContext,
    ForecastHorizon,
    OptimizationObjectiveCollection,
]:
    context = make_context()
    horizon, _ = make_horizon()
    objectives = OptimizationObjectiveCollection(
        (
            OptimizationObjective("cost", "minimize"),
            OptimizationObjective("self-consumption", "maximize"),
        )
    )
    return (
        OptimizationProblem(context, horizon, objectives),
        context,
        horizon,
        objectives,
    )


def test_objective_and_collection_are_frozen_slotted_and_preserve_order() -> None:
    first = OptimizationObjective("cost", "minimize")
    second = OptimizationObjective("resilience", "maximize")
    supplied = (first, second)
    collection = OptimizationObjectiveCollection(supplied)

    assert [field.name for field in fields(OptimizationObjective)] == ["name", "sense"]
    assert [field.name for field in fields(OptimizationObjectiveCollection)] == [
        "objectives"
    ]
    assert not hasattr(first, "__dict__")
    assert not hasattr(collection, "__dict__")
    assert collection.objectives is supplied
    assert collection.objectives[0] is first
    assert collection.objectives[1] is second
    with pytest.raises(FrozenInstanceError):
        cast(Any, first).name = "changed"
    with pytest.raises(FrozenInstanceError):
        cast(Any, collection).objectives = ()


@pytest.mark.parametrize(
    ("name", "sense", "error"),
    [
        ("", "minimize", ValueError),
        ("cost", "unknown", ValueError),
        (cast(Any, None), "minimize", TypeError),
    ],
)
def test_objective_rejects_invalid_semantic_fields(
    name: object,
    sense: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        OptimizationObjective(cast(Any, name), cast(Any, sense))


def test_collection_rejects_mutable_or_invalid_contents() -> None:
    objective = OptimizationObjective("cost", "minimize")

    with pytest.raises(TypeError, match="tuple"):
        OptimizationObjectiveCollection(cast(Any, [objective]))
    with pytest.raises(TypeError, match="OptimizationObjective"):
        OptimizationObjectiveCollection(cast(Any, ("not an objective",)))


def test_problem_preserves_exact_context_horizon_objective_tuple_and_identity() -> None:
    problem, context, horizon, objectives = make_problem()

    assert problem.context is context
    assert problem.forecast_horizon is horizon
    assert problem.objectives is objectives
    assert problem.objectives.objectives[0] is objectives.objectives[0]
    assert not hasattr(problem, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, problem).context = context


def test_problem_rejects_empty_objectives_or_invalid_source_contracts() -> None:
    context = make_context()
    horizon, _ = make_horizon()
    empty = OptimizationObjectiveCollection(())
    objectives = OptimizationObjectiveCollection(
        (OptimizationObjective("cost", "minimize"),)
    )

    with pytest.raises(ValueError, match="at least one"):
        OptimizationProblem(context, horizon, empty)
    with pytest.raises(TypeError, match="context"):
        OptimizationProblem(cast(Any, None), horizon, objectives)
    with pytest.raises(TypeError, match="forecast_horizon"):
        OptimizationProblem(context, cast(Any, None), objectives)
    with pytest.raises(TypeError, match="objectives"):
        OptimizationProblem(context, horizon, cast(Any, None))


@pytest.mark.parametrize("outcome", ["optimal", "infeasible", "unavailable"])
def test_result_is_immutable_and_preserves_exact_source_problem_identity(
    outcome: str,
) -> None:
    problem, _, _, _ = make_problem()
    result = OptimizationResult(problem, cast(Any, outcome))

    assert [field.name for field in fields(OptimizationResult)] == [
        "source_problem",
        "outcome",
    ]
    assert result.source_problem is problem
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).source_problem = problem


def test_result_rejects_invalid_problem_or_outcome() -> None:
    problem, _, _, _ = make_problem()

    with pytest.raises(TypeError, match="source_problem"):
        OptimizationResult(cast(Any, None), "unavailable")
    with pytest.raises(ValueError, match="outcome"):
        OptimizationResult(problem, cast(Any, "solved"))


def test_boundary_is_abstract_empty_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(OptimizationBoundary.solve)
    hints = get_type_hints(OptimizationBoundary.solve)

    assert issubclass(OptimizationBoundary, ABC)
    assert inspect.isabstract(OptimizationBoundary)
    assert OptimizationBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "problem"]
    assert hints == {"problem": OptimizationProblem, "return": OptimizationResult}
    with pytest.raises(TypeError):
        OptimizationBoundary()  # type: ignore[abstract]


def test_minimal_boundary_preserves_exact_problem_provenance_and_is_stateless() -> None:
    problem, _, _, _ = make_problem()
    boundary = MinimalOptimizationBoundary()

    result = boundary.solve(problem)

    assert result.source_problem is problem
    assert result.outcome == "unavailable"
    assert MinimalOptimizationBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")
    assert not hasattr(boundary, "cache")


def test_boundary_and_model_modules_have_no_solver_or_execution_dependencies() -> None:
    package_path = Path(optimization.__file__).parent
    forbidden_roots = {
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "dispatch",
        "execution",
    }
    forbidden_names = (
        "scipy",
        "cvxpy",
        "pulp",
        "pyomo",
        "ortools",
        "BatterySimulationActuation",
        "FeasibleDecision",
        "Command",
    )

    for module_path in package_path.glob("*.py"):
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or module.split(".", maxsplit=1)[0] not in forbidden_roots
            for module in imported_modules
        )
        assert all(forbidden_name not in source for forbidden_name in forbidden_names)


def test_public_api_exports_optimization_contracts() -> None:
    assert optimization.__all__ == [
        "OptimizationBoundary",
        "OptimizationControlPlan",
        "OptimizationControlStep",
        "OptimizationObjective",
        "OptimizationObjectiveCollection",
        "OptimizationOutcome",
        "OptimizationProblem",
        "OptimizationResult",
        "OptimizationSense",
    ]
