"""Tests for current-step-only headroom-aware net-load candidate planning."""

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
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    HeadroomAwareCandidatePlanningBoundary,
    HeadroomAwareCandidatePlanningInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    PVHeadroomRequirementInput,
)
from tests.unit.optimization.test_optimization_contracts import make_context


def point(
    hour: int,
    *,
    pv: float,
    load: float,
    price: float | None,
) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def make_planning_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    requirement_points: tuple[ForecastPoint, ...] | None = None,
    objective: OptimizationObjective | None = None,
) -> HeadroomAwareCandidatePlanningInput:
    model = BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)
    horizon = ForecastHorizon(points)
    problem = OptimizationProblem(
        make_context(),
        horizon,
        OptimizationObjectiveCollection(
            (objective or OptimizationObjective("energy_cost", "minimize"),)
        ),
    )
    headroom_horizon = ForecastHorizon(requirement_points or points)
    requirement = DeterministicPVHeadroomRequirementCalculator().calculate(
        PVHeadroomRequirementInput(headroom_horizon, model, 3600.0)
    )
    return HeadroomAwareCandidatePlanningInput(
        BatteryOptimizationInput(problem, BatteryOptimizationState(soc), model),
        requirement,
        3600.0,
    )


def make_planner() -> DeterministicHeadroomAwareCandidatePlanner:
    return DeterministicHeadroomAwareCandidatePlanner(
        NetLoadAwareBaselineOptimizer(
            NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
        ),
        DeterministicHeadroomAwareGridChargeReservationCalculator(),
    )


def target_half_requirement_points() -> tuple[ForecastPoint, ...]:
    """Yield 5 kWh stored PV headroom with 95% charge efficiency."""

    return (
        point(1, pv=3.0, load=0.0, price=None),
        point(2, pv=2.263157894736842, load=0.0, price=None),
    )


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = make_planning_input((point(1, pv=0.0, load=1.0, price=0.3),))
    assert [field.name for field in fields(HeadroomAwareCandidatePlanningInput)] == [
        "battery_input",
        "headroom_requirement",
        "control_step_duration_seconds",
    ]
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).control_step_duration_seconds = 1.0
    with pytest.raises(TypeError):
        cast(Any, HeadroomAwareCandidatePlanningBoundary)()
    assert DeterministicHeadroomAwareCandidatePlanner.__slots__ == (
        "candidate_optimizer",
        "grid_charge_reservation_calculator",
    )


def test_current_low_price_grid_charge_is_reservation_adjusted_with_provenance() -> (
    None
):
    source = make_planning_input(
        (point(1, pv=0.0, load=1.0, price=0.3),),
        soc=0.45,
        requirement_points=target_half_requirement_points(),
    )
    result = make_planner().plan(source)

    candidate = result.source_candidate_output.solution.steps[0]
    final = result.final_output.solution.steps[0]
    reservation = result.grid_charge_reservation
    assert result.source_input is source
    assert (
        result.source_candidate_output.result.source_problem
        is source.battery_input.problem
    )
    assert result.final_output.result.source_problem is source.battery_input.problem
    assert candidate.intent.action == "charge"
    assert candidate.requested_power_kw == 3.0
    assert reservation is not None
    assert reservation.source_input.battery_state is source.battery_input.battery_state
    assert reservation.source_input.battery_model is source.battery_input.battery_model
    assert reservation.source_input.headroom_requirement is source.headroom_requirement
    assert final.timestamp is candidate.timestamp
    assert final.intent is candidate.intent
    assert final.requested_power_kw == pytest.approx(0.5263157894736842)


def test_current_soc_at_target_turns_only_current_grid_charge_into_idle() -> None:
    source = make_planning_input(
        (
            point(1, pv=0.0, load=1.0, price=0.3),
            point(2, pv=0.0, load=1.0, price=0.3),
        ),
        soc=0.5,
        requirement_points=target_half_requirement_points(),
    )
    result = make_planner().plan(source)

    assert result.grid_charge_reservation is not None
    assert result.grid_charge_reservation.allowed_grid_charge_power_kw == 0.0
    assert result.final_output.solution.steps[0].intent.action == "idle"
    assert result.final_output.solution.steps[0].requested_power_kw == 0.0
    assert result.final_output.solution.steps[1].intent is (
        result.source_candidate_output.solution.steps[1].intent
    )
    assert result.final_output.solution.steps[1].requested_power_kw == 3.0


