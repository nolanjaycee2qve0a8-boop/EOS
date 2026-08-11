"""Tests for the explicit non-repeating MPC cycle contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

import pytest

import ems_strategy
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from ems_strategy import (
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FirstStepMPCCurrentActionExtractor,
    MPCConfiguration,
    MPCCurrentAction,
    MPCCycleBoundary,
    MPCCycleInput,
    MPCCycleResult,
)
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


class MinimalCycle(MPCCycleBoundary):
    """Test-only boundary returning a pre-composed immutable cycle result."""

    __slots__ = ()
    result: ClassVar[MPCCycleResult | None] = None

    def run_cycle(self, cycle_input: MPCCycleInput) -> MPCCycleResult:
        if not isinstance(cycle_input, MPCCycleInput):
            raise TypeError("cycle_input must be an MPCCycleInput")
        if self.result is None:
            raise RuntimeError("test result must be configured")
        if self.result.source_input is not cycle_input:
            raise ValueError("result must preserve exact cycle input identity")
        return self.result


def make_cycle_artifacts() -> tuple[
    MPCCycleInput,
    OptimizationProblem,
    OptimizationResult,
    OptimizationControlPlan,
    MPCCurrentAction,
    EMSDecision,
]:
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
    configuration = MPCConfiguration(1, 3600.0)
    objectives = OptimizationObjectiveCollection(
        (OptimizationObjective("cost", "minimize"),)
    )
    descriptor = EMSStrategyDescriptor("mpc", "1.0")
    cycle_input = MPCCycleInput(
        context,
        horizon,
        configuration,
        objectives,
        descriptor,
    )
    problem = OptimizationProblem(context, horizon, objectives)
    result = OptimizationResult(problem, "optimal")
    step = OptimizationControlStep(
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        DecisionIntent("charge"),
        1.0,
    )
    plan = OptimizationControlPlan(result, (step,))
    action = FirstStepMPCCurrentActionExtractor().extract(plan)
    decision = EMSDecision(context, descriptor, step.intent, step.requested_power_kw)
    return cycle_input, problem, result, plan, action, decision


def test_cycle_input_is_frozen_slotted_and_preserves_exact_caller_identities() -> None:
    cycle_input, _, _, _, _, _ = make_cycle_artifacts()

    assert [field.name for field in fields(MPCCycleInput)] == [
        "context",
        "forecast_horizon",
        "configuration",
        "objectives",
        "source_strategy",
    ]
    assert not hasattr(cycle_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cycle_input).context = cycle_input.context


def test_cycle_result_is_frozen_slotted_and_preserves_the_full_exact_chain() -> None:
    cycle_input, problem, optimization_result, plan, action, decision = (
        make_cycle_artifacts()
    )
    cycle_result = MPCCycleResult(
        cycle_input,
        problem,
        optimization_result,
        plan,
        action,
        decision,
    )

    assert [field.name for field in fields(MPCCycleResult)] == [
        "source_input",
        "problem",
        "optimization_result",
        "control_plan",
        "current_action",
        "decision",
    ]
    assert cycle_result.source_input is cycle_input
    assert cycle_result.problem is problem
    assert cycle_result.optimization_result is optimization_result
    assert cycle_result.control_plan is plan
    assert cycle_result.current_action is action
    assert cycle_result.decision is decision
    assert decision.source_context is cycle_input.context
    assert decision.source_strategy is cycle_input.source_strategy
    assert not hasattr(cycle_result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cycle_result).decision = decision


def test_cycle_result_rejects_reconstructed_or_foreign_provenance() -> None:
    cycle_input, problem, optimization_result, plan, action, decision = (
        make_cycle_artifacts()
    )
    reconstructed_problem = OptimizationProblem(
        cycle_input.context,
        cycle_input.forecast_horizon,
        cycle_input.objectives,
    )
    foreign_result = OptimizationResult(problem, "optimal")
    foreign_plan = OptimizationControlPlan(foreign_result, plan.steps)
    foreign_action = FirstStepMPCCurrentActionExtractor().extract(foreign_plan)

    with pytest.raises(ValueError, match="problem identity"):
        MPCCycleResult(
            cycle_input,
            reconstructed_problem,
            optimization_result,
            plan,
            action,
            decision,
        )
    with pytest.raises(ValueError, match="control plan identity"):
        MPCCycleResult(
            cycle_input,
            problem,
            optimization_result,
            plan,
            foreign_action,
            decision,
        )


def test_cycle_input_rejects_invalid_types_and_horizon_mismatch() -> None:
    cycle_input, _, _, _, _, _ = make_cycle_artifacts()
    with pytest.raises(TypeError, match="context"):
        MPCCycleInput(
            cast(Any, object()),
            cycle_input.forecast_horizon,
            cycle_input.configuration,
            cycle_input.objectives,
            cycle_input.source_strategy,
        )
    with pytest.raises(ValueError, match="point count"):
        MPCCycleInput(
            cycle_input.context,
            cycle_input.forecast_horizon,
            MPCConfiguration(2, 3600.0),
            cycle_input.objectives,
            cycle_input.source_strategy,
        )


def test_cycle_boundary_is_abstract_empty_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(MPCCycleBoundary.run_cycle)
    hints = get_type_hints(MPCCycleBoundary.run_cycle)

    assert issubclass(MPCCycleBoundary, ABC)
    assert inspect.isabstract(MPCCycleBoundary)
    assert MPCCycleBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "cycle_input"]
    assert hints == {"cycle_input": MPCCycleInput, "return": MPCCycleResult}
    with pytest.raises(TypeError):
        MPCCycleBoundary()  # type: ignore[abstract]


def test_minimal_cycle_returns_one_supplied_result_without_automatic_next_cycle() -> (
    None
):
    cycle_input, problem, optimization_result, plan, action, decision = (
        make_cycle_artifacts()
    )
    result = MPCCycleResult(
        cycle_input,
        problem,
        optimization_result,
        plan,
        action,
        decision,
    )

    MinimalCycle.result = result
    cycle = MinimalCycle()

    assert cycle.run_cycle(cycle_input) is result
    assert len(result.control_plan.steps) == 1
    assert not hasattr(cycle, "__dict__")


def test_mpc_cycle_module_has_no_solver_runtime_device_or_execution_dependency() -> (
    None
):
    module_path = Path(ems_strategy.__file__).parent / "mpc_cycle.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "ems_strategy.context",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
        "ems_strategy.mpc",
        "ems_strategy.mpc_current_action",
        "forecast",
        "optimization",
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


def test_public_api_exports_mpc_cycle_contracts() -> None:
    for name in ("MPCCycleBoundary", "MPCCycleInput", "MPCCycleResult"):
        assert name in ems_strategy.__all__
