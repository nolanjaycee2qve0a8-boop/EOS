"""Immutable base representation of an EOS energy asset."""

from dataclasses import dataclass

from kernel.asset.validation import require_non_empty_string
from kernel.ids import AssetId


@dataclass(frozen=True, slots=True)
class EnergyAsset:
    """Identify one named physical energy component."""

    asset_id: AssetId
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "asset_id",
            AssetId(require_non_empty_string(self.asset_id, "asset_id")),
        )
        object.__setattr__(
            self,
            "name",
            require_non_empty_string(self.name, "name"),
        )
