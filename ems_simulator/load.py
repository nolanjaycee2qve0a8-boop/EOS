"""Concrete deterministic Load profile model for the EMS Simulator demo."""

from simulator import (
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
)


class LoadProfileSimulationModel(LoadSimulationModelBoundary):
    """Expose one caller-supplied Load profile value as consumed power.

    The hourly profile value already enters through
    ``LoadSimulationInput.demand_power_kw`` as finite, non-negative raw kW.
    This model performs no user-behavior, appliance, stochastic-generation,
    forecast, prediction, or demand-response calculation. It retains no input
    or result state.
    """

    __slots__ = ()

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        """Return consumed power while preserving the exact input reference."""
        if not isinstance(simulation_input, LoadSimulationInput):
            raise TypeError("simulation_input must be a LoadSimulationInput")
        return LoadSimulationResult(
            simulation_input=simulation_input,
            actual_power_kw=simulation_input.demand_power_kw,
        )
