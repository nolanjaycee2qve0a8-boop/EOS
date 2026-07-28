"""Immutable aggregate of one physical energy system observation."""

from dataclasses import dataclass

from kernel.system_state.battery import BatteryState
from kernel.system_state.grid import GridState
from kernel.system_state.pcs import PCSState
from kernel.system_state.pv import PVState
from kernel.system_state.validation import require_instance


@dataclass(frozen=True, slots=True)
class EnergySystemState:
    """Preserve exact component state identities in one physical snapshot."""

    battery_state: BatteryState
    pcs_state: PCSState
    pv_state: PVState
    grid_state: GridState

    def __post_init__(self) -> None:
        require_instance(self.battery_state, BatteryState, "battery_state")
        require_instance(self.pcs_state, PCSState, "pcs_state")
        require_instance(self.pv_state, PVState, "pv_state")
        require_instance(self.grid_state, GridState, "grid_state")
