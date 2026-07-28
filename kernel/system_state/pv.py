"""Immutable factual state of photovoltaic generation."""

from dataclasses import dataclass

from kernel.system_state.validation import require_non_negative_number


@dataclass(frozen=True, slots=True)
class PVState:
    """Observe non-negative available and actual PV power in kW."""

    available_power_kw: float
    actual_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "available_power_kw",
            require_non_negative_number(
                self.available_power_kw,
                "available_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "actual_power_kw",
            require_non_negative_number(self.actual_power_kw, "actual_power_kw"),
        )
