"""Tests for the photovoltaic self-consumption EMS capability."""

import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from capability import EMSCapabilityBoundary, SelfConsumptionCapability
from capability import self_consumption as capability_module
from kernel.decision import DecisionContext, DecisionIntent
from kernel.policy import DecisionContextPolicy, SelfConsumptionPolicy


def make_context(
    *,
    pv_power_kw: float,
    load_power_kw: float,
    soc: float = 0.5,
    battery_power_limit_kw: float = 50.0,
    grid_power_kw: float = 0.0,
    electricity_price_cny_per_kwh: float = 0.5,
    reserve_soc: float = 0.2,
    export_limit_kw: float = 10.0,
) -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=soc,
        battery_power_limit_kw=battery_power_limit_kw,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        grid_power_kw=grid_power_kw,
        electricity_price_cny_per_kwh=electricity_price_cny_per_kwh,
        reserve_soc=reserve_soc,
        export_limit_kw=export_limit_kw,
    )


def test_capability_implements_boundary_contract() -> None:
    assert issubclass(SelfConsumptionCapability, EMSCapabilityBoundary)
    assert not inspect.isabstract(SelfConsumptionCapability)
    assert get_type_hints(SelfConsumptionCapability.evaluate) == {
        "context": DecisionContext,
        "return": DecisionIntent,
    }


@pytest.mark.parametrize(
    ("pv_power_kw", "load_power_kw", "expected_intent_kw"),
    [
        (5.0, 2.0, 3.0),
        (1.0, 4.0, -3.0),
        (4.0, 4.0, 0.0),
    ],
)
def test_pv_load_balance_generates_expected_intent(
    pv_power_kw: float,
    load_power_kw: float,
    expected_intent_kw: float,
) -> None:
    intent = SelfConsumptionCapability().evaluate(
        make_context(
            pv_power_kw=pv_power_kw,
            load_power_kw=load_power_kw,
        )
    )

    assert intent.battery_power_intent_kw == expected_intent_kw


def test_capability_does_not_enforce_soc_or_battery_power_limits() -> None:
    capability = SelfConsumptionCapability()

    charge_intent = capability.evaluate(
        make_context(
            pv_power_kw=10.0,
            load_power_kw=1.0,
            soc=1.0,
            battery_power_limit_kw=0.0,
        )
    )
    discharge_intent = capability.evaluate(
        make_context(
            pv_power_kw=1.0,
            load_power_kw=10.0,
            soc=0.0,
            reserve_soc=0.0,
            battery_power_limit_kw=0.0,
        )
    )

    assert charge_intent.battery_power_intent_kw == 9.0
    assert discharge_intent.battery_power_intent_kw == -9.0


def test_grid_price_and_export_facts_do_not_change_intent() -> None:
    capability = SelfConsumptionCapability()

    first = capability.evaluate(
        make_context(
            pv_power_kw=5.0,
            load_power_kw=2.0,
            grid_power_kw=100.0,
            electricity_price_cny_per_kwh=-1.0,
            export_limit_kw=0.0,
        )
    )
    second = capability.evaluate(
        make_context(
            pv_power_kw=5.0,
            load_power_kw=2.0,
            grid_power_kw=-100.0,
            electricity_price_cny_per_kwh=10.0,
            export_limit_kw=100.0,
        )
    )

    assert first.battery_power_intent_kw == 3.0
    assert second.battery_power_intent_kw == 3.0


def test_capability_does_not_mutate_context() -> None:
    context = make_context(pv_power_kw=5.0, load_power_kw=2.0)
    values_before = tuple(getattr(context, field.name) for field in fields(context))

    SelfConsumptionCapability().evaluate(context)

    assert tuple(getattr(context, field.name) for field in fields(context)) == (
        values_before
    )


def test_invalid_context_raises_type_error() -> None:
    with pytest.raises(TypeError, match="context"):
        SelfConsumptionCapability().evaluate(cast(DecisionContext, object()))


def test_capability_is_stateless_and_slotted() -> None:
    capability = SelfConsumptionCapability()

    assert SelfConsumptionCapability.__slots__ == ()
    assert not hasattr(capability, "__dict__")
    for forbidden in (
        "parameters",
        "runtime",
        "dispatcher",
        "device",
        "commands",
        "constraint",
        "cache",
        "history",
    ):
        assert not hasattr(capability, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, capability).cache = {}


def test_capability_is_independent_from_policy_contracts() -> None:
    assert not issubclass(SelfConsumptionCapability, DecisionContextPolicy)
    assert not issubclass(DecisionContextPolicy, SelfConsumptionCapability)
    assert not issubclass(SelfConsumptionCapability, SelfConsumptionPolicy)
    assert not issubclass(SelfConsumptionPolicy, SelfConsumptionCapability)


def test_module_has_only_stable_capability_dependencies() -> None:
    source = inspect.getsource(capability_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "capability.base",
        "kernel.decision",
    }
    for forbidden in (
        "constraint",
        "runtime",
        "dispatch",
        "device",
        "pcs",
        "bms",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
        "policy",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_public_imports() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "AvailableCapabilityCollection",
        "CapabilityCompositionBoundary",
        "CapabilityDescriptor",
        "CapabilityDiscoveryBoundary",
        "CapabilityMatch",
        "CapabilityMatchCollection",
        "CapabilityMatchingBoundary",
        "DeterministicIntentResolutionImplementation",
        "DeterministicIntentResolutionParameters",
        "EMSCapabilityBoundary",
        "IntentResolutionBoundary",
        "RequiredCapabilityCollection",
        "SelfConsumptionCapability",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
