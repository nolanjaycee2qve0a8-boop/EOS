"""Tests for the concrete time-of-use EMS capability."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from math import inf, nan
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    EMSCapabilityBoundary,
    TOUCapabilityParameters,
    TOUEnergyCapability,
)
from capability import tou as tou_module
from kernel.decision import DecisionContext, DecisionIntent
from kernel.policy import DecisionContextPolicy


def make_context(
    *,
    hour: int,
    electricity_price_cny_per_kwh: float,
) -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, hour=hour, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=25.0,
        load_power_kw=20.0,
        grid_power_kw=-5.0,
        electricity_price_cny_per_kwh=electricity_price_cny_per_kwh,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


def make_parameters() -> TOUCapabilityParameters:
    return TOUCapabilityParameters(
        charge_hours=(0, 1, 2, 3, 4, 5),
        discharge_hours=(17, 18, 19, 20),
        charge_price_ceiling_cny_per_kwh=0.4,
        discharge_price_floor_cny_per_kwh=0.8,
        charge_power_intent_kw=6.0,
        discharge_power_intent_kw=8.0,
    )


def test_tou_capability_implements_boundary_contract() -> None:
    assert issubclass(TOUEnergyCapability, EMSCapabilityBoundary)
    assert not inspect.isabstract(TOUEnergyCapability)
    assert get_type_hints(TOUEnergyCapability.evaluate) == {
        "context": DecisionContext,
        "return": DecisionIntent,
    }


def test_low_price_charge_hour_generates_charging_intent() -> None:
    intent = TOUEnergyCapability(make_parameters()).evaluate(
        make_context(hour=2, electricity_price_cny_per_kwh=0.3)
    )

    assert intent.battery_power_intent_kw == 6.0


def test_charge_price_ceiling_is_inclusive() -> None:
    intent = TOUEnergyCapability(make_parameters()).evaluate(
        make_context(hour=2, electricity_price_cny_per_kwh=0.4)
    )

    assert intent.battery_power_intent_kw == 6.0


def test_high_price_discharge_hour_generates_discharging_intent() -> None:
    intent = TOUEnergyCapability(make_parameters()).evaluate(
        make_context(hour=18, electricity_price_cny_per_kwh=1.0)
    )

    assert intent.battery_power_intent_kw == -8.0


def test_discharge_price_floor_is_inclusive() -> None:
    intent = TOUEnergyCapability(make_parameters()).evaluate(
        make_context(hour=18, electricity_price_cny_per_kwh=0.8)
    )

    assert intent.battery_power_intent_kw == -8.0


@pytest.mark.parametrize(
    ("hour", "price"),
    [
        (2, 0.5),
        (18, 0.7),
        (12, 0.2),
        (12, 1.2),
    ],
)
def test_unmatched_time_or_price_generates_idle_intent(
    hour: int,
    price: float,
) -> None:
    intent = TOUEnergyCapability(make_parameters()).evaluate(
        make_context(hour=hour, electricity_price_cny_per_kwh=price)
    )

    assert intent.battery_power_intent_kw == 0.0


def test_capability_preserves_parameter_identity_and_context() -> None:
    parameters = make_parameters()
    capability = TOUEnergyCapability(parameters)
    context = make_context(hour=2, electricity_price_cny_per_kwh=0.3)
    before = (
        context.timestamp,
        context.electricity_price_cny_per_kwh,
        context.soc,
    )

    capability.evaluate(context)

    assert capability.parameters is parameters
    assert (
        context.timestamp,
        context.electricity_price_cny_per_kwh,
        context.soc,
    ) == before


def test_capability_and_parameters_are_frozen_and_slotted() -> None:
    parameters = make_parameters()
    capability = TOUEnergyCapability(parameters)

    assert tuple(field.name for field in fields(TOUCapabilityParameters)) == (
        "charge_hours",
        "discharge_hours",
        "charge_price_ceiling_cny_per_kwh",
        "discharge_price_floor_cny_per_kwh",
        "charge_power_intent_kw",
        "discharge_power_intent_kw",
    )
    assert tuple(field.name for field in fields(TOUEnergyCapability)) == ("parameters",)
    assert not hasattr(parameters, "__dict__")
    assert not hasattr(capability, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, parameters).charge_hours = (6,)
    with pytest.raises(FrozenInstanceError):
        cast(Any, capability).parameters = make_parameters()


@pytest.mark.parametrize("field_name", ["charge_hours", "discharge_hours"])
def test_hour_fields_require_tuples(field_name: str) -> None:
    values: dict[str, object] = {
        "charge_hours": (0,),
        "discharge_hours": (18,),
    }
    values[field_name] = [0]

    with pytest.raises(TypeError, match=field_name):
        TOUCapabilityParameters(
            charge_hours=cast(tuple[int, ...], values["charge_hours"]),
            discharge_hours=cast(tuple[int, ...], values["discharge_hours"]),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )


@pytest.mark.parametrize("invalid_hour", [-1, 24])
def test_hours_must_be_between_zero_and_twenty_three(
    invalid_hour: int,
) -> None:
    with pytest.raises(ValueError, match="charge_hours"):
        TOUCapabilityParameters(
            charge_hours=(invalid_hour,),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )


def test_hours_reject_bool_and_duplicate_values() -> None:
    with pytest.raises(TypeError, match="charge_hours"):
        TOUCapabilityParameters(
            charge_hours=cast(tuple[int, ...], (True,)),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )
    with pytest.raises(ValueError, match="discharge_hours"):
        TOUCapabilityParameters(
            charge_hours=(2,),
            discharge_hours=(18, 18),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )


def test_charge_and_discharge_hours_must_not_overlap() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        TOUCapabilityParameters(
            charge_hours=(2, 3),
            discharge_hours=(3, 18),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "charge_price_ceiling_cny_per_kwh",
        "discharge_price_floor_cny_per_kwh",
        "charge_power_intent_kw",
        "discharge_power_intent_kw",
    ],
)
@pytest.mark.parametrize("invalid_value", [True, "1"])
def test_numeric_fields_reject_non_numeric_values(
    field_name: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "charge_price_ceiling_cny_per_kwh": 0.4,
        "discharge_price_floor_cny_per_kwh": 0.8,
        "charge_power_intent_kw": 6.0,
        "discharge_power_intent_kw": 8.0,
    }
    values[field_name] = invalid_value

    with pytest.raises(TypeError, match=field_name):
        TOUCapabilityParameters(
            charge_hours=(2,),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=cast(
                float,
                values["charge_price_ceiling_cny_per_kwh"],
            ),
            discharge_price_floor_cny_per_kwh=cast(
                float,
                values["discharge_price_floor_cny_per_kwh"],
            ),
            charge_power_intent_kw=cast(float, values["charge_power_intent_kw"]),
            discharge_power_intent_kw=cast(
                float,
                values["discharge_power_intent_kw"],
            ),
        )


@pytest.mark.parametrize("invalid_value", [nan, inf, -inf])
def test_numeric_fields_reject_non_finite_values(invalid_value: float) -> None:
    with pytest.raises(ValueError, match="charge_price_ceiling_cny_per_kwh"):
        TOUCapabilityParameters(
            charge_hours=(2,),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=invalid_value,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=6.0,
            discharge_power_intent_kw=8.0,
        )


@pytest.mark.parametrize(
    "field_name",
    ["charge_power_intent_kw", "discharge_power_intent_kw"],
)
def test_power_intent_magnitudes_must_be_non_negative(field_name: str) -> None:
    values = {
        "charge_power_intent_kw": 6.0,
        "discharge_power_intent_kw": 8.0,
    }
    values[field_name] = -1.0

    with pytest.raises(ValueError, match=field_name):
        TOUCapabilityParameters(
            charge_hours=(2,),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=0.4,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=values["charge_power_intent_kw"],
            discharge_power_intent_kw=values["discharge_power_intent_kw"],
        )


def test_invalid_parameters_and_context_raise_type_error() -> None:
    with pytest.raises(TypeError, match="parameters"):
        TOUEnergyCapability(cast(TOUCapabilityParameters, object()))
    with pytest.raises(TypeError, match="context"):
        TOUEnergyCapability(make_parameters()).evaluate(cast(DecisionContext, object()))


def test_tou_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(tou_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "capability.base",
        "dataclasses",
        "kernel.decision",
        "math",
    }
    for forbidden in (
        "constraint",
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_policy_and_existing_contracts_remain_independent() -> None:
    assert not issubclass(TOUEnergyCapability, DecisionContextPolicy)
    assert not issubclass(DecisionContextPolicy, TOUEnergyCapability)


def test_public_imports() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "EMSCapabilityBoundary",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
