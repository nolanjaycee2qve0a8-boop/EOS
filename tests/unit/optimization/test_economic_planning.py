"""Tests for pure deterministic import-cost economic planning evidence."""

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
    DeterministicEconomicPlanningCalculator,
    EconomicPlanningBoundary,
    EconomicPlanningEvidence,
    EconomicPlanningInput,
    EconomicPlanningStepEvidence,
    EconomicShiftClassification,
)


def _model(
    *,
    charge_efficiency: float = 0.95,
    discharge_efficiency: float = 0.95,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0,
        0.2,
        1.0,
        3.0,
        3.0,
        charge_efficiency,
        discharge_efficiency,
    )


def _point(hour: int, price: float | None) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        0.0,
        1.0,
        price,
    )


def _calculate(
    prices: tuple[float | None, ...],
    *,
    charge_efficiency: float = 0.95,
    discharge_efficiency: float = 0.95,
) -> tuple[EconomicPlanningInput, EconomicPlanningEvidence]:
    points = tuple(_point(index, price) for index, price in enumerate(prices))
    planning_input = EconomicPlanningInput(
        ForecastHorizon(points),
        _model(
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
        ),
    )
    return planning_input, DeterministicEconomicPlanningCalculator().calculate(
        planning_input
    )


def test_input_evidence_and_step_are_frozen_slotted_and_preserve_identity() -> None:
    planning_input, evidence = _calculate((0.2, 0.9, 0.5))
    step = evidence.steps[0]

    assert [field.name for field in fields(EconomicPlanningInput)] == [
        "forecast_horizon",
        "battery_model",
    ]
    assert [field.name for field in fields(EconomicPlanningEvidence)] == [
        "source_input",
        "steps",
    ]
    assert [field.name for field in fields(EconomicPlanningStepEvidence)] == [
        "source_index",
        "source_forecast_point",
        "import_price_cny_per_kwh",
        "best_future_import_price_cny_per_kwh",
        "best_future_source_index",
        "best_future_forecast_point",
        "round_trip_efficiency",
        "break_even_future_import_price_cny_per_kwh",
        "gross_avoided_import_cost_per_grid_input_kwh",
        "gross_shift_margin_per_grid_input_kwh",
        "classification",
        "economically_positive_shift",
    ]
    assert planning_input.forecast_horizon is evidence.source_input.forecast_horizon
    assert planning_input.battery_model is evidence.source_input.battery_model
    assert (
        evidence.steps[0].source_forecast_point
        is planning_input.forecast_horizon.points[0]
    )
    assert step.best_future_forecast_point is planning_input.forecast_horizon.points[1]
    assert all(
        not hasattr(item, "__dict__") for item in (planning_input, evidence, step)
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, planning_input).battery_model = _model()


def test_clear_fixture_uses_round_trip_efficiency_for_gross_margin() -> None:
    _, evidence = _calculate((0.20, 0.90))
    step = evidence.steps[0]

    assert step.round_trip_efficiency == pytest.approx(0.95 * 0.95)
    assert step.gross_avoided_import_cost_per_grid_input_kwh == pytest.approx(
        0.90 * 0.95 * 0.95
    )
    assert step.gross_shift_margin_per_grid_input_kwh == pytest.approx(
        0.90 * 0.95 * 0.95 - 0.20
    )
    assert step.break_even_future_import_price_cny_per_kwh == pytest.approx(
        0.20 / (0.95 * 0.95)
    )
    assert step.classification is EconomicShiftClassification.POSITIVE
    assert step.economically_positive_shift is True


def test_same_price_is_negative_when_round_trip_efficiency_is_less_than_one() -> None:
    _, evidence = _calculate(
        (0.5, 0.5), charge_efficiency=0.9, discharge_efficiency=0.9
    )
    step = evidence.steps[0]

    assert step.gross_shift_margin_per_grid_input_kwh == pytest.approx(0.5 * 0.81 - 0.5)
    assert step.classification is EconomicShiftClassification.NEGATIVE
    assert step.economically_positive_shift is False


def test_break_even_price_is_classified_with_explicit_zero_tolerance() -> None:
    _, evidence = _calculate(
        (0.81, 1.0), charge_efficiency=0.9, discharge_efficiency=0.9
    )
    step = evidence.steps[0]

    assert step.gross_shift_margin_per_grid_input_kwh == pytest.approx(0.0)
    assert step.classification is EconomicShiftClassification.BREAK_EVEN
    assert step.economically_positive_shift is False


