"""Tests for the immutable EMS decision input context."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import DecisionContext
from kernel.dispatch import CommandDispatcher, CommandExecutor
from kernel.policy import EMSPolicy
from kernel.runtime import JournaledEMSRuntime

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_context(**overrides: object) -> DecisionContext:
    values: dict[str, object] = {
        "timestamp": FIXED_TIME,
        "soc": 0.5,
        "battery_power_limit_kw": 50.0,
        "battery_energy_capacity_kwh": 100.0,
        "pv_power_kw": 40.0,
        "load_power_kw": 30.0,
        "grid_power_kw": -10.0,
        "electricity_price": 0.25,
        "reserve_soc": 0.2,
        "export_limit_kw": 15.0,
    }
    values.update(overrides)
    return DecisionContext(**cast(Any, values))


def test_context_stores_decision_input_facts() -> None:
    context = make_context()

    assert context.timestamp is FIXED_TIME
    assert context.soc == 0.5
    assert context.battery_power_limit_kw == 50.0
    assert context.battery_energy_capacity_kwh == 100.0
    assert context.pv_power_kw == 40.0
    assert context.load_power_kw == 30.0
    assert context.grid_power_kw == -10.0
    assert context.electricity_price == 0.25
    assert context.reserve_soc == 0.2
    assert context.export_limit_kw == 15.0


def test_context_identity_is_preserved_when_passed_as_input() -> None:
    original_context = make_context()

    observed_context = original_context

    assert observed_context is original_context


def test_context_is_frozen_slotted_and_has_only_fixed_fields() -> None:
    context = make_context()

    assert tuple(field.name for field in fields(DecisionContext)) == (
        "timestamp",
        "soc",
        "battery_power_limit_kw",
        "battery_energy_capacity_kwh",
        "pv_power_kw",
        "load_power_kw",
        "grid_power_kw",
        "electricity_price",
        "reserve_soc",
        "export_limit_kw",
    )
    assert DecisionContext.__slots__ == tuple(
        field.name for field in fields(DecisionContext)
    )
    assert not hasattr(context, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, context).soc = 0.7


def test_context_has_no_mutable_container_fields() -> None:
    context = make_context()

    assert not any(
        isinstance(getattr(context, field.name), list | dict | set)
        for field in fields(DecisionContext)
    )


def test_context_creation_invokes_no_execution_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object) -> None:
        raise AssertionError("DecisionContext invoked execution behavior")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        EMSPolicy,
        "evaluate",
        fail_if_called,
    )
    monkeypatch.setattr(
        CommandDispatcher,
        "dispatch",
        fail_if_called,
    )
    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fail_if_called),
    )

    context = make_context()

    assert context.timestamp is FIXED_TIME


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("soc", -0.1),
        ("soc", 1.1),
        ("reserve_soc", -0.1),
        ("reserve_soc", 1.1),
        ("battery_power_limit_kw", -0.1),
        ("battery_energy_capacity_kwh", 0.0),
        ("pv_power_kw", -0.1),
        ("load_power_kw", -0.1),
        ("export_limit_kw", -0.1),
    ],
)
def test_context_rejects_invalid_ranges(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_context(**{field_name: invalid_value})


@pytest.mark.parametrize(
    "field_name",
    [
        "soc",
        "battery_power_limit_kw",
        "battery_energy_capacity_kwh",
        "pv_power_kw",
        "load_power_kw",
        "grid_power_kw",
        "electricity_price",
        "reserve_soc",
        "export_limit_kw",
    ],
)
def test_context_rejects_boolean_numeric_fields(field_name: str) -> None:
    with pytest.raises(TypeError, match=field_name):
        make_context(**{field_name: True})


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf")])
def test_context_rejects_non_finite_values(invalid_value: float) -> None:
    with pytest.raises(ValueError, match="grid_power_kw"):
        make_context(grid_power_kw=invalid_value)


def test_context_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        make_context(timestamp=datetime(2026, 1, 1, 12, 0))


def test_context_does_not_define_decision_behavior() -> None:
    forbidden_methods = (
        "charge",
        "discharge",
        "optimize",
        "calculate_strategy",
        "policy",
    )

    assert not any(hasattr(DecisionContext, name) for name in forbidden_methods)
