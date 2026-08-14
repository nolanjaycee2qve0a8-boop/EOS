"""Tests for pure current grid-charge physical/economic value composition."""

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
    DeterministicEconomicGridChargeValueCalculator,
    DeterministicEconomicPlanningCalculator,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    EconomicGridChargeValueBoundary,
    EconomicGridChargeValueInput,
    EconomicGridChargeValueResult,
    EconomicPlanningInput,
    EconomicShiftClassification,
    MultiOpportunityGridChargeReservationInput,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleInput,
    PVOpportunityWindowConfiguration,
)


def _model() -> BatteryOptimizationModel:
    return BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95)


def _points(prices: tuple[float | None, ...]) -> tuple[ForecastPoint, ...]:
    return tuple(
        ForecastPoint(
            datetime(2026, 3, 1, tzinfo=UTC) + timedelta(hours=index),
            0.0,
            1.0,
            price,
        )
        for index, price in enumerate(prices)
    )


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


def _value_input(
    prices: tuple[float | None, ...],
    *,
    current_soc: float = 0.886,
    requested_power: float = 3.0,
    current_index: int = 0,
) -> EconomicGridChargeValueInput:
    model = _model()
    horizon = ForecastHorizon(_points(prices))
    reservation = (
        DeterministicMultiOpportunityGridChargeReservationCalculator().calculate(
            MultiOpportunityGridChargeReservationInput(
                _schedule(horizon, model),
                BatteryOptimizationState(current_soc),
                model,
                requested_power,
                3600.0,
            )
        )
    )
    economic_evidence = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(horizon, model)
    )
    return EconomicGridChargeValueInput(
        reservation,
        economic_evidence,
        current_index,
    )


def _calculate(
    value_input: EconomicGridChargeValueInput,
) -> EconomicGridChargeValueResult:
    return DeterministicEconomicGridChargeValueCalculator().calculate(value_input)


def test_input_and_result_are_frozen_slotted_and_preserve_exact_evidence() -> None:
    value_input = _value_input((0.2, 0.9))
    result = _calculate(value_input)

    assert [field.name for field in fields(EconomicGridChargeValueInput)] == [
        "reservation_result",
        "economic_planning_evidence",
        "current_source_index",
    ]
    assert [field.name for field in fields(EconomicGridChargeValueResult)] == [
        "source_input",
        "reservation_result",
        "economic_step_evidence",
        "requested_grid_charge_power_kw",
        "headroom_allowed_grid_charge_power_kw",
        "economically_supported_grid_charge_power_kw",
        "economic_classification",
        "economic_support_applied",
    ]
    assert result.source_input is value_input
    assert result.reservation_result is value_input.reservation_result
    assert (
        result.economic_step_evidence is value_input.economic_planning_evidence.steps[0]
    )
    assert (
        result.economic_step_evidence.source_forecast_point
        is (
            value_input.economic_planning_evidence.source_input.forecast_horizon.points[
                0
            ]
        )
    )
    assert (
        result.economic_step_evidence.best_future_forecast_point
        is (
            value_input.economic_planning_evidence.source_input.forecast_horizon.points[
                1
            ]
        )
    )
    assert all(not hasattr(item, "__dict__") for item in (value_input, result))
    with pytest.raises(FrozenInstanceError):
        cast(Any, value_input).current_source_index = 1


def test_positive_fixture_preserves_partial_headroom_allowance() -> None:
    result = _calculate(_value_input((0.20, 0.90)))

    assert result.economic_classification is EconomicShiftClassification.POSITIVE
    assert result.economic_step_evidence.gross_shift_margin_per_grid_input_kwh == (
        pytest.approx(0.61225)
    )
    assert result.requested_grid_charge_power_kw == 3.0
    assert result.headroom_allowed_grid_charge_power_kw == pytest.approx(1.2)
    assert result.economically_supported_grid_charge_power_kw == pytest.approx(1.2)
    assert result.economic_support_applied is False


def test_negative_margin_gates_headroom_allowance_to_zero() -> None:
    result = _calculate(_value_input((0.80, 0.85)))

    assert result.economic_classification is EconomicShiftClassification.NEGATIVE
    assert result.headroom_allowed_grid_charge_power_kw == pytest.approx(1.2)
    assert result.economically_supported_grid_charge_power_kw == 0.0
    assert result.economic_support_applied is True


