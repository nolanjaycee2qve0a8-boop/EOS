"""Aggregate existing typed battery-horizon constraint evidence only."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optimization.battery_power_constraint import (
    BatteryPowerHorizonConstraintEvaluation,
)
from optimization.battery_soc_constraint import BatterySOCHorizonConstraintEvaluation


@dataclass(frozen=True, slots=True)
class BatteryHorizonConstraintInput:
    """Compose compatible exact SOC and power horizon evaluations."""

    soc_evaluation: BatterySOCHorizonConstraintEvaluation
    power_evaluation: BatteryPowerHorizonConstraintEvaluation

    def __post_init__(self) -> None:
        if not isinstance(self.soc_evaluation, BatterySOCHorizonConstraintEvaluation):
            raise TypeError(
                "soc_evaluation must be a BatterySOCHorizonConstraintEvaluation"
            )
        if not isinstance(
            self.power_evaluation,
            BatteryPowerHorizonConstraintEvaluation,
        ):
            raise TypeError(
                "power_evaluation must be a BatteryPowerHorizonConstraintEvaluation"
            )

        soc_solution = self.soc_evaluation.source_input.projection.source_input.solution
        power_solution = self.power_evaluation.source_input.solution
        if soc_solution is not power_solution:
            raise ValueError(
                "SOC and power evaluations must preserve exact solution identity"
            )
        soc_model = self.soc_evaluation.source_input.battery_model
        power_model = self.power_evaluation.source_input.battery_model
        if soc_model is not power_model:
            raise ValueError(
                "SOC and power evaluations must preserve exact battery model identity"
            )


@dataclass(frozen=True, slots=True)
class BatteryHorizonConstraintEvaluation:
    """Report combined feasibility while retaining typed evidence via input."""

    source_input: BatteryHorizonConstraintInput
    feasible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, BatteryHorizonConstraintInput):
            raise TypeError("source_input must be a BatteryHorizonConstraintInput")
        if not isinstance(self.feasible, bool):
            raise TypeError("feasible must be a bool")
        expected_feasible = (
            self.source_input.soc_evaluation.feasible
            and self.source_input.power_evaluation.feasible
        )
        if self.feasible is not expected_feasible:
            raise ValueError(
                "feasible must equal the conjunction of component feasibility"
            )


class BatteryHorizonConstraintAggregateBoundary(ABC):
    """Define stateless aggregation of already-produced battery evidence."""

    __slots__ = ()

    @abstractmethod
    def aggregate(
        self,
        aggregate_input: BatteryHorizonConstraintInput,
    ) -> BatteryHorizonConstraintEvaluation:
        """Combine component feasibility without evaluating or correcting them."""
        raise NotImplementedError


class DeterministicBatteryHorizonConstraintAggregator(
    BatteryHorizonConstraintAggregateBoundary
):
    """Combine exact component feasibility without owning either evaluator."""

    __slots__ = ()

    def aggregate(
        self,
        aggregate_input: BatteryHorizonConstraintInput,
    ) -> BatteryHorizonConstraintEvaluation:
        if not isinstance(aggregate_input, BatteryHorizonConstraintInput):
            raise TypeError("aggregate_input must be a BatteryHorizonConstraintInput")
        feasible = (
            aggregate_input.soc_evaluation.feasible
            and aggregate_input.power_evaluation.feasible
        )
        return BatteryHorizonConstraintEvaluation(aggregate_input, feasible)
