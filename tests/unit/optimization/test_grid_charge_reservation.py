"""Tests for deterministic headroom-aware cheap-grid-charge allowance evidence."""

import ast
from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    HeadroomAwareGridChargeReservation,
    HeadroomAwareGridChargeReservationBoundary,
    HeadroomAwareGridChargeReservationInput,
    PVHeadroomRequirement,
    PVHeadroomRequirementInput,
)
from tests.unit.optimization.test_pv_headroom import point


def make_model(
    *,
    minimum: float = 0.2,
    maximum: float = 1.0,
    charge_power: float = 3.0,
    efficiency: float = 0.95,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0, minimum, maximum, charge_power, 3.0, efficiency, 0.95
    )


def make_requirement(
    model: BatteryOptimizationModel,
    *,
    desired_target_soc: float = 0.5,
) -> PVHeadroomRequirement:
    """Create real TASK-132 evidence yielding a requested target SOC."""

    stored_energy = (
        model.max_soc_fraction - desired_target_soc
    ) * model.usable_capacity_kwh
    input_energy = stored_energy / model.charge_efficiency
    powers: list[float] = []
    remaining_input_energy = input_energy
    while remaining_input_energy > 0:
        power = min(remaining_input_energy, model.max_charge_power_kw)
        powers.append(power)
        remaining_input_energy -= power
    points = tuple(point(index + 1, power, 0.0) for index, power in enumerate(powers))
    requirement = DeterministicPVHeadroomRequirementCalculator().calculate(
        PVHeadroomRequirementInput(ForecastHorizon(points), model, 3600.0)
    )
    return requirement


def make_input(
    *,
    current_soc: float = 0.45,
    target_soc: float = 0.5,
    requested: float = 3.0,
    duration: float = 3600.0,
    model: BatteryOptimizationModel | None = None,
) -> HeadroomAwareGridChargeReservationInput:
    supplied_model = model or make_model()
    requirement = make_requirement(supplied_model, desired_target_soc=target_soc)
    return HeadroomAwareGridChargeReservationInput(
        BatteryOptimizationState(current_soc),
        supplied_model,
        requirement,
        requested,
        duration,
    )


def test_input_is_frozen_slotted_and_preserves_exact_requirement_identity() -> None:
    source = make_input()

    assert [
        field.name for field in fields(HeadroomAwareGridChargeReservationInput)
    ] == [
        "battery_state",
        "battery_model",
        "headroom_requirement",
        "requested_grid_charge_power_kw",
        "control_step_duration_seconds",
    ]
    assert (
        source.battery_model is source.headroom_requirement.source_input.battery_model
    )
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).requested_grid_charge_power_kw = 1.0


@pytest.mark.parametrize("requested", [0.0, -1.0, nan, inf, True])
def test_input_rejects_invalid_requested_grid_charge(requested: object) -> None:
    with pytest.raises((TypeError, ValueError), match="requested_grid_charge_power_kw"):
        make_input(requested=cast(Any, requested))


@pytest.mark.parametrize("duration", [0.0, -1.0, nan, inf, True])
def test_input_rejects_invalid_duration(duration: object) -> None:
    with pytest.raises((TypeError, ValueError), match="control_step_duration_seconds"):
        make_input(duration=cast(Any, duration))


def test_input_rejects_value_equal_reconstructed_battery_model() -> None:
    model = make_model()
    requirement = make_requirement(model)
    reconstructed = make_model()

    with pytest.raises(ValueError, match="exact headroom requirement model identity"):
        HeadroomAwareGridChargeReservationInput(
            BatteryOptimizationState(0.45), reconstructed, requirement, 3.0, 3600.0
        )


def test_target_above_current_calculates_efficiency_aware_soc_allowance() -> None:
    source = make_input(current_soc=0.45, target_soc=0.5, requested=3.0)
    result = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        source
    )

    assert isinstance(result, HeadroomAwareGridChargeReservation)
    assert result.source_input is source
    assert result.source_input.headroom_requirement is source.headroom_requirement
    assert result.target_soc_fraction == pytest.approx(0.5)
    assert result.current_soc_fraction == pytest.approx(0.45)
    assert result.available_soc_charge_fraction == pytest.approx(0.05)
    assert result.available_stored_energy_kwh == pytest.approx(0.5)
    assert result.available_input_energy_kwh == pytest.approx(0.5 / 0.95)
    assert result.soc_limited_charge_power_kw == pytest.approx(0.5 / 0.95)
    assert result.allowed_grid_charge_power_kw == pytest.approx(0.5 / 0.95)
    assert result.reservation_applied is True


@pytest.mark.parametrize("current_soc", [0.5, 0.7])
def test_current_soc_at_or_above_target_allows_no_grid_charge(
    current_soc: float,
) -> None:
    result = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        make_input(current_soc=current_soc, target_soc=0.5)
    )

    assert result.available_soc_charge_fraction == 0.0
    assert result.allowed_grid_charge_power_kw == 0.0
    assert result.reservation_applied is True


def test_requested_power_is_preserved_when_smaller_than_allowance() -> None:
    result = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        make_input(current_soc=0.2, target_soc=0.9, requested=2.0)
    )

    assert result.allowed_grid_charge_power_kw == 2.0
    assert result.reservation_applied is False


def test_battery_max_charge_power_caps_allowance() -> None:
    result = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        make_input(current_soc=0.2, target_soc=0.9, requested=5.0)
    )

    assert result.soc_limited_charge_power_kw > 3.0
    assert result.allowed_grid_charge_power_kw == 3.0
    assert result.reservation_applied is True


def test_non_one_hour_duration_changes_power_but_not_input_energy_room() -> None:
    hourly = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        make_input(current_soc=0.45, target_soc=0.5, duration=3600.0)
    )
    half_hour = DeterministicHeadroomAwareGridChargeReservationCalculator().calculate(
        make_input(current_soc=0.45, target_soc=0.5, duration=1800.0)
    )

    assert half_hour.available_input_energy_kwh == hourly.available_input_energy_kwh
    assert half_hour.soc_limited_charge_power_kw == pytest.approx(
        hourly.soc_limited_charge_power_kw * 2.0
    )


def test_boundary_is_abstract_and_calculator_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, HeadroomAwareGridChargeReservationBoundary)()
    calculator = DeterministicHeadroomAwareGridChargeReservationCalculator()
    assert DeterministicHeadroomAwareGridChargeReservationCalculator.__slots__ == ()
    assert not hasattr(calculator, "__dict__")


def test_module_has_no_price_forecast_decision_or_simulator_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "grid_charge_reservation.py"
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
        "optimization.pv_headroom",
    }
    for forbidden in (
        "ForecastHorizon",
        "ForecastPoint",
        "electricity_price_cny_per_kwh",
        "DecisionIntent",
        "OptimizationSolution",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
    ):
        assert forbidden not in source


def test_public_api_exports_grid_charge_reservation_contracts() -> None:
    assert "HeadroomAwareGridChargeReservationInput" in optimization.__all__
    assert "HeadroomAwareGridChargeReservation" in optimization.__all__
    assert "HeadroomAwareGridChargeReservationBoundary" in optimization.__all__
    assert (
        "DeterministicHeadroomAwareGridChargeReservationCalculator"
        in optimization.__all__
    )
