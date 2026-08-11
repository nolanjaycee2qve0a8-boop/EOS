"""Deterministic battery SOC horizon projection without feasibility behavior."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import BatteryOptimizationInput
from optimization.solution import OptimizationSolution, OptimizationSolutionStep


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_positive_seconds(value: object) -> float:
    normalized = _require_finite_number(value, "control_step_duration_seconds")
    if normalized <= 0:
        raise ValueError("control_step_duration_seconds must be greater than 0")
    return normalized


@dataclass(frozen=True, slots=True)
class BatterySOCHorizonProjectionInput:
    """Preserve exact planning facts and solved values for one projection."""

    battery_input: BatteryOptimizationInput
    solution: OptimizationSolution
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.battery_input, BatteryOptimizationInput):
            raise TypeError("battery_input must be a BatteryOptimizationInput")
        if not isinstance(self.solution, OptimizationSolution):
            raise TypeError("solution must be an OptimizationSolution")
        if self.solution.source_result.source_problem is not self.battery_input.problem:
            raise ValueError(
                "solution must preserve exact battery input problem identity"
            )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class BatterySOCProjectionStep:
    """Record one mathematical SOC transition from one exact solution step."""

    source_step: OptimizationSolutionStep
    starting_soc_fraction: float
    ending_soc_fraction: float
    battery_energy_delta_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_step, OptimizationSolutionStep):
            raise TypeError("source_step must be an OptimizationSolutionStep")
        object.__setattr__(
            self,
            "starting_soc_fraction",
            _require_finite_number(
                self.starting_soc_fraction,
                "starting_soc_fraction",
            ),
        )
        object.__setattr__(
            self,
            "ending_soc_fraction",
            _require_finite_number(
                self.ending_soc_fraction,
                "ending_soc_fraction",
            ),
        )
        object.__setattr__(
            self,
            "battery_energy_delta_kwh",
            _require_finite_number(
                self.battery_energy_delta_kwh,
                "battery_energy_delta_kwh",
            ),
        )


@dataclass(frozen=True, slots=True)
class BatterySOCHorizonProjection:
    """Preserve an ordered mathematical SOC trajectory for one exact input."""

    source_input: BatterySOCHorizonProjectionInput
    steps: tuple[BatterySOCProjectionStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, BatterySOCHorizonProjectionInput):
            raise TypeError("source_input must be a BatterySOCHorizonProjectionInput")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        source_steps = self.source_input.solution.steps
        if len(self.steps) != len(source_steps):
            raise ValueError("steps must match the source solution step count")
        for projection_step, source_step in zip(self.steps, source_steps, strict=True):
            if not isinstance(projection_step, BatterySOCProjectionStep):
                raise TypeError("steps must contain BatterySOCProjectionStep objects")
            if projection_step.source_step is not source_step:
                raise ValueError("steps must preserve exact source step identity")


class BatterySOCHorizonProjectionBoundary(ABC):
    """Define stateless mathematical projection of one explicit horizon."""

    __slots__ = ()

    @abstractmethod
    def project(
        self,
        projection_input: BatterySOCHorizonProjectionInput,
    ) -> BatterySOCHorizonProjection:
        """Return one ordered SOC trajectory without modifying the source plan."""
        raise NotImplementedError


class DeterministicBatterySOCHorizonProjector(BatterySOCHorizonProjectionBoundary):
    """Project every caller-ordered solution step once using planning physics."""

    __slots__ = ()

    def project(
        self,
        projection_input: BatterySOCHorizonProjectionInput,
    ) -> BatterySOCHorizonProjection:
        if not isinstance(projection_input, BatterySOCHorizonProjectionInput):
            raise TypeError(
                "projection_input must be a BatterySOCHorizonProjectionInput"
            )
        battery_model = projection_input.battery_input.battery_model
        duration_hours = projection_input.control_step_duration_seconds / 3600.0
        current_soc = projection_input.battery_input.battery_state.soc_fraction
        steps: list[BatterySOCProjectionStep] = []
        for source_step in projection_input.solution.steps:
            energy_delta = self._energy_delta_kwh(
                source_step,
                duration_hours,
                battery_model.charge_efficiency,
                battery_model.discharge_efficiency,
            )
            ending_soc = current_soc + energy_delta / battery_model.usable_capacity_kwh
            projection_step = BatterySOCProjectionStep(
                source_step,
                current_soc,
                ending_soc,
                energy_delta,
            )
            steps.append(projection_step)
            current_soc = projection_step.ending_soc_fraction
        return BatterySOCHorizonProjection(projection_input, tuple(steps))

    @staticmethod
    def _energy_delta_kwh(
        source_step: OptimizationSolutionStep,
        duration_hours: float,
        charge_efficiency: float,
        discharge_efficiency: float,
    ) -> float:
        if source_step.intent.action == "charge":
            return source_step.requested_power_kw * duration_hours * charge_efficiency
        if source_step.intent.action == "discharge":
            return -(
                source_step.requested_power_kw * duration_hours / discharge_efficiency
            )
        return 0.0
