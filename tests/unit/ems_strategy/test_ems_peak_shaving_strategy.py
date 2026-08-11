"""Tests for the concrete Phase 9 peak-shaving strategy."""

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
    PeakShavingConfiguration,
    PeakShavingStrategy,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_context(load_power_kw: float) -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=2.0,
        load_power_kw=load_power_kw,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("peak-shaving", "Required capability.")
    available = CapabilityDescriptor("peak-shaving", "Available capability.")
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
        ObjectiveDescriptor("demand", "Reduce peak demand."),
        active,
    )
    return EMSContext(source_context, composition, available)


def test_load_above_demand_limit_creates_discharge_request() -> None:
    decision = PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(
        make_context(5.0)
    )

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 2.0


@pytest.mark.parametrize("load_power_kw", [2.0, 3.0])
def test_load_at_or_below_demand_limit_creates_idle_request(
    load_power_kw: float,
) -> None:
    decision = PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(
        make_context(load_power_kw)
    )

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


def make_horizon(*load_powers_kw: float) -> ForecastHorizon:
    points = tuple(
        ForecastPoint(
            datetime(2026, 1, 1, index + 1, tzinfo=UTC),
            pv_power_kw=0.0,
            load_power_kw=load_power_kw,
        )
        for index, load_power_kw in enumerate(load_powers_kw)
    )
    return ForecastHorizon(points)


def test_future_load_peak_creates_discharge_request() -> None:
    decision = PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(
        make_context(2.0),
        forecast_horizon=make_horizon(2.5, 4.5),
    )

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 1.5


def test_current_load_peak_takes_precedence_over_forecast() -> None:
    decision = PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(
        make_context(5.0),
        forecast_horizon=make_horizon(8.0),
    )

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 2.0


def test_non_exceeding_forecast_keeps_idle_request() -> None:
    decision = PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(
        make_context(2.0),
        forecast_horizon=make_horizon(2.0, 3.0),
    )

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


def test_decision_preserves_exact_context_and_strategy_descriptor_identity() -> None:
    context = make_context(5.0)
    configuration = PeakShavingConfiguration(3.0)
    strategy = PeakShavingStrategy(configuration)

    decision = strategy.evaluate(context)

    assert isinstance(decision, EMSDecision)
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor
    assert strategy.configuration is configuration


def test_forecast_input_identity_is_preserved_without_strategy_retention() -> None:
    context = make_context(2.0)
    point = ForecastPoint(
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        pv_power_kw=0.0,
        load_power_kw=4.0,
    )
    points = (point,)
    horizon = ForecastHorizon(points)
    strategy = PeakShavingStrategy(PeakShavingConfiguration(3.0))

    decision = strategy.evaluate(context, forecast_horizon=horizon)

    assert horizon.points is points
    assert horizon.points[0] is point
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor
    assert not hasattr(strategy, "forecast_horizon")


def test_strategy_and_configuration_are_frozen_slotted_without_runtime_state() -> None:
    configuration = PeakShavingConfiguration(3.0)
    strategy = PeakShavingStrategy(configuration)

    assert [field.name for field in fields(PeakShavingConfiguration)] == [
        "demand_limit_kw"
    ]
    assert [field.name for field in fields(PeakShavingStrategy)] == ["configuration"]
    assert not hasattr(configuration, "__dict__")
    assert not hasattr(strategy, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).demand_limit_kw = 4.0
    with pytest.raises(FrozenInstanceError):
        cast(Any, strategy).configuration = configuration


@pytest.mark.parametrize("value", [True, "3", None])
def test_configuration_rejects_non_numeric_demand_limit(value: object) -> None:
    with pytest.raises(TypeError, match="demand_limit_kw"):
        PeakShavingConfiguration(cast(Any, value))


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("nan")])
def test_configuration_rejects_invalid_demand_limit(value: float) -> None:
    with pytest.raises(ValueError, match="demand_limit_kw"):
        PeakShavingConfiguration(value)


def test_strategy_rejects_invalid_configuration_and_context_types() -> None:
    with pytest.raises(TypeError, match="configuration"):
        PeakShavingStrategy(cast(Any, object()))
    with pytest.raises(TypeError, match="context"):
        PeakShavingStrategy(PeakShavingConfiguration(3.0)).evaluate(cast(Any, object()))


def test_strategy_has_no_simulation_or_execution_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "peak_shaving.py"
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


def test_public_api_exports_peak_shaving_strategy_contracts() -> None:
    assert "PeakShavingConfiguration" in ems_strategy.__all__
    assert "PeakShavingStrategy" in ems_strategy.__all__
    assert ems_strategy.PeakShavingConfiguration is PeakShavingConfiguration
    assert ems_strategy.PeakShavingStrategy is PeakShavingStrategy
