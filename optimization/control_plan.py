"""Immutable future control-sequence contracts for optimization outcomes."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from decision_formation import DecisionIntent
from optimization.model import OptimizationResult


def _require_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_requested_power(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("requested_power_kw must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError("requested_power_kw must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class OptimizationControlStep:
    """Describe one future semantic battery request with a raw-kW magnitude.

    ``timestamp`` is caller supplied and explicit. The existing semantic
    ``DecisionIntent`` carries action direction; ``requested_power_kw`` is
    always a non-negative magnitude. This artifact is a proposed plan step,
    not a physical execution instruction.
    """

    timestamp: datetime
    intent: DecisionIntent
    requested_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            _require_timezone_aware_datetime(self.timestamp, "timestamp"),
        )
        if not isinstance(self.intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")
        requested_power_kw = _require_requested_power(self.requested_power_kw)
        if self.intent.action == "idle" and requested_power_kw != 0:
            raise ValueError("idle intent requires requested_power_kw equal to 0")
        if self.intent.action != "idle" and requested_power_kw == 0:
            raise ValueError(
                "charge and discharge intents require requested_power_kw greater than 0"
            )
        object.__setattr__(self, "requested_power_kw", requested_power_kw)


@dataclass(frozen=True, slots=True)
class OptimizationControlPlan:
    """Preserve one ordered finite plan with exact optimization provenance.

    The plan retains the exact ``source_result`` and caller-supplied tuple of
    steps. It neither generates timestamps, reorders steps, advances a
    horizon, evaluates feasibility, nor executes the proposed sequence.
    """

    source_result: OptimizationResult
    steps: tuple[OptimizationControlStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, OptimizationResult):
            raise TypeError("source_result must be an OptimizationResult")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        previous_timestamp: datetime | None = None
        for step in self.steps:
            if not isinstance(step, OptimizationControlStep):
                raise TypeError("steps must contain OptimizationControlStep objects")
            if previous_timestamp is not None and step.timestamp <= previous_timestamp:
                raise ValueError("steps must be in strictly increasing timestamp order")
            previous_timestamp = step.timestamp
