"""Focused validation for the immutable energy-system context."""

from kernel.asset import EnergyAsset
from kernel.power import PowerFlow
from kernel.state import BatteryState, LoadState, PVState

type EnergyState = BatteryState | PVState | LoadState

ENERGY_STATE_TYPES = (BatteryState, PVState, LoadState)


def require_assets(value: object) -> tuple[EnergyAsset, ...]:
    """Require an immutable tuple containing only energy assets."""
    if not isinstance(value, tuple):
        raise TypeError("assets must be a tuple")
    for item in value:
        if not isinstance(item, EnergyAsset):
            raise TypeError("assets must contain only EnergyAsset instances")
    return value


def require_states(value: object) -> tuple[EnergyState, ...]:
    """Require an immutable tuple containing only existing state models."""
    if not isinstance(value, tuple):
        raise TypeError("states must be a tuple")
    for item in value:
        if not isinstance(item, ENERGY_STATE_TYPES):
            raise TypeError(
                "states must contain only BatteryState, PVState, or LoadState instances"
            )
    return value


def require_power_flow(value: object) -> PowerFlow:
    """Require an already validated PowerFlow observation."""
    if not isinstance(value, PowerFlow):
        raise TypeError("power_flow must be a PowerFlow instance")
    return value


def require_state_for_every_asset(
    assets: tuple[EnergyAsset, ...],
    states: tuple[EnergyState, ...],
) -> None:
    """Require every asset identity to occur in the supplied state tuple."""
    state_asset_ids = {state.asset_id for state in states}
    for asset in assets:
        if asset.asset_id not in state_asset_ids:
            raise ValueError(
                f"asset {asset.asset_id!r} has no matching state in states"
            )
