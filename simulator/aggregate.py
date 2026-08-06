"""Immutable aggregate contracts for deterministic simulation evidence."""

from dataclasses import dataclass

from simulator.battery import BatterySimulationInput, BatterySimulationResult
from simulator.core import SimulationStepIdentity
from simulator.grid import GridSimulationInput, GridSimulationResult
from simulator.load import LoadSimulationInput, LoadSimulationResult
from simulator.pv import PVSimulationInput, PVSimulationResult
from simulator.tariff import TariffSimulationInput, TariffSimulationResult


@dataclass(frozen=True, slots=True)
class SimulationStepInput:
    """Aggregate exact component inputs for one exact simulation step."""

    step_identity: SimulationStepIdentity
    pv_input: PVSimulationInput
    load_input: LoadSimulationInput
    tariff_input: TariffSimulationInput
    battery_input: BatterySimulationInput
    grid_input: GridSimulationInput

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        component_inputs = (
            ("pv_input", self.pv_input, PVSimulationInput),
            ("load_input", self.load_input, LoadSimulationInput),
            ("tariff_input", self.tariff_input, TariffSimulationInput),
            ("battery_input", self.battery_input, BatterySimulationInput),
            ("grid_input", self.grid_input, GridSimulationInput),
        )
        for field_name, component_input, expected_type in component_inputs:
            if not isinstance(component_input, expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")
            if component_input.step_identity is not self.step_identity:
                raise ValueError(
                    f"{field_name}.step_identity must be the exact step_identity"
                )


@dataclass(frozen=True, slots=True)
class SimulationState:
    """Aggregate exact immutable component observations for one step."""

    step_identity: SimulationStepIdentity
    pv_result: PVSimulationResult
    load_result: LoadSimulationResult
    tariff_result: TariffSimulationResult
    battery_result: BatterySimulationResult
    grid_result: GridSimulationResult

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        component_results = (
            ("pv_result", self.pv_result, PVSimulationResult),
            ("load_result", self.load_result, LoadSimulationResult),
            ("tariff_result", self.tariff_result, TariffSimulationResult),
            ("battery_result", self.battery_result, BatterySimulationResult),
            ("grid_result", self.grid_result, GridSimulationResult),
        )
        for field_name, component_result, expected_type in component_results:
            if not isinstance(component_result, expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")
            if (
                component_result.simulation_input.step_identity
                is not self.step_identity
            ):
                raise ValueError(
                    f"{field_name} step_identity must be the exact step_identity"
                )


@dataclass(frozen=True, slots=True)
class SimulationStepResult:
    """Relate one exact aggregate input to its exact aggregate state."""

    simulation_input: SimulationStepInput
    state: SimulationState

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, SimulationStepInput):
            raise TypeError("simulation_input must be a SimulationStepInput")
        if not isinstance(self.state, SimulationState):
            raise TypeError("state must be a SimulationState")
        if self.state.step_identity is not self.simulation_input.step_identity:
            raise ValueError(
                "state.step_identity must be the exact input step_identity"
            )
        relationships = (
            ("pv_result", self.state.pv_result, self.simulation_input.pv_input),
            (
                "load_result",
                self.state.load_result,
                self.simulation_input.load_input,
            ),
            (
                "tariff_result",
                self.state.tariff_result,
                self.simulation_input.tariff_input,
            ),
            (
                "battery_result",
                self.state.battery_result,
                self.simulation_input.battery_input,
            ),
            (
                "grid_result",
                self.state.grid_result,
                self.simulation_input.grid_input,
            ),
        )
        for field_name, component_result, component_input in relationships:
            if component_result.simulation_input is not component_input:
                raise ValueError(
                    f"state.{field_name}.simulation_input must be the exact "
                    "aggregate component input"
                )


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """Preserve a caller-ordered tuple of immutable simulation step inputs."""

    steps: tuple[SimulationStepInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        for step in self.steps:
            if not isinstance(step, SimulationStepInput):
                raise TypeError("steps must contain only SimulationStepInput objects")
