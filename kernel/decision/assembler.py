"""Stateless assembly of one immutable EMS decision input."""

from datetime import datetime

from kernel.decision.context import DecisionContext
from kernel.system_state import (
    BatteryState,
    EnergySystemState,
    GridState,
    PCSState,
    PVState,
)


class DecisionContextAssembler:
    """Assemble decision facts without calculation, policy, or runtime state."""

    __slots__ = ()

    @staticmethod
    def assemble(
        state: EnergySystemState,
        *,
        timestamp: datetime,
        battery_power_limit_kw: float,
        battery_energy_capacity_kwh: float,
        load_power_kw: float,
        electricity_price_cny_per_kwh: float,
        reserve_soc: float,
        export_limit_kw: float,
    ) -> DecisionContext:
        """Map physical observations and explicit facts into a context."""
        if not isinstance(state, EnergySystemState):
            raise TypeError("state must be an EnergySystemState")

        required_components = (
            ("battery", state.battery, BatteryState),
            ("pcs", state.pcs, PCSState),
            ("pv", state.pv, PVState),
            ("grid", state.grid, GridState),
        )
        for field_name, component, expected_type in required_components:
            if not isinstance(component, expected_type):
                raise TypeError(
                    f"state.{field_name} must be a {expected_type.__name__}"
                )

        return DecisionContext(
            timestamp=timestamp,
            soc=state.battery.soc,
            battery_power_limit_kw=battery_power_limit_kw,
            battery_energy_capacity_kwh=battery_energy_capacity_kwh,
            pv_power_kw=state.pv.actual_power_kw,
            load_power_kw=load_power_kw,
            grid_power_kw=state.grid.grid_power_kw,
            electricity_price_cny_per_kwh=electricity_price_cny_per_kwh,
            reserve_soc=reserve_soc,
            export_limit_kw=export_limit_kw,
        )
