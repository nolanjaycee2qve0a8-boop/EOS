"""Immutable rated characteristics of a battery energy asset."""

from dataclasses import dataclass

from kernel.asset.base import EnergyAsset
from kernel.asset.validation import (
    require_non_negative_number,
    require_positive_number,
)


@dataclass(frozen=True, slots=True)
class BatteryAsset(EnergyAsset):
    """Describe battery capacity and charge/discharge power limits."""

    capacity_kwh: float
    max_charge_kw: float
    max_discharge_kw: float

    def __post_init__(self) -> None:
        EnergyAsset.__post_init__(self)
        object.__setattr__(
            self,
            "capacity_kwh",
            require_positive_number(self.capacity_kwh, "capacity_kwh"),
        )
        object.__setattr__(
            self,
            "max_charge_kw",
            require_non_negative_number(self.max_charge_kw, "max_charge_kw"),
        )
        object.__setattr__(
            self,
            "max_discharge_kw",
            require_non_negative_number(
                self.max_discharge_kw,
                "max_discharge_kw",
            ),
        )