def test_pv_surplus_charge_is_never_restricted_by_grid_charge_reservation() -> None:
    source = make_planning_input(
        (point(1, pv=3.0, load=1.0, price=0.1),),
        soc=1.0,
        requirement_points=(point(1, pv=5.0, load=0.0, price=None),),
    )
    result = make_planner().plan(source)

    assert result.grid_charge_reservation is None
    candidate = result.source_candidate_output.solution.steps[0]
    final = result.final_output.solution.steps[0]
    assert candidate.intent.action == final.intent.action == "charge"
    assert candidate.requested_power_kw == final.requested_power_kw == 2.0
    assert final.intent is candidate.intent


@pytest.mark.parametrize(
    ("forecast", "action", "power"),
    [
        (point(1, pv=0.0, load=2.0, price=0.9), "discharge", 2.0),
        (point(1, pv=0.0, load=2.0, price=0.5), "idle", 0.0),
    ],
)
def test_non_grid_charge_current_candidates_remain_unchanged(
    forecast: ForecastPoint,
    action: str,
    power: float,
) -> None:
    result = make_planner().plan(make_planning_input((forecast,)))
    candidate = result.source_candidate_output.solution.steps[0]
    final = result.final_output.solution.steps[0]

    assert result.grid_charge_reservation is None
    assert candidate.intent.action == final.intent.action == action
    assert candidate.requested_power_kw == final.requested_power_kw == power
    assert final.intent is candidate.intent


def test_future_low_price_grid_charge_is_not_adjusted() -> None:
    source = make_planning_input(
        (
            point(1, pv=0.0, load=1.0, price=0.5),
            point(2, pv=0.0, load=1.0, price=0.3),
        ),
        soc=1.0,
        requirement_points=(point(1, pv=5.0, load=0.0, price=None),),
    )
    result = make_planner().plan(source)

    assert result.grid_charge_reservation is None
    candidate_future = result.source_candidate_output.solution.steps[1]
    final_future = result.final_output.solution.steps[1]
    assert candidate_future.intent.action == final_future.intent.action == "charge"
    assert candidate_future.requested_power_kw == final_future.requested_power_kw == 3.0
    assert final_future.timestamp is candidate_future.timestamp
    assert final_future.intent is candidate_future.intent


def test_unsupported_objective_remains_empty_unavailable_without_reservation() -> None:
    source = make_planning_input(
        (point(1, pv=0.0, load=1.0, price=0.3),),
        objective=OptimizationObjective("peak", "minimize"),
    )
    result = make_planner().plan(source)

    assert result.source_candidate_output.result.outcome == "unavailable"
    assert result.final_output.result.outcome == "unavailable"
    assert result.source_candidate_output.solution.steps == ()
    assert result.final_output.solution.steps == ()
    assert result.grid_charge_reservation is None


def test_input_rejects_reconstructed_model_from_headroom_requirement() -> None:
    source = make_planning_input((point(1, pv=0.0, load=1.0, price=0.3),))
    reconstructed = BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)

    with pytest.raises(ValueError, match="exact battery model identity"):
        HeadroomAwareCandidatePlanningInput(
            BatteryOptimizationInput(
                source.battery_input.problem,
                source.battery_input.battery_state,
                reconstructed,
            ),
            source.headroom_requirement,
            3600.0,
        )


def test_public_api_exports_candidate_planning_contracts() -> None:
    for name in (
        "HeadroomAwareCandidatePlanningInput",
        "HeadroomAwareCandidatePlanningResult",
        "HeadroomAwareCandidatePlanningBoundary",
        "DeterministicHeadroomAwareCandidatePlanner",
    ):
        assert name in optimization.__all__


def test_module_has_no_physical_revision_or_execution_dependencies() -> None:
    module_path = (
        Path(optimization.__file__).parent / "headroom_aware_candidate_planning.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "optimization.physically_aware_baseline",
        "optimization.battery_soc_projection",
        "optimization.battery_soc_constraint",
        "optimization.battery_power_constraint",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
