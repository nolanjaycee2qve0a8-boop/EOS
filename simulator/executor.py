"""Stateless deterministic execution of one explicit simulation step."""

from typing import cast

from simulator.aggregate import (
    SimulationState,
    SimulationStepInput,
    SimulationStepResult,
)
from simulator.battery import (
    BatterySimulationModelBoundary,
    BatterySimulationResult,
)
from simulator.binding import (
    SimulationModelBindingCollection,
)
from simulator.grid import GridSimulationModelBoundary, GridSimulationResult
from simulator.load import LoadSimulationModelBoundary, LoadSimulationResult
from simulator.pv import PVSimulationModelBoundary, PVSimulationResult
from simulator.tariff import TariffSimulationModelBoundary, TariffSimulationResult

type _RequiredContract = (
    type[PVSimulationModelBoundary]
    | type[LoadSimulationModelBoundary]
    | type[TariffSimulationModelBoundary]
    | type[BatterySimulationModelBoundary]
    | type[GridSimulationModelBoundary]
)

_REQUIRED_CONTRACTS: tuple[_RequiredContract, ...] = (
    PVSimulationModelBoundary,
    LoadSimulationModelBoundary,
    TariffSimulationModelBoundary,
    BatterySimulationModelBoundary,
    GridSimulationModelBoundary,
)


class SingleStepSimulationExecutor:
    """Execute each exact caller-bound component model once for one step."""

    __slots__ = ()

    @staticmethod
    def execute(
        simulation_input: SimulationStepInput,
        bindings: SimulationModelBindingCollection,
    ) -> SimulationStepResult:
        """Return one exact step result without retaining models or state."""
        if not isinstance(simulation_input, SimulationStepInput):
            raise TypeError("simulation_input must be a SimulationStepInput")
        if not isinstance(bindings, SimulationModelBindingCollection):
            raise TypeError("bindings must be a SimulationModelBindingCollection")

        SingleStepSimulationExecutor._validate_complete_bindings(bindings)

        pv_result: PVSimulationResult | None = None
        load_result: LoadSimulationResult | None = None
        tariff_result: TariffSimulationResult | None = None
        battery_result: BatterySimulationResult | None = None
        grid_result: GridSimulationResult | None = None

        for binding in bindings.bindings:
            if binding.component_contract is PVSimulationModelBoundary:
                pv_model = cast(PVSimulationModelBoundary, binding.model)
                pv_component_result = pv_model.simulate(simulation_input.pv_input)
                if not isinstance(pv_component_result, PVSimulationResult):
                    raise TypeError("PV model must return a PVSimulationResult")
                pv_result = pv_component_result
            elif binding.component_contract is LoadSimulationModelBoundary:
                load_model = cast(LoadSimulationModelBoundary, binding.model)
                load_component_result = load_model.simulate(simulation_input.load_input)
                if not isinstance(load_component_result, LoadSimulationResult):
                    raise TypeError("Load model must return a LoadSimulationResult")
                load_result = load_component_result
            elif binding.component_contract is TariffSimulationModelBoundary:
                tariff_model = cast(TariffSimulationModelBoundary, binding.model)
                tariff_component_result = tariff_model.simulate(
                    simulation_input.tariff_input
                )
                if not isinstance(tariff_component_result, TariffSimulationResult):
                    raise TypeError("Tariff model must return a TariffSimulationResult")
                tariff_result = tariff_component_result
            elif binding.component_contract is BatterySimulationModelBoundary:
                battery_model = cast(BatterySimulationModelBoundary, binding.model)
                battery_component_result = battery_model.simulate(
                    simulation_input.battery_input
                )
                if not isinstance(
                    battery_component_result,
                    BatterySimulationResult,
                ):
                    raise TypeError(
                        "Battery model must return a BatterySimulationResult"
                    )
                battery_result = battery_component_result
            else:
                grid_model = cast(GridSimulationModelBoundary, binding.model)
                grid_component_result = grid_model.simulate(simulation_input.grid_input)
                if not isinstance(grid_component_result, GridSimulationResult):
                    raise TypeError("Grid model must return a GridSimulationResult")
                grid_result = grid_component_result

        if pv_result is None:
            raise AssertionError("validated PV binding must produce a result")
        if load_result is None:
            raise AssertionError("validated Load binding must produce a result")
        if tariff_result is None:
            raise AssertionError("validated Tariff binding must produce a result")
        if battery_result is None:
            raise AssertionError("validated Battery binding must produce a result")
        if grid_result is None:
            raise AssertionError("validated Grid binding must produce a result")

        state = SimulationState(
            simulation_input.step_identity,
            pv_result,
            load_result,
            tariff_result,
            battery_result,
            grid_result,
        )
        return SimulationStepResult(simulation_input, state)

    @staticmethod
    def _validate_complete_bindings(
        bindings: SimulationModelBindingCollection,
    ) -> None:
        for required_contract in _REQUIRED_CONTRACTS:
            matching = sum(
                binding.component_contract is required_contract
                for binding in bindings.bindings
            )
            if matching != 1:
                raise ValueError(
                    "bindings must contain exactly one "
                    f"{required_contract.__name__} binding"
                )
