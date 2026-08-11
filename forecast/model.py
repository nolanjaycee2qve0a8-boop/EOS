"""Immutable future prediction artifacts without prediction behavior."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


def _require_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_non_negative_number(value: object, field_name: str) -> float:
    normalized = _require_number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """Describe caller-supplied predictions for one exact future timestamp.

    PV and Load predictions are non-negative finite raw kW values. An optional
    price is a signed finite raw CNY per kWh value. This artifact does not
    predict, normalize, interpolate, or retrieve any fact.
    """

    timestamp: datetime
    pv_power_kw: float
    load_power_kw: float
    electricity_price_cny_per_kwh: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            _require_timezone_aware_datetime(self.timestamp, "timestamp"),
        )
        object.__setattr__(
            self,
            "pv_power_kw",
            _require_non_negative_number(self.pv_power_kw, "pv_power_kw"),
        )
        object.__setattr__(
            self,
            "load_power_kw",
            _require_non_negative_number(self.load_power_kw, "load_power_kw"),
        )
        if self.electricity_price_cny_per_kwh is not None:
            object.__setattr__(
                self,
                "electricity_price_cny_per_kwh",
                _require_number(
                    self.electricity_price_cny_per_kwh,
                    "electricity_price_cny_per_kwh",
                ),
            )


@dataclass(frozen=True, slots=True)
class ForecastHorizon:
    """Preserve a caller-ordered, strictly increasing sequence of forecast points.

    The exact caller-supplied tuple and all point references are retained. The
    caller declares the timestamps as future information; this contract reads
    no current clock to determine that relationship. The horizon accepts an
    empty tuple and performs no point creation, sorting, deduplication,
    selection, optimization, or strategy evaluation.
    """

    points: tuple[ForecastPoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple):
            raise TypeError("points must be a tuple")
        previous_timestamp: datetime | None = None
        for point in self.points:
            if not isinstance(point, ForecastPoint):
                raise TypeError("points must contain only ForecastPoint objects")
            if previous_timestamp is not None and point.timestamp <= previous_timestamp:
                raise ValueError(
                    "points must be in strictly increasing timestamp order"
                )
            previous_timestamp = point.timestamp
