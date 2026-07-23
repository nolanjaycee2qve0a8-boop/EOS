"""Tests for immutable LoadAsset definitions."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import EnergyAsset, LoadAsset
from kernel.ids import AssetId


def make_load() -> LoadAsset:
    return LoadAsset(AssetId("load-1"), "Building load", 180)


def test_load_asset_creation() -> None:
    asset = make_load()
    assert isinstance(asset, EnergyAsset)
    assert asset.rated_power_kw == 180.0


@pytest.mark.parametrize("rated_power_kw", [0, -1, float("nan")])
def test_load_asset_rejects_invalid_rating(rated_power_kw: float) -> None:
    with pytest.raises(ValueError, match="rated_power_kw"):
        LoadAsset(AssetId("load-1"), "Building load", rated_power_kw)


def test_load_asset_rejects_invalid_rating_type() -> None:
    with pytest.raises(TypeError, match="rated_power_kw"):
        LoadAsset(AssetId("load-1"), "Building load", cast(float, "180"))


def test_load_asset_is_frozen_and_slotted() -> None:
    asset = make_load()
    assert not hasattr(asset, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, asset).rated_power_kw = 200


def test_load_asset_has_only_definition_fields() -> None:
    assert [field.name for field in fields(LoadAsset)] == [
        "asset_id",
        "name",
        "rated_power_kw",
    ]
