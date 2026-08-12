"""Tests for one physically-aware MPC candidate-to-decision cycle."""

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
    PhysicallyAwareMPCCycleBoundary,
    PhysicallyAwareMPCCycleInput,
    PhysicallyAwareMPCCycleResult,
    PhysicallyAwareSingleMPCCycleOrchestrator,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    OptimizationControlPlan,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationBoundary,
    PhysicallyAwareOptimizationSolveOutput,
    PhysicallyAwarePriceBaselineOptimizer,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)


class CountingPhysicalBoundary(PhysicallyAwareOptimizationBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def __init__(self, delegate: PhysicallyAwareOptimizationBoundary) -> None:
        self._delegate = delegate

    def solve_physically(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return self._delegate.solve_physically(optimization_input)


class CountingPlanConstructor(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None
    received_solution: ClassVar[object | None] = None

    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        self.__class__.calls += 1
        self.__class__.received_solution = construction_input.solution
        if self.failure is not None:
            raise self.failure
        return OptimizationSolutionControlPlanBuilder().construct(construction_input)


class CountingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class MinimalDecisionTranslator(MPCDecisionTranslationBoundary):
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
        CountingPhysicalBoundary,
        CountingPlanConstructor,
        CountingExtractor,
        MinimalDecisionTranslator,
    ):
        dependency.calls = 0
        dependency.failure = None
    CountingPlanConstructor.received_solution = None


def make_cycle_input(
    *,
    prices: tuple[float, ...] = (0.9,),
    objectives: tuple[OptimizationObjective, ...] = (
        OptimizationObjective("energy_cost", "minimize"),
    ),
) -> MPCCycleInput:
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
    points = tuple(
        ForecastPoint(
            datetime(2026, 1, 1, hour + 1, tzinfo=UTC),
            pv_power_kw=1.0,
            load_power_kw=2.0,
            electricity_price_cny_per_kwh=price,
        )
        for hour, price in enumerate(prices)
    )
    return MPCCycleInput(
        context,
        ForecastHorizon(points),
        MPCConfiguration(len(points), 3600.0),
        OptimizationObjectiveCollection(objectives),
        EMSStrategyDescriptor("mpc", "1.0"),
    )


def make_physical_input(
    *,
    prices: tuple[float, ...] = (0.9,),
    soc: float = 0.8,
    model: BatteryOptimizationModel | None = None,
    objectives: tuple[OptimizationObjective, ...] = (
        OptimizationObjective("energy_cost", "minimize"),
    ),
) -> PhysicallyAwareMPCCycleInput:
    return PhysicallyAwareMPCCycleInput(
        make_cycle_input(prices=prices, objectives=objectives),
        BatteryOptimizationState(soc),
        model or BatteryOptimizationModel(10.0, 0.1, 0.9, 4.0, 4.0, 1.0, 1.0),
    )


def make_real_physical_optimizer(
    power: float = 6.0,
) -> PhysicallyAwarePriceBaselineOptimizer:
    return PhysicallyAwarePriceBaselineOptimizer(
        PriceAwareBaselineOptimizer(
            PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, power)
        ),
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )


def make_orchestrator(
    physical_boundary: PhysicallyAwareOptimizationBoundary | None = None,
) -> PhysicallyAwareSingleMPCCycleOrchestrator:
    return PhysicallyAwareSingleMPCCycleOrchestrator(
        physical_boundary or make_real_physical_optimizer(),
        CountingPlanConstructor(),
        CountingExtractor(),
        MinimalDecisionTranslator(),
    )


def test_contracts_are_frozen_slotted_and_preserve_exact_complete_chain() -> None:
    source_input = make_physical_input()
    result = make_orchestrator().run_cycle(source_input)

    assert [field.name for field in fields(PhysicallyAwareMPCCycleInput)] == [
        "cycle_input",
        "battery_state",
        "battery_model",
    ]
    assert [field.name for field in fields(PhysicallyAwareMPCCycleResult)] == [
        "source_input",
        "problem",
        "battery_input",
        "physically_aware_input",
        "optimization_output",
        "control_plan",
        "current_action",
        "decision",
    ]
    assert result.source_input is source_input
    assert result.problem.context is source_input.cycle_input.context
    assert result.problem.forecast_horizon is source_input.cycle_input.forecast_horizon
    assert result.problem.objectives is source_input.cycle_input.objectives
    assert result.battery_input.problem is result.problem
    assert result.battery_input.battery_state is source_input.battery_state
    assert result.battery_input.battery_model is source_input.battery_model
    assert result.physically_aware_input.battery_input is result.battery_input
    assert result.optimization_output.source_input is result.physically_aware_input
    assert (
        result.control_plan.source_result
        is result.optimization_output.final_output.result
    )
    assert result.current_action.source_plan is result.control_plan
    assert result.decision.source_context is source_input.cycle_input.context
    assert result.decision.source_strategy is source_input.cycle_input.source_strategy
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).decision = result.decision


