"""Tests for TASK-149 schedule-aware current candidate planning."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicMultiOpportunityCandidatePlanner,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    MultiOpportunityCandidatePlanningBoundary,
    MultiOpportunityCandidatePlanningInput,
    MultiOpportunityGridChargeReservationBoundary,
    MultiOpportunityGridChargeReservationInput,
    MultiOpportunityGridChargeReservationResult,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    PVOpportunityWindowConfiguration,
)
from optimization.solution_boundary import OptimizationSolveOutput
from tests.unit.optimization.test_optimization_contracts import make_context


def _point(hour: int, *, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 3, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def _model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)


def _configuration() -> NetLoadAwareBaselineOptimizationConfiguration:
    return NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)


def _schedule(
    model: BatteryOptimizationModel,
    points: tuple[ForecastPoint, ...] | None = None,
) -> MultiOpportunityHeadroomSchedule:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    ).calculate(
        MultiOpportunityHeadroomScheduleInput(
            ForecastHorizon(
                points
                or (
                    _point(8, pv=3.0, load=0.0, price=None),
                    _point(9, pv=2.263157894736842, load=0.0, price=None),
                )
            ),
            model,
            3600.0,
            PVOpportunityWindowConfiguration(0),
        )
    )


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    model: BatteryOptimizationModel | None = None,
    schedule: MultiOpportunityHeadroomSchedule | None = None,
    configuration: NetLoadAwareBaselineOptimizationConfiguration | None = None,
) -> MultiOpportunityCandidatePlanningInput:
    resolved_model = model or _model()
    return MultiOpportunityCandidatePlanningInput(
        OptimizationProblem(
            make_context(),
            ForecastHorizon(points),
            OptimizationObjectiveCollection(
                (OptimizationObjective("energy_cost", "minimize"),)
            ),
        ),
        configuration or _configuration(),
        BatteryOptimizationState(soc),
        resolved_model,
        schedule or _schedule(resolved_model),
        3600.0,
    )


class _CountingNetLoadOptimizer(NetLoadAwareBaselineOptimizer):
    """Test-only call counter without changing production optimizer semantics."""

    __slots__ = ()
    calls: ClassVar[int] = 0

    def solve_with_solution(
        self, problem: OptimizationProblem
    ) -> OptimizationSolveOutput:
        type(self).calls += 1
        return super().solve_with_solution(problem)


class _TrackingReservation(MultiOpportunityGridChargeReservationBoundary):
    __slots__ = ("calls", "result")

    def __init__(self) -> None:
        self.calls = 0
        self.result: MultiOpportunityGridChargeReservationResult | None = None

    def calculate(
        self,
        reservation_input: MultiOpportunityGridChargeReservationInput,
    ) -> MultiOpportunityGridChargeReservationResult:
        self.calls += 1
        self.result = (
            DeterministicMultiOpportunityGridChargeReservationCalculator().calculate(
                reservation_input
            )
        )
        return self.result


def _planner(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
    reservation: MultiOpportunityGridChargeReservationBoundary | None = None,
) -> DeterministicMultiOpportunityCandidatePlanner:
    return DeterministicMultiOpportunityCandidatePlanner(
        _CountingNetLoadOptimizer(configuration),
        reservation or DeterministicMultiOpportunityGridChargeReservationCalculator(),
    )


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = _input((_point(0, pv=0.0, load=1.0, price=0.3),))

    assert [field.name for field in fields(MultiOpportunityCandidatePlanningInput)] == [
        "problem",
        "configuration",
        "battery_state",
        "battery_model",
        "headroom_schedule",
        "control_step_duration_seconds",
    ]
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).control_step_duration_seconds = 1800.0
    with pytest.raises(TypeError):
        cast(Any, MultiOpportunityCandidatePlanningBoundary)()
    assert DeterministicMultiOpportunityCandidatePlanner.__slots__ == (
        "candidate_optimizer",
        "reservation_calculator",
    )


def test_current_cheap_grid_charge_is_partially_adjusted_once() -> None:
    source = _input(
        (
            _point(0, pv=0.0, load=1.0, price=0.3),
            _point(1, pv=0.0, load=1.0, price=0.3),
        )
    )
    tracker = _TrackingReservation()
    _CountingNetLoadOptimizer.calls = 0
    result = _planner(source.configuration, tracker).plan(source)

    candidate_steps = result.source_candidate_output.solution.steps
    final_steps = result.final_output.solution.steps
    assert _CountingNetLoadOptimizer.calls == 1
    assert tracker.calls == 1
    assert result.source_input is source
    assert result.reservation_result is tracker.result
    assert result.reservation_result is not None
    assert (
        result.reservation_result.source_input.headroom_schedule
        is source.headroom_schedule
    )
    assert candidate_steps[0].requested_power_kw == 3.0
    assert final_steps[0].intent.action == "charge"
    assert final_steps[0].intent is candidate_steps[0].intent
    assert final_steps[0].requested_power_kw == pytest.approx(0.5263157894736842)
    assert final_steps[1] is candidate_steps[1]


def test_below_allowance_retains_exact_source_candidate_output() -> None:
    model = _model()
    source = _input(
        (_point(0, pv=0.0, load=1.0, price=0.3),),
        soc=0.2,
        model=model,
        schedule=_schedule(model, ()),
    )
    tracker = _TrackingReservation()
    result = _planner(source.configuration, tracker).plan(source)

    assert tracker.calls == 1
    assert result.reservation_result is tracker.result
    assert result.reservation_result is not None
    assert result.reservation_result.allowed_grid_charge_power_kw == 3.0
    assert result.final_output is result.source_candidate_output


def test_zero_allowance_turns_current_charge_to_idle_never_discharge() -> None:
    source = _input((_point(0, pv=0.0, load=1.0, price=0.3),), soc=0.5)
    result = _planner(source.configuration).plan(source)

    assert result.reservation_result is not None
    assert result.reservation_result.allowed_grid_charge_power_kw == 0.0
    final = result.final_output.solution.steps[0]
    assert final.intent.action == "idle"
    assert final.requested_power_kw == 0.0


def test_pv_surplus_discharge_and_idle_do_not_call_reservation_or_change_output() -> (
    None
):
    cases = (
        _point(0, pv=4.0, load=1.0, price=0.1),
        _point(0, pv=0.0, load=2.0, price=0.9),
        _point(0, pv=0.0, load=2.0, price=0.5),
    )
    for current in cases:
        source = _input((current,))
        tracker = _TrackingReservation()
        result = _planner(source.configuration, tracker).plan(source)

        assert tracker.calls == 0
        assert result.reservation_result is None
        assert result.final_output is result.source_candidate_output


def test_input_rejects_value_equal_reconstructed_schedule_model() -> None:
    schedule_model = _model()
    schedule = _schedule(schedule_model)

    with pytest.raises(ValueError, match="exact battery model identity"):
        _input(
            (_point(0, pv=0.0, load=1.0, price=0.3),),
            model=_model(),
            schedule=schedule,
        )


def test_planner_requires_exact_configuration_identity() -> None:
    source = _input((_point(0, pv=0.0, load=1.0, price=0.3),))

    with pytest.raises(ValueError, match="exact configuration identity"):
        _planner(_configuration()).plan(source)


def test_schedule_aware_reservation_uses_later_opportunity_requirement() -> None:
    model = _model()
    schedule = _schedule(
        model,
        (
            _point(8, pv=3.8, load=0.0, price=None),
            _point(9, pv=0.0, load=2.0, price=None),
            _point(10, pv=4.2, load=0.0, price=None),
        ),
    )
    source = _input(
        (_point(0, pv=0.0, load=1.0, price=0.3),),
        soc=0.6,
        model=model,
        schedule=schedule,
    )
    result = _planner(source.configuration).plan(source)

    assert result.reservation_result is not None
    first = schedule.entries[0]
    standalone = first.headroom_requirement.recommended_pre_pv_max_soc_fraction
    assert first.recommended_pre_opportunity_max_soc_fraction < standalone
    assert result.reservation_result.target_soc_fraction == (
        first.recommended_pre_opportunity_max_soc_fraction
    )
    assert result.reservation_result.allowed_grid_charge_power_kw < min(
        3.0,
        (standalone - source.battery_state.soc_fraction)
        * model.usable_capacity_kwh
        / model.charge_efficiency,
    )


def test_public_api_exports_task_149_contracts() -> None:
    for name in (
        "MultiOpportunityCandidatePlanningInput",
        "MultiOpportunityCandidatePlanningResult",
        "MultiOpportunityCandidatePlanningBoundary",
        "DeterministicMultiOpportunityCandidatePlanner",
    ):
        assert name in optimization.__all__


def test_module_uses_completed_schedule_without_recomputation() -> None:
    module_path = (
        Path(optimization.__file__).parent / "multi_opportunity_candidate_planning.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "optimization.pv_headroom",
        "optimization.pv_opportunity_window",
        "optimization.multi_opportunity_headroom_schedule.DeterministicMultiOpportunityHeadroomScheduleCalculator",
        "optimization.physically_aware_baseline",
        "optimization.headroom_aware_physical_optimization",
        "ems_simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    assert "DeterministicMultiOpportunityHeadroomScheduleCalculator" not in source
