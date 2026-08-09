"""Concrete deterministic battery physics for the EMS Simulator demo."""

from dataclasses import dataclass

from ems_simulator.input import BatteryParameters
from simulator import (
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
)

SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True, slots=True)
class SimpleBatteryPhysicsModel(BatterySimulationModelBoundary):
    """Apply simple power, efficiency, and SOC boundary physics.

    ``parameters`` is the exact caller-supplied immutable configuration. The
    model owns no current state, cache, or history. Positive Battery power
    charges; negative power discharges; zero is idle.

    Charging stores ``power * duration * charge_efficiency``. Discharging
    removes ``abs(power) * duration / discharge_efficiency`` from stored
    energy. Actual power is limited by configured power limits, SOC ``1.0``,
    and the configured ``reserve_soc`` lower boundary.
    """

    parameters: BatteryParameters

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, BatteryParameters):
            raise TypeError("parameters must be BatteryParameters")

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        """Return one immutable transition preserving the exact input."""
        if not isinstance(simulation_input, BatterySimulationInput):
            raise TypeError("simulation_input must be a BatterySimulationInput")

        requested_power_kw = simulation_input.actuation.battery_power_kw
        duration_hours = (
            simulation_input.step_identity.duration_seconds / SECONDS_PER_HOUR
        )
        source_soc = simulation_input.source_state.soc

        if requested_power_kw > 0:
            actual_power_kw, next_soc = self._charge_transition(
                requested_power_kw,
                duration_hours,
                source_soc,
            )
        elif requested_power_kw < 0:
            actual_power_kw, next_soc = self._discharge_transition(
                requested_power_kw,
                duration_hours,
                source_soc,
            )
        else:
            actual_power_kw, next_soc = 0.0, source_soc

        next_state = (
            simulation_input.source_state
            if next_soc == source_soc
            else BatterySimulationState(next_soc)
        )
        return BatterySimulationResult(
            simulation_input=simulation_input,
            next_state=next_state,
            actual_power_kw=actual_power_kw,
        )

    def _charge_transition(
        self,
        requested_power_kw: float,
        duration_hours: float,
        source_soc: float,
    ) -> tuple[float, float]:
        headroom_kwh = (1.0 - source_soc) * self.parameters.capacity_kwh
        soc_limited_power_kw = headroom_kwh / (
            duration_hours * self.parameters.charge_efficiency
        )
        actual_power_kw = min(
            requested_power_kw,
            self.parameters.max_charge_power_kw,
            soc_limited_power_kw,
        )
        stored_energy_kwh = (
            actual_power_kw * duration_hours * self.parameters.charge_efficiency
        )
        next_soc = min(
            1.0,
            source_soc + stored_energy_kwh / self.parameters.capacity_kwh,
        )
        return actual_power_kw, next_soc

    def _discharge_transition(
        self,
        requested_power_kw: float,
        duration_hours: float,
        source_soc: float,
    ) -> tuple[float, float]:
        available_energy_kwh = (
            max(0.0, source_soc - self.parameters.reserve_soc)
            * self.parameters.capacity_kwh
        )
        soc_limited_power_kw = (
            available_energy_kwh * self.parameters.discharge_efficiency / duration_hours
        )
        discharge_power_kw = min(
            abs(requested_power_kw),
            self.parameters.max_discharge_power_kw,
            soc_limited_power_kw,
        )
        if discharge_power_kw == 0:
            return 0.0, source_soc
        removed_energy_kwh = (
            discharge_power_kw * duration_hours / self.parameters.discharge_efficiency
        )
        next_soc = max(
            self.parameters.reserve_soc,
            source_soc - removed_energy_kwh / self.parameters.capacity_kwh,
        )
        return -discharge_power_kw, next_soc
