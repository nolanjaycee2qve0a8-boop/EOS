"""Immutable operational observation of a photovoltaic asset."""

from dataclasses import dataclass

from kernel.ids import AssetId
from kernel.state.validation import (
    require_non_empty_string,
    require_non_negative_number,
)


@dataclass(frozen=True, slots=True)
class PVState:
    """Record observed non-negative photovoltaic output power."""

    asset_id: AssetId
    power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "asset_id",
            AssetId(require_non_empty_string(self.asset_id, "asset_id")),
        )
        object.__setattr__(
            self,
            "power_kw",
            require_non_negative_number(self.power_kw, "power_kw"),
        )
