"""Concrete deterministic PV profile model for the EMS Simulator demo."""

from simulator import (
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
)


class PVProfileSimulationModel(PVSimulationModelBoundary):
    """Expose one caller-supplied PV profile value as generated PV power.

    The hourly profile value already enters through
    ``PVSimulationInput.available_power_kw`` as finite, non-negative raw kW.
    This model performs no weather, irradiance, temperature, MPPT, inverter,
    forecast, or curtailment calculation. It retains no input or result state.
    """

    __slots__ = ()

    def simulate(
        self,
        simulation_input: PVSimulationInput,
    ) -> PVSimulationResult:
        """Return generated power while preserving the exact input reference."""
        if not isinstance(simulation_input, PVSimulationInput):
            raise TypeError("simulation_input must be a PVSimulationInput")
        return PVSimulationResult(
            simulation_input=simulation_input,
            actual_power_kw=simulation_input.available_power_kw,
        )
