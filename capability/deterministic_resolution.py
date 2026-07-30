"""Deterministic caller-parameterized intent resolution."""

from dataclasses import dataclass

from capability.resolution import IntentResolutionBoundary
from kernel.decision import DecisionIntent


@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionParameters:
    """Select one candidate by an explicit zero-based tuple index."""

    selected_candidate_index: int

    def __post_init__(self) -> None:
        if isinstance(self.selected_candidate_index, bool) or not isinstance(
            self.selected_candidate_index,
            int,
        ):
            raise TypeError("selected_candidate_index must be an int")
        if self.selected_candidate_index < 0:
            raise ValueError(
                "selected_candidate_index must be greater than or equal to 0"
            )


@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionImplementation(IntentResolutionBoundary):
    """Return the exact candidate selected by immutable caller parameters."""

    parameters: DeterministicIntentResolutionParameters

    def __post_init__(self) -> None:
        if not isinstance(
            self.parameters,
            DeterministicIntentResolutionParameters,
        ):
            raise TypeError(
                "parameters must be a DeterministicIntentResolutionParameters"
            )

    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent:
        """Return the exact candidate at the configured tuple index."""
        if not isinstance(candidates, tuple):
            raise TypeError("candidates must be a tuple")
        for candidate in candidates:
            if not isinstance(candidate, DecisionIntent):
                raise TypeError("candidates must contain only DecisionIntent values")

        index = self.parameters.selected_candidate_index
        if index >= len(candidates):
            raise ValueError(
                "selected_candidate_index must identify an existing candidate"
            )
        return candidates[index]