def test_each_efficiency_loss_reduces_margin() -> None:
    _, charge_loss = _calculate((0.2, 0.9), charge_efficiency=0.8)
    _, discharge_loss = _calculate((0.2, 0.9), discharge_efficiency=0.8)
    _, ideal = _calculate((0.2, 0.9), charge_efficiency=1.0, discharge_efficiency=1.0)

    charge_loss_margin = charge_loss.steps[0].gross_shift_margin_per_grid_input_kwh
    discharge_loss_margin = discharge_loss.steps[
        0
    ].gross_shift_margin_per_grid_input_kwh
    ideal_margin = ideal.steps[0].gross_shift_margin_per_grid_input_kwh

    assert charge_loss_margin is not None
    assert discharge_loss_margin is not None
    assert ideal_margin is not None
    assert charge_loss_margin < ideal_margin
    assert discharge_loss_margin < ideal_margin


def test_best_future_price_selects_maximum_then_earliest_equal_index() -> None:
    planning_input, evidence = _calculate((0.2, 0.8, 0.9, 0.9, 0.7))
    step = evidence.steps[0]

    assert step.best_future_import_price_cny_per_kwh == 0.9
    assert step.best_future_source_index == 2
    assert step.best_future_forecast_point is planning_input.forecast_horizon.points[2]


def test_last_point_without_future_price_is_explicitly_unavailable() -> None:
    _, evidence = _calculate((0.2, 0.9))
    step = evidence.steps[1]

    assert step.best_future_import_price_cny_per_kwh is None
    assert step.best_future_source_index is None
    assert step.best_future_forecast_point is None
    assert step.gross_shift_margin_per_grid_input_kwh is None
    assert step.classification is EconomicShiftClassification.UNAVAILABLE
    assert step.economically_positive_shift is False


def test_missing_prices_are_unavailable_or_skipped_deterministically() -> None:
    planning_input, evidence = _calculate((None, 0.2, None, 0.9))
    missing_current = evidence.steps[0]
    priced_step = evidence.steps[1]

    assert missing_current.break_even_future_import_price_cny_per_kwh is None
    assert missing_current.best_future_forecast_point is None
    assert missing_current.classification is EconomicShiftClassification.UNAVAILABLE
    assert priced_step.best_future_source_index == 3
    assert (
        priced_step.best_future_forecast_point
        is planning_input.forecast_horizon.points[3]
    )
    assert priced_step.classification is EconomicShiftClassification.POSITIVE


def test_exact_reconstructed_forecast_artifacts_are_rejected_by_evidence_contract() -> (
    None
):
    planning_input, evidence = _calculate((0.2, 0.9))
    original = evidence.steps[0]
    reconstructed_point = _point(0, 0.2)
    reconstructed_step = EconomicPlanningStepEvidence(
        original.source_index,
        reconstructed_point,
        original.import_price_cny_per_kwh,
        original.best_future_import_price_cny_per_kwh,
        original.best_future_source_index,
        original.best_future_forecast_point,
        original.round_trip_efficiency,
        original.break_even_future_import_price_cny_per_kwh,
        original.gross_avoided_import_cost_per_grid_input_kwh,
        original.gross_shift_margin_per_grid_input_kwh,
        original.classification,
        original.economically_positive_shift,
    )

    with pytest.raises(ValueError, match="exact forecast point identity"):
        EconomicPlanningEvidence(
            planning_input, (reconstructed_step, evidence.steps[1])
        )


def test_boundary_is_abstract_and_calculator_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, EconomicPlanningBoundary)()
    calculator = DeterministicEconomicPlanningCalculator()
    assert DeterministicEconomicPlanningCalculator.__slots__ == ()
    assert not hasattr(calculator, "__dict__")


@pytest.mark.parametrize("value", [nan, inf, True, "0.2"])
def test_step_rejects_invalid_numeric_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EconomicPlanningStepEvidence(
            0,
            _point(0, 0.2),
            cast(Any, value),
            None,
            None,
            None,
            0.9,
            None,
            None,
            None,
            EconomicShiftClassification.UNAVAILABLE,
            False,
        )


def test_module_has_no_soc_headroom_control_or_execution_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "economic_planning.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "enum",
        "forecast",
        "math",
        "optimization.battery_planning",
    }


def test_public_api_exports_economic_planning_contracts() -> None:
    for name in (
        "EconomicPlanningInput",
        "EconomicPlanningStepEvidence",
        "EconomicPlanningEvidence",
        "EconomicPlanningBoundary",
        "DeterministicEconomicPlanningCalculator",
        "EconomicShiftClassification",
    ):
        assert name in optimization.__all__
