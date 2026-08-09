"""Concrete deterministic Grid energy balance for the EMS Simulator demo."""

from dataclasses import dataclass

from simulator import (
    BatterySimulationResult,
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    LoadSimulationResult,
    PVSimulationResult,
    SimulationStepIdentity,
)


@dataclass(frozen=True, slots=True)
class GridEnergyBalanceSimulationModel(GridSimulationModelBoundary):
    """Calculate one Grid exchange from exact component result references.

    Grid power is finite signed raw kW: positive means import, negative means
    export, and zero means balanced. Battery power is positive when charging
    and negative when discharging. The balance is therefore:

    ``load_power_kw + battery_power_kw - pv_power_kw``.

    The model is immutable per-step configuration. It preserves the exact PV,
    Load, and Battery result references and retains no evolving state, cache,
    or history.
    """

    pv_result: PVSimulationResult
    load_result: LoadSimulationResult
    battery_result: BatterySimulationResult

    def __post_init__(self) -> None:
        if not isinstance(self.pv_result, PVSimulationResult):
            raise TypeError("pv_result must be a PVSimulationResult")
        if not isinstance(self.load_result, LoadSimulationResult):
            raise TypeError("load_result must be a LoadSimulationResult")
        if not isinstance(self.battery_result, BatterySimulationResult):
            raise TypeError("battery_result must be a BatterySimulationResult")

        step_identity = self.pv_result.simulation_input.step_identity
        self._require_exact_step_identity(
            self.load_result.simulation_input.step_identity,
            step_identity,
            "load_result",
        )
        self._require_exact_step_identity(
            self.battery_result.simulation_input.step_identity,
            step_identity,
            "battery_result",
        )

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        """Return the balance while preserving the exact Grid input."""
        if not isinstance(simulation_input, GridSimulationInput):
            raise TypeError("simulation_input must be a GridSimulationInput")
        self._require_exact_step_identity(
            simulation_input.step_identity,
            self.pv_result.simulation_input.step_identity,
            "simulation_input",
        )

        grid_power_kw = (
            self.load_result.actual_power_kw
            + self.battery_result.actual_power_kw
            - self.pv_result.actual_power_kw
        )
        return GridSimulationResult(
            simulation_input=simulation_input,
            actual_grid_power_kw=grid_power_kw,
        )

    @staticmethod
    def _require_exact_step_identity(
        candidate: SimulationStepIdentity,
        expected: SimulationStepIdentity,
        field_name: str,
    ) -> None:
        if candidate is not expected:
            raise ValueError(
                f"{field_name} must reference the exact shared step identity"
            )
