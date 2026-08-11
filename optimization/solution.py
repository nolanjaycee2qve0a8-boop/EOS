"""Immutable solver-output payload contracts without plan representation logic."""

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
class OptimizationSolutionStep:
    """Represent one explicit solved planning value, not an EOS control step.

    Action direction remains semantic through ``DecisionIntent`` and the
    raw-kW magnitude is non-negative. This artifact is solver output only;
    control-plan construction remains a separate boundary.
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
class OptimizationSolution:
    """Preserve concrete planning values for one exact generic outcome.

    The solution retains an exact source ``OptimizationResult`` and its exact
    caller-provided tuple of solved points. It does not form or execute an EOS
    control plan, invoke a solver, or derive physical feasibility.
    """

    source_result: OptimizationResult
    steps: tuple[OptimizationSolutionStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, OptimizationResult):
            raise TypeError("source_result must be an OptimizationResult")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        previous_timestamp: datetime | None = None
        for step in self.steps:
            if not isinstance(step, OptimizationSolutionStep):
                raise TypeError("steps must contain OptimizationSolutionStep objects")
            if previous_timestamp is not None and step.timestamp <= previous_timestamp:
                raise ValueError("steps must be in strictly increasing timestamp order")
            previous_timestamp = step.timestamp
