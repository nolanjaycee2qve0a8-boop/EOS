"""Immutable fact and provenance snapshot for one EMS strategy evaluation."""

from dataclasses import dataclass

from capability import CapabilityDescriptor
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition


@dataclass(frozen=True, slots=True)
class EMSContext:
    """Preserve exact facts and active capability evidence for one evaluation.

    The context does not copy, normalize, derive, or execute any source object.
    ``capability`` must be the exact descriptor contained in the supplied
    objective/capability composition.
    """

    source_context: DecisionContext
    objective_composition: ObjectiveCapabilityActivationComposition
    capability: CapabilityDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.source_context, DecisionContext):
            raise TypeError("source_context must be a DecisionContext")
        if not isinstance(
            self.objective_composition,
            ObjectiveCapabilityActivationComposition,
        ):
            raise TypeError(
                "objective_composition must be an "
                "ObjectiveCapabilityActivationComposition"
            )
        if not isinstance(self.capability, CapabilityDescriptor):
            raise TypeError("capability must be a CapabilityDescriptor")
        if not any(
            self.capability is active_capability
            for active_capability in (
                self.objective_composition.active_capabilities.active_capabilities
            )
        ):
            raise ValueError(
                "capability must preserve exact active capability identity"
            )
