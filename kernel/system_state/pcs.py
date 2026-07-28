"""Immutable factual state of the power conversion system."""

from dataclasses import dataclass

from kernel.system_state.validation import (
    require_non_empty_string,
    require_number,
)


@dataclass(frozen=True, slots=True)
class PCSState:
    """Observe PCS facts without issuing control commands.

    Active power is in kW: positive means AC output to the load or grid, while
    negative means AC absorption from the grid or battery side. Reactive power
    is a signed finite observation in kVAr. State labels are non-empty strings.
    """

    active_power_kw: float
    reactive_power_kvar: float
    operating_state: str
    fault_state: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "active_power_kw",
            require_number(self.active_power_kw, "active_power_kw"),
        )
        object.__setattr__(
            self,
            "reactive_power_kvar",
            require_number(self.reactive_power_kvar, "reactive_power_kvar"),
        )
        object.__setattr__(
            self,
            "operating_state",
            require_non_empty_string(self.operating_state, "operating_state"),
        )
        object.__setattr__(
            self,
            "fault_state",
            require_non_empty_string(self.fault_state, "fault_state"),
        )
