"""Tests for the TASK-142 rolling-headroom physical composition path."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunityWindowSelector,
    DeterministicRollingHeadroomAwarePhysicalOptimizer,
    DeterministicRollingPVHeadroomRequirementCalculator,
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    HeadroomAwareCandidatePlanningBoundary,
    HeadroomAwareCandidatePlanningInput,
    HeadroomAwareCandidatePlanningResult,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationSolveOutput,
    PVOpportunityWindowConfiguration,
    RollingHeadroomAwarePhysicalOptimizationBoundary,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
    RollingPVHeadroomRequirement,
    RollingPVHeadroomRequirementBoundary,
    RollingPVHeadroomRequirementInput,
)
from tests.unit.optimization.test_optimization_contracts import make_context


def _point(hour: int, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def _model(*, maximum: float = 1.0) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.2, maximum, 3.0, 3.0, 0.95, 0.95)


def _source(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    model: BatteryOptimizationModel | None = None,
    objectives: tuple[OptimizationObjective, ...] | None = None,
) -> PhysicallyAwareBaselineOptimizationInput:
    problem = OptimizationProblem(
        make_context(),
        ForecastHorizon(points),
        OptimizationObjectiveCollection(
            objectives or (OptimizationObjective("energy_cost", "minimize"),)
        ),
    )
    return PhysicallyAwareBaselineOptimizationInput(
        BatteryOptimizationInput(
            problem, BatteryOptimizationState(soc), model or _model()
        ),
        3600.0,
    )


def _rolling_calculator() -> DeterministicRollingPVHeadroomRequirementCalculator:
    return DeterministicRollingPVHeadroomRequirementCalculator(
        DeterministicPVOpportunityWindowSelector(),
        DeterministicPVHeadroomRequirementCalculator(),
    )


def _planner() -> DeterministicHeadroomAwareCandidatePlanner:
    return DeterministicHeadroomAwareCandidatePlanner(
        NetLoadAwareBaselineOptimizer(
            NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
        ),
        DeterministicHeadroomAwareGridChargeReservationCalculator(),
    )


def _reviser() -> DeterministicExplicitCandidatePhysicalReviser:
    return DeterministicExplicitCandidatePhysicalReviser(
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )


def _optimizer(
    configuration: PVOpportunityWindowConfiguration | None = None,
) -> DeterministicRollingHeadroomAwarePhysicalOptimizer:
    return DeterministicRollingHeadroomAwarePhysicalOptimizer(
        _rolling_calculator(),
        _planner(),
        _reviser(),
        configuration or PVOpportunityWindowConfiguration(1),
    )


def test_contract_is_frozen_slotted_and_boundary_is_abstract() -> None:
    output = _optimizer().solve_rolling_headroom_aware(
        _source((_point(0, 0.0, 1.0, 0.3),))
    )

    assert [
        field.name
        for field in fields(RollingHeadroomAwarePhysicalOptimizationSolveOutput)
    ] == [
        "source_input",
        "rolling_headroom_requirement",
        "candidate_planning_result",
        "physical_output",
    ]
    assert not hasattr(output, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, output).source_input = output.source_input
    with pytest.raises(TypeError):
        cast(Any, RollingHeadroomAwarePhysicalOptimizationBoundary)()
    assert DeterministicRollingHeadroomAwarePhysicalOptimizer.__slots__ == (
        "rolling_headroom_calculator",
        "candidate_planner",
        "explicit_physical_reviser",
        "window_configuration",
    )


def test_full_forecast_to_first_opportunity_headroom_provenance_is_exact() -> None:
    points = (
        _point(0, 0.0, 1.0, 0.3),
        _point(1, 3.0, 0.0, None),
        _point(2, 2.263157894736842, 0.0, None),
        _point(3, 0.0, 1.0, None),
        _point(4, 0.0, 1.0, None),
        _point(5, 11.0, 0.0, None),
    )
    source = _source(points)
    configuration = PVOpportunityWindowConfiguration(1)
    output = _optimizer(configuration).solve_rolling_headroom_aware(source)

    rolling = output.rolling_headroom_requirement
    assert output.source_input is source
    assert rolling.source_input.forecast_horizon is (
        source.battery_input.problem.forecast_horizon
    )
    assert rolling.source_input.window_configuration is configuration
    assert rolling.source_input.battery_model is source.battery_input.battery_model
    assert tuple(step.source_index for step in rolling.opportunity_window.steps) == (
        1,
        2,
    )
    assert all(
        selected is original
        for selected, original in zip(
            rolling.selected_forecast_horizon.points,
            points[1:3],
            strict=True,
        )
    )
    assert rolling.headroom_requirement.source_input.forecast_horizon is (
        rolling.selected_forecast_horizon
    )
    assert rolling.headroom_requirement.total_forecast_pv_surplus_energy_kwh == (
        pytest.approx(5.2631578947368425)
    )


def test_cheap_grid_reservation_uses_rolling_requirement_and_physical_candidate() -> (
    None
):
    source = _source(
        (
            _point(0, 0.0, 1.0, 0.3),
            _point(1, 3.0, 0.0, None),
            _point(2, 2.263157894736842, 0.0, None),
        )
    )
    output = _optimizer().solve_rolling_headroom_aware(source)
    planning = output.candidate_planning_result

    assert planning.source_input.battery_input is source.battery_input
    assert planning.source_input.headroom_requirement is (
        output.rolling_headroom_requirement.headroom_requirement
    )
    assert planning.source_candidate_output.solution.steps[0].requested_power_kw == 3.0
    assert planning.grid_charge_reservation is not None
    assert planning.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        0.5263157894736842
    )
    assert output.physical_output.candidate_output is planning.final_output
    assert output.physical_output.final_output.solution.steps[0].requested_power_kw == (
        pytest.approx(0.5263157894736842)
    )


def test_current_opportunity_uses_only_remaining_current_window() -> None:
    points = (
        _point(0, 3.0, 0.0, None),
        _point(1, 2.0, 0.0, None),
        _point(2, 0.0, 1.0, None),
        _point(3, 0.0, 1.0, None),
        _point(4, 8.0, 0.0, None),
    )
    output = _optimizer().solve_rolling_headroom_aware(_source(points, soc=0.2))

    rolling = output.rolling_headroom_requirement
    assert tuple(step.source_index for step in rolling.opportunity_window.steps) == (
        0,
        1,
    )
    assert rolling.selected_forecast_horizon.points[0] is points[0]
    assert rolling.headroom_requirement.total_forecast_pv_surplus_energy_kwh == 5.0


def test_confirmed_cloud_gap_remains_inner_headroom_evidence() -> None:
    points = (
        _point(0, 3.0, 0.0, None),
        _point(1, 1.0, 1.0, None),
        _point(2, 4.0, 0.0, None),
    )
    output = _optimizer(
        PVOpportunityWindowConfiguration(1)
    ).solve_rolling_headroom_aware(_source(points, soc=0.2))
    rolling = output.rolling_headroom_requirement

    assert tuple(step.source_index for step in rolling.opportunity_window.steps) == (
        0,
        1,
        2,
    )
    assert rolling.selected_forecast_horizon.points[1] is points[1]
    assert rolling.headroom_requirement.steps[1].pv_surplus_power_kw == 0.0
    assert rolling.headroom_requirement.total_forecast_pv_surplus_energy_kwh == 7.0


def test_empty_opportunity_leaves_cheap_grid_charge_unrestricted_by_headroom() -> None:
    output = _optimizer().solve_rolling_headroom_aware(
        _source((_point(0, 0.0, 1.0, 0.3), _point(1, 0.0, 1.0, 0.3)))
    )
    rolling = output.rolling_headroom_requirement
    planning = output.candidate_planning_result

    assert rolling.selected_forecast_horizon.points == ()
    assert rolling.headroom_requirement.required_headroom_energy_kwh == 0.0
    assert rolling.headroom_requirement.recommended_pre_pv_max_soc_fraction == 1.0
    assert planning.grid_charge_reservation is not None
    assert planning.grid_charge_reservation.allowed_grid_charge_power_kw == 3.0
    assert planning.final_output.solution.steps[0].requested_power_kw == 3.0


def test_pv_surplus_bypasses_reservation_but_physical_power_limit_remains() -> None:
    output = _optimizer().solve_rolling_headroom_aware(
        _source((_point(0, 6.0, 0.0, None),), soc=0.2)
    )
    planning = output.candidate_planning_result
    final = output.physical_output.final_output.solution.steps[0]

    assert planning.grid_charge_reservation is None
    assert planning.final_output.solution.steps[0].requested_power_kw == 6.0
    assert final.requested_power_kw == 3.0
    assert output.physical_output.revision.steps[0].reasons == ("charge_power_limit",)


def test_physical_soc_revision_can_further_reduce_rolling_candidate() -> None:
    output = _optimizer().solve_rolling_headroom_aware(
        _source((_point(0, 6.0, 0.0, None),), soc=0.98)
    )
    final = output.physical_output.final_output.solution.steps[0]

    assert (
        output.candidate_planning_result.final_output.solution.steps[
            0
        ].requested_power_kw
        == 6.0
    )
    assert final.intent.action == "charge"
    assert final.requested_power_kw == pytest.approx(0.21052631578947364)
    assert output.physical_output.revision.steps[0].reasons == (
        "charge_power_limit",
        "max_soc_limit",
    )


def test_unsupported_candidate_remains_empty_without_invented_idle() -> None:
    output = _optimizer().solve_rolling_headroom_aware(
        _source(
            (_point(0, 0.0, 1.0, 0.3),),
            objectives=(OptimizationObjective("peak", "minimize"),),
        )
    )

    assert output.candidate_planning_result.source_candidate_output.result.outcome == (
        "unavailable"
    )
    assert output.candidate_planning_result.final_output.solution.steps == ()
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.physical_output.final_output.solution.steps == ()


class _TrackingRollingCalculator(RollingPVHeadroomRequirementBoundary):
    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: RollingPVHeadroomRequirementBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: object | None = None

    def calculate(
        self,
        requirement_input: RollingPVHeadroomRequirementInput,
    ) -> RollingPVHeadroomRequirement:
        self.calls += 1
        self.received = requirement_input
        return self.delegate.calculate(requirement_input)


class _TrackingPlanner(HeadroomAwareCandidatePlanningBoundary):
    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: HeadroomAwareCandidatePlanningBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: object | None = None

    def plan(
        self,
        planning_input: HeadroomAwareCandidatePlanningInput,
    ) -> HeadroomAwareCandidatePlanningResult:
        self.calls += 1
        self.received = planning_input
        return self.delegate.plan(planning_input)


class _TrackingReviser(ExplicitCandidatePhysicalRevisionBoundary):
    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: ExplicitCandidatePhysicalRevisionBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.received: object | None = None

    def revise(
        self,
        revision_input: ExplicitCandidatePhysicalRevisionInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        self.calls += 1
        self.received = revision_input
        return self.delegate.revise(revision_input)


def test_each_injected_stage_executes_once_without_duplicate_candidate_solve() -> None:
    rolling = _TrackingRollingCalculator(_rolling_calculator())
    planner = _TrackingPlanner(_planner())
    reviser = _TrackingReviser(_reviser())
    configuration = PVOpportunityWindowConfiguration(1)
    source = _source((_point(0, 0.0, 1.0, 0.3), _point(1, 3.0, 0.0, None)))
    output = DeterministicRollingHeadroomAwarePhysicalOptimizer(
        rolling,
        planner,
        reviser,
        configuration,
    ).solve_rolling_headroom_aware(source)

    assert (rolling.calls, planner.calls, reviser.calls) == (1, 1, 1)
    assert cast(Any, rolling.received).forecast_horizon is (
        source.battery_input.problem.forecast_horizon
    )
    assert cast(Any, rolling.received).window_configuration is configuration
    assert cast(Any, planner.received).headroom_requirement is (
        output.rolling_headroom_requirement.headroom_requirement
    )
    assert cast(Any, reviser.received).candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )


def test_public_api_and_module_dependencies_remain_composition_only() -> None:
    for name in (
        "RollingHeadroomAwarePhysicalOptimizationSolveOutput",
        "RollingHeadroomAwarePhysicalOptimizationBoundary",
        "DeterministicRollingHeadroomAwarePhysicalOptimizer",
    ):
        assert name in optimization.__all__

    module_path = (
        Path(optimization.__file__).parent
        / "rolling_headroom_aware_physical_optimization.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.net_load_aware_baseline",
        "optimization.grid_charge_reservation",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
