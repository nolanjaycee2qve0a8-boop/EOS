"""Tests for TASK-150 schedule-aware physical optimization composition."""

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
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicMultiOpportunityCandidatePlanner,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicMultiOpportunityPhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    MultiOpportunityCandidatePlanningBoundary,
    MultiOpportunityCandidatePlanningInput,
    MultiOpportunityCandidatePlanningResult,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleBoundary,
    MultiOpportunityHeadroomScheduleInput,
    MultiOpportunityPhysicalOptimizationBoundary,
    MultiOpportunityPhysicalOptimizationInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    PhysicallyAwareOptimizationSolveOutput,
    PVOpportunityWindowConfiguration,
)
from tests.unit.optimization.test_optimization_contracts import make_context

_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)


def _point(hour: int, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 4, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def _model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    model: BatteryOptimizationModel | None = None,
) -> MultiOpportunityPhysicalOptimizationInput:
    return MultiOpportunityPhysicalOptimizationInput(
        OptimizationProblem(
            make_context(),
            ForecastHorizon(points),
            OptimizationObjectiveCollection(
                (OptimizationObjective("energy_cost", "minimize"),)
            ),
        ),
        _CONFIGURATION,
        BatteryOptimizationState(soc),
        model or _model(),
        PVOpportunityWindowConfiguration(1),
        3600.0,
    )


def _schedule_calculator() -> DeterministicMultiOpportunityHeadroomScheduleCalculator:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    )


