"""Tests for immutable LoadState observations."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.ids import AssetId
from kernel.state import LoadState


def test_load_state_creation() -> None:
    state = LoadState(AssetId("load-1"), 80)
    assert state.asset_id == AssetId("load-1")
    assert state.power_kw == 80.0


def test_load_state_accepts_zero_power() -> None:
    assert LoadState(AssetId("load-1"), 0).power_kw == 0.0


@pytest.mark.parametrize(
    "power_kw",
    [-1, float("nan"), float("inf"), float("-inf")],
)
def test_load_state_rejects_invalid_power(power_kw: float) -> None:
    with pytest.raises(ValueError, match="power_kw"):
        LoadState(AssetId("load-1"), power_kw)


@pytest.mark.parametrize("power_kw", [True, "80", None])
def test_load_state_rejects_invalid_power_type(power_kw: object) -> None:
    with pytest.raises(TypeError, match="power_kw"):
        LoadState(AssetId("load-1"), cast(float, power_kw))


def test_load_state_is_frozen_and_slotted() -> None:
    state = LoadState(AssetId("load-1"), 80)
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, state).power_kw = 70


def test_load_state_has_only_observation_fields() -> None:
    assert [field.name for field in fields(LoadState)] == [
        "asset_id",
        "power_kw",
    ]
