"""Solution-producing optimization seam without changing generic solve results."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optimization.model import OptimizationProblem, OptimizationResult
from optimization.solution import OptimizationSolution


@dataclass(frozen=True, slots=True)
class OptimizationSolveOutput:
    """Pair one generic optimization result with its concrete solved values."""

    result: OptimizationResult
    solution: OptimizationSolution

    def __post_init__(self) -> None:
        if not isinstance(self.result, OptimizationResult):
            raise TypeError("result must be an OptimizationResult")
        if not isinstance(self.solution, OptimizationSolution):
            raise TypeError("solution must be an OptimizationSolution")
        if self.solution.source_result is not self.result:
            raise ValueError("solution must preserve exact result identity")


class OptimizationSolutionBoundary(ABC):
    """Define a stateless seam returning an outcome and explicit solution."""

    __slots__ = ()

    @abstractmethod
    def solve_with_solution(
        self,
        problem: OptimizationProblem,
    ) -> OptimizationSolveOutput:
        """Return result and solved values preserving exact problem provenance."""
        raise NotImplementedError
