"""Tests for schedule-aware current cheap-grid-charge reservation evidence."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    MultiOpportunityGridChargeReservationBoundary,
    MultiOpportunityGridChargeReservationInput,
    MultiOpportunityGridChargeReservationResult,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleInput,
    PVOpportunityWindowConfiguration,
)


def _point(hour: int, pv: float, load: float) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 2, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
    )


def _model(*, max_charge_power: float = 3.0) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0,
        0.2,
        1.0,
        max_charge_power,
        3.0,
        0.95,
        0.95,
    )


def _schedule(
    points: tuple[ForecastPoint, ...],
    model: BatteryOptimizationModel,
    *,
    gap: int = 0,
) -> MultiOpportunityHeadroomSchedule:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    ).calculate(
        MultiOpportunityHeadroomScheduleInput(
            ForecastHorizon(points),
            model,
            3600.0,
            PVOpportunityWindowConfiguration(gap),
        )
    )


def _half_target_schedule(
    model: BatteryOptimizationModel,
) -> MultiOpportunityHeadroomSchedule:
    """Return TASK-132 evidence for 5.0 stored kWh / a 50% max-SOC target."""

    return _schedule(
        (
            _point(0, 3.0, 0.0),
            _point(1, 2.263157894736842, 0.0),
        ),
        model,
    )


def _input(
    schedule: MultiOpportunityHeadroomSchedule,
    model: BatteryOptimizationModel,
    *,
    current_soc: float = 0.2,
    requested: float = 3.0,
    duration: float = 3600.0,
) -> MultiOpportunityGridChargeReservationInput:
    return MultiOpportunityGridChargeReservationInput(
        schedule,
        BatteryOptimizationState(current_soc),
        model,
        requested,
        duration,
    )


def _calculate(
    reservation_input: MultiOpportunityGridChargeReservationInput,
) -> MultiOpportunityGridChargeReservationResult:
    return DeterministicMultiOpportunityGridChargeReservationCalculator().calculate(
        reservation_input
    )


def test_input_is_frozen_slotted_and_preserves_exact_schedule_identity() -> None:
    model = _model()
    schedule = _schedule((_point(0, 3.0, 0.0),), model)
    reservation_input = _input(schedule, model)

    assert [
        field.name for field in fields(MultiOpportunityGridChargeReservationInput)
    ] == [
        "headroom_schedule",
        "battery_state",
        "battery_model",
        "requested_grid_charge_power_kw",
        "duration_seconds",
    ]
    assert reservation_input.headroom_schedule is schedule
    assert reservation_input.battery_model is model
    assert not hasattr(reservation_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, reservation_input).duration_seconds = 1800.0


@pytest.mark.parametrize("requested", [-1.0, nan, inf, True])
def test_input_rejects_invalid_requested_power(requested: object) -> None:
    model = _model()
    schedule = _schedule((), model)

    with pytest.raises((TypeError, ValueError), match="requested_grid_charge_power_kw"):
        _input(schedule, model, requested=cast(Any, requested))


@pytest.mark.parametrize("duration", [0.0, -1.0, nan, inf, True])
def test_input_rejects_invalid_duration(duration: object) -> None:
    model = _model()
    schedule = _schedule((), model)

    with pytest.raises((TypeError, ValueError), match="duration_seconds"):
        _input(schedule, model, duration=cast(Any, duration))


def test_input_rejects_value_equal_reconstructed_battery_model() -> None:
    schedule_model = _model()
    schedule = _schedule((_point(0, 3.0, 0.0),), schedule_model)

    with pytest.raises(ValueError, match="exact headroom schedule model identity"):
        _input(schedule, _model())


def test_empty_schedule_uses_model_max_soc_and_preserves_none_selection() -> None:
    model = _model()
    result = _calculate(
        _input(_schedule((), model), model, current_soc=0.5, requested=5.0)
    )

    assert result.selected_schedule_entry is None
    assert result.target_soc_fraction == 1.0
    assert result.target_stored_energy_kwh == 10.0
    assert result.available_stored_energy_room_kwh == 5.0
    assert result.allowed_grid_charge_power_kw == 3.0
    assert result.reservation_applied is True


def test_non_empty_schedule_selects_exact_first_entry_and_preserves_provenance() -> (
    None
):
    model = _model()
    schedule = _schedule(
        (_point(0, 3.0, 0.0), _point(1, 0.0, 1.0), _point(2, 4.0, 0.0)),
        model,
    )
    source = _input(schedule, model, current_soc=0.2)
    result = _calculate(source)

    assert result.source_input is source
    assert result.selected_schedule_entry is schedule.entries[0]
    assert (
        result.selected_schedule_entry.opportunity
        is (schedule.opportunity_sequence.entries[0])
    )
    assert result.selected_schedule_entry.headroom_requirement is (
        schedule.entries[0].headroom_requirement
    )
    assert result.target_soc_fraction == (
        schedule.entries[0].recommended_pre_opportunity_max_soc_fraction
    )


def test_soc_limited_allowance_uses_charge_efficiency_in_input_energy_direction() -> (
    None
):
    model = _model()
    schedule = _half_target_schedule(model)
    # TASK-132 target is 0.5; at 0.45 SOC, 0.5 stored kWh needs 0.5 / 0.95 input.
    result = _calculate(_input(schedule, model, current_soc=0.45, requested=3.0))

    assert result.target_soc_fraction == pytest.approx(0.5)
    assert result.available_soc_charge_fraction == pytest.approx(0.05)
    assert result.available_stored_energy_room_kwh == pytest.approx(0.5)
    assert result.required_input_energy_kwh == pytest.approx(0.5 / 0.95)
    assert result.soc_limited_charge_power_kw == pytest.approx(0.5 / 0.95)
    assert result.allowed_grid_charge_power_kw == pytest.approx(0.5 / 0.95)


@pytest.mark.parametrize("current_soc", [0.5, 0.7])
def test_current_soc_at_or_above_target_allows_zero_charge(current_soc: float) -> None:
    model = _model()
    schedule = _half_target_schedule(model)
    result = _calculate(_input(schedule, model, current_soc=current_soc))

    assert result.available_soc_charge_fraction == 0.0
    assert result.allowed_grid_charge_power_kw == 0.0
    assert result.reservation_applied is True


def test_requested_power_below_all_limits_is_preserved() -> None:
    model = _model()
    result = _calculate(
        _input(_schedule((), model), model, current_soc=0.2, requested=2.0)
    )

    assert result.allowed_grid_charge_power_kw == 2.0
    assert result.reservation_applied is False


def test_model_max_charge_power_caps_allowance() -> None:
    model = _model(max_charge_power=2.0)
    result = _calculate(
        _input(_schedule((), model), model, current_soc=0.2, requested=5.0)
    )

    assert result.model_max_charge_power_kw == 2.0
    assert result.allowed_grid_charge_power_kw == 2.0
    assert result.reservation_applied is True


def test_duration_changes_soc_limited_power_but_not_required_input_energy() -> None:
    model = _model()
    schedule = _half_target_schedule(model)
    hourly = _calculate(_input(schedule, model, current_soc=0.45, duration=3600.0))
    half_hour = _calculate(_input(schedule, model, current_soc=0.45, duration=1800.0))

    assert half_hour.required_input_energy_kwh == hourly.required_input_energy_kwh
    assert half_hour.soc_limited_charge_power_kw == pytest.approx(
        hourly.soc_limited_charge_power_kw * 2.0
    )


def test_two_opportunity_schedule_is_stricter_than_first_only_target() -> None:
    model = _model()
    schedule = _schedule(
        (
            _point(8, 3.8, 0.0),
            _point(9, 0.0, 2.0),
            _point(10, 4.2, 0.0),
        ),
        model,
    )
    first = schedule.entries[0]
    result = _calculate(_input(schedule, model, current_soc=0.6, requested=3.0))
    standalone_target = first.headroom_requirement.recommended_pre_pv_max_soc_fraction
    standalone_allowed = min(
        3.0,
        model.max_charge_power_kw,
        (standalone_target - 0.6) * model.usable_capacity_kwh / model.charge_efficiency,
    )

    assert first.recommended_pre_opportunity_max_soc_fraction < standalone_target
    assert (
        result.target_soc_fraction == first.recommended_pre_opportunity_max_soc_fraction
    )
    assert result.allowed_grid_charge_power_kw < standalone_allowed


def test_boundary_is_abstract_and_calculator_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, MultiOpportunityGridChargeReservationBoundary)()
    calculator = DeterministicMultiOpportunityGridChargeReservationCalculator()
    assert DeterministicMultiOpportunityGridChargeReservationCalculator.__slots__ == ()
    assert not hasattr(calculator, "__dict__")


def test_module_reads_schedule_without_recomputation_or_execution() -> None:
    module_path = (
        Path(optimization.__file__).parent
        / "multi_opportunity_grid_charge_reservation.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "math",
        "optimization.battery_planning",
        "optimization.multi_opportunity_headroom_schedule",
    }
    for forbidden in (
        "ForecastHorizon",
        "ForecastPoint",
        "PVHeadroomRequirementInput",
        "DeterministicPVHeadroomRequirementCalculator",
        "DeterministicMultiOpportunityHeadroomScheduleCalculator",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "DecisionIntent",
    ):
        assert forbidden not in source


def test_public_api_exports_schedule_aware_reservation_contracts() -> None:
    for name in (
        "MultiOpportunityGridChargeReservationInput",
        "MultiOpportunityGridChargeReservationResult",
        "MultiOpportunityGridChargeReservationBoundary",
        "DeterministicMultiOpportunityGridChargeReservationCalculator",
    ):
        assert name in optimization.__all__
