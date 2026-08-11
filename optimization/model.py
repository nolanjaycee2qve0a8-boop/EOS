"""Solver-independent immutable optimization request and outcome contracts."""

from dataclasses import dataclass
from typing import Literal

from ems_strategy.context import EMSContext
from forecast import ForecastHorizon

OptimizationSense = Literal["minimize", "maximize"]
OptimizationOutcome = Literal["optimal", "infeasible", "unavailable"]


@dataclass(frozen=True, slots=True)
class OptimizationObjective:
    """Describe one semantic concern without an executable cost function.

    ``name`` identifies the concern and ``sense`` declares only whether a
    future solver should minimize or maximize it. This contract contains no
    weight calculation, callback, matrix, model, or framework-specific object.
    """

    name: str
    sense: OptimizationSense

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a str")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if self.sense not in ("minimize", "maximize"):
            raise ValueError("sense must be 'minimize' or 'maximize'")


@dataclass(frozen=True, slots=True)
class OptimizationObjectiveCollection:
    """Retain caller-defined objective references in exact tuple order.

    The collection does not sort, deduplicate, normalize, score, or alter
    objective semantics. Individual objective identities remain intact.
    """

    objectives: tuple[OptimizationObjective, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.objectives, tuple):
            raise TypeError("objectives must be a tuple")
        for objective in self.objectives:
            if not isinstance(objective, OptimizationObjective):
                raise TypeError(
                    "objectives must contain OptimizationObjective instances"
                )


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    """Preserve one immutable optimization request without solving it.

    Current measured facts, future predictions, and semantic objective
    references are retained exactly as supplied. The request is solver-
    independent: it has no matrices, cost callbacks, constraint equations,
    state prediction, or serialized provenance.
    """

    context: EMSContext
    forecast_horizon: ForecastHorizon
    objectives: OptimizationObjectiveCollection

    def __post_init__(self) -> None:
        if not isinstance(self.context, EMSContext):
            raise TypeError("context must be an EMSContext")
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.objectives, OptimizationObjectiveCollection):
            raise TypeError("objectives must be an OptimizationObjectiveCollection")
        if not self.objectives.objectives:
            raise ValueError("objectives must contain at least one objective")


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Describe a generic outcome while retaining exact problem provenance.

    The result is neither an ``EMSDecision``, a feasible decision, a Simulator
    actuation, nor a device command. A future MPC Strategy may interpret an
    outcome and produce the current semantic decision through the existing
    Strategy contract.
    """

    source_problem: OptimizationProblem
    outcome: OptimizationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.source_problem, OptimizationProblem):
            raise TypeError("source_problem must be an OptimizationProblem")
        if self.outcome not in ("optimal", "infeasible", "unavailable"):
            raise ValueError(
                "outcome must be 'optimal', 'infeasible', or 'unavailable'"
            )
