"""Tests for one schedule-aware MPC cycle and its physical evidence view."""

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
    MultiOpportunityMPCCycleBoundary,
    MultiOpportunityMPCCycleInput,
    MultiOpportunityMPCCycleResult,
    MultiOpportunitySingleMPCCycleOrchestrator,
    PhysicallyAwareMPCCycleInput,
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
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicMultiOpportunityCandidatePlanner,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicMultiOpportunityPhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    MultiOpportunityPhysicalOptimizationBoundary,
    MultiOpportunityPhysicalOptimizationInput,
    MultiOpportunityPhysicalOptimizationSolveOutput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationControlPlan,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PVOpportunityWindowConfiguration,
)

CANDIDATE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)


class CountingOptimizationBoundary(MultiOpportunityPhysicalOptimizationBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0
    received_input: ClassVar[object | None] = None

    def __init__(self, delegate: MultiOpportunityPhysicalOptimizationBoundary) -> None:
        self._delegate = delegate

    def solve_multi_opportunity(
        self, optimization_input: MultiOpportunityPhysicalOptimizationInput
    ) -> MultiOpportunityPhysicalOptimizationSolveOutput:
        self.__class__.calls += 1
        self.__class__.received_input = optimization_input
        return self._delegate.solve_multi_opportunity(optimization_input)


class CountingPlanConstructor(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    received_solution: ClassVar[object | None] = None

    def construct(
        self, construction_input: OptimizationSolutionControlPlanConstructionInput
    ) -> OptimizationControlPlan:
        self.__class__.calls += 1
        self.__class__.received_solution = construction_input.solution
        return OptimizationSolutionControlPlanBuilder().construct(construction_input)


class CountingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.__class__.calls += 1
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class MinimalDecisionTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        self.__class__.calls += 1
        step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            context, translation.source_strategy, step.intent, step.requested_power_kw
        )


@pytest.fixture(autouse=True)
def reset_dependencies() -> None:
    CountingOptimizationBoundary.calls = 0
    CountingOptimizationBoundary.received_input = None
    CountingPlanConstructor.calls = 0
    CountingPlanConstructor.received_solution = None
    CountingExtractor.calls = 0
    MinimalDecisionTranslator.calls = 0


def make_context() -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=0.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.3,
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
    return EMSContext(
        source_context,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("cost", "Describe cost without solving it."),
            ActiveCapabilityCollection(matches, (available,), ()),
        ),
        available,
    )


