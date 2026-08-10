"""Tests for the first concrete Phase 9 EMS strategy."""

import ast
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
from ems_strategy import EMSContext, EMSDecision, SelfConsumptionStrategy
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_context(
    *,
    pv_power_kw: float,
    load_power_kw: float,
    soc: float = 0.5,
    reserve_soc: float = 0.2,
    battery_power_limit_kw: float = 3.0,
) -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=soc,
        battery_power_limit_kw=battery_power_limit_kw,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=reserve_soc,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("self-consumption", "Required capability.")
    available = CapabilityDescriptor("self-consumption", "Available capability.")
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
        ObjectiveDescriptor("self-consumption", "Use local PV energy."),
        active,
    )
    return EMSContext(source_context, composition, available)


def test_pv_surplus_produces_charge_request() -> None:
    context = make_context(pv_power_kw=5.0, load_power_kw=2.0)

    decision = SelfConsumptionStrategy().evaluate(context)

    assert decision.intent.action == "charge"
    assert decision.requested_power_kw == 3.0


def test_load_deficit_with_available_soc_produces_discharge_request() -> None:
    context = make_context(
        pv_power_kw=1.0,
        load_power_kw=4.0,
        soc=0.6,
        reserve_soc=0.2,
    )

    decision = SelfConsumptionStrategy().evaluate(context)

    assert decision.intent.action == "discharge"
    assert decision.requested_power_kw == 3.0


@pytest.mark.parametrize("soc", [0.2, 0.1])
def test_reserve_soc_prevents_discharge_request(soc: float) -> None:
    context = make_context(
        pv_power_kw=1.0,
        load_power_kw=4.0,
        soc=soc,
        reserve_soc=0.2,
    )

    decision = SelfConsumptionStrategy().evaluate(context)

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


def test_balanced_pv_and_load_produce_idle_request() -> None:
    context = make_context(pv_power_kw=2.0, load_power_kw=2.0)

    decision = SelfConsumptionStrategy().evaluate(context)

    assert decision.intent.action == "idle"
    assert decision.requested_power_kw == 0.0


def test_strategy_does_not_clip_request_to_battery_power_limit() -> None:
    context = make_context(
        pv_power_kw=5.0,
        load_power_kw=1.0,
        battery_power_limit_kw=0.5,
    )

    decision = SelfConsumptionStrategy().evaluate(context)

    assert decision.intent.action == "charge"
    assert decision.requested_power_kw == 4.0


def test_decision_preserves_context_and_strategy_descriptor_identity() -> None:
    context = make_context(pv_power_kw=5.0, load_power_kw=2.0)
    strategy = SelfConsumptionStrategy()

    decision = strategy.evaluate(context)

    assert isinstance(decision, EMSDecision)
    assert decision.source_context is context
    assert decision.source_strategy is strategy.descriptor


def test_strategy_is_stateless_and_empty_slotted() -> None:
    strategy = SelfConsumptionStrategy()

    assert SelfConsumptionStrategy.__slots__ == ()
    assert not hasattr(strategy, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, strategy).cache = object()


def test_strategy_rejects_invalid_context_type() -> None:
    with pytest.raises(TypeError, match="context"):
        SelfConsumptionStrategy().evaluate(cast(Any, object()))


def test_strategy_has_no_simulator_or_execution_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "self_consumption.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "decision_formation",
        "ems_strategy.boundary",
        "ems_strategy.context",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
        "typing",
    }


def test_public_api_exports_self_consumption_strategy() -> None:
    assert "SelfConsumptionStrategy" in ems_strategy.__all__
    assert ems_strategy.SelfConsumptionStrategy is SelfConsumptionStrategy
