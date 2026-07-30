"""Stateless integration of one complete decision evaluation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from kernel.decision.assembler import DecisionContextAssembler
from kernel.decision.constraint import (
    DecisionConstraintBoundary,
    FeasibleDecisionIntent,
)
from kernel.decision.constraint_explanation import ConstraintExplanation
from kernel.decision.constraint_explanation_chain import (
    ConstraintExplanationChain,
    ConstraintExplanationEntry,
)
from kernel.decision.constraint_pipeline import ConstraintEvaluationPipeline
from kernel.decision.context_result import DecisionContextResult
from kernel.decision.evaluation_cycle import DecisionEvaluationCycle
from kernel.decision.intent import DecisionIntent
from kernel.policy.decision_context import DecisionContextPolicy
from kernel.system_state import EnergySystemState


@dataclass(frozen=True, slots=True)
class DecisionEvaluationIntegrationResult:
    """Preserve the exact cycle and explanation chain from one evaluation."""

    cycle: DecisionEvaluationCycle
    explanation_chain: ConstraintExplanationChain

    def __post_init__(self) -> None:
        if not isinstance(self.cycle, DecisionEvaluationCycle):
            raise TypeError("cycle must be a DecisionEvaluationCycle")
        if not isinstance(
            self.explanation_chain,
            ConstraintExplanationChain,
        ):
            raise TypeError("explanation_chain must be a ConstraintExplanationChain")
        if self.explanation_chain.source_intent is not self.cycle.source_intent:
            raise ValueError(
                "explanation_chain must reference the exact cycle source intent"
            )
        if self.explanation_chain.feasible_intent is not self.cycle.feasible_intent:
            raise ValueError(
                "explanation_chain must reference the exact cycle feasible intent"
            )


@dataclass(frozen=True, slots=True)
class _ExplainingConstraint(DecisionConstraintBoundary):
    """Observe one delegated constraint call without changing its contract."""

    constraint: DecisionConstraintBoundary
    adjustment_reason: str
    record: Callable[[ConstraintExplanationEntry], None]

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        """Delegate exactly once and record the exact completed artifacts."""
        feasible_intent = self.constraint.evaluate(intent)
        if not isinstance(feasible_intent, FeasibleDecisionIntent):
            raise TypeError("constraint must return a FeasibleDecisionIntent")

        entry = ConstraintExplanationEntry.create(
            intent,
            feasible_intent,
            adjustment_reason=(
                self.adjustment_reason if feasible_intent.intent is not intent else None
            ),
        )
        self.record(entry)
        return feasible_intent


class DecisionEvaluationIntegration:
    """Coordinate existing decision boundaries without retaining state."""

    __slots__ = ()

    @staticmethod
    def evaluate(
        state: EnergySystemState,
        policy: DecisionContextPolicy,
        constraints: tuple[DecisionConstraintBoundary, ...],
        *,
        constraint_adjustment_reasons: tuple[str, ...],
        timestamp: datetime,
        battery_power_limit_kw: float,
        battery_energy_capacity_kwh: float,
        load_power_kw: float,
        electricity_price_cny_per_kwh: float,
        reserve_soc: float,
        export_limit_kw: float,
    ) -> DecisionEvaluationIntegrationResult:
        """Evaluate once through existing boundaries and preserve exact evidence."""
        if not isinstance(state, EnergySystemState):
            raise TypeError("state must be an EnergySystemState")
        if not isinstance(policy, DecisionContextPolicy):
            raise TypeError("policy must be a DecisionContextPolicy")
        if not isinstance(constraints, tuple):
            raise TypeError("constraints must be a tuple")
        for constraint in constraints:
            if not isinstance(constraint, DecisionConstraintBoundary):
                raise TypeError(
                    "constraints must contain only DecisionConstraintBoundary instances"
                )
        if not isinstance(constraint_adjustment_reasons, tuple):
            raise TypeError("constraint_adjustment_reasons must be a tuple")
        if len(constraint_adjustment_reasons) != len(constraints):
            raise ValueError(
                "constraint_adjustment_reasons must match constraints length"
            )
        for reason in constraint_adjustment_reasons:
            if not isinstance(reason, str):
                raise TypeError(
                    "constraint_adjustment_reasons must contain only str values"
                )
            if not reason.strip():
                raise ValueError("constraint_adjustment_reasons must be non-empty")

        context = DecisionContextAssembler.assemble(
            state,
            timestamp=timestamp,
            battery_power_limit_kw=battery_power_limit_kw,
            battery_energy_capacity_kwh=battery_energy_capacity_kwh,
            load_power_kw=load_power_kw,
            electricity_price_cny_per_kwh=electricity_price_cny_per_kwh,
            reserve_soc=reserve_soc,
            export_limit_kw=export_limit_kw,
        )

        policy_result = policy.evaluate(context)
        if not isinstance(policy_result, DecisionContextResult):
            raise TypeError("policy must return a DecisionContextResult")

        entries: tuple[ConstraintExplanationEntry, ...] = ()

        def record(entry: ConstraintExplanationEntry) -> None:
            nonlocal entries
            entries = (*entries, entry)

        explaining_constraints = tuple(
            _ExplainingConstraint(
                constraint=constraint,
                adjustment_reason=reason,
                record=record,
            )
            for constraint, reason in zip(
                constraints,
                constraint_adjustment_reasons,
                strict=True,
            )
        )
        feasible_intent = ConstraintEvaluationPipeline.evaluate(
            policy_result.intent,
            explaining_constraints,
        )
        explanation_chain = ConstraintExplanationChain.create(
            policy_result.intent,
            entries,
            feasible_intent,
        )
        explanation = ConstraintExplanation.create(
            feasible_intent,
            policy_result.intent,
        )
        cycle = DecisionEvaluationCycle.create(
            context,
            policy_result,
            feasible_intent,
            explanation,
        )
        return DecisionEvaluationIntegrationResult(
            cycle=cycle,
            explanation_chain=explanation_chain,
        )
