"""Tests for deterministic orchestration of one explicit MPC cycle."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

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
    MPCCurrentActionExtractionBoundary,
    MPCCycleInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    SingleMPCCycleOrchestrator,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationBoundary,
    OptimizationControlPlan,
    OptimizationControlPlanConstructionBoundary,
    OptimizationControlPlanConstructionInput,
    OptimizationControlStep,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)


class CountingOptimizationBoundary(OptimizationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def solve(self, problem: OptimizationProblem) -> OptimizationResult:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return OptimizationResult(problem, "optimal")


class CountingPlanConstructor(OptimizationControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def construct(
        self,
        construction_input: OptimizationControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        step = OptimizationControlStep(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            DecisionIntent("charge"),
            1.0,
        )
        return OptimizationControlPlan(construction_input.source_result, (step,))


class CountingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class CountingTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            context,
            translation.source_strategy,
            step.intent,
            step.requested_power_kw,
        )


@pytest.fixture(autouse=True)
def reset_dependencies() -> None:
    for dependency in (
        CountingOptimizationBoundary,
        CountingPlanConstructor,
        CountingExtractor,
        CountingTranslator,
    ):
        dependency.calls = 0
        dependency.failure = None


def make_input() -> MPCCycleInput:
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
    return MPCCycleInput(
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
        MPCConfiguration(1, 3600.0),
        OptimizationObjectiveCollection((OptimizationObjective("cost", "minimize"),)),
        EMSStrategyDescriptor("mpc", "1.0"),
    )


def make_orchestrator() -> tuple[
    SingleMPCCycleOrchestrator,
    tuple[
        CountingOptimizationBoundary,
        CountingPlanConstructor,
        CountingExtractor,
        CountingTranslator,
    ],
]:
    dependencies = (
        CountingOptimizationBoundary(),
        CountingPlanConstructor(),
        CountingExtractor(),
        CountingTranslator(),
    )
    return SingleMPCCycleOrchestrator(*dependencies), dependencies


def test_orchestrator_is_frozen_slotted_and_preserves_dependency_identity() -> None:
    orchestrator, dependencies = make_orchestrator()

    assert [field.name for field in fields(SingleMPCCycleOrchestrator)] == [
        "optimization_boundary",
        "plan_constructor",
        "current_action_extractor",
        "decision_translator",
    ]
    assert orchestrator.optimization_boundary is dependencies[0]
    assert orchestrator.plan_constructor is dependencies[1]
    assert orchestrator.current_action_extractor is dependencies[2]
    assert orchestrator.decision_translator is dependencies[3]
    assert not hasattr(orchestrator, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, orchestrator).optimization_boundary = dependencies[0]


def test_successful_cycle_calls_every_dependency_once_and_preserves_full_chain() -> (
    None
):
    orchestrator, _ = make_orchestrator()
    cycle_input = make_input()

    cycle_result = orchestrator.run_cycle(cycle_input)

    assert (
        CountingOptimizationBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        CountingTranslator.calls,
    ) == (1, 1, 1, 1)
    assert cycle_result.source_input is cycle_input
    assert cycle_result.problem.context is cycle_input.context
    assert cycle_result.problem.forecast_horizon is cycle_input.forecast_horizon
    assert cycle_result.problem.objectives is cycle_input.objectives
    assert cycle_result.optimization_result.source_problem is cycle_result.problem
    assert cycle_result.control_plan.source_result is cycle_result.optimization_result
    assert cycle_result.current_action.source_plan is cycle_result.control_plan
    assert cycle_result.decision.source_context is cycle_input.context
    assert cycle_result.decision.source_strategy is cycle_input.source_strategy
    assert (
        cycle_result.decision.intent is cycle_result.current_action.selected_step.intent
    )


@pytest.mark.parametrize(
    ("failure_stage", "expected_calls"),
    [
        ("optimization", (1, 0, 0, 0)),
        ("construction", (1, 1, 0, 0)),
        ("extraction", (1, 1, 1, 0)),
        ("translation", (1, 1, 1, 1)),
    ],
)
def test_first_dependency_failure_stops_without_retry_or_downstream_invocation(
    failure_stage: str,
    expected_calls: tuple[int, int, int, int],
) -> None:
    orchestrator, _ = make_orchestrator()
    failures: dict[str, type[Exception]] = {
        "optimization": LookupError,
        "construction": ArithmeticError,
        "extraction": KeyError,
        "translation": RuntimeError,
    }
    failure = failures[failure_stage]("stop")
    if failure_stage == "optimization":
        CountingOptimizationBoundary.failure = failure
    elif failure_stage == "construction":
        CountingPlanConstructor.failure = failure
    elif failure_stage == "extraction":
        CountingExtractor.failure = failure
    else:
        CountingTranslator.failure = failure

    with pytest.raises(failures[failure_stage], match="stop"):
        orchestrator.run_cycle(make_input())

    assert (
        CountingOptimizationBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        CountingTranslator.calls,
    ) == expected_calls


def test_orchestrator_rejects_invalid_dependencies_and_cycle_input() -> None:
    _, dependencies = make_orchestrator()
    with pytest.raises(TypeError, match="optimization_boundary"):
        SingleMPCCycleOrchestrator(cast(Any, object()), *dependencies[1:])
    with pytest.raises(TypeError, match="cycle_input"):
        SingleMPCCycleOrchestrator(*dependencies).run_cycle(cast(Any, object()))


def test_orchestrator_module_has_no_feasibility_actuation_or_execution_dependency() -> (
    None
):
    module_path = Path(ems_strategy.__file__).parent / "mpc_orchestrator.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "ems_strategy.decision",
        "ems_strategy.mpc_current_action",
        "ems_strategy.mpc_cycle",
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


def test_public_api_exports_single_mpc_cycle_orchestrator() -> None:
    assert "SingleMPCCycleOrchestrator" in ems_strategy.__all__
    assert ems_strategy.SingleMPCCycleOrchestrator is SingleMPCCycleOrchestrator
