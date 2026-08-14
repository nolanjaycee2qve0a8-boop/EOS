"""Tests for TASK-157 economic schedule-aware current candidate planning."""

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
    DeterministicEconomicGridChargeValueCalculator,
    DeterministicEconomicMultiOpportunityCandidatePlanner,
    DeterministicEconomicPlanningCalculator,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    EconomicGridChargeValueBoundary,
    EconomicGridChargeValueInput,
    EconomicGridChargeValueResult,
    EconomicMultiOpportunityCandidatePlanningBoundary,
    EconomicMultiOpportunityCandidatePlanningInput,
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
from optimization.economic_planning import EconomicPlanningInput
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
    horizon: ForecastHorizon,
    model: BatteryOptimizationModel,
) -> MultiOpportunityHeadroomSchedule:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    ).calculate(
        MultiOpportunityHeadroomScheduleInput(
            horizon,
            model,
            3600.0,
            PVOpportunityWindowConfiguration(0),
        )
    )


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.886,
    model: BatteryOptimizationModel | None = None,
) -> EconomicMultiOpportunityCandidatePlanningInput:
    resolved_model = model or _model()
    horizon = ForecastHorizon(points)
    problem = OptimizationProblem(
        make_context(),
        horizon,
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
    )
    evidence = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(horizon, resolved_model)
    )
    return EconomicMultiOpportunityCandidatePlanningInput(
        problem,
        _configuration(),
        BatteryOptimizationState(soc),
        resolved_model,
        _schedule(horizon, resolved_model),
        evidence,
    )


class _CountingNetLoadOptimizer(NetLoadAwareBaselineOptimizer):
    """Test-only call counter preserving the concrete candidate semantics."""

    __slots__ = ()
    calls: ClassVar[int] = 0

    def solve_with_solution(
        self, problem: OptimizationProblem
    ) -> OptimizationSolveOutput:
        type(self).calls += 1
        return super().solve_with_solution(problem)


class _TrackingReservation(MultiOpportunityGridChargeReservationBoundary):
    __slots__ = ("calls", "result")

    calls: int
    result: MultiOpportunityGridChargeReservationResult | None

    def __init__(self) -> None:
        self.calls = 0
        self.result = None

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


class _TrackingEconomicValue(EconomicGridChargeValueBoundary):
    __slots__ = ("calls", "result")

    calls: int
    result: EconomicGridChargeValueResult | None

    def __init__(self) -> None:
        self.calls = 0
        self.result = None

    def calculate(
        self,
        value_input: EconomicGridChargeValueInput,
    ) -> EconomicGridChargeValueResult:
        self.calls += 1
        self.result = DeterministicEconomicGridChargeValueCalculator().calculate(
            value_input
        )
        return self.result


def _planner(
    source: EconomicMultiOpportunityCandidatePlanningInput,
    reservation: MultiOpportunityGridChargeReservationBoundary | None = None,
    economic_value: EconomicGridChargeValueBoundary | None = None,
) -> DeterministicEconomicMultiOpportunityCandidatePlanner:
    return DeterministicEconomicMultiOpportunityCandidatePlanner(
        _CountingNetLoadOptimizer(source.configuration),
        reservation or DeterministicMultiOpportunityGridChargeReservationCalculator(),
        economic_value or DeterministicEconomicGridChargeValueCalculator(),
    )


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = _input((_point(0, pv=0.0, load=1.0, price=0.2),))

    assert [
        field.name for field in fields(EconomicMultiOpportunityCandidatePlanningInput)
    ] == [
        "problem",
        "configuration",
        "battery_state",
        "battery_model",
        "headroom_schedule",
        "economic_planning_evidence",
    ]
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).battery_state = BatteryOptimizationState(0.2)
    with pytest.raises(TypeError):
        cast(Any, EconomicMultiOpportunityCandidatePlanningBoundary)()
    assert DeterministicEconomicMultiOpportunityCandidatePlanner.__slots__ == (
        "candidate_optimizer",
        "reservation_calculator",
        "economic_value_calculator",
    )


def test_positive_economics_preserves_partial_headroom_allowance_once() -> None:
    source = _input(
        (
            _point(0, pv=0.0, load=1.0, price=0.2),
            _point(1, pv=0.0, load=1.0, price=0.9),
        )
    )
    reservation = _TrackingReservation()
    economic_value = _TrackingEconomicValue()
    _CountingNetLoadOptimizer.calls = 0

    result = _planner(source, reservation, economic_value).plan(source)

    assert _CountingNetLoadOptimizer.calls == 1
    assert reservation.calls == 1
    assert economic_value.calls == 1
    assert result.source_input is source
    assert result.reservation_result is reservation.result
    assert result.economic_value_result is economic_value.result
    assert result.reservation_result is not None
    assert result.economic_value_result is not None
    assert result.reservation_result.allowed_grid_charge_power_kw == pytest.approx(1.2)
    assert (
        result.economic_value_result.economically_supported_grid_charge_power_kw
        == pytest.approx(1.2)
    )
    assert result.final_output.solution.steps[0].intent.action == "charge"
    assert result.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        1.2
    )
    assert (
        result.final_output.solution.steps[1]
        is result.source_candidate_output.solution.steps[1]
    )


