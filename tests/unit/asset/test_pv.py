"""Tests for immutable PVAsset definitions."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import EnergyAsset, PVAsset
from kernel.ids import AssetId


def make_pv() -> PVAsset:
    return PVAsset(AssetId("pv-1"), "Rooftop PV", 250)


def test_pv_asset_creation() -> None:
    asset = make_pv()
    assert isinstance(asset, EnergyAsset)
    assert asset.rated_power_kw == 250.0


@pytest.mark.parametrize("rated_power_kw", [0, -1, float("nan")])
def test_pv_asset_rejects_invalid_rating(rated_power_kw: float) -> None:
    with pytest.raises(ValueError, match="rated_power_kw"):
        PVAsset(AssetId("pv-1"), "Rooftop PV", rated_power_kw)


def test_pv_asset_rejects_invalid_rating_type() -> None:
    with pytest.raises(TypeError, match="rated_power_kw"):
        PVAsset(AssetId("pv-1"), "Rooftop PV", cast(float, True))


def test_pv_asset_is_frozen_and_slotted() -> None:
    asset = make_pv()
    assert not hasattr(asset, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, asset).rated_power_kw = 300


def test_pv_asset_has_only_definition_fields() -> None:
    assert [field.name for field in fields(PVAsset)] == [
        "asset_id",
        "name",
        "rated_power_kw",
    ]
