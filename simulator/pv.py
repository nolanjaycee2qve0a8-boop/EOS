"""Immutable contracts for photovoltaic simulation observations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from simulator.core import SimulationStepIdentity
from simulator.validation import require_non_negative_number


@dataclass(frozen=True, slots=True)
class PVSimulationInput:
    """Preserve explicit facts supplied to one PV simulation evaluation.

    ``available_power_kw`` is a caller-supplied, non-negative finite raw power
    value in kW. It is an exogenous simulation fact, not an MPPT calculation,
    inverter parameter, forecast, or device observation.
    """

    step_identity: SimulationStepIdentity
    available_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        object.__setattr__(
            self,
            "available_power_kw",
            require_non_negative_number(
                self.available_power_kw,
                "available_power_kw",
            ),
        )


@dataclass(frozen=True, slots=True)
class PVSimulationResult:
    """Relate one exact PV input to one simulated generation observation.

    ``actual_power_kw`` is non-negative finite generated power in raw kW and
    cannot exceed the input availability. The result does not explain or
    calculate how the observation was obtained.
    """

    simulation_input: PVSimulationInput
    actual_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, PVSimulationInput):
            raise TypeError("simulation_input must be a PVSimulationInput")
        actual_power_kw = require_non_negative_number(
            self.actual_power_kw,
            "actual_power_kw",
        )
        if actual_power_kw > self.simulation_input.available_power_kw:
            raise ValueError(
                "actual_power_kw must be less than or equal to available_power_kw"
            )
        object.__setattr__(self, "actual_power_kw", actual_power_kw)


class PVSimulationModelBoundary(ABC):
    """Define a stateless extension point for one PV simulation evaluation."""

    __slots__ = ()

    @abstractmethod
    def simulate(
        self,
        simulation_input: PVSimulationInput,
    ) -> PVSimulationResult:
        """Return one result without mutating or retaining the input."""
        raise NotImplementedError