@pytest.mark.parametrize(
    ("future_price",),
    [
        (0.21,),
        (0.2 / (0.95 * 0.95),),
        (None,),
    ],
    ids=("negative", "break-even", "unavailable"),
)
def test_non_positive_or_unavailable_economics_turns_current_charge_to_idle(
    future_price: float | None,
) -> None:
    source = _input(
        (
            _point(0, pv=0.0, load=1.0, price=0.2),
            _point(1, pv=0.0, load=1.0, price=future_price),
        )
    )
    reservation = _TrackingReservation()
    economic_value = _TrackingEconomicValue()

    result = _planner(source, reservation, economic_value).plan(source)

    assert reservation.calls == 1
    assert economic_value.calls == 1
    assert result.reservation_result is reservation.result
    assert result.economic_value_result is economic_value.result
    assert result.economic_value_result is not None
    assert (
        result.economic_value_result.economically_supported_grid_charge_power_kw == 0.0
    )
    current = result.final_output.solution.steps[0]
    assert current.intent.action == "idle"
    assert current.requested_power_kw == 0.0


def test_zero_headroom_allowance_remains_zero_after_positive_economics() -> None:
    source = _input(
        (
            _point(0, pv=0.0, load=1.0, price=0.2),
            _point(1, pv=0.0, load=1.0, price=0.9),
        ),
        soc=1.0,
    )
    result = _planner(source).plan(source)

    assert result.reservation_result is not None
    assert result.economic_value_result is not None
    assert result.reservation_result.allowed_grid_charge_power_kw == 0.0
    assert (
        result.economic_value_result.economically_supported_grid_charge_power_kw == 0.0
    )
    assert result.final_output.solution.steps[0].intent.action == "idle"
    assert result.final_output.solution.steps[0].requested_power_kw == 0.0


def test_pv_surplus_discharge_and_idle_bypass_reservation_and_economics() -> None:
    cases = (
        _point(0, pv=4.0, load=1.0, price=0.2),
        _point(0, pv=0.0, load=2.0, price=0.9),
        _point(0, pv=0.0, load=2.0, price=0.5),
    )
    for current in cases:
        source = _input((current,))
        reservation = _TrackingReservation()
        economic_value = _TrackingEconomicValue()

        result = _planner(source, reservation, economic_value).plan(source)

        assert reservation.calls == 0
        assert economic_value.calls == 0
        assert result.reservation_result is None
        assert result.economic_value_result is None
        assert result.final_output is result.source_candidate_output


def test_only_current_step_changes_and_future_identity_is_preserved() -> None:
    source = _input(
        (
            _point(0, pv=0.0, load=1.0, price=0.2),
            _point(1, pv=0.0, load=1.0, price=0.9),
            _point(2, pv=0.0, load=1.0, price=0.2),
        )
    )
    result = _planner(source).plan(source)

    source_steps = result.source_candidate_output.solution.steps
    final_steps = result.final_output.solution.steps
    assert final_steps[0] is not source_steps[0]
    assert final_steps[0].timestamp is source_steps[0].timestamp
    assert final_steps[1] is source_steps[1]
    assert final_steps[2] is source_steps[2]


def test_input_rejects_reconstructed_forecast_or_battery_model_evidence() -> None:
    model = _model()
    points = (
        _point(0, pv=0.0, load=1.0, price=0.2),
        _point(1, pv=0.0, load=1.0, price=0.9),
    )
    horizon = ForecastHorizon(points)
    problem = OptimizationProblem(
        make_context(),
        horizon,
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
    )
    different_horizon = ForecastHorizon(points)
    schedule = _schedule(horizon, model)
    mismatched_evidence = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(different_horizon, model)
    )

    with pytest.raises(ValueError, match="exact problem forecast identity"):
        EconomicMultiOpportunityCandidatePlanningInput(
            problem,
            _configuration(),
            BatteryOptimizationState(0.5),
            model,
            schedule,
            mismatched_evidence,
        )

    reconstructed_model = _model()
    matching_evidence = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(horizon, model)
    )
    with pytest.raises(ValueError, match="exact battery model identity"):
        EconomicMultiOpportunityCandidatePlanningInput(
            problem,
            _configuration(),
            BatteryOptimizationState(0.5),
            reconstructed_model,
            schedule,
            matching_evidence,
        )


def test_public_api_exports_task_157_contracts() -> None:
    for name in (
        "EconomicMultiOpportunityCandidatePlanningInput",
        "EconomicMultiOpportunityCandidatePlanningResult",
        "EconomicMultiOpportunityCandidatePlanningBoundary",
        "DeterministicEconomicMultiOpportunityCandidatePlanner",
    ):
        assert name in optimization.__all__


def test_module_uses_completed_evidence_without_recomputation() -> None:
    module_path = (
        Path(optimization.__file__).parent
        / "economic_multi_opportunity_candidate_planning.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    forbidden = (
        "optimization.multi_opportunity_headroom_schedule.DeterministicMultiOpportunityHeadroomScheduleCalculator",
        "optimization.economic_planning.DeterministicEconomicPlanningCalculator",
        "optimization.physically_aware_baseline",
        "optimization.multi_opportunity_physical_optimization",
        "ems_simulator",
        "runtime",
        "device",
        "command",
    )
    assert all(name not in imported_modules for name in forbidden)
    assert "DeterministicMultiOpportunityHeadroomScheduleCalculator" not in source
    assert "DeterministicEconomicPlanningCalculator" not in source
