"""Stateless orchestration of one decision evaluation lifecycle."""

from datetime import datetime

from kernel.decision.assembler import DecisionContextAssembler
from kernel.decision.constraint import (
    DecisionConstraintBoundary,
    FeasibleDecisionIntent,
)
from kernel.decision.constraint_explanation import ConstraintExplanation
from kernel.decision.context_result import DecisionContextResult
from kernel.decision.evaluation_cycle import DecisionEvaluationCycle
from kernel.policy.decision_context import DecisionContextPolicy
from kernel.system_state import EnergySystemState


class DecisionEvaluationOrchestrator:
    """Compose existing decision boundaries without owning lifecycle state."""

    __slots__ = ()

    @staticmethod
    def evaluate(
        state: EnergySystemState,
        policy: DecisionContextPolicy,
        constraint: DecisionConstraintBoundary,
        *,
        timestamp: datetime,
        battery_power_limit_kw: float,
        battery_energy_capacity_kwh: float,
        load_power_kw: float,
        electricity_price_cny_per_kwh: float,
        reserve_soc: float,
        export_limit_kw: float,
    ) -> DecisionEvaluationCycle:
        """Evaluate one decision lifecycle through the existing boundaries."""
        if not isinstance(state, EnergySystemState):
            raise TypeError("state must be an EnergySystemState")
        if not isinstance(policy, DecisionContextPolicy):
            raise TypeError("policy must be a DecisionContextPolicy")
        if not isinstance(constraint, DecisionConstraintBoundary):
            raise TypeError("constraint must be a DecisionConstraintBoundary")

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

        result = policy.evaluate(context)
        if not isinstance(result, DecisionContextResult):
            raise TypeError("policy must return a DecisionContextResult")

        feasible_intent = constraint.evaluate(result.intent)
        if not isinstance(feasible_intent, FeasibleDecisionIntent):
            raise TypeError("constraint must return a FeasibleDecisionIntent")

        explanation = ConstraintExplanation.create(feasible_intent)
        return DecisionEvaluationCycle.create(
            context,
            result,
            feasible_intent,
            explanation,
        )
