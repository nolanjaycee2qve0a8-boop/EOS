"""Immutable output boundary for DecisionContext policies."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecisionContextResult:
    """Represent policy output before future command generation.

    The initial contract is intentionally fieldless. Device commands, execution
    events, and algorithm-specific outputs belong to later architecture tasks.
    """
