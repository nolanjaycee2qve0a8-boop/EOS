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

    battery: BatteryState
    pcs: PCSState
    pv: PVState
    grid: GridState

    def __post_init__(self) -> None:
        require_instance(self.battery, BatteryState, "battery")
        require_instance(self.pcs, PCSState, "pcs")
        require_instance(self.pv, PVState, "pv")
        require_instance(self.grid, GridState, "grid")
