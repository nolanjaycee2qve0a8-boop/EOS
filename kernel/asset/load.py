"""Immutable rated characteristics of an electrical load asset."""

from dataclasses import dataclass

from kernel.asset.base import EnergyAsset
from kernel.asset.validation import require_positive_number


@dataclass(frozen=True, slots=True)
class LoadAsset(EnergyAsset):
    """Describe an electrical load's rated power."""

    rated_power_kw: float

    def __post_init__(self) -> None:
        EnergyAsset.__post_init__(self)
        object.__setattr__(
            self,
            "rated_power_kw",
            require_positive_number(self.rated_power_kw, "rated_power_kw"),
        )
