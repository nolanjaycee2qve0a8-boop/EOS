"""Battery power-horizon constraint evidence without altering a solution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from optimization.battery_planning import BatteryOptimizationModel
from optimization.solution import OptimizationSolution, OptimizationSolutionStep

BatteryPowerConstraintViolationKind = Literal[
    "charge_power_above_max",
    "discharge_power_above_max",
]


def _require_finite_nonnegative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


def _require_finite_positive_number(value: object, field_name: str) -> float:
    normalized = _require_finite_nonnegative_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


@dataclass(frozen=True, slots=True)
class BatteryPowerHorizonConstraintInput:
    """Preserve exact caller-supplied solution and planning power model facts."""

    solution: OptimizationSolution
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(self.solution, OptimizationSolution):
            raise TypeError("solution must be an OptimizationSolution")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")


@dataclass(frozen=True, slots=True)
class BatteryPowerConstraintViolation:
    """Record one exact solution-step request above its directional limit."""

    source_step: OptimizationSolutionStep
    step_index: int
    kind: BatteryPowerConstraintViolationKind
    requested_power_kw: float
    limit_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_step, OptimizationSolutionStep):
            raise TypeError("source_step must be an OptimizationSolutionStep")
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int):
            raise TypeError("step_index must be an integer")
        if self.step_index < 0:
            raise ValueError("step_index must be greater than or equal to 0")
        if self.kind not in (
            "charge_power_above_max",
            "discharge_power_above_max",
        ):
            raise ValueError(
                "kind must be charge_power_above_max or discharge_power_above_max"
            )
        object.__setattr__(
            self,
            "requested_power_kw",
            _require_finite_nonnegative_number(
                self.requested_power_kw,
                "requested_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "limit_power_kw",
            _require_finite_positive_number(self.limit_power_kw, "limit_power_kw"),
        )


@dataclass(frozen=True, slots=True)
class BatteryPowerHorizonConstraintEvaluation:
    """Preserve ordered battery-power violation evidence for one exact input."""

    source_input: BatteryPowerHorizonConstraintInput
    feasible: bool
    violations: tuple[BatteryPowerConstraintViolation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, BatteryPowerHorizonConstraintInput):
            raise TypeError("source_input must be a BatteryPowerHorizonConstraintInput")
        if not isinstance(self.feasible, bool):
            raise TypeError("feasible must be a bool")
        if not isinstance(self.violations, tuple):
            raise TypeError("violations must be a tuple")
        if self.feasible is not (not self.violations):
            raise ValueError(
                "feasible must be true if and only if violations are empty"
            )

        previous_index = -1
        solution_steps = self.source_input.solution.steps
        model = self.source_input.battery_model
        for violation in self.violations:
            if not isinstance(violation, BatteryPowerConstraintViolation):
                raise TypeError(
                    "violations must contain BatteryPowerConstraintViolation"
                )
            if violation.step_index >= len(solution_steps):
                raise ValueError("violation step_index must reference a solution step")
            if violation.step_index <= previous_index:
                raise ValueError("violations must preserve strict solution step order")
            source_step = solution_steps[violation.step_index]
            if violation.source_step is not source_step:
                raise ValueError("violation must preserve exact solution step identity")
            if violation.requested_power_kw != source_step.requested_power_kw:
                raise ValueError(
                    "violation requested power must preserve the solution step power"
                )
            if violation.kind == "charge_power_above_max":
                if source_step.intent.action != "charge":
                    raise ValueError("charge violation must reference a charge step")
                if violation.limit_power_kw != model.max_charge_power_kw:
                    raise ValueError("charge violation must preserve the charge limit")
                if violation.requested_power_kw <= model.max_charge_power_kw:
                    raise ValueError(
                        "charge violation power must exceed the charge limit"
                    )
            else:
                if source_step.intent.action != "discharge":
                    raise ValueError(
                        "discharge violation must reference a discharge step"
                    )
                if violation.limit_power_kw != model.max_discharge_power_kw:
                    raise ValueError(
                        "discharge violation must preserve the discharge limit"
                    )
                if violation.requested_power_kw <= model.max_discharge_power_kw:
                    raise ValueError(
                        "discharge violation power must exceed the discharge limit"
                    )
            previous_index = violation.step_index


class BatteryPowerHorizonConstraintBoundary(ABC):
    """Define stateless power-envelope evidence evaluation for one solution."""

    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        constraint_input: BatteryPowerHorizonConstraintInput,
    ) -> BatteryPowerHorizonConstraintEvaluation:
        """Return all directional power violations without altering the solution."""
        raise NotImplementedError


class DeterministicBatteryPowerHorizonConstraintEvaluator(
    BatteryPowerHorizonConstraintBoundary
):
    """Evaluate every solution step once in its exact caller-supplied order."""

    __slots__ = ()

    def evaluate(
        self,
        constraint_input: BatteryPowerHorizonConstraintInput,
    ) -> BatteryPowerHorizonConstraintEvaluation:
        if not isinstance(constraint_input, BatteryPowerHorizonConstraintInput):
            raise TypeError(
                "constraint_input must be a BatteryPowerHorizonConstraintInput"
            )
        model = constraint_input.battery_model
        violations: list[BatteryPowerConstraintViolation] = []
        for step_index, source_step in enumerate(constraint_input.solution.steps):
            requested_power = source_step.requested_power_kw
            if (
                source_step.intent.action == "charge"
                and requested_power > model.max_charge_power_kw
            ):
                violations.append(
                    BatteryPowerConstraintViolation(
                        source_step,
                        step_index,
                        "charge_power_above_max",
                        requested_power,
                        model.max_charge_power_kw,
                    )
                )
            elif (
                source_step.intent.action == "discharge"
                and requested_power > model.max_discharge_power_kw
            ):
                violations.append(
                    BatteryPowerConstraintViolation(
                        source_step,
                        step_index,
                        "discharge_power_above_max",
                        requested_power,
                        model.max_discharge_power_kw,
                    )
                )
        supplied_violations = tuple(violations)
        return BatteryPowerHorizonConstraintEvaluation(
            constraint_input,
            not supplied_violations,
            supplied_violations,
        )
