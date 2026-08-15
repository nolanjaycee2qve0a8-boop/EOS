"""Tests for TASK-158 economic schedule-aware physical composition."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
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
    EconomicMultiOpportunityCandidatePlanningBoundary,
    EconomicMultiOpportunityCandidatePlanningInput,
    EconomicMultiOpportunityCandidatePlanningResult,
    EconomicMultiOpportunityPhysicalOptimizationBoundary,
    EconomicMultiOpportunityPhysicalOptimizationInput,
    EconomicPlanningBoundary,
    EconomicPlanningEvidence,
    EconomicPlanningInput,
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleBoundary,
    MultiOpportunityHeadroomScheduleInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    PhysicallyAwareOptimizationSolveOutput,
    PVOpportunityWindowConfiguration,
)
from tests.unit.optimization.test_optimization_contracts import make_context


def _point(hour: int, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 5, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def _model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)


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
) -> EconomicMultiOpportunityPhysicalOptimizationInput:
    return EconomicMultiOpportunityPhysicalOptimizationInput(
        OptimizationProblem(
            make_context(),
            ForecastHorizon(points),
            OptimizationObjectiveCollection(
                (OptimizationObjective("energy_cost", "minimize"),)
            ),
        ),
        configuration or _configuration(),
        BatteryOptimizationState(soc),
        _model(),
        PVOpportunityWindowConfiguration(0),
        3600.0,
    )


def _schedule() -> DeterministicMultiOpportunityHeadroomScheduleCalculator:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    )


def _candidate(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> DeterministicEconomicMultiOpportunityCandidatePlanner:
    return DeterministicEconomicMultiOpportunityCandidatePlanner(
        NetLoadAwareBaselineOptimizer(configuration),
        DeterministicMultiOpportunityGridChargeReservationCalculator(),
        DeterministicEconomicGridChargeValueCalculator(),
    )


def _reviser() -> DeterministicExplicitCandidatePhysicalReviser:
    return DeterministicExplicitCandidatePhysicalReviser(
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )


class _TrackingSchedule(MultiOpportunityHeadroomScheduleBoundary):
    __slots__ = ("calls", "delegate", "received")

    calls: int
    delegate: MultiOpportunityHeadroomScheduleBoundary
    received: MultiOpportunityHeadroomScheduleInput | None

    def __init__(self, delegate: MultiOpportunityHeadroomScheduleBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received = None

    def calculate(
        self,
        schedule_input: MultiOpportunityHeadroomScheduleInput,
    ) -> MultiOpportunityHeadroomSchedule:
        self.calls += 1
        self.received = schedule_input
        return self.delegate.calculate(schedule_input)


class _TrackingEconomics(EconomicPlanningBoundary):
    __slots__ = ("calls", "delegate", "received")

    calls: int
    delegate: EconomicPlanningBoundary
    received: EconomicPlanningInput | None

    def __init__(self, delegate: EconomicPlanningBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received = None

    def calculate(
        self, planning_input: EconomicPlanningInput
    ) -> EconomicPlanningEvidence:
        self.calls += 1
        self.received = planning_input
        return self.delegate.calculate(planning_input)


class _TrackingCandidate(EconomicMultiOpportunityCandidatePlanningBoundary):
    __slots__ = ("calls", "delegate", "received")

    calls: int
    delegate: EconomicMultiOpportunityCandidatePlanningBoundary
    received: EconomicMultiOpportunityCandidatePlanningInput | None

    def __init__(
        self,
        delegate: EconomicMultiOpportunityCandidatePlanningBoundary,
    ) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received = None

    def plan(
        self,
        planning_input: EconomicMultiOpportunityCandidatePlanningInput,
    ) -> EconomicMultiOpportunityCandidatePlanningResult:
        self.calls += 1
        self.received = planning_input
        return self.delegate.plan(planning_input)


class _TrackingReviser(ExplicitCandidatePhysicalRevisionBoundary):
    __slots__ = ("calls", "delegate", "received")

    calls: int
    delegate: ExplicitCandidatePhysicalRevisionBoundary
    received: ExplicitCandidatePhysicalRevisionInput | None

    def __init__(self, delegate: ExplicitCandidatePhysicalRevisionBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received = None

    def revise(
        self,
        revision_input: ExplicitCandidatePhysicalRevisionInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        self.calls += 1
        self.received = revision_input
        return self.delegate.revise(revision_input)


def _optimizer(
    source: EconomicMultiOpportunityPhysicalOptimizationInput,
) -> tuple[
    DeterministicEconomicMultiOpportunityPhysicalOptimizer,
    _TrackingSchedule,
    _TrackingEconomics,
    _TrackingCandidate,
    _TrackingReviser,
]:
    schedule = _TrackingSchedule(_schedule())
    economics = _TrackingEconomics(DeterministicEconomicPlanningCalculator())
    candidate = _TrackingCandidate(_candidate(source.configuration))
    reviser = _TrackingReviser(_reviser())
    return (
        DeterministicEconomicMultiOpportunityPhysicalOptimizer(
            schedule,
            economics,
            candidate,
            reviser,
        ),
        schedule,
        economics,
        candidate,
        reviser,
    )


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = _input((_point(0, 0.0, 1.0, 0.2),))
    optimizer, _, _, _, _ = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)

    assert [
        field.name
        for field in fields(EconomicMultiOpportunityPhysicalOptimizationInput)
    ] == [
        "problem",
        "configuration",
        "battery_state",
        "battery_model",
        "opportunity_configuration",
        "control_step_duration_seconds",
    ]
    assert not hasattr(output, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, output).source_input = source
    with pytest.raises(TypeError):
        cast(Any, EconomicMultiOpportunityPhysicalOptimizationBoundary)()
    assert DeterministicEconomicMultiOpportunityPhysicalOptimizer.__slots__ == (
        "schedule_calculator",
        "economic_calculator",
        "candidate_planner",
        "explicit_physical_reviser",
    )


def test_all_stages_run_once_and_preserve_exact_identity_chain() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.2),
            _point(1, 0.0, 1.0, 0.9),
        )
    )
    optimizer, schedule, economics, candidate, reviser = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)

    assert (schedule.calls, economics.calls, candidate.calls, reviser.calls) == (
        1,
        1,
        1,
        1,
    )
    assert schedule.received is output.headroom_schedule.source_input
    assert schedule.received is not None
    assert schedule.received.forecast_horizon is source.problem.forecast_horizon
    assert schedule.received.battery_model is source.battery_model
    assert economics.received is output.economic_planning_evidence.source_input
    assert economics.received is not None
    assert economics.received.forecast_horizon is source.problem.forecast_horizon
    assert economics.received.battery_model is source.battery_model
    assert candidate.received is output.candidate_planning_result.source_input
    assert candidate.received is not None
    assert candidate.received.headroom_schedule is output.headroom_schedule
    assert (
        candidate.received.economic_planning_evidence
        is output.economic_planning_evidence
    )
    assert reviser.received is not None
    assert (
        reviser.received.candidate_output
        is output.candidate_planning_result.final_output
    )
    assert (
        output.physical_output.candidate_output
        is output.candidate_planning_result.final_output
    )


def test_positive_economics_preserves_headroom_candidate_before_physical_revision() -> (
    None
):
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.2),
            _point(1, 0.0, 1.0, 0.9),
        )
    )
    optimizer, _, _, _, _ = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)
    planning = output.candidate_planning_result

    assert planning.reservation_result is not None
    assert planning.economic_value_result is not None
    assert planning.economic_value_result.economic_classification == "positive"
    assert planning.final_output.solution.steps[0].intent.action == "charge"
    assert planning.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        1.2
    )
    assert output.physical_output.candidate_output is planning.final_output


def test_negative_economics_enters_physical_revision_as_idle_without_recharge() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.8),
            _point(1, 0.0, 1.0, 0.85),
        ),
        configuration=_configuration(0.8, 1.0),
    )
    optimizer, _, _, _, _ = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)
    planning = output.candidate_planning_result

    assert planning.economic_value_result is not None
    assert planning.economic_value_result.economic_classification == "negative"
    assert planning.final_output.solution.steps[0].intent.action == "idle"
    assert planning.final_output.solution.steps[0].requested_power_kw == 0.0
    assert output.physical_output.candidate_output is planning.final_output
    assert output.physical_output.final_output.solution.steps[0].intent.action == "idle"
    assert (
        output.physical_output.final_output.solution.steps[0].requested_power_kw == 0.0
    )


def test_pv_surplus_bypasses_economics_but_still_receives_physical_revision() -> None:
    source = _input((_point(0, 6.0, 0.0, 0.2),), soc=0.2)
    optimizer, _, _, _, _ = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)
    planning = output.candidate_planning_result

    assert planning.reservation_result is None
    assert planning.economic_value_result is None
    assert planning.final_output is planning.source_candidate_output
    assert output.physical_output.candidate_output is planning.final_output
    assert (
        output.physical_output.final_output.solution.steps[0].requested_power_kw == 3.0
    )


def test_physical_revision_can_further_limit_positive_economic_candidate_horizon() -> (
    None
):
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.2),
            _point(1, 0.0, 1.0, 0.9),
            _point(2, 6.0, 0.0, None),
        ),
        soc=0.2,
    )
    optimizer, _, _, _, _ = _optimizer(source)
    output = optimizer.solve_economic_multi_opportunity(source)

    planning = output.candidate_planning_result
    assert planning.economic_value_result is not None
    assert planning.economic_value_result.economic_classification == "positive"
    assert output.physical_output.candidate_output is planning.final_output
    assert planning.final_output.solution.steps[2].requested_power_kw == 6.0
    assert (
        output.physical_output.final_output.solution.steps[2].requested_power_kw == 3.0
    )
    assert "charge_power_limit" in output.physical_output.revision.steps[2].reasons


def test_public_api_exports_task_158_contracts() -> None:
    for name in (
        "EconomicMultiOpportunityPhysicalOptimizationInput",
        "EconomicMultiOpportunityPhysicalOptimizationSolveOutput",
        "EconomicMultiOpportunityPhysicalOptimizationBoundary",
        "DeterministicEconomicMultiOpportunityPhysicalOptimizer",
    ):
        assert name in optimization.__all__


def test_composition_has_no_direct_inner_candidate_or_execution_dependencies() -> None:
    module_path = (
        Path(optimization.__file__).parent
        / "economic_multi_opportunity_physical_optimization.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "optimization.multi_opportunity_grid_charge_reservation",
        "optimization.economic_grid_charge_value",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    assert "DeterministicEconomicPlanningCalculator" not in source
    assert "DeterministicMultiOpportunityHeadroomScheduleCalculator" not in source
