"""Immutable contracts for grid simulation observations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from simulator.core import SimulationStepIdentity
from simulator.validation import require_number


@dataclass(frozen=True, slots=True)
class GridSimulationInput:
    """Preserve explicit facts supplied to one Grid model evaluation.

    ``requested_grid_power_kw`` is a signed finite raw value in kW. Positive
    means requested import from the grid, negative means requested export to
    the grid, and zero means balanced. It is a caller-supplied simulation fact,
    not a Command, grid-limit calculation, or power-balance calculation.
    """

    step_identity: SimulationStepIdentity
    requested_grid_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        object.__setattr__(
            self,
            "requested_grid_power_kw",
            require_number(
                self.requested_grid_power_kw,
                "requested_grid_power_kw",
            ),
        )


@dataclass(frozen=True, slots=True)
class GridSimulationResult:
    """Relate one exact Grid input to one exchange observation.

    ``actual_grid_power_kw`` is signed finite raw kW. Positive means import
    from the grid, negative means export to the grid, and zero means balanced.
    The result does not calculate, constrain, or execute this exchange.
    """

    simulation_input: GridSimulationInput
    actual_grid_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, GridSimulationInput):
            raise TypeError("simulation_input must be a GridSimulationInput")
        object.__setattr__(
            self,
            "actual_grid_power_kw",
            require_number(self.actual_grid_power_kw, "actual_grid_power_kw"),
        )


class GridSimulationModelBoundary(ABC):
    """Define a stateless extension point for one Grid simulation evaluation."""

    __slots__ = ()

    @abstractmethod
    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        """Return one result without mutating or retaining the input."""
        raise NotImplementedError
