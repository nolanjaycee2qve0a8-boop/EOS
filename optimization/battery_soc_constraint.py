"""SOC-horizon constraint evidence without modifying a proposed solution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from optimization.battery_planning import BatteryOptimizationModel
from optimization.battery_soc_projection import (
    BatterySOCHorizonProjection,
    BatterySOCProjectionStep,
)

BatterySOCConstraintViolationKind = Literal["below_min_soc", "above_max_soc"]


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class BatterySOCHorizonConstraintInput:
    """Compose one exact SOC projection with its exact planning model."""

    projection: BatterySOCHorizonProjection
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(self.projection, BatterySOCHorizonProjection):
            raise TypeError("projection must be a BatterySOCHorizonProjection")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        if (
            self.battery_model
            is not self.projection.source_input.battery_input.battery_model
        ):
            raise ValueError(
                "battery_model must preserve exact projection planning model identity"
            )


@dataclass(frozen=True, slots=True)
class BatterySOCConstraintViolation:
    """Record one exact projected endpoint outside one SOC planning bound."""

    source_projection_step: BatterySOCProjectionStep
    step_index: int
    kind: BatterySOCConstraintViolationKind
    soc_fraction: float
    limit_soc_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_projection_step, BatterySOCProjectionStep):
            raise TypeError("source_projection_step must be a BatterySOCProjectionStep")
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int):
            raise TypeError("step_index must be an integer")
        if self.step_index < 0:
            raise ValueError("step_index must be greater than or equal to 0")
        if self.kind not in ("below_min_soc", "above_max_soc"):
            raise ValueError("kind must be below_min_soc or above_max_soc")
        object.__setattr__(
            self,
            "soc_fraction",
            _require_finite_number(self.soc_fraction, "soc_fraction"),
        )
        object.__setattr__(
            self,
            "limit_soc_fraction",
            _require_finite_number(self.limit_soc_fraction, "limit_soc_fraction"),
        )


@dataclass(frozen=True, slots=True)
class BatterySOCHorizonConstraintEvaluation:
    """Preserve ordered SOC-bound violation evidence for one exact input."""

    source_input: BatterySOCHorizonConstraintInput
    feasible: bool
    violations: tuple[BatterySOCConstraintViolation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, BatterySOCHorizonConstraintInput):
            raise TypeError("source_input must be a BatterySOCHorizonConstraintInput")
        if not isinstance(self.feasible, bool):
            raise TypeError("feasible must be a bool")
        if not isinstance(self.violations, tuple):
            raise TypeError("violations must be a tuple")
        if self.feasible is not (not self.violations):
            raise ValueError(
                "feasible must be true if and only if violations are empty"
            )

        previous_index = -1
        projection_steps = self.source_input.projection.steps
        model = self.source_input.battery_model
        for violation in self.violations:
            if not isinstance(violation, BatterySOCConstraintViolation):
                raise TypeError("violations must contain BatterySOCConstraintViolation")
            if violation.step_index >= len(projection_steps):
                raise ValueError(
                    "violation step_index must reference a projection step"
                )
            if violation.step_index <= previous_index:
                raise ValueError(
                    "violations must preserve strict projection step order"
                )
            source_step = projection_steps[violation.step_index]
            if violation.source_projection_step is not source_step:
                raise ValueError(
                    "violation must preserve exact projection step identity"
                )
            if violation.soc_fraction != source_step.ending_soc_fraction:
                raise ValueError(
                    "violation SOC must preserve the projection ending SOC"
                )
            if violation.kind == "below_min_soc":
                if violation.limit_soc_fraction != model.min_soc_fraction:
                    raise ValueError(
                        "below-min violation must preserve the minimum SOC"
                    )
                if violation.soc_fraction >= model.min_soc_fraction:
                    raise ValueError(
                        "below-min violation SOC must be below the minimum"
                    )
            else:
                if violation.limit_soc_fraction != model.max_soc_fraction:
                    raise ValueError(
                        "above-max violation must preserve the maximum SOC"
                    )
                if violation.soc_fraction <= model.max_soc_fraction:
                    raise ValueError(
                        "above-max violation SOC must be above the maximum"
                    )
            previous_index = violation.step_index


class BatterySOCHorizonConstraintBoundary(ABC):
    """Define stateless SOC-bound evidence evaluation for one projection."""

    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        constraint_input: BatterySOCHorizonConstraintInput,
    ) -> BatterySOCHorizonConstraintEvaluation:
        """Return all endpoint-bound violations without altering the projection."""
        raise NotImplementedError


class DeterministicBatterySOCHorizonConstraintEvaluator(
    BatterySOCHorizonConstraintBoundary
):
    """Evaluate every projected endpoint once in existing projection order."""

    __slots__ = ()

    def evaluate(
        self,
        constraint_input: BatterySOCHorizonConstraintInput,
    ) -> BatterySOCHorizonConstraintEvaluation:
        if not isinstance(constraint_input, BatterySOCHorizonConstraintInput):
            raise TypeError(
                "constraint_input must be a BatterySOCHorizonConstraintInput"
            )
        model = constraint_input.battery_model
        violations: list[BatterySOCConstraintViolation] = []
        for step_index, projection_step in enumerate(constraint_input.projection.steps):
            ending_soc = projection_step.ending_soc_fraction
            if ending_soc < model.min_soc_fraction:
                violations.append(
                    BatterySOCConstraintViolation(
                        projection_step,
                        step_index,
                        "below_min_soc",
                        ending_soc,
                        model.min_soc_fraction,
                    )
                )
            elif ending_soc > model.max_soc_fraction:
                violations.append(
                    BatterySOCConstraintViolation(
                        projection_step,
                        step_index,
                        "above_max_soc",
                        ending_soc,
                        model.max_soc_fraction,
                    )
                )
        supplied_violations = tuple(violations)
        return BatterySOCHorizonConstraintEvaluation(
            constraint_input,
            not supplied_violations,
            supplied_violations,
        )
