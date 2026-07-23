"""Immutable aggregate input boundary for future energy decisions."""

from dataclasses import dataclass

from kernel.asset import EnergyAsset
from kernel.context.validation import (
    EnergyState,
    require_assets,
    require_power_flow,
    require_state_for_every_asset,
    require_states,
)
from kernel.power import PowerFlow


@dataclass(frozen=True, slots=True)
class EnergySystemContext:
    """Aggregate assets and observations without calculating or controlling."""

    assets: tuple[EnergyAsset, ...]
    states: tuple[EnergyState, ...]
    power_flow: PowerFlow

    def __post_init__(self) -> None:
        assets = require_assets(self.assets)
        states = require_states(self.states)
        power_flow = require_power_flow(self.power_flow)
        require_state_for_every_asset(assets, states)

        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "power_flow", power_flow)
