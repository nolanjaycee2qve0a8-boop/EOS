"""Abstract provenance-preserving construction seam for control plans."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optimization.control_plan import OptimizationControlPlan
from optimization.model import OptimizationResult


@dataclass(frozen=True, slots=True)
class OptimizationControlPlanConstructionInput:
    """Preserve one exact optimization outcome for plan representation.

    This artifact carries only the caller-supplied result. It does not create
    steps, invoke a solver, derive state, or own planning configuration.
    """

    source_result: OptimizationResult

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, OptimizationResult):
            raise TypeError("source_result must be an OptimizationResult")


class OptimizationControlPlanConstructionBoundary(ABC):
    """Define construction of an EOS future control plan from one result.

    Implementations must return an ``OptimizationControlPlan`` whose
    ``source_result is construction_input.source_result``. The boundary owns
    neither a solver nor a registry, plan execution, current-action extraction,
    decision translation, feasibility, actuation, or simulation.
    """

    __slots__ = ()

    @abstractmethod
    def construct(
        self,
        construction_input: OptimizationControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        """Return one plan preserving exact optimization-result provenance."""
        raise NotImplementedError