def _candidate_planner() -> DeterministicMultiOpportunityCandidatePlanner:
    return DeterministicMultiOpportunityCandidatePlanner(
        NetLoadAwareBaselineOptimizer(_CONFIGURATION),
        DeterministicMultiOpportunityGridChargeReservationCalculator(),
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

    def __init__(self, delegate: MultiOpportunityHeadroomScheduleBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: MultiOpportunityHeadroomScheduleInput | None = None

    def calculate(
        self,
        schedule_input: MultiOpportunityHeadroomScheduleInput,
    ) -> MultiOpportunityHeadroomSchedule:
        self.calls += 1
        self.received = schedule_input
        return self.delegate.calculate(schedule_input)


class _TrackingCandidate(MultiOpportunityCandidatePlanningBoundary):
    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: MultiOpportunityCandidatePlanningBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: MultiOpportunityCandidatePlanningInput | None = None

    def plan(
        self,
        planning_input: MultiOpportunityCandidatePlanningInput,
    ) -> MultiOpportunityCandidatePlanningResult:
        self.calls += 1
        self.received = planning_input
        return self.delegate.plan(planning_input)


class _TrackingReviser(ExplicitCandidatePhysicalRevisionBoundary):
    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: ExplicitCandidatePhysicalRevisionBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: ExplicitCandidatePhysicalRevisionInput | None = None

    def revise(
        self,
        revision_input: ExplicitCandidatePhysicalRevisionInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        self.calls += 1
        self.received = revision_input
        return self.delegate.revise(revision_input)


def _tracking_optimizer() -> tuple[
    DeterministicMultiOpportunityPhysicalOptimizer,
    _TrackingSchedule,
    _TrackingCandidate,
    _TrackingReviser,
]:
    schedule = _TrackingSchedule(_schedule_calculator())
    candidate = _TrackingCandidate(_candidate_planner())
    reviser = _TrackingReviser(_reviser())
    return (
        DeterministicMultiOpportunityPhysicalOptimizer(schedule, candidate, reviser),
        schedule,
        candidate,
        reviser,
    )


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    optimizer, _, _, _ = _tracking_optimizer()
    output = optimizer.solve_multi_opportunity(_input((_point(0, 0.0, 1.0, 0.3),)))

    assert [
        field.name for field in fields(MultiOpportunityPhysicalOptimizationInput)
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
        cast(Any, output).source_input = output.source_input
    with pytest.raises(TypeError):
        cast(Any, MultiOpportunityPhysicalOptimizationBoundary)()
    assert DeterministicMultiOpportunityPhysicalOptimizer.__slots__ == (
        "schedule_calculator",
        "candidate_planner",
        "explicit_physical_reviser",
    )


def test_all_three_boundaries_run_once_with_exact_identity_chain() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.3),
            _point(1, 3.8, 0.0, None),
            _point(2, 0.0, 2.0, None),
            _point(3, 4.2, 0.0, None),
        ),
        soc=0.6,
    )
    optimizer, schedule, candidate, reviser = _tracking_optimizer()
    output = optimizer.solve_multi_opportunity(source)

    assert (schedule.calls, candidate.calls, reviser.calls) == (1, 1, 1)
    assert schedule.received is not None
    assert schedule.received.forecast_horizon is source.problem.forecast_horizon
    assert schedule.received.battery_model is source.battery_model
    assert (
        schedule.received.opportunity_configuration is source.opportunity_configuration
    )
    assert candidate.received is output.candidate_planning_result.source_input
    assert candidate.received is not None
    assert candidate.received.headroom_schedule is output.headroom_schedule
    assert candidate.received.problem is source.problem
    assert candidate.received.configuration is source.configuration
    assert candidate.received.battery_state is source.battery_state
    assert candidate.received.battery_model is source.battery_model
    assert reviser.received is not None
    assert reviser.received.candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.headroom_schedule.source_input.forecast_horizon is (
        source.problem.forecast_horizon
    )


def test_schedule_adjustment_and_downstream_physical_revision_remain_distinct() -> None:
    source = _input(
        (
            _point(0, 0.0, 1.0, 0.3),
            _point(1, 3.0, 0.0, None),
            _point(2, 0.0, 2.0, None),
            _point(3, 6.0, 0.0, None),
        ),
        soc=0.6,
    )
    optimizer, _, _, _ = _tracking_optimizer()
    output = optimizer.solve_multi_opportunity(source)
    planning = output.candidate_planning_result

    assert planning.reservation_result is not None
    assert planning.final_output.solution.steps[0].requested_power_kw < 3.0
    assert output.physical_output.candidate_output is planning.final_output
    final_future = output.physical_output.final_output.solution.steps[3]
    assert final_future.intent.action == "charge"
    assert final_future.requested_power_kw < 6.0
    assert "charge_power_limit" in output.physical_output.revision.steps[3].reasons


def test_pv_surplus_bypasses_reservation_and_still_enters_physical_revision() -> None:
    source = _input((_point(0, 6.0, 0.0, 0.1),), soc=0.2)
    optimizer, _, _, _ = _tracking_optimizer()
    output = optimizer.solve_multi_opportunity(source)
    planning = output.candidate_planning_result

    assert planning.reservation_result is None
    assert planning.final_output is planning.source_candidate_output
    assert output.physical_output.candidate_output is planning.final_output
    assert (
        output.physical_output.final_output.solution.steps[0].requested_power_kw == 3.0
    )


def test_public_api_exports_task_150_contracts() -> None:
    for name in (
        "MultiOpportunityPhysicalOptimizationInput",
        "MultiOpportunityPhysicalOptimizationSolveOutput",
        "MultiOpportunityPhysicalOptimizationBoundary",
        "DeterministicMultiOpportunityPhysicalOptimizer",
    ):
        assert name in optimization.__all__


def test_composition_has_no_direct_planning_or_execution_dependencies() -> None:
    module_path = (
        Path(optimization.__file__).parent
        / "multi_opportunity_physical_optimization.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "optimization.pv_headroom",
        "optimization.multi_opportunity_grid_charge_reservation",
        "optimization.physically_aware_baseline.DeterministicExplicitCandidatePhysicalReviser",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    assert "DeterministicPVOpportunitySequenceCalculator" not in source
    assert "DeterministicPVHeadroomRequirementCalculator" not in source