def test_final_solution_drives_power_limited_decision_with_retained_evidence() -> None:
    result = make_orchestrator().run_cycle(make_physical_input(soc=0.8))
    output = result.optimization_output
    candidate_step = output.candidate_output.solution.steps[0]
    revision_step = output.revision.steps[0]
    final_step = output.final_output.solution.steps[0]

    assert candidate_step.requested_power_kw == 6.0
    assert final_step.requested_power_kw == 4.0
    assert revision_step.source_candidate_step is candidate_step
    assert revision_step.revised_step is final_step
    assert revision_step.reasons == ("discharge_power_limit",)
    assert CountingPlanConstructor.received_solution is output.final_output.solution
    assert result.decision.requested_power_kw == 4.0
    assert result.decision.intent is final_step.intent
    assert output.candidate_constraint_evaluation.feasible is False
    assert output.candidate_power_evaluation.violations[0].source_step is candidate_step
    assert output.final_constraint_evaluation.feasible is True


def test_soc_limited_final_decision_uses_revised_power_and_reason() -> None:
    result = make_orchestrator().run_cycle(
        make_physical_input(
            soc=0.2,
            model=BatteryOptimizationModel(10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 0.9),
        )
    )
    output = result.optimization_output
    candidate_step = output.candidate_output.solution.steps[0]
    final_step = output.final_output.solution.steps[0]

    assert candidate_step.requested_power_kw == 6.0
    assert 0 < final_step.requested_power_kw < candidate_step.requested_power_kw
    assert output.revision.steps[0].reasons == ("min_soc_limit",)
    assert result.decision.requested_power_kw == final_step.requested_power_kw
    assert output.final_constraint_evaluation.feasible is True


def test_feasible_candidate_remains_semantically_equivalent_but_final_is_distinct() -> (
    None
):
    result = make_orchestrator(make_real_physical_optimizer(2.0)).run_cycle(
        make_physical_input(
            soc=0.8,
            model=BatteryOptimizationModel(10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 1.0),
        )
    )
    output = result.optimization_output
    candidate_step = output.candidate_output.solution.steps[0]
    final_step = output.final_output.solution.steps[0]

    assert candidate_step is not final_step
    assert candidate_step.intent.action == final_step.intent.action
    assert candidate_step.requested_power_kw == final_step.requested_power_kw
    assert output.revision.steps[0].reasons == ()
    assert result.decision.requested_power_kw == final_step.requested_power_kw


def test_unsupported_objective_preserves_empty_solution_and_extractor_failure() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        make_orchestrator().run_cycle(
            make_physical_input(
                objectives=(OptimizationObjective("unsupported", "minimize"),),
            )
        )
    assert CountingPlanConstructor.calls == 1
    assert CountingExtractor.calls == 1
    assert MinimalDecisionTranslator.calls == 0


@pytest.mark.parametrize(
    ("stage", "expected_calls"),
    [
        ("physical", (1, 0, 0, 0)),
        ("plan", (1, 1, 0, 0)),
        ("extract", (1, 1, 1, 0)),
        ("translate", (1, 1, 1, 1)),
    ],
)
def test_first_failure_stops_without_retries(
    stage: str,
    expected_calls: tuple[int, int, int, int],
) -> None:
    physical = CountingPhysicalBoundary(make_real_physical_optimizer())
    if stage == "physical":
        CountingPhysicalBoundary.failure = LookupError("stop")
    elif stage == "plan":
        CountingPlanConstructor.failure = ArithmeticError("stop")
    elif stage == "extract":
        CountingExtractor.failure = KeyError("stop")
    else:
        MinimalDecisionTranslator.failure = RuntimeError("stop")

    failures: dict[str, type[Exception]] = {
        "physical": LookupError,
        "plan": ArithmeticError,
        "extract": KeyError,
        "translate": RuntimeError,
    }
    with pytest.raises(failures[stage], match="stop"):
        make_orchestrator(physical).run_cycle(make_physical_input())

    assert (
        CountingPhysicalBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == expected_calls


def test_boundary_is_abstract_slotted_with_explicit_orchestrator_dependencies() -> None:
    signature = inspect.signature(PhysicallyAwareMPCCycleBoundary.run_cycle)
    hints = get_type_hints(PhysicallyAwareMPCCycleBoundary.run_cycle)
    orchestrator = make_orchestrator()

    assert issubclass(PhysicallyAwareMPCCycleBoundary, ABC)
    assert inspect.isabstract(PhysicallyAwareMPCCycleBoundary)
    assert PhysicallyAwareMPCCycleBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "cycle_input"]
    assert hints == {
        "cycle_input": PhysicallyAwareMPCCycleInput,
        "return": PhysicallyAwareMPCCycleResult,
    }
    assert isinstance(
        orchestrator.physically_aware_optimization_boundary,
        PhysicallyAwareOptimizationBoundary,
    )
    assert isinstance(
        orchestrator.solution_plan_constructor,
        OptimizationSolutionControlPlanConstructionBoundary,
    )
    assert isinstance(
        orchestrator.current_action_extractor,
        MPCCurrentActionExtractionBoundary,
    )
    assert isinstance(orchestrator.decision_translator, MPCDecisionTranslationBoundary)
    with pytest.raises(TypeError):
        PhysicallyAwareMPCCycleBoundary()  # type: ignore[abstract]


def test_module_isolated_from_feasibility_actuation_simulator_and_execution() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc_physically_aware.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
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
    assert "FeasibilityBoundary" not in source
    assert "ActuationHandoffBoundary" not in source


def test_public_api_exports_physically_aware_mpc_cycle_contracts() -> None:
    for name in (
        "PhysicallyAwareMPCCycleBoundary",
        "PhysicallyAwareMPCCycleInput",
        "PhysicallyAwareMPCCycleResult",
        "PhysicallyAwareSingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
