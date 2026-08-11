"""End-to-end evidence tests for the application-level EMS integration flow."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, cast

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_simulator import (
    BatteryParameters,
    EMSIntegrationResult,
    EMSIntegrationRunner,
    EMSIntegrationScenarioInput,
)
from ems_simulator.input import DailySimulationScenarioInput
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
    EMSDecision,
    FeasibilityBoundary,
    FeasibleDecision,
    SelfConsumptionStrategy,
    StrategyCoordinator,
    StrategyCoordinatorConfiguration,
)
from kernel.decision import DecisionIntent as SimulatorDecisionIntent
from kernel.decision import FeasibleDecisionIntent
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from simulator import (
    BatterySimulationActuation,
    SimulationStepIdentity,
)


class RecordingSelfConsumptionStrategy(SelfConsumptionStrategy):
    """Record exact contexts while reusing the existing strategy behavior."""

    __slots__ = ()

    contexts: ClassVar[list[EMSContext]] = []

    def evaluate(self, context: EMSContext) -> EMSDecision:
        self.contexts.append(context)
        return super().evaluate(context)


class PassThroughFeasibility(FeasibilityBoundary):
    """Test-only feasibility implementation that approves unchanged requests."""

    __slots__ = ()

    decisions: ClassVar[list[EMSDecision]] = []

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> FeasibleDecision:
        self.decisions.append(decision)
        return FeasibleDecision(
            decision,
            provenance,
            decision.intent,
            decision.requested_power_kw,
        )


class SimulationActuationHandoff(ActuationHandoffBoundary):
    """Test-only adapter preserving the frozen semantic action mapping."""

    __slots__ = ()

    feasible_decisions: ClassVar[list[FeasibleDecision]] = []

    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
    ) -> ActuationHandoffResult:
        self.feasible_decisions.append(feasible_decision)
        signed_power_kw = (
            feasible_decision.approved_power_kw
            if feasible_decision.approved_intent.action == "charge"
            else -feasible_decision.approved_power_kw
            if feasible_decision.approved_intent.action == "discharge"
            else 0.0
        )
        actuation = BatterySimulationActuation(
            FeasibleDecisionIntent(SimulatorDecisionIntent(signed_power_kw)),
            signed_power_kw,
        )
        return ActuationHandoffResult(feasible_decision, actuation)


@pytest.fixture(autouse=True)
def clear_evidence() -> None:
    RecordingSelfConsumptionStrategy.contexts.clear()
    PassThroughFeasibility.decisions.clear()
    SimulationActuationHandoff.feasible_decisions.clear()


def make_source_input() -> DailySimulationScenarioInput:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return DailySimulationScenarioInput(
        step_identities=tuple(
            SimulationStepIdentity(
                hour,
                3600.0,
                start + timedelta(hours=hour),
            )
            for hour in range(24)
        ),
        pv_power_curve_kw=(0.0,) * 6 + (4.0,) * 10 + (0.0,) * 8,
        load_power_curve_kw=(1.0,) * 24,
        tariff_curve_cny_per_kwh=(0.5,) * 24,
        battery_parameters=BatteryParameters(
            capacity_kwh=10.0,
            max_charge_power_kw=3.0,
            max_discharge_power_kw=3.0,
            charge_efficiency=0.95,
            discharge_efficiency=0.95,
            reserve_soc=0.2,
        ),
        initial_soc=0.5,
    )


def make_integration_input() -> EMSIntegrationScenarioInput:
    required = CapabilityDescriptor("self-consumption", "Required capability.")
    available = CapabilityDescriptor("self-consumption", "Available capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("self-consumption", "Use available PV locally."),
        active,
    )
    return EMSIntegrationScenarioInput(
        make_source_input(),
        composition,
        available,
        battery_power_limit_kw=3.0,
        export_limit_kw=5.0,
        initial_grid_power_kw=0.0,
    )


def make_coordinator() -> StrategyCoordinator:
    strategy = RecordingSelfConsumptionStrategy()
    return StrategyCoordinator(
        StrategyCoordinatorConfiguration((strategy.descriptor,)),
        (strategy,),
    )


def run_integration() -> EMSIntegrationResult:
    return EMSIntegrationRunner.run(
        make_integration_input(),
        coordinator=make_coordinator(),
        feasibility=PassThroughFeasibility(),
        handoff=SimulationActuationHandoff(),
    )


def test_runner_executes_deterministic_24_hour_ems_flow() -> None:
    result = run_integration()

    assert len(result.traces) == 24
    assert len(result.simulation_result.traces) == 24
    assert len(RecordingSelfConsumptionStrategy.contexts) == 24
    assert len(PassThroughFeasibility.decisions) == 24
    assert len(SimulationActuationHandoff.feasible_decisions) == 24
    assert [
        trace.simulation_trace.simulation_input.step_identity.sequence
        for trace in result.traces
    ] == list(range(24))


def test_trace_preserves_complete_strategy_to_simulation_provenance() -> None:
    result = run_integration()

    for index, trace in enumerate(result.traces):
        assert trace.context is RecordingSelfConsumptionStrategy.contexts[index]
        assert trace.decision is PassThroughFeasibility.decisions[index]
        assert trace.provenance.decision is trace.decision
        assert trace.provenance.source_context is trace.context
        assert trace.feasible_decision.source_decision is trace.decision
        assert trace.feasible_decision.source_provenance is trace.provenance
        assert trace.handoff.source_feasible_decision is trace.feasible_decision
        assert (
            trace.simulation_trace.simulation_input.battery_input.actuation
            is trace.handoff.actuation
        )
        assert trace.simulation_trace is result.simulation_result.traces[index]


def test_soc_progression_and_grid_balance_are_valid() -> None:
    result = run_integration()

    for index, trace in enumerate(result.traces):
        state = trace.simulation_trace.state
        assert 0.2 <= state.battery_result.next_state.soc <= 1.0
        assert state.grid_result.actual_grid_power_kw == pytest.approx(
            state.load_result.actual_power_kw
            + state.battery_result.actual_power_kw
            - state.pv_result.actual_power_kw
        )
        if index:
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                result.traces[
                    index - 1
                ].simulation_trace.state.grid_result.actual_grid_power_kw
            )
            assert (
                trace.simulation_trace.simulation_input.battery_input.source_state
                is result.traces[
                    index - 1
                ].simulation_trace.state.battery_result.next_state
            )


def test_runner_is_deterministic_for_equal_caller_inputs() -> None:
    first = run_integration()
    second = run_integration()

    assert first is not second
    assert tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in first.traces
    ) == tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in second.traces
    )
    assert tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in first.traces
    ) == tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in second.traces
    )


def test_integration_artifacts_are_frozen_and_runner_is_stateless() -> None:
    result = run_integration()

    assert not hasattr(result, "__dict__")
    assert not hasattr(result.traces[0], "__dict__")
    assert EMSIntegrationRunner.__slots__ == ()
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).traces = ()
    with pytest.raises(AttributeError):
        cast(Any, EMSIntegrationRunner()).cache = object()
