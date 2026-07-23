"""Tests for immutable EnergySnapshot collections."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.ids import AssetId
from kernel.state import BatteryState, EnergySnapshot, LoadState, PVState


def make_battery(number: int) -> BatteryState:
    return BatteryState(AssetId(f"battery-{number}"), 0.5, 0)


def make_pv(number: int) -> PVState:
    return PVState(AssetId(f"pv-{number}"), number)


def make_load(number: int) -> LoadState:
    return LoadState(AssetId(f"load-{number}"), number)


def test_energy_snapshot_creation() -> None:
    batteries = (make_battery(1),)
    pvs = (make_pv(1),)
    loads = (make_load(1),)
    snapshot = EnergySnapshot(batteries, pvs, loads)
    assert snapshot.battery_states is batteries
    assert snapshot.pv_states is pvs
    assert snapshot.load_states is loads


def test_energy_snapshot_accepts_empty_tuples() -> None:
    assert EnergySnapshot((), (), ()) == EnergySnapshot((), (), ())


@pytest.mark.parametrize(
    ("field_name", "batteries", "pvs", "loads"),
    [
        ("battery_states", [], (), ()),
        ("pv_states", (), [], ()),
        ("load_states", (), (), []),
    ],
)
def test_energy_snapshot_rejects_mutable_collections(
    field_name: str,
    batteries: object,
    pvs: object,
    loads: object,
) -> None:
    with pytest.raises(TypeError, match=field_name):
        EnergySnapshot(
            cast(tuple[BatteryState, ...], batteries),
            cast(tuple[PVState, ...], pvs),
            cast(tuple[LoadState, ...], loads),
        )


@pytest.mark.parametrize(
    ("field_name", "batteries", "pvs", "loads"),
    [
        ("battery_states", (object(),), (), ()),
        ("pv_states", (), (object(),), ()),
        ("load_states", (), (), (object(),)),
    ],
)
def test_energy_snapshot_rejects_invalid_elements(
    field_name: str,
    batteries: tuple[object, ...],
    pvs: tuple[object, ...],
    loads: tuple[object, ...],
) -> None:
    with pytest.raises(TypeError, match=field_name):
        EnergySnapshot(
            cast(tuple[BatteryState, ...], batteries),
            cast(tuple[PVState, ...], pvs),
            cast(tuple[LoadState, ...], loads),
        )


def test_energy_snapshot_preserves_deterministic_order() -> None:
    battery_1, battery_2 = make_battery(1), make_battery(2)
    pv_1, pv_2 = make_pv(1), make_pv(2)
    load_1, load_2 = make_load(1), make_load(2)
    snapshot = EnergySnapshot(
        (battery_2, battery_1),
        (pv_2, pv_1),
        (load_2, load_1),
    )
    assert snapshot.battery_states == (battery_2, battery_1)
    assert snapshot.pv_states == (pv_2, pv_1)
    assert snapshot.load_states == (load_2, load_1)


def test_energy_snapshot_tuples_are_immutable() -> None:
    snapshot = EnergySnapshot((make_battery(1),), (), ())
    with pytest.raises(TypeError):
        cast(Any, snapshot.battery_states)[0] = make_battery(2)


def test_energy_snapshot_is_frozen_and_slotted() -> None:
    snapshot = EnergySnapshot((), (), ())
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, snapshot).battery_states = ()


def test_energy_snapshot_has_only_state_tuple_fields() -> None:
    assert [field.name for field in fields(EnergySnapshot)] == [
        "battery_states",
        "pv_states",
        "load_states",
    ]
