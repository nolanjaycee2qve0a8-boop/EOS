"""Immutable input contract for one Phase 5 decision formation."""

from dataclasses import dataclass

from capability.descriptor import CapabilityDescriptor
from kernel.decision.context import DecisionContext
from objective.activation_composition import (
    ObjectiveCapabilityActivationComposition,
)


@dataclass(frozen=True, slots=True)
class DecisionFormationInput:
    """Preserve exact facts and evidence supplied for intent formation."""

    source_context: DecisionContext
    composition: ObjectiveCapabilityActivationComposition
    capability: CapabilityDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.source_context, DecisionContext):
            raise TypeError("source_context must be a DecisionContext")
        if not isinstance(
            self.composition,
            ObjectiveCapabilityActivationComposition,
        ):
            raise TypeError(
                "composition must be an ObjectiveCapabilityActivationComposition"
            )
        if not isinstance(self.capability, CapabilityDescriptor):
            raise TypeError("capability must be a CapabilityDescriptor")
        if not any(
            self.capability is active_capability
            for active_capability in (
                self.composition.active_capabilities.active_capabilities
            )
        ):
            raise ValueError(
                "capability must preserve active capability descriptor identity"
            )
