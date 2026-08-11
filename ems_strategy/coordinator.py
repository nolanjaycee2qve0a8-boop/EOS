"""Stateless selection of caller-supplied EMS strategy decisions."""

from dataclasses import dataclass

from ems_strategy.boundary import EMSStrategyBoundary
from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor


def _require_strategy_descriptor(
    strategy: EMSStrategyBoundary,
) -> EMSStrategyDescriptor:
    """Return the strategy's declared descriptor without reconstructing it."""
    descriptor = getattr(strategy, "descriptor", None)
    if not isinstance(descriptor, EMSStrategyDescriptor):
        raise TypeError("each strategy must declare an EMSStrategyDescriptor")
    return descriptor


@dataclass(frozen=True, slots=True)
class StrategyCoordinatorConfiguration:
    """Preserve caller-defined exact descriptor identities as priority order.

    The tuple is retained exactly as supplied.  Its order is an explicit caller
    policy; this contract performs neither ranking nor scoring.
    """

    strategy_priority: tuple[EMSStrategyDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_priority, tuple):
            raise TypeError("strategy_priority must be a tuple")
        if not self.strategy_priority:
            raise ValueError("strategy_priority must not be empty")
        for descriptor in self.strategy_priority:
            if not isinstance(descriptor, EMSStrategyDescriptor):
                raise TypeError(
                    "strategy_priority entries must be EMSStrategyDescriptor objects"
                )
        for index, descriptor in enumerate(self.strategy_priority):
            if any(
                descriptor is later_descriptor
                for later_descriptor in self.strategy_priority[index + 1 :]
            ):
                raise ValueError(
                    "strategy_priority must not repeat descriptor identity"
                )


@dataclass(frozen=True, slots=True)
class StrategyCoordinator:
    """Coordinate exact decisions from all caller-supplied strategies.

    This coordinator evaluates every supplied strategy exactly once in the
    supplied tuple order.  It then returns the exact decision associated with
    the first descriptor in the caller-supplied priority tuple.  It neither
    changes a request nor performs feasibility or physical execution.
    """

    configuration: StrategyCoordinatorConfiguration
    strategies: tuple[EMSStrategyBoundary, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, StrategyCoordinatorConfiguration):
            raise TypeError("configuration must be a StrategyCoordinatorConfiguration")
        if not isinstance(self.strategies, tuple):
            raise TypeError("strategies must be a tuple")
        if not self.strategies:
            raise ValueError("strategies must not be empty")
        for strategy in self.strategies:
            if not isinstance(strategy, EMSStrategyBoundary):
                raise TypeError("strategies must contain EMSStrategyBoundary objects")

        descriptors = tuple(
            _require_strategy_descriptor(strategy) for strategy in self.strategies
        )
        for index, descriptor in enumerate(descriptors):
            if any(
                descriptor is later_descriptor
                for later_descriptor in descriptors[index + 1 :]
            ):
                raise ValueError("strategies must not repeat descriptor identity")

        priority = self.configuration.strategy_priority
        if len(priority) != len(descriptors) or any(
            not any(priority_descriptor is descriptor for descriptor in descriptors)
            for priority_descriptor in priority
        ):
            raise ValueError(
                "strategy_priority must contain each strategy descriptor "
                "by exact identity"
            )

    def evaluate(self, context: EMSContext) -> EMSDecision:
        """Return the selected exact decision while preserving context provenance."""
        if not isinstance(context, EMSContext):
            raise TypeError("context must be an EMSContext")

        decisions = tuple(strategy.evaluate(context) for strategy in self.strategies)
        for strategy, decision in zip(self.strategies, decisions, strict=True):
            if not isinstance(decision, EMSDecision):
                raise TypeError("strategies must return EMSDecision objects")
            if decision.source_context is not context:
                raise ValueError("decision must preserve exact source_context identity")
            if decision.source_strategy is not _require_strategy_descriptor(strategy):
                raise ValueError(
                    "decision must preserve exact source_strategy identity"
                )

        for priority_descriptor in self.configuration.strategy_priority:
            for decision in decisions:
                if decision.source_strategy is priority_descriptor:
                    return decision

        raise RuntimeError("validated strategy priority did not produce a decision")
