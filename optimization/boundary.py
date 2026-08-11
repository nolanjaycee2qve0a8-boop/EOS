"""Abstract solver-independent boundary for optimization implementations."""

from abc import ABC, abstractmethod

from optimization.model import OptimizationProblem, OptimizationResult


class OptimizationBoundary(ABC):
    """Define a stateless solve seam without solver selection or state.

    Implementations receive one exact immutable problem and return one result
    retaining ``result.source_problem is problem``. This boundary does not
    provide a registry, framework adapter, cache, history, device access,
    simulation, command generation, or Strategy behavior.
    """

    __slots__ = ()

    @abstractmethod
    def solve(self, problem: OptimizationProblem) -> OptimizationResult:
        """Return one result preserving exact source-problem identity."""
        raise NotImplementedError
