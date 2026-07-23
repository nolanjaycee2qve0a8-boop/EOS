"""Immutable operational observation of a battery asset."""

from dataclasses import dataclass

from kernel.ids import AssetId
from kernel.state.validation import (
    require_non_empty_string,
    require_number,
    require_unit_interval,
)


@dataclass(frozen=True, slots=True)
class BatteryState:
    """Record observed battery state without calculating it."""

    asset_id: AssetId
    soc: float
    power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "asset_id",
            AssetId(require_non_empty_string(self.asset_id, "asset_id")),
        )
        object.__setattr__(
            self,
            "soc",
            require_unit_interval(self.soc, "soc"),
        )
        object.__setattr__(
            self,
            "power_kw",
            require_number(self.power_kw, "power_kw"),
        )
