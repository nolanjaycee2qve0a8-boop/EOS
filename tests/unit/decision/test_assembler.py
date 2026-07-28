"""Tests for deterministic DecisionContext assembly."""

from dataclasses import fields
from datetime import UTC, datetime
from inspect import Parameter, signature
from typing import Any, cast, get_type_hints

import pytest

from kernel.decision import DecisionContext, DecisionContextAssembler
from kernel.dispatch import CommandDispatcher, CommandExecutor
from kernel.policy import EMSPolicy
from kernel.runtime import JournaledEMSRuntime
from kernel.system_state import (
    BatteryState,
    EnergySystemState,
    GridState,
    PCSState,
    PVState,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_state(
    *,
    soc: float = 0.5,
    actual_pv_power_kw: float = 40.0,
    grid_power_kw: float = -10.0,
) -> EnergySystemState:
    return EnergySystemState(
        battery=BatteryState(
            soc=soc,
            soh=0.9,
            voltage_v=700.0,
            current_a=-20.0,
            temperature_c=25.0,
            available_charge_power_kw=80.0,
            available_discharge_power_kw=90.0,
        ),
        pcs=PCSState(
            active_power_kw=-15.0,
            reactive_power_kvar=2.0,
            operating_state="running",
            fault_state="none",
        ),
        pv=PVState(
            available_power_kw=45.0,
            actual_power_kw=actual_pv_power_kw,
        ),
        grid=GridState(
            grid_power_kw=grid_power_kw,
            voltage_v=400.0,
            frequency_hz=50.0,
        ),
    )


def assemble(
    state: EnergySystemState,
    **overrides: object,
) -> DecisionContext:
    values: dict[str, object] = {
        "timestamp": FIXED_TIME,
        "battery_power_limit_kw": 50.0,
        "battery_energy_capacity_kwh": 100.0,
        "load_power_kw": 30.0,
        "electricity_price_cny_per_kwh": 0.25,
        "reserve_soc": 0.2,
        "export_limit_kw": 15.0,
    }
    values.update(overrides)
    return DecisionContextAssembler.assemble(state, **cast(Any, values))


def test_assemble_maps_only_confirmed_physical_observations() -> None:
    state = make_state(soc=0.6, actual_pv_power_kw=35.0, grid_power_kw=-8.0)

    context = assemble(state)

    assert context.soc == state.battery.soc
    assert context.pv_power_kw == state.pv.actual_power_kw
    assert context.grid_power_kw == state.grid.grid_power_kw


def test_assemble_preserves_explicit_facts_and_timestamp_identity() -> None:
    timestamp = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)

    context = assemble(
        make_state(),
        timestamp=timestamp,
        battery_power_limit_kw=12.0,
        battery_energy_capacity_kwh=75.0,
        load_power_kw=22.0,
        electricity_price_cny_per_kwh=-0.15,
        reserve_soc=0.3,
        export_limit_kw=9.0,
    )

    assert context.timestamp is timestamp
    assert context.battery_power_limit_kw == 12.0
    assert context.battery_energy_capacity_kwh == 75.0
    assert context.load_power_kw == 22.0
    assert context.electricity_price_cny_per_kwh == -0.15
    assert context.reserve_soc == 0.3
    assert context.export_limit_kw == 9.0


@pytest.mark.parametrize("grid_power_kw", [10.0, -10.0, 0.0])
def test_assemble_preserves_grid_power_sign(grid_power_kw: float) -> None:
    context = assemble(make_state(grid_power_kw=grid_power_kw))

    assert context.grid_power_kw == grid_power_kw


def test_assemble_does_not_derive_battery_power_limit() -> None:
    state = make_state()

    context = assemble(state, battery_power_limit_kw=7.0)

    assert state.battery.available_charge_power_kw == 80.0
    assert state.battery.available_discharge_power_kw == 90.0
    assert context.battery_power_limit_kw == 7.0


def test_assemble_preserves_state_and_component_identities() -> None:
    state = make_state()
    components = (state.battery, state.pcs, state.pv, state.grid)
    values = tuple(
        tuple(getattr(component, field.name) for field in fields(component))
        for component in components
    )

    assemble(state)

    assert (state.battery, state.pcs, state.pv, state.grid) == components
    assert state.battery is components[0]
    assert state.pcs is components[1]
    assert state.pv is components[2]
    assert state.grid is components[3]
    assert values == tuple(
        tuple(getattr(component, field.name) for field in fields(component))
        for component in components
    )


def test_assemble_revalidates_battery_soc() -> None:
    state = make_state()
    object.__setattr__(state.battery, "soc", 1.1)

    with pytest.raises(ValueError, match="soc"):
        assemble(state)


def test_assemble_rejects_invalid_state() -> None:
    with pytest.raises(TypeError, match="state"):
        assemble(cast(EnergySystemState, object()))


@pytest.mark.parametrize(
    ("field_name", "expected_type"),
    [
        ("battery", BatteryState),
        ("pcs", PCSState),
        ("pv", PVState),
        ("grid", GridState),
    ],
)
def test_assemble_requires_every_component(
    field_name: str,
    expected_type: type[object],
) -> None:
    state = make_state()
    object.__setattr__(state, field_name, object())

    with pytest.raises(
        TypeError,
        match=rf"state\.{field_name} must be a {expected_type.__name__}",
    ):
        assemble(state)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("battery_power_limit_kw", -0.1),
        ("battery_energy_capacity_kwh", 0.0),
        ("load_power_kw", -0.1),
        ("electricity_price_cny_per_kwh", float("nan")),
        ("reserve_soc", 1.1),
        ("export_limit_kw", -0.1),
    ],
)
def test_assemble_validates_explicit_facts(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        assemble(make_state(), **{field_name: invalid_value})


def test_assemble_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        assemble(
            make_state(),
            timestamp=datetime(2026, 1, 1, 12, 0),
        )


def test_assemble_invokes_no_execution_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object) -> None:
        raise AssertionError("assembler invoked execution behavior")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(EMSPolicy, "evaluate", fail_if_called)
    monkeypatch.setattr(CommandDispatcher, "dispatch", fail_if_called)
    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fail_if_called),
    )

    context = assemble(make_state())

    assert isinstance(context, DecisionContext)


def test_assembler_is_stateless() -> None:
    assembler = DecisionContextAssembler()

    assert DecisionContextAssembler.__slots__ == ()
    assert not hasattr(assembler, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, assembler).history = ()


def test_assemble_signature_has_no_defaults_and_uses_keyword_only_facts() -> None:
    parameters = signature(DecisionContextAssembler.assemble).parameters

    assert tuple(parameters) == (
        "state",
        "timestamp",
        "battery_power_limit_kw",
        "battery_energy_capacity_kwh",
        "load_power_kw",
        "electricity_price_cny_per_kwh",
        "reserve_soc",
        "export_limit_kw",
    )
    assert parameters["state"].kind is Parameter.POSITIONAL_OR_KEYWORD
    assert all(
        parameter.kind is Parameter.KEYWORD_ONLY
        and parameter.default is Parameter.empty
        for name, parameter in parameters.items()
        if name != "state"
    )


def test_assemble_annotations_are_explicit() -> None:
    hints = get_type_hints(DecisionContextAssembler.assemble)

    assert hints == {
        "state": EnergySystemState,
        "timestamp": datetime,
        "battery_power_limit_kw": float,
        "battery_energy_capacity_kwh": float,
        "load_power_kw": float,
        "electricity_price_cny_per_kwh": float,
        "reserve_soc": float,
        "export_limit_kw": float,
        "return": DecisionContext,
    }
