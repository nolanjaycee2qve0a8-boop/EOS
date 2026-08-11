"""Tests for the concrete Phase 9 time-of-use strategy."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import ems_strategy
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_strategy import (
    EMSContext,
    EMSDecision,
    TOUStrategy,
    TOUStrategyConfiguration,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_context(price_cny_per_kwh: float) -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=2.0,
        load_power_kw=2.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=price_cny_per_kwh,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("tou", "Required capability.")
    available = CapabilityDescriptor("tou", "Available capability.")
    required_collection = RequiredCapabilityCollection((required,))
    available_collection = AvailableCapabilityCollection((available,))
    matches = CapabilityMatchCollection(
        required_collection,
        available_collection,
        (CapabilityMatch(required, available),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("cost", "Use tariff facts."),
        active,
    )
    return EMSContext(source_context, composition, available)


def make_configuration() -> TOUStrategyConfiguration:
    return TOUStrategyConfiguration(
        low_price_threshold_cny_per_kwh=0.4,
        high_price_threshold_cny_per_kwh=0.8,
        charge_request_power_kw=2.0,
        discharge_request_power_kw=3.0,
    )


def make_horizon(*prices: float | None) -> ForecastHorizon:
    points = tuple(
        ForecastPoint(
            datetime(2026, 1, 1, index + 1, tzinfo=UTC),
            pv_power_kw=0.0,
            load_power_kw=0.0,
            electricity_price_cny_per_kwh=price,
        )
        for index, price in enumerate(prices)
    )
    return ForecastHorizon(points)


def test_low_price_creates_charge_request() -> None:
    decision = TOUStrategy(make_configuration()).evaluate(make_context(0.3))

    assert decision.intent.action == "charge"
    assert decision.requested_power_kw == 2.0


def test_high_price_creates_discharge_request() -> None:
    decision = TOUStrategy(make_configuration()).evaluate(make_context(0.9))

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 3.0


@pytest.mark.parametrize("price", [0.5, 0.7])
def test_normal_price_period_creates_idle_request(price: float) -> None:
    decision = TOUStrategy(make_configuration()).evaluate(make_context(price))

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


def test_normal_price_with_future_high_tariff_requests_charge() -> None:
    decision = TOUStrategy(make_configuration()).evaluate(
        make_context(0.5),
        forecast_horizon=make_horizon(0.9),
    )

    assert decision.intent.action == "charge"
    assert decision.requested_power_kw == 2.0


def test_normal_price_with_future_low_tariff_requests_discharge() -> None:
    decision = TOUStrategy(make_configuration()).evaluate(
        make_context(0.5),
        forecast_horizon=make_horizon(0.3),
    )

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 3.0


@pytest.mark.parametrize(
    ("current_price", "forecast_price", "action"),
    [
        (0.3, 0.9, "charge"),
        (0.9, 0.3, "discharge"),
    ],
)
def test_current_price_thresholds_take_precedence_over_forecast(
    current_price: float,
    forecast_price: float,
    action: str,
) -> None:
    decision = TOUStrategy(make_configuration()).evaluate(
        make_context(current_price),
        forecast_horizon=make_horizon(forecast_price),
    )

    assert decision.intent.action == action


@pytest.mark.parametrize(
    "horizon",
    [
        make_horizon(),
        make_horizon(None),
        make_horizon(0.3, 0.9),
    ],
)
def test_normal_price_with_ambiguous_or_unavailable_forecast_stays_idle(
    horizon: ForecastHorizon,
) -> None:
    decision = TOUStrategy(make_configuration()).evaluate(
        make_context(0.5),
        forecast_horizon=horizon,
    )

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


@pytest.mark.parametrize(
    ("price", "action"),
    [(0.4, "charge"), (0.8, "discharge")],
)
def test_tariff_thresholds_are_inclusive(price: float, action: str) -> None:
    decision = TOUStrategy(make_configuration()).evaluate(make_context(price))

    assert decision.intent.action == action


def test_decision_preserves_exact_context_and_strategy_descriptor_identity() -> None:
    context = make_context(0.3)
    configuration = make_configuration()
    strategy = TOUStrategy(configuration)

    decision = strategy.evaluate(context)

    assert isinstance(decision, EMSDecision)
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor
    assert strategy.configuration is configuration


def test_forecast_input_identity_is_preserved_without_strategy_retention() -> None:
    context = make_context(0.5)
    point = ForecastPoint(
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        pv_power_kw=0.0,
        load_power_kw=0.0,
        electricity_price_cny_per_kwh=0.9,
    )
    points = (point,)
    horizon = ForecastHorizon(points)
    strategy = TOUStrategy(make_configuration())

    decision = strategy.evaluate(context, forecast_horizon=horizon)

    assert horizon.points is points
    assert horizon.points[0] is point
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor
    assert not hasattr(strategy, "forecast_horizon")


def test_strategy_and_configuration_are_frozen_slotted_without_runtime_state() -> None:
    configuration = make_configuration()
    strategy = TOUStrategy(configuration)

    assert [field.name for field in fields(TOUStrategyConfiguration)] == [
        "low_price_threshold_cny_per_kwh",
        "high_price_threshold_cny_per_kwh",
        "charge_request_power_kw",
        "discharge_request_power_kw",
    ]
    assert [field.name for field in fields(TOUStrategy)] == ["configuration"]
    assert not hasattr(configuration, "__dict__")
    assert not hasattr(strategy, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).charge_request_power_kw = 1.0
    with pytest.raises(FrozenInstanceError):
        cast(Any, strategy).configuration = make_configuration()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"low_price_threshold_cny_per_kwh": 0.8},
        {"high_price_threshold_cny_per_kwh": float("inf")},
        {"charge_request_power_kw": 0.0},
        {"discharge_request_power_kw": -1.0},
    ],
)
def test_configuration_rejects_invalid_contract_values(
    kwargs: dict[str, float],
) -> None:
    values = {
        "low_price_threshold_cny_per_kwh": 0.4,
        "high_price_threshold_cny_per_kwh": 0.8,
        "charge_request_power_kw": 2.0,
        "discharge_request_power_kw": 3.0,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        TOUStrategyConfiguration(**values)


def test_strategy_rejects_invalid_configuration_and_context_types() -> None:
    with pytest.raises(TypeError, match="configuration"):
        TOUStrategy(cast(Any, object()))
    with pytest.raises(TypeError, match="context"):
        TOUStrategy(make_configuration()).evaluate(cast(Any, object()))
    with pytest.raises(TypeError, match="forecast_horizon"):
        TOUStrategy(make_configuration()).evaluate(
            make_context(0.5),
            forecast_horizon=cast(Any, object()),
        )


def test_strategy_has_no_simulation_or_execution_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "tou.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "decision_formation",
        "ems_strategy.boundary",
        "ems_strategy.context",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
        "forecast",
        "math",
        "typing",
    }


def test_public_api_exports_tou_strategy_contracts() -> None:
    assert "TOUStrategy" in ems_strategy.__all__
    assert "TOUStrategyConfiguration" in ems_strategy.__all__
    assert ems_strategy.TOUStrategy is TOUStrategy
    assert ems_strategy.TOUStrategyConfiguration is TOUStrategyConfiguration
