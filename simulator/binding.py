"""Immutable caller-supplied simulation model binding contracts."""

from dataclasses import dataclass

from simulator.battery import BatterySimulationModelBoundary
from simulator.grid import GridSimulationModelBoundary
from simulator.load import LoadSimulationModelBoundary
from simulator.pv import PVSimulationModelBoundary
from simulator.tariff import TariffSimulationModelBoundary

type _ModelContract = (
    type[PVSimulationModelBoundary]
    | type[LoadSimulationModelBoundary]
    | type[TariffSimulationModelBoundary]
    | type[BatterySimulationModelBoundary]
    | type[GridSimulationModelBoundary]
)
type _Model = (
    PVSimulationModelBoundary
    | LoadSimulationModelBoundary
    | TariffSimulationModelBoundary
    | BatterySimulationModelBoundary
    | GridSimulationModelBoundary
)

_MODEL_CONTRACTS: tuple[_ModelContract, ...] = (
    PVSimulationModelBoundary,
    LoadSimulationModelBoundary,
    TariffSimulationModelBoundary,
    BatterySimulationModelBoundary,
    GridSimulationModelBoundary,
)


@dataclass(frozen=True, slots=True, eq=False)
class SimulationModelBinding:
    """Relate one exact component contract to one exact caller model.

    Binding expresses an ownership/reference relationship only. It does not
    execute, select, create, or manage models. Identity-based equality prevents
    a reconstructed binding with equal field values from substituting for the
    original artifact.
    """

    component_contract: _ModelContract
    model: _Model

    def __post_init__(self) -> None:
        for expected_contract in _MODEL_CONTRACTS:
            if self.component_contract is expected_contract:
                if not isinstance(self.model, expected_contract):
                    raise TypeError("model must implement the exact component_contract")
                return
        raise TypeError("component_contract must be a simulation model boundary")


@dataclass(frozen=True, slots=True, eq=False)
class SimulationModelBindingCollection:
    """Preserve an exact caller-ordered tuple of exact model bindings.

    The collection performs no sorting, deduplication, normalization,
    completion, lookup, selection, model creation, or model execution.
    """

    bindings: tuple[SimulationModelBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            raise TypeError("bindings must be a tuple")
        for binding in self.bindings:
            if not isinstance(binding, SimulationModelBinding):
                raise TypeError(
                    "bindings must contain only SimulationModelBinding objects"
                )
