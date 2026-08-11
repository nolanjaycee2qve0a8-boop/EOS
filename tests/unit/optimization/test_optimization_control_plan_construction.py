"""Tests for the contract-only optimization control-plan construction seam."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

import pytest

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
    OptimizationControlPlanConstructionBoundary,
    OptimizationControlPlanConstructionInput,
    OptimizationControlStep,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)
from optimization import (
    __all__ as optimization_all,
)
from optimization import (
    __file__ as optimization_init_file,
)


class MinimalPlanConstructor(OptimizationControlPlanConstructionBoundary):
    """Test-only implementation that receives a caller-configured plan."""

    __slots__ = ()
    plan: ClassVar[OptimizationControlPlan | None] = None

    def construct(
        self,
        construction_input: OptimizationControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        if not isinstance(
            construction_input,
            OptimizationControlPlanConstructionInput,
        ):
            raise TypeError(
                "construction_input must be an OptimizationControlPlanConstructionInput"
            )
        if self.plan is None:
            raise RuntimeError("test plan must be configured")
        if self.plan.source_result is not construction_input.source_result:
            raise ValueError("plan must preserve exact source result identity")
        return self.plan


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


def make_plan(result: OptimizationResult) -> OptimizationControlPlan:
    return OptimizationControlPlan(
        result,
        (
            OptimizationControlStep(
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                DecisionIntent("charge"),
                1.0,
            ),
        ),
    )


def test_construction_input_is_frozen_slotted_and_preserves_exact_result() -> None:
    result = make_result()
    construction_input = OptimizationControlPlanConstructionInput(result)

    assert [
        field.name for field in fields(OptimizationControlPlanConstructionInput)
    ] == ["source_result"]
    assert construction_input.source_result is result
    assert not hasattr(construction_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, construction_input).source_result = result


def test_construction_input_rejects_invalid_result_type() -> None:
    with pytest.raises(TypeError, match="source_result"):
        OptimizationControlPlanConstructionInput(cast(Any, object()))


def test_boundary_is_abstract_empty_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(OptimizationControlPlanConstructionBoundary.construct)
    hints = get_type_hints(OptimizationControlPlanConstructionBoundary.construct)

    assert issubclass(OptimizationControlPlanConstructionBoundary, ABC)
    assert inspect.isabstract(OptimizationControlPlanConstructionBoundary)
    assert OptimizationControlPlanConstructionBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "construction_input"]
    assert hints == {
        "construction_input": OptimizationControlPlanConstructionInput,
        "return": OptimizationControlPlan,
    }
    with pytest.raises(TypeError):
        OptimizationControlPlanConstructionBoundary()  # type: ignore[abstract]


def test_minimal_constructor_returns_plan_with_exact_original_result_identity() -> None:
    result = make_result()
    construction_input = OptimizationControlPlanConstructionInput(result)
    plan = make_plan(result)
    MinimalPlanConstructor.plan = plan

    returned = MinimalPlanConstructor().construct(construction_input)

    assert returned is plan
    assert returned.source_result is result
    assert not hasattr(MinimalPlanConstructor(), "__dict__")


def test_minimal_constructor_rejects_reconstructed_equal_result_provenance() -> None:
    result = make_result()
    original_input = OptimizationControlPlanConstructionInput(result)
    reconstructed_result = OptimizationResult(result.source_problem, result.outcome)
    MinimalPlanConstructor.plan = make_plan(reconstructed_result)

    with pytest.raises(ValueError, match="identity"):
        MinimalPlanConstructor().construct(original_input)


def test_construction_module_has_no_solver_mpc_or_execution_dependency() -> None:
    module_path = Path(optimization_init_file).parent / "control_plan_construction.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "optimization.control_plan",
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


def test_public_api_exports_control_plan_construction_contracts() -> None:
    for name in (
        "OptimizationControlPlanConstructionBoundary",
        "OptimizationControlPlanConstructionInput",
    ):
        assert name in optimization_all
