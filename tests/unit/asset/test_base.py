"""Tests for the immutable EnergyAsset base model."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import EnergyAsset
from kernel.ids import AssetId


def test_energy_asset_creation() -> None:
    asset = EnergyAsset(AssetId("asset-1"), "Site connection")
    assert asset.asset_id == AssetId("asset-1")
    assert asset.name == "Site connection"


def test_energy_asset_is_frozen() -> None:
    asset = EnergyAsset(AssetId("asset-1"), "Site connection")
    with pytest.raises(FrozenInstanceError):
        cast(Any, asset).name = "Changed"


def test_energy_asset_uses_slots() -> None:
    assert not hasattr(
        EnergyAsset(AssetId("asset-1"), "Site connection"),
        "__dict__",
    )


@pytest.mark.parametrize("name", ["", " ", "\t"])
def test_energy_asset_rejects_empty_name(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        EnergyAsset(AssetId("asset-1"), name)


def test_energy_asset_rejects_invalid_name_type() -> None:
    with pytest.raises(TypeError, match="name"):
        EnergyAsset(AssetId("asset-1"), cast(str, object()))


def test_energy_asset_rejects_empty_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        EnergyAsset(AssetId(""), "Site connection")


def test_energy_asset_has_only_definition_fields() -> None:
    assert [field.name for field in fields(EnergyAsset)] == ["asset_id", "name"]
