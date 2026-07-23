"""Immutable consistent collection of energy operational observations."""

from dataclasses import dataclass

from kernel.state.battery import BatteryState
from kernel.state.load import LoadState
from kernel.state.pv import PVState
from kernel.state.validation import require_tuple_of


@dataclass(frozen=True, slots=True)
class EnergySnapshot:
    """Group ordered asset state tuples into one system observation."""

    battery_states: tuple[BatteryState, ...]
    pv_states: tuple[PVState, ...]
    load_states: tuple[LoadState, ...]

    def __post_init__(self) -> None:
        require_tuple_of(self.battery_states, BatteryState, "battery_states")
        require_tuple_of(self.pv_states, PVState, "pv_states")
        require_tuple_of(self.load_states, LoadState, "load_states")