def test_break_even_is_conservatively_not_economically_supported() -> None:
    result = _calculate(_value_input((0.9025, 1.0)))

    assert result.economic_classification is EconomicShiftClassification.BREAK_EVEN
    assert result.economically_supported_grid_charge_power_kw == 0.0
    assert result.economic_support_applied is True


def test_unavailable_economics_gates_power_to_zero_without_guessing() -> None:
    result = _calculate(_value_input((None, 0.9)))

    assert result.economic_classification is EconomicShiftClassification.UNAVAILABLE
    assert result.economically_supported_grid_charge_power_kw == 0.0
    assert result.economic_support_applied is True


def test_positive_economics_never_overrides_zero_headroom_allowance() -> None:
    result = _calculate(_value_input((0.2, 0.9), current_soc=1.0))

    assert result.headroom_allowed_grid_charge_power_kw == 0.0
    assert result.economic_classification is EconomicShiftClassification.POSITIVE
    assert result.economically_supported_grid_charge_power_kw == 0.0
    assert result.economic_support_applied is False


def test_positive_economics_cannot_create_power_for_zero_request() -> None:
    result = _calculate(_value_input((0.2, 0.9), requested_power=0.0))

    assert result.requested_grid_charge_power_kw == 0.0
    assert result.headroom_allowed_grid_charge_power_kw == 0.0
    assert result.economically_supported_grid_charge_power_kw == 0.0


def test_input_rejects_forecast_reconstruction_even_when_values_match() -> None:
    model = _model()
    reservation_horizon = ForecastHorizon(_points((0.2, 0.9)))
    reservation = (
        DeterministicMultiOpportunityGridChargeReservationCalculator().calculate(
            MultiOpportunityGridChargeReservationInput(
                _schedule(reservation_horizon, model),
                BatteryOptimizationState(0.886),
                model,
                3.0,
                3600.0,
            )
        )
    )
    reconstructed_horizon = ForecastHorizon(_points((0.2, 0.9)))
    economic = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(reconstructed_horizon, model)
    )

    with pytest.raises(ValueError, match="exact forecast identity"):
        EconomicGridChargeValueInput(reservation, economic, 0)


def test_input_rejects_battery_model_reconstruction_even_when_values_match() -> None:
    reservation_model = _model()
    horizon = ForecastHorizon(_points((0.2, 0.9)))
    reservation = (
        DeterministicMultiOpportunityGridChargeReservationCalculator().calculate(
            MultiOpportunityGridChargeReservationInput(
                _schedule(horizon, reservation_model),
                BatteryOptimizationState(0.886),
                reservation_model,
                3.0,
                3600.0,
            )
        )
    )
    economic = DeterministicEconomicPlanningCalculator().calculate(
        EconomicPlanningInput(horizon, _model())
    )

    with pytest.raises(ValueError, match="exact battery model identity"):
        EconomicGridChargeValueInput(reservation, economic, 0)


def test_boundary_is_abstract_and_calculator_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, EconomicGridChargeValueBoundary)()
    calculator = DeterministicEconomicGridChargeValueCalculator()
    assert DeterministicEconomicGridChargeValueCalculator.__slots__ == ()
    assert not hasattr(calculator, "__dict__")


def test_module_has_no_recomputation_or_control_imports() -> None:
    module_path = Path(optimization.__file__).parent / "economic_grid_charge_value.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "DeterministicEconomicPlanningCalculator" not in imported_names
    assert (
        "DeterministicMultiOpportunityGridChargeReservationCalculator"
        not in imported_names
    )
    assert imported_names.isdisjoint(
        {
            "MultiOpportunityCandidatePlanner",
            "NetLoadAwareBaselineOptimizer",
            "DecisionIntent",
            "EMSDecision",
            "BatterySimulationActuation",
        }
    )


def test_public_api_exports_economic_grid_charge_value_contracts() -> None:
    for name in (
        "EconomicGridChargeValueInput",
        "EconomicGridChargeValueResult",
        "EconomicGridChargeValueBoundary",
        "DeterministicEconomicGridChargeValueCalculator",
    ):
        assert name in optimization.__all__