def point(hour: int, *, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(datetime(2026, 1, 1, hour, tzinfo=UTC), pv, load, price)


def make_input(
    points: tuple[ForecastPoint, ...], *, soc: float = 0.45
) -> MultiOpportunityMPCCycleInput:
    cycle = MPCCycleInput(
        make_context(),
        ForecastHorizon(points),
        MPCConfiguration(len(points), 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("mpc", "1.0"),
    )
    return MultiOpportunityMPCCycleInput(
        PhysicallyAwareMPCCycleInput(
            cycle,
            BatteryOptimizationState(soc),
            BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95),
        ),
        CANDIDATE_CONFIGURATION,
        PVOpportunityWindowConfiguration(1),
    )


def make_boundary() -> MultiOpportunityPhysicalOptimizationBoundary:
    return DeterministicMultiOpportunityPhysicalOptimizer(
        DeterministicMultiOpportunityHeadroomScheduleCalculator(
            DeterministicPVOpportunitySequenceCalculator(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
        DeterministicMultiOpportunityCandidatePlanner(
            NetLoadAwareBaselineOptimizer(CANDIDATE_CONFIGURATION),
            DeterministicMultiOpportunityGridChargeReservationCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )


def make_orchestrator(
    boundary: MultiOpportunityPhysicalOptimizationBoundary | None = None,
) -> MultiOpportunitySingleMPCCycleOrchestrator:
    return MultiOpportunitySingleMPCCycleOrchestrator(
        boundary or make_boundary(),
        CountingPlanConstructor(),
        CountingExtractor(),
        MinimalDecisionTranslator(),
    )


def test_schedule_aware_cycle_preserves_complete_physical_final_provenance() -> None:
    source = make_input(
        (
            point(0, pv=0.0, load=1.0, price=0.3),
            point(1, pv=3.0, load=0.0, price=None),
            point(2, pv=0.0, load=1.0, price=None),
            point(3, pv=3.0, load=0.0, price=None),
        )
    )
    result = make_orchestrator().run_cycle(source)
    output = result.multi_opportunity_optimization_output
    physical = output.physical_output
    view = result.physical_cycle_view

    assert (
        output.source_input.problem.context
        is source.physical_cycle_input.cycle_input.context
    )
    assert (
        output.source_input.problem.forecast_horizon
        is source.physical_cycle_input.cycle_input.forecast_horizon
    )
    assert (
        output.source_input.battery_state is source.physical_cycle_input.battery_state
    )
    assert (
        output.source_input.battery_model is source.physical_cycle_input.battery_model
    )
    assert (
        output.source_input.opportunity_configuration
        is source.opportunity_configuration
    )
    assert physical.candidate_output is output.candidate_planning_result.final_output
    assert result.control_plan.source_result is physical.final_output.result
    assert CountingPlanConstructor.received_solution is physical.final_output.solution
    assert view.optimization_output is physical
    assert view.control_plan is result.control_plan
    assert view.current_action is result.current_action
    assert view.decision is result.decision


def test_only_task_150_and_downstream_boundaries_execute_once() -> None:
    result = make_orchestrator(CountingOptimizationBoundary(make_boundary())).run_cycle(
        make_input((point(0, pv=0.0, load=2.0, price=0.9),))
    )
    assert (
        CountingOptimizationBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 1, 1, 1)
    assert (
        CountingOptimizationBoundary.received_input
        is result.multi_opportunity_optimization_output.source_input
    )


def test_pv_surplus_bypasses_reservation_and_physical_final_alone_drives_plan() -> None:
    result = make_orchestrator().run_cycle(
        make_input((point(0, pv=6.0, load=0.0, price=None),), soc=0.2)
    )
    planning = result.multi_opportunity_optimization_output.candidate_planning_result
    physical = result.multi_opportunity_optimization_output.physical_output
    assert planning.reservation_result is None
    assert physical.candidate_output.solution.steps[0].requested_power_kw == 6.0
    assert physical.final_output.solution.steps[0].requested_power_kw == 3.0
    assert result.decision.requested_power_kw == 3.0
    assert result.control_plan.source_result is physical.final_output.result


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = make_input((point(0, pv=0.0, load=2.0, price=0.9),))
    result = make_orchestrator().run_cycle(source)
    assert [field.name for field in fields(MultiOpportunityMPCCycleInput)] == [
        "physical_cycle_input",
        "candidate_configuration",
        "opportunity_configuration",
    ]
    assert [field.name for field in fields(MultiOpportunityMPCCycleResult)] == [
        "source_input",
        "multi_opportunity_optimization_output",
        "control_plan",
        "current_action",
        "decision",
        "physical_cycle_view",
    ]
    assert not hasattr(source, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).decision = result.decision
    assert issubclass(MultiOpportunityMPCCycleBoundary, ABC)
    assert inspect.isabstract(MultiOpportunityMPCCycleBoundary)
    assert MultiOpportunityMPCCycleBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, MultiOpportunityMPCCycleBoundary)()
    assert get_type_hints(MultiOpportunityMPCCycleBoundary.run_cycle) == {
        "cycle_input": MultiOpportunityMPCCycleInput,
        "return": MultiOpportunityMPCCycleResult,
    }


def test_module_only_consumes_task_150_public_boundary_and_exports_api() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc_multi_opportunity.py"
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.multi_opportunity_headroom_schedule",
        "optimization.multi_opportunity_candidate_planning",
        "optimization.physically_aware_baseline",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    for name in (
        "MultiOpportunityMPCCycleBoundary",
        "MultiOpportunityMPCCycleInput",
        "MultiOpportunityMPCCycleResult",
        "MultiOpportunitySingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
