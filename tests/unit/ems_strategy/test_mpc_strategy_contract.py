"""Tests for the contract-only MPC strategy extension seam."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

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
from decision_formation import DecisionIntent
from ems_strategy import (
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    MPCConfiguration,
    MPCStrategyBoundary,
    MPCStrategyInput,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor


class MinimalMPCStrategy(MPCStrategyBoundary):
    """Test-only implementation proving the extension returns EMSDecision."""

    __slots__ = ()

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor(
        "mpc-test-only",
        "1.0",
    )

    def evaluate(self, strategy_input: MPCStrategyInput) -> EMSDecision:
        if not isinstance(strategy_input, MPCStrategyInput):
            raise TypeError("strategy_input must be an MPCStrategyInput")
        return EMSDecision(
            source_context=strategy_input.context,
            source_strategy=self.descriptor,
            intent=DecisionIntent("idle"),
            requested_power_kw=0.0,
        )


def make_context() -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=1.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("mpc", "Required MPC capability.")
    available = CapabilityDescriptor("mpc", "Available MPC capability.")
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
        ObjectiveDescriptor("cost", "Describe an objective without solving it."),
        active,
    )
    return EMSContext(source_context, composition, available)


def make_horizon() -> tuple[ForecastHorizon, tuple[ForecastPoint, ...]]:
    points = (
        ForecastPoint(
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            pv_power_kw=1.0,
            load_power_kw=2.0,
            electricity_price_cny_per_kwh=0.4,
        ),
        ForecastPoint(
            datetime(2026, 1, 1, 2, tzinfo=UTC),
            pv_power_kw=0.0,
            load_power_kw=3.0,
            electricity_price_cny_per_kwh=0.9,
        ),
    )
    return ForecastHorizon(points), points


def make_input() -> tuple[
    MPCStrategyInput, EMSContext, ForecastHorizon, MPCConfiguration
]:
    context = make_context()
    horizon, _ = make_horizon()
    configuration = MPCConfiguration(
        forecast_horizon_points=2,
        control_step_duration_seconds=3600.0,
    )
    return (
        MPCStrategyInput(context, horizon, configuration),
        context,
        horizon,
        configuration,
    )


def test_mpc_configuration_is_frozen_slotted_and_validated() -> None:
    configuration = MPCConfiguration(2, 3600.0)

    assert [field.name for field in fields(MPCConfiguration)] == [
        "forecast_horizon_points",
        "control_step_duration_seconds",
    ]
    assert MPCConfiguration.__slots__ == (
        "forecast_horizon_points",
        "control_step_duration_seconds",
    )
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, configuration).forecast_horizon_points = 3


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_configuration_rejects_invalid_horizon_length(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="forecast_horizon_points"):
        MPCConfiguration(cast(Any, value), 3600.0)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan"), True])
def test_configuration_rejects_invalid_control_step_duration(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="control_step_duration_seconds"):
        MPCConfiguration(2, cast(Any, value))


def test_input_preserves_exact_context_horizon_configuration_and_point_identity() -> (
    None
):
    context = make_context()
    horizon, points = make_horizon()
    configuration = MPCConfiguration(2, 3600.0)

    strategy_input = MPCStrategyInput(context, horizon, configuration)

    assert strategy_input.context is context
    assert strategy_input.forecast_horizon is horizon
    assert strategy_input.configuration is configuration
    assert strategy_input.forecast_horizon.points is points
    assert strategy_input.forecast_horizon.points[0] is points[0]
    assert not hasattr(strategy_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, strategy_input).context = context


def test_input_rejects_wrong_horizon_count_or_contract_types() -> None:
    context = make_context()
    horizon, _ = make_horizon()

    with pytest.raises(ValueError, match="point count"):
        MPCStrategyInput(context, horizon, MPCConfiguration(1, 3600.0))
    with pytest.raises(TypeError, match="context"):
        MPCStrategyInput(cast(Any, object()), horizon, MPCConfiguration(2, 3600.0))
    with pytest.raises(TypeError, match="forecast_horizon"):
        MPCStrategyInput(context, cast(Any, object()), MPCConfiguration(2, 3600.0))
    with pytest.raises(TypeError, match="configuration"):
        MPCStrategyInput(context, horizon, cast(Any, object()))


def test_boundary_is_abstract_empty_slotted_and_has_explicit_signature() -> None:
    signature = inspect.signature(MPCStrategyBoundary.evaluate)
    hints = get_type_hints(MPCStrategyBoundary.evaluate)

    assert issubclass(MPCStrategyBoundary, ABC)
    assert inspect.isabstract(MPCStrategyBoundary)
    assert MPCStrategyBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "strategy_input"]
    assert hints == {"strategy_input": MPCStrategyInput, "return": EMSDecision}
    with pytest.raises(TypeError):
        MPCStrategyBoundary()  # type: ignore[abstract]


def test_minimal_implementation_returns_decision_with_exact_provenance() -> None:
    strategy_input, context, _, _ = make_input()
    strategy = MinimalMPCStrategy()

    decision = strategy.evaluate(strategy_input)

    assert isinstance(decision, EMSDecision)
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor
    assert MinimalMPCStrategy.__slots__ == ()
    assert not hasattr(strategy, "__dict__")
    assert not hasattr(strategy, "cache")


def test_minimal_implementation_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="strategy_input"):
        MinimalMPCStrategy().evaluate(cast(Any, object()))


def test_mpc_contract_has_no_simulator_device_or_command_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "ems_strategy.context",
        "ems_strategy.decision",
        "forecast",
        "math",
    }
    assert "EMSContext" not in {field.name for field in fields(EMSContext)}


def test_public_api_exports_mpc_contracts() -> None:
    assert "MPCConfiguration" in ems_strategy.__all__
    assert "MPCStrategyBoundary" in ems_strategy.__all__
    assert "MPCStrategyInput" in ems_strategy.__all__
    assert ems_strategy.MPCConfiguration is MPCConfiguration
    assert ems_strategy.MPCStrategyBoundary is MPCStrategyBoundary
    assert ems_strategy.MPCStrategyInput is MPCStrategyInput
