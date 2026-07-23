"""Tests for immutable PVState observations."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.ids import AssetId
from kernel.state import PVState


def test_pv_state_creation() -> None:
    state = PVState(AssetId("pv-1"), 120)
    assert state.asset_id == AssetId("pv-1")
    assert state.power_kw == 120.0


def test_pv_state_accepts_zero_power() -> None:
    assert PVState(AssetId("pv-1"), 0).power_kw == 0.0


@pytest.mark.parametrize(
    "power_kw",
    [-1, float("nan"), float("inf"), float("-inf")],
)
def test_pv_state_rejects_invalid_power(power_kw: float) -> None:
    with pytest.raises(ValueError, match="power_kw"):
        PVState(AssetId("pv-1"), power_kw)


@pytest.mark.parametrize("power_kw", [True, "120", None])
def test_pv_state_rejects_invalid_power_type(power_kw: object) -> None:
    with pytest.raises(TypeError, match="power_kw"):
        PVState(AssetId("pv-1"), cast(float, power_kw))


def test_pv_state_is_frozen_and_slotted() -> None:
    state = PVState(AssetId("pv-1"), 120)
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, state).power_kw = 100


def test_pv_state_has_only_observation_fields() -> None:
    assert [field.name for field in fields(PVState)] == [
        "asset_id",
        "power_kw",
    ]
