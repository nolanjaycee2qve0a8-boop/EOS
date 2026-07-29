"""Abstract implementation seam for DecisionContext policies."""

from kernel.policy.decision_context import DecisionContextPolicy


class DecisionContextPolicyImplementation(DecisionContextPolicy):
    """Mark the extension boundary for future concrete decision policies.

    Concrete subclasses implement the inherited
    ``evaluate(DecisionContext) -> DecisionContextResult`` contract. This
    boundary introduces no policy behavior, execution, or retained state.
    """

    __slots__ = ()
