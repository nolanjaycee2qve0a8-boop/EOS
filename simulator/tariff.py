"""Immutable contracts for tariff simulation observations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from simulator.core import SimulationStepIdentity
from simulator.validation import require_number


@dataclass(frozen=True, slots=True)
class TariffSimulationInput:
    """Preserve explicit facts supplied to one tariff simulation evaluation.

    Import and export prices are caller-supplied signed finite raw values in
    CNY per kWh. The step must contain an explicit timezone-aware timestamp.
    The input performs no tariff lookup, time conversion, price prediction,
    TOU selection, external API access, or clock read.
    """

    step_identity: SimulationStepIdentity
    import_price_cny_per_kwh: float
    export_price_cny_per_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        if self.step_identity.timestamp is None:
            raise ValueError("step_identity timestamp must be present for tariff input")
        object.__setattr__(
            self,
            "import_price_cny_per_kwh",
            require_number(
                self.import_price_cny_per_kwh,
                "import_price_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "export_price_cny_per_kwh",
            require_number(
                self.export_price_cny_per_kwh,
                "export_price_cny_per_kwh",
            ),
        )


@dataclass(frozen=True, slots=True)
class TariffSimulationResult:
    """Relate one exact tariff input to one simulated price observation.

    Result prices are signed finite raw values in CNY per kWh. The result does
    not explain, predict, select, scale, or calculate either price.
    """

    simulation_input: TariffSimulationInput
    import_price_cny_per_kwh: float
    export_price_cny_per_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, TariffSimulationInput):
            raise TypeError("simulation_input must be a TariffSimulationInput")
        object.__setattr__(
            self,
            "import_price_cny_per_kwh",
            require_number(
                self.import_price_cny_per_kwh,
                "import_price_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "export_price_cny_per_kwh",
            require_number(
                self.export_price_cny_per_kwh,
                "export_price_cny_per_kwh",
            ),
        )


class TariffSimulationModelBoundary(ABC):
    """Define a stateless extension point for one tariff simulation evaluation."""

    __slots__ = ()

    @abstractmethod
    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        """Return one result without mutating or retaining the input."""
        raise NotImplementedError
