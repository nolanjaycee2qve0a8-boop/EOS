"""Tests for the basic photovoltaic self-consumption policy."""

import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from kernel.decision import (
    DecisionContext,
    DecisionContextResult,
    DecisionIntent,
)
from kernel.policy import (
    DecisionContextPolicyImplementation,
    SelfConsumptionPolicy,
)
from kernel.policy import self_consumption as policy_module


def make_context(
    *,
    pv_power_kw: float,
    load_power_kw: float,
    soc: float = 0.5,
    battery_power_limit_kw: float = 50.0,
    grid_power_kw: float = 0.0,
    electricity_price_cny_per_kwh: float = 0.5,
    reserve_soc: float = 0.2,
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
        export_limit_kw=10.0,
    )


def test_policy_inherits_implementation_boundary() -> None:
    assert issubclass(
        SelfConsumptionPolicy,
        DecisionContextPolicyImplementation,
    )


def test_evaluate_signature_preserves_policy_contract() -> None:
    parameters = list(inspect.signature(SelfConsumptionPolicy.evaluate).parameters)
    hints = get_type_hints(SelfConsumptionPolicy.evaluate)

    assert parameters == ["self", "context"]
    assert hints == {
        "context": DecisionContext,
        "return": DecisionContextResult,
    }


def test_surplus_pv_creates_charging_intent() -> None:
    result = SelfConsumptionPolicy().evaluate(
        make_context(pv_power_kw=5.0, load_power_kw=2.0)
    )

    assert result.intent.battery_power_intent_kw == 3.0


def test_load_deficit_creates_discharging_intent() -> None:
    result = SelfConsumptionPolicy().evaluate(
        make_context(pv_power_kw=1.0, load_power_kw=4.0)
    )

    assert result.intent.battery_power_intent_kw == -3.0


def test_balanced_pv_and_load_create_idle_intent() -> None:
    result = SelfConsumptionPolicy().evaluate(
        make_context(pv_power_kw=4.0, load_power_kw=4.0)
    )

    assert result.intent.battery_power_intent_kw == 0.0


def test_policy_does_not_enforce_charge_power_or_upper_soc() -> None:
    result = SelfConsumptionPolicy().evaluate(
        make_context(
            pv_power_kw=10.0,
            load_power_kw=1.0,
            soc=1.0,
            battery_power_limit_kw=0.0,
        )
    )

    assert result.intent.battery_power_intent_kw == 9.0


def test_policy_does_not_enforce_discharge_power_or_reserve_soc() -> None:
    result = SelfConsumptionPolicy().evaluate(
        make_context(
            pv_power_kw=1.0,
            load_power_kw=10.0,
            soc=0.0,
            battery_power_limit_kw=0.0,
            reserve_soc=0.0,
        )
    )

    assert result.intent.battery_power_intent_kw == -9.0


def test_grid_and_price_do_not_change_basic_self_consumption_intent() -> None:
    policy = SelfConsumptionPolicy()
    first = policy.evaluate(
        make_context(
            pv_power_kw=5.0,
            load_power_kw=2.0,
            grid_power_kw=100.0,
            electricity_price_cny_per_kwh=-1.0,
        )
    )
    second = policy.evaluate(
        make_context(
            pv_power_kw=5.0,
            load_power_kw=2.0,
            grid_power_kw=-100.0,
            electricity_price_cny_per_kwh=10.0,
        )
    )

    assert first.intent.battery_power_intent_kw == 3.0
    assert second.intent.battery_power_intent_kw == 3.0


def test_result_preserves_exact_created_intent_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_intent_type = DecisionIntent
    created: list[DecisionIntent] = []

    def capture_intent(
        battery_power_intent_kw: float,
    ) -> DecisionIntent:
        intent = original_intent_type(battery_power_intent_kw)
        created.append(intent)
        return intent

    monkeypatch.setattr(policy_module, "DecisionIntent", capture_intent)

    result = SelfConsumptionPolicy().evaluate(
        make_context(pv_power_kw=5.0, load_power_kw=2.0)
    )

    assert len(created) == 1
    assert result.intent is created[0]


def test_policy_does_not_mutate_context() -> None:
    context = make_context(pv_power_kw=5.0, load_power_kw=2.0)
    values_before = tuple(getattr(context, field.name) for field in fields(context))

    SelfConsumptionPolicy().evaluate(context)

    assert tuple(getattr(context, field.name) for field in fields(context)) == (
        values_before
    )


def test_policy_rejects_invalid_context_type() -> None:
    with pytest.raises(TypeError, match="context"):
        SelfConsumptionPolicy().evaluate(cast(DecisionContext, object()))


def test_policy_is_stateless_and_slotted() -> None:
    policy = SelfConsumptionPolicy()

    assert SelfConsumptionPolicy.__slots__ == ()
    assert not hasattr(policy, "__dict__")
    for forbidden in (
        "runtime",
        "dispatcher",
        "device",
        "commands",
        "cache",
        "history",
        "storage",
    ):
        assert not hasattr(policy, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, policy).cache = {}


def test_policy_module_has_only_decision_boundary_dependencies() -> None:
    source = inspect.getsource(policy_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "kernel.decision.context",
        "kernel.decision.context_result",
        "kernel.decision.intent",
        "kernel.policy.implementation",
    }
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "pcs",
        "bms",
        "can",
        "modbus",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
        "constraint",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_public_import_works() -> None:
    assert SelfConsumptionPolicy.__name__ == "SelfConsumptionPolicy"
