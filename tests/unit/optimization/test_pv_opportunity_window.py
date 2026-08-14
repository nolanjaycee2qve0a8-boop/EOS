"""Tests for deterministic rolling PV-surplus opportunity selection."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    DeterministicPVOpportunityWindowSelector,
    PVOpportunityWindow,
    PVOpportunityWindowConfiguration,
    PVOpportunityWindowSelectionBoundary,
    PVOpportunityWindowSelectionInput,
    PVOpportunityWindowStep,
)


def _horizon(
    *active: bool, prices: tuple[float | None, ...] | None = None
) -> ForecastHorizon:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return ForecastHorizon(
        tuple(
            ForecastPoint(
                start + timedelta(hours=index),
                2.0 if value else 1.0,
                1.0,
                None if prices is None else prices[index],
            )
            for index, value in enumerate(active)
        )
    )


def _select(
    horizon: ForecastHorizon,
    max_inactive_gap_points: int = 1,
) -> PVOpportunityWindow:
    selection_input = PVOpportunityWindowSelectionInput(
        horizon,
        PVOpportunityWindowConfiguration(max_inactive_gap_points),
    )
    return DeterministicPVOpportunityWindowSelector().select(selection_input)


def test_configuration_is_frozen_slotted_and_rejects_invalid_gap_count() -> None:
    configuration = PVOpportunityWindowConfiguration(0)

    assert configuration.max_inactive_gap_points == 0
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).max_inactive_gap_points = 1
    with pytest.raises(TypeError):
        PVOpportunityWindowConfiguration(True)
    with pytest.raises(TypeError):
        PVOpportunityWindowConfiguration(cast(Any, 1.0))
    with pytest.raises(ValueError):
        PVOpportunityWindowConfiguration(-1)


def test_selection_input_preserves_exact_forecast_and_configuration_identity() -> None:
    horizon = _horizon(False, True)
    configuration = PVOpportunityWindowConfiguration(1)
    selection_input = PVOpportunityWindowSelectionInput(horizon, configuration)

    assert selection_input.forecast_horizon is horizon
    assert selection_input.configuration is configuration
    assert not hasattr(selection_input, "__dict__")


def test_no_surplus_returns_empty_window_metadata() -> None:
    result = _select(_horizon(False, False, False))

    assert result.steps == ()
    assert result.start_index is None
    assert result.end_index_exclusive is None
    assert result.active_surplus_point_count == 0
    assert result.inactive_gap_point_count == 0


def test_first_future_surplus_starts_the_window() -> None:
    result = _select(_horizon(False, False, True, True))

    assert tuple(step.source_index for step in result.steps) == (2, 3)
    assert result.start_index == 2
    assert result.end_index_exclusive == 4


def test_current_active_point_starts_current_opportunity() -> None:
    result = _select(_horizon(True, True, False, True, False, False, True))

    assert tuple(step.source_index for step in result.steps) == (0, 1, 2, 3)
    assert result.start_index == 0
    assert result.end_index_exclusive == 4
    assert result.active_surplus_point_count == 3
    assert result.inactive_gap_point_count == 1


def test_one_point_cloud_gap_is_retained_when_surplus_resumes() -> None:
    result = _select(_horizon(False, False, True, True, False, True, True))

    assert tuple(step.source_index for step in result.steps) == (2, 3, 4, 5, 6)
    assert tuple(step.active for step in result.steps) == (
        True,
        True,
        False,
        True,
        True,
    )
    assert result.inactive_gap_point_count == 1


def test_gap_larger_than_tolerance_ends_first_window_and_discards_gap() -> None:
    result = _select(_horizon(False, True, True, False, False, True, True))

    assert tuple(step.source_index for step in result.steps) == (1, 2)
    assert result.end_index_exclusive == 3
    assert result.inactive_gap_point_count == 0


def test_trailing_unconfirmed_gap_is_discarded() -> None:
    result = _select(_horizon(True, True, False, False), max_inactive_gap_points=2)

    assert tuple(step.source_index for step in result.steps) == (0, 1)
    assert result.inactive_gap_point_count == 0


def test_zero_gap_tolerance_splits_immediately() -> None:
    result = _select(_horizon(True, False, True), max_inactive_gap_points=0)

    assert tuple(step.source_index for step in result.steps) == (0,)
    assert result.inactive_gap_point_count == 0


def test_two_clearly_separate_opportunities_selects_first_only() -> None:
    result = _select(_horizon(False, True, True, False, False, False, True, True))

    assert tuple(step.source_index for step in result.steps) == (1, 2)


def test_variable_cloud_pattern_preserves_identity_order_and_surplus_evidence() -> None:
    horizon = _horizon(False, False, True, True, False, True, True, False, False)
    result = _select(horizon)

    assert tuple(step.source_index for step in result.steps) == (2, 3, 4, 5, 6)
    assert tuple(step.forecast_point for step in result.steps) == horizon.points[2:7]
    assert all(
        step.forecast_point is horizon.points[step.source_index]
        for step in result.steps
    )
    assert tuple(step.pv_surplus_power_kw for step in result.steps) == (
        1.0,
        1.0,
        0.0,
        1.0,
        1.0,
    )
    assert [field.name for field in fields(PVOpportunityWindowStep)] == [
        "forecast_point",
        "source_index",
        "pv_surplus_power_kw",
        "active",
    ]
    assert not hasattr(result.steps[0], "__dict__")


def test_price_does_not_affect_pv_opportunity_selection() -> None:
    low_price = _horizon(False, True, False, True, prices=(0.1, 0.1, 0.1, 0.1))
    high_price = _horizon(False, True, False, True, prices=(2.0, 2.0, 2.0, 2.0))

    low_result = _select(low_price)
    high_result = _select(high_price)

    assert tuple(step.source_index for step in low_result.steps) == (1, 2, 3)
    assert tuple(step.source_index for step in high_result.steps) == (1, 2, 3)
    assert tuple(step.pv_surplus_power_kw for step in low_result.steps) == (
        1.0,
        0.0,
        1.0,
    )


def test_result_rejects_reconstructed_value_equal_forecast_point() -> None:
    horizon = _horizon(True)
    selection_input = PVOpportunityWindowSelectionInput(
        horizon,
        PVOpportunityWindowConfiguration(1),
    )
    original = horizon.points[0]
    reconstructed = ForecastPoint(
        original.timestamp,
        original.pv_power_kw,
        original.load_power_kw,
        original.electricity_price_cny_per_kwh,
    )
    step = PVOpportunityWindowStep(reconstructed, 0, 1.0, True)

    with pytest.raises(ValueError, match="exact ForecastPoint identity"):
        PVOpportunityWindow(selection_input, (step,), 0, 1, 1, 0)


def test_selection_boundary_is_abstract_and_concrete_selector_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, PVOpportunityWindowSelectionBoundary)()

    selector = DeterministicPVOpportunityWindowSelector()
    assert selector.__slots__ == ()
    assert not hasattr(selector, "__dict__")


def test_module_has_only_forecast_selection_dependencies() -> None:
    module_path = Path(optimization.__file__).parent / "pv_opportunity_window.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "dataclasses", "forecast", "math"}
    for forbidden in (
        "BatteryOptimizationState",
        "BatteryOptimizationModel",
        "DecisionIntent",
        "OptimizationSolution",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
    ):
        assert forbidden not in source


def test_public_api_exports_pv_opportunity_window_contracts() -> None:
    for name in (
        "PVOpportunityWindowConfiguration",
        "PVOpportunityWindowSelectionInput",
        "PVOpportunityWindowStep",
        "PVOpportunityWindow",
        "PVOpportunityWindowSelectionBoundary",
        "DeterministicPVOpportunityWindowSelector",
    ):
        assert name in optimization.__all__
