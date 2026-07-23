"""Tests for immutable energy-system context aggregation."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import BatteryAsset, EnergyAsset, LoadAsset, PVAsset
from kernel.context import EnergySystemContext
from kernel.ids import AssetId
from kernel.power import PowerFlow
from kernel.state import BatteryState, LoadState, PVState


def make_power_flow() -> PowerFlow:
    return PowerFlow(
        pv_power_kw=5.0,
        load_power_kw=5.0,
        battery_power_kw=0.0,
        grid_power_kw=0.0,
    )


def make_battery(number: int) -> BatteryAsset:
    return BatteryAsset(
        asset_id=AssetId(f"battery-{number}"),
        name=f"Battery {number}",
        capacity_kwh=10.0,
        max_charge_kw=5.0,
        max_discharge_kw=5.0,
    )


def make_pv(number: int) -> PVAsset:
    return PVAsset(
        asset_id=AssetId(f"pv-{number}"),
        name=f"PV {number}",
        rated_power_kw=5.0,
    )


def make_load(number: int) -> LoadAsset:
    return LoadAsset(
        asset_id=AssetId(f"load-{number}"),
        name=f"Load {number}",
        rated_power_kw=5.0,
    )


def state_for(asset: EnergyAsset) -> BatteryState | PVState | LoadState:
    if isinstance(asset, BatteryAsset):
        return BatteryState(asset.asset_id, soc=0.5, power_kw=0.0)
    if isinstance(asset, PVAsset):
        return PVState(asset.asset_id, power_kw=5.0)
    if isinstance(asset, LoadAsset):
        return LoadState(asset.asset_id, power_kw=5.0)
    raise TypeError("test asset has no state factory")


def test_creates_valid_context() -> None:
    assets = (make_battery(1), make_pv(1), make_load(1))
    states = tuple(state_for(asset) for asset in assets)
    power_flow = make_power_flow()

    context = EnergySystemContext(assets, states, power_flow)

    assert context.assets is assets
    assert context.states is states
    assert context.power_flow is power_flow


def test_accepts_empty_asset_and_state_tuples() -> None:
    power_flow = make_power_flow()

    context = EnergySystemContext((), (), power_flow)

    assert context.assets == ()
    assert context.states == ()


def test_accepts_existing_state_types() -> None:
    battery = make_battery(1)
    pv = make_pv(1)
    load = make_load(1)

    context = EnergySystemContext(
        (battery, pv, load),
        (
            BatteryState(battery.asset_id, soc=0.5, power_kw=0.0),
            PVState(pv.asset_id, power_kw=5.0),
            LoadState(load.asset_id, power_kw=5.0),
        ),
        make_power_flow(),
    )

    assert len(context.states) == 3


def test_rejects_mutable_asset_list() -> None:
    with pytest.raises(TypeError, match="assets"):
        EnergySystemContext(
            cast(tuple[EnergyAsset, ...], [make_battery(1)]),
            (),
            make_power_flow(),
        )


def test_rejects_invalid_asset_element() -> None:
    with pytest.raises(TypeError, match="assets"):
        EnergySystemContext(
            cast(tuple[EnergyAsset, ...], (object(),)),
            (),
            make_power_flow(),
        )


def test_rejects_mutable_state_list() -> None:
    asset = make_battery(1)

    with pytest.raises(TypeError, match="states"):
        EnergySystemContext(
            (asset,),
            cast(
                tuple[BatteryState | PVState | LoadState, ...],
                [state_for(asset)],
            ),
            make_power_flow(),
        )


def test_rejects_invalid_state_element() -> None:
    with pytest.raises(TypeError, match="states"):
        EnergySystemContext(
            (),
            cast(
                tuple[BatteryState | PVState | LoadState, ...],
                (object(),),
            ),
            make_power_flow(),
        )


def test_rejects_invalid_power_flow() -> None:
    with pytest.raises(TypeError, match="power_flow"):
        EnergySystemContext(
            (),
            (),
            cast(PowerFlow, object()),
        )


def test_rejects_asset_without_matching_state() -> None:
    asset = make_battery(1)

    with pytest.raises(ValueError, match="battery-1"):
        EnergySystemContext((asset,), (), make_power_flow())


def test_matches_assets_and_states_by_asset_id() -> None:
    asset = make_battery(1)
    separate_identity = AssetId("battery-1")
    state = BatteryState(separate_identity, soc=0.5, power_kw=0.0)

    context = EnergySystemContext((asset,), (state,), make_power_flow())

    assert context.assets[0].asset_id == context.states[0].asset_id


def test_allows_additional_states_without_hidden_filtering() -> None:
    asset = make_battery(1)
    matching_state = state_for(asset)
    additional_state = PVState(AssetId("pv-unregistered"), power_kw=0.0)
    states = (additional_state, matching_state)

    context = EnergySystemContext((asset,), states, make_power_flow())

    assert context.states is states


def test_preserves_asset_and_state_order() -> None:
    battery_1, battery_2 = make_battery(1), make_battery(2)
    state_1, state_2 = state_for(battery_1), state_for(battery_2)
    assets = (battery_2, battery_1)
    states = (state_1, state_2)

    context = EnergySystemContext(assets, states, make_power_flow())

    assert context.assets == (battery_2, battery_1)
    assert context.states == (state_1, state_2)


def test_preserves_duplicate_entries() -> None:
    asset = make_battery(1)
    state = state_for(asset)
    assets = (asset, asset)
    states = (state, state)

    context = EnergySystemContext(assets, states, make_power_flow())

    assert context.assets is assets
    assert context.states is states


def test_public_collections_are_immutable_tuples() -> None:
    asset = make_battery(1)
    context = EnergySystemContext(
        (asset,),
        (state_for(asset),),
        make_power_flow(),
    )

    with pytest.raises(TypeError):
        cast(Any, context.assets)[0] = make_battery(2)
    with pytest.raises(TypeError):
        cast(Any, context.states)[0] = state_for(make_battery(2))


def test_is_frozen_and_slotted() -> None:
    context = EnergySystemContext((), (), make_power_flow())

    assert not hasattr(context, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, context).assets = ()


def test_has_only_specified_fields() -> None:
    assert [field.name for field in fields(EnergySystemContext)] == [
        "assets",
        "states",
        "power_flow",
    ]
