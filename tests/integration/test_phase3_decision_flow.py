"""End-to-end validation of the EOS Phase 3 decision flow."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from capability import (
    CapabilityCompositionBoundary,
    DeterministicIntentResolutionImplementation,
    DeterministicIntentResolutionParameters,
    EMSCapabilityBoundary,
    SelfConsumptionCapability,
    TOUCapabilityParameters,
    TOUEnergyCapability,
)
from kernel.decision import (
    BatteryConstraintImplementation,
    ConstraintEvaluationPipeline,
    ConstraintExplanation,
    ConstraintExplanationChain,
    ConstraintExplanationEntry,
    DecisionConstraintBoundary,
    DecisionContext,
    DecisionContextResult,
    DecisionEvaluationCycle,
    DecisionIntent,
    FeasibleDecisionIntent,
    GridPowerLimitConstraintImplementation,
)


class _SequentialCapabilityComposition(CapabilityCompositionBoundary):
    """Test-only implementation of the accepted composition contract."""

    __slots__ = ()

    def evaluate(
        self,
        context: DecisionContext,
        capabilities: tuple[EMSCapabilityBoundary, ...],
    ) -> tuple[DecisionIntent, ...]:
        return tuple(capability.evaluate(context) for capability in capabilities)


class _CapabilityProbe(EMSCapabilityBoundary):
    """Count calls while preserving the delegated capability result identity."""

    __slots__ = ("calls", "delegate", "input_context", "output_intent")

    def __init__(self, delegate: EMSCapabilityBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.input_context: DecisionContext | None = None
        self.output_intent: DecisionIntent | None = None

    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        self.calls += 1
        self.input_context = context
        self.output_intent = self.delegate.evaluate(context)
        return self.output_intent


class _ConstraintProbe(DecisionConstraintBoundary):
    """Count calls while preserving delegated constraint artifact identities."""

    __slots__ = ("calls", "delegate", "input_intent", "output_feasible_intent")

    def __init__(self, delegate: DecisionConstraintBoundary) -> None:
        self.calls = 0
        self.delegate = delegate
        self.input_intent: DecisionIntent | None = None
        self.output_feasible_intent: FeasibleDecisionIntent | None = None

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        self.calls += 1
        self.input_intent = intent
        self.output_feasible_intent = self.delegate.evaluate(intent)
        return self.output_feasible_intent


@dataclass(frozen=True, slots=True)
class _CompletedFlow:
    """Exact artifacts produced by the test-only integration harness."""

    candidates: tuple[DecisionIntent, ...]
    resolved_intent: DecisionIntent
    result: DecisionContextResult
    feasible_intent: FeasibleDecisionIntent
    explanation_chain: ConstraintExplanationChain
    cycle: DecisionEvaluationCycle


def _make_context(
    *,
    hour: int,
    pv_power_kw: float,
    load_power_kw: float,
    grid_power_kw: float,
    electricity_price_cny_per_kwh: float,
) -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, hour=hour, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        grid_power_kw=grid_power_kw,
        electricity_price_cny_per_kwh=electricity_price_cny_per_kwh,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


def _make_tou_capability() -> TOUEnergyCapability:
    return TOUEnergyCapability(
        TOUCapabilityParameters(
            charge_hours=(1,),
            discharge_hours=(18,),
            charge_price_ceiling_cny_per_kwh=0.3,
            discharge_price_floor_cny_per_kwh=0.8,
            charge_power_intent_kw=4.0,
            discharge_power_intent_kw=5.0,
        )
    )


def _complete_flow(
    context: DecisionContext,
    capabilities: tuple[_CapabilityProbe, ...],
    *,
    selected_candidate_index: int,
    constraints: tuple[_ConstraintProbe, ...],
    adjustment_reasons: tuple[str, ...],
) -> _CompletedFlow:
    candidates = _SequentialCapabilityComposition().evaluate(context, capabilities)
    resolved_intent = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(
            selected_candidate_index=selected_candidate_index,
        )
    ).resolve(candidates)
    result = DecisionContextResult(intent=resolved_intent)
    feasible_intent = ConstraintEvaluationPipeline.evaluate(
        resolved_intent,
        constraints,
    )

    entries: tuple[ConstraintExplanationEntry, ...] = ()
    for constraint, reason in zip(
        constraints,
        adjustment_reasons,
        strict=True,
    ):
        assert constraint.input_intent is not None
        assert constraint.output_feasible_intent is not None
        entry = ConstraintExplanationEntry.create(
            constraint.input_intent,
            constraint.output_feasible_intent,
            adjustment_reason=(
                reason
                if constraint.output_feasible_intent.intent
                is not constraint.input_intent
                else None
            ),
        )
        entries = (*entries, entry)

    explanation_chain = ConstraintExplanationChain.create(
        resolved_intent,
        entries,
        feasible_intent,
    )
    explanation = ConstraintExplanation.create(
        feasible_intent,
        resolved_intent,
    )
    cycle = DecisionEvaluationCycle.create(
        context,
        result,
        feasible_intent,
        explanation,
    )
    return _CompletedFlow(
        candidates=candidates,
        resolved_intent=resolved_intent,
        result=result,
        feasible_intent=feasible_intent,
        explanation_chain=explanation_chain,
        cycle=cycle,
    )


def test_pv_surplus_selected_charge_intent_completes_exact_flow() -> None:
    context = _make_context(
        hour=1,
        pv_power_kw=5.0,
        load_power_kw=2.0,
        grid_power_kw=-2.0,
        electricity_price_cny_per_kwh=0.2,
    )
    tou = _CapabilityProbe(_make_tou_capability())
    self_consumption = _CapabilityProbe(SelfConsumptionCapability())
    battery = _ConstraintProbe(
        BatteryConstraintImplementation(
            soc=0.5,
            reserve_soc=0.2,
            max_charge_power_kw=2.0,
            max_discharge_power_kw=2.0,
        )
    )
    grid = _ConstraintProbe(
        GridPowerLimitConstraintImplementation(
            grid_power_baseline_kw=-2.0,
            max_import_power_kw=4.0,
            max_export_power_kw=4.0,
        )
    )

    completed = _complete_flow(
        context,
        (tou, self_consumption),
        selected_candidate_index=1,
        constraints=(battery, grid),
        adjustment_reasons=("battery charge power limit", "grid power limit"),
    )

    assert completed.candidates[0].battery_power_intent_kw == pytest.approx(4.0)
    assert completed.candidates[1].battery_power_intent_kw == pytest.approx(3.0)
    assert completed.candidates[0] is tou.output_intent
    assert completed.candidates[1] is self_consumption.output_intent
    assert completed.resolved_intent is completed.candidates[1]
    assert completed.result.intent is completed.resolved_intent
    assert completed.cycle.context is context
    assert completed.cycle.result is completed.result
    assert completed.cycle.source_intent is completed.result.intent
    assert completed.feasible_intent.intent.battery_power_intent_kw == pytest.approx(
        2.0
    )
    assert completed.cycle.feasible_intent is completed.feasible_intent

    first_entry, second_entry = completed.explanation_chain.entries
    assert completed.explanation_chain.source_intent is completed.resolved_intent
    assert first_entry.source_intent is completed.resolved_intent
    assert first_entry.feasible_intent is battery.output_feasible_intent
    assert first_entry.adjusted is True
    assert first_entry.adjustment_reason == "battery charge power limit"
    assert second_entry.source_intent is first_entry.feasible_intent.intent
    assert second_entry.feasible_intent is grid.output_feasible_intent
    assert second_entry.adjusted is False
    assert second_entry.adjustment_reason is None
    assert completed.explanation_chain.feasible_intent is second_entry.feasible_intent
    assert completed.cycle.explanation.feasible_intent is completed.feasible_intent

    assert tou.calls == 1
    assert self_consumption.calls == 1
    assert tou.input_context is context
    assert self_consumption.input_context is context
    assert battery.calls == 1
    assert grid.calls == 1
    assert battery.input_intent is completed.resolved_intent
    assert grid.input_intent is first_entry.feasible_intent.intent


def test_pv_deficit_discharge_adjustment_preserves_complete_lineage() -> None:
    context = _make_context(
        hour=18,
        pv_power_kw=1.0,
        load_power_kw=4.0,
        grid_power_kw=3.0,
        electricity_price_cny_per_kwh=1.0,
    )
    self_consumption = _CapabilityProbe(SelfConsumptionCapability())
    tou = _CapabilityProbe(_make_tou_capability())
    battery = _ConstraintProbe(
        BatteryConstraintImplementation(
            soc=0.5,
            reserve_soc=0.2,
            max_charge_power_kw=2.0,
            max_discharge_power_kw=2.0,
        )
    )
    grid = _ConstraintProbe(
        GridPowerLimitConstraintImplementation(
            grid_power_baseline_kw=3.0,
            max_import_power_kw=2.0,
            max_export_power_kw=2.0,
        )
    )

    completed = _complete_flow(
        context,
        (self_consumption, tou),
        selected_candidate_index=0,
        constraints=(battery, grid),
        adjustment_reasons=("battery discharge power limit", "grid power limit"),
    )

    assert completed.candidates[0].battery_power_intent_kw == pytest.approx(-3.0)
    assert completed.candidates[1].battery_power_intent_kw == pytest.approx(-5.0)
    assert completed.candidates[0] is self_consumption.output_intent
    assert completed.candidates[1] is tou.output_intent
    assert completed.resolved_intent is completed.candidates[0]
    assert completed.result.intent is completed.resolved_intent
    assert completed.cycle.context is context
    assert completed.cycle.result is completed.result
    assert completed.cycle.source_intent is completed.resolved_intent
    assert completed.feasible_intent.intent is not completed.resolved_intent
    assert completed.feasible_intent.intent.battery_power_intent_kw == pytest.approx(
        -2.0
    )

    first_entry, second_entry = completed.explanation_chain.entries
    assert first_entry.source_intent is completed.resolved_intent
    assert first_entry.feasible_intent is battery.output_feasible_intent
    assert first_entry.feasible_intent.intent is completed.feasible_intent.intent
    assert first_entry.adjusted is True
    assert first_entry.adjustment_reason == "battery discharge power limit"
    assert second_entry.source_intent is first_entry.feasible_intent.intent
    assert second_entry.feasible_intent is grid.output_feasible_intent
    assert second_entry.feasible_intent is completed.feasible_intent
    assert second_entry.adjusted is False
    assert completed.explanation_chain.feasible_intent is completed.feasible_intent
    assert completed.cycle.feasible_intent is completed.feasible_intent
    assert completed.cycle.explanation.source_intent is completed.resolved_intent

    assert self_consumption.calls == 1
    assert tou.calls == 1
    assert self_consumption.input_context is context
    assert tou.input_context is context
    assert battery.calls == 1
    assert grid.calls == 1
    assert battery.input_intent is completed.resolved_intent
    assert grid.input_intent is first_entry.feasible_intent.intent
