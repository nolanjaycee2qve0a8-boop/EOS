"""Tests for TASK-159 economic schedule-aware MPC cycle integration."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    EconomicMultiOpportunityMPCCycleBoundary,
    EconomicMultiOpportunityMPCCycleInput,
    EconomicMultiOpportunityMPCCycleResult,
    EconomicMultiOpportunitySingleMPCCycleOrchestrator,
    EMSDecision,
    EMSStrategyDescriptor,
    FirstStepMPCCurrentActionExtractor,
    MPCConfiguration,
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCCycleInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    PhysicallyAwareMPCCycleInput,
)
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicEconomicGridChargeValueCalculator,
    DeterministicEconomicMultiOpportunityCandidatePlanner,
    DeterministicEconomicMultiOpportunityPhysicalOptimizer,
    DeterministicEconomicPlanningCalculator,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    EconomicMultiOpportunityPhysicalOptimizationBoundary,
    EconomicMultiOpportunityPhysicalOptimizationInput,
    EconomicMultiOpportunityPhysicalOptimizationSolveOutput,
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
from tests.unit.optimization.test_optimization_contracts import make_context


def _point(hour: int, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def _configuration(
    low: float = 0.3,
    high: float = 0.8,
) -> NetLoadAwareBaselineOptimizationConfiguration:
    return NetLoadAwareBaselineOptimizationConfiguration(low, high, 3.0)


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.886,
    configuration: NetLoadAwareBaselineOptimizationConfiguration | None = None,
) -> EconomicMultiOpportunityMPCCycleInput:
    cycle = MPCCycleInput(
        make_context(),
        ForecastHorizon(points),
        MPCConfiguration(len(points), 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("mpc", "1.0"),
    )
    return EconomicMultiOpportunityMPCCycleInput(
        PhysicallyAwareMPCCycleInput(
            cycle,
            BatteryOptimizationState(soc),
            BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95),
        ),
        configuration or _configuration(),
        PVOpportunityWindowConfiguration(0),
    )


def _economic_physical_boundary(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> DeterministicEconomicMultiOpportunityPhysicalOptimizer:
    return DeterministicEconomicMultiOpportunityPhysicalOptimizer(
        DeterministicMultiOpportunityHeadroomScheduleCalculator(
            DeterministicPVOpportunitySequenceCalculator(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
        DeterministicEconomicPlanningCalculator(),
        DeterministicEconomicMultiOpportunityCandidatePlanner(
            NetLoadAwareBaselineOptimizer(configuration),
            DeterministicMultiOpportunityGridChargeReservationCalculator(),
            DeterministicEconomicGridChargeValueCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )


class _TrackingEconomicPhysical(EconomicMultiOpportunityPhysicalOptimizationBoundary):
    __slots__ = ("calls", "delegate", "received")

    calls: int
    delegate: EconomicMultiOpportunityPhysicalOptimizationBoundary
    received: EconomicMultiOpportunityPhysicalOptimizationInput | None

    def __init__(
        self,
        delegate: EconomicMultiOpportunityPhysicalOptimizationBoundary,
    ) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received = None

    def solve_economic_multi_opportunity(
        self,
        optimization_input: EconomicMultiOpportunityPhysicalOptimizationInput,
    ) -> EconomicMultiOpportunityPhysicalOptimizationSolveOutput:
        self.calls += 1
        self.received = optimization_input
        return self.delegate.solve_economic_multi_opportunity(optimization_input)


class _TrackingPlan(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ("calls", "received")

    calls: int
    received: OptimizationSolutionControlPlanConstructionInput | None

    def __init__(self) -> None:
        self.calls = 0
        self.received = None

    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        self.calls += 1
        self.received = construction_input
        return OptimizationSolutionControlPlanBuilder().construct(construction_input)


class _TrackingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ("calls",)

    calls: int

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.calls += 1
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class _TrackingTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ("calls",)

    calls: int

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        self.calls += 1
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


def _orchestrator(
    source: EconomicMultiOpportunityMPCCycleInput,
) -> tuple[
    EconomicMultiOpportunitySingleMPCCycleOrchestrator,
    _TrackingEconomicPhysical,
    _TrackingPlan,
    _TrackingExtractor,
    _TrackingTranslator,
]:
    physical = _TrackingEconomicPhysical(
        _economic_physical_boundary(source.candidate_configuration)
    )
    plan = _TrackingPlan()
    extractor = _TrackingExtractor()
    translator = _TrackingTranslator()
    return (
        EconomicMultiOpportunitySingleMPCCycleOrchestrator(
            physical,
            plan,
            extractor,
            translator,
        ),
        physical,
        plan,
        extractor,
        translator,
    )


def test_cycle_runs_each_stage_once_and_reuses_exact_compatibility_artifacts() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.2),
            _point(1, 0.0, 1.0, 0.9),
        )
    )
    orchestrator, physical, plan, extractor, translator = _orchestrator(source)
    result = orchestrator.run_cycle(source)
    output = result.economic_multi_opportunity_optimization_output
    source_cycle = source.physical_cycle_input.cycle_input

    assert (physical.calls, plan.calls, extractor.calls, translator.calls) == (
        1,
        1,
        1,
        1,
    )
    assert physical.received is output.source_input
    assert physical.received is not None
    assert physical.received.problem.forecast_horizon is source_cycle.forecast_horizon
    assert physical.received.battery_state is source.physical_cycle_input.battery_state
    assert physical.received.battery_model is source.physical_cycle_input.battery_model
    assert plan.received is not None
    assert plan.received.solution is output.physical_output.final_output.solution
    assert (
        result.control_plan.source_result is output.physical_output.final_output.result
    )
    assert result.current_action.source_plan is result.control_plan
    assert result.decision.source_context is source_cycle.context
    assert result.decision.source_strategy is source_cycle.source_strategy
    assert result.physical_cycle_view.optimization_output is output.physical_output
    assert result.physical_cycle_view.control_plan is result.control_plan
    assert result.physical_cycle_view.current_action is result.current_action
    assert result.physical_cycle_view.decision is result.decision


def test_positive_economics_reaches_decision_from_exact_physical_final() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.2),
            _point(1, 0.0, 1.0, 0.9),
        )
    )
    result = _orchestrator(source)[0].run_cycle(source)
    output = result.economic_multi_opportunity_optimization_output
    planning = output.candidate_planning_result

    assert planning.economic_value_result is not None
    assert planning.economic_value_result.economic_classification == "positive"
    assert planning.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        1.2
    )
    assert output.physical_output.candidate_output is planning.final_output
    assert (
        result.decision.intent
        is output.physical_output.final_output.solution.steps[0].intent
    )
    assert result.decision.requested_power_kw == pytest.approx(1.2)


def test_negative_economics_remains_idle_through_physical_final_and_decision() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.8),
            _point(1, 0.0, 1.0, 0.85),
        ),
        configuration=_configuration(0.8, 1.0),
    )
    result = _orchestrator(source)[0].run_cycle(source)
    output = result.economic_multi_opportunity_optimization_output

    assert output.candidate_planning_result.economic_value_result is not None
    assert (
        output.candidate_planning_result.final_output.solution.steps[0].intent.action
        == "idle"
    )
    assert output.physical_output.final_output.solution.steps[0].intent.action == "idle"
    assert result.current_action.selected_step.intent.action == "idle"
    assert result.decision.intent.action == "idle"
    assert result.decision.requested_power_kw == 0.0


def test_pv_surplus_bypasses_economics_but_physical_final_drives_charge_decision() -> (
    None
):
    source = _input((_point(0, 6.0, 0.0, 0.2),), soc=0.2)
    result = _orchestrator(source)[0].run_cycle(source)
    output = result.economic_multi_opportunity_optimization_output
    planning = output.candidate_planning_result

    assert planning.reservation_result is None
    assert planning.economic_value_result is None
    assert (
        output.physical_output.candidate_output.solution.steps[0].requested_power_kw
        == 6.0
    )
    assert (
        output.physical_output.final_output.solution.steps[0].requested_power_kw == 3.0
    )
    assert result.decision.intent.action == "charge"
    assert result.decision.requested_power_kw == 3.0


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = _input((_point(0, 0.0, 1.0, 0.2),))
    result = _orchestrator(source)[0].run_cycle(source)

    assert [field.name for field in fields(EconomicMultiOpportunityMPCCycleInput)] == [
        "physical_cycle_input",
        "candidate_configuration",
        "opportunity_configuration",
    ]
    assert [field.name for field in fields(EconomicMultiOpportunityMPCCycleResult)] == [
        "source_input",
        "economic_multi_opportunity_optimization_output",
        "control_plan",
        "current_action",
        "decision",
        "physical_cycle_view",
    ]
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).decision = result.decision
    assert issubclass(EconomicMultiOpportunityMPCCycleBoundary, ABC)
    assert inspect.isabstract(EconomicMultiOpportunityMPCCycleBoundary)
    assert EconomicMultiOpportunityMPCCycleBoundary.__slots__ == ()
    assert get_type_hints(EconomicMultiOpportunityMPCCycleBoundary.run_cycle) == {
        "cycle_input": EconomicMultiOpportunityMPCCycleInput,
        "return": EconomicMultiOpportunityMPCCycleResult,
    }
    with pytest.raises(TypeError):
        cast(Any, EconomicMultiOpportunityMPCCycleBoundary)()


def test_module_consumes_task_158_boundary_only_and_exports_api() -> None:
    module_path = (
        Path(ems_strategy.__file__).parent / "mpc_economic_multi_opportunity.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "optimization.economic_planning",
        "optimization.economic_multi_opportunity_candidate_planning",
        "optimization.multi_opportunity_headroom_schedule",
        "optimization.multi_opportunity_grid_charge_reservation",
        "optimization.economic_grid_charge_value",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    assert "DeterministicEconomicMultiOpportunityPhysicalOptimizer" not in source
    for name in (
        "EconomicMultiOpportunityMPCCycleInput",
        "EconomicMultiOpportunityMPCCycleResult",
        "EconomicMultiOpportunityMPCCycleBoundary",
        "EconomicMultiOpportunitySingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
