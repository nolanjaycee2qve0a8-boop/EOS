"""Tests for the stateless decision evaluation orchestrator."""

import ast
import inspect
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import (
    ConstraintExplanation,
    DecisionConstraintBoundary,
    DecisionContext,
    DecisionContextAssembler,
    DecisionContextResult,
    DecisionEvaluationCycle,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.policy import (
    DecisionContextPolicy,
    DecisionEvaluationOrchestrator,
)
from kernel.policy import orchestration as orchestration_module
from kernel.system_state import (
    BatteryState,
    EnergySystemState,
    GridState,
    PCSState,
    PVState,
)

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
POLICY_ERROR = RuntimeError("policy failed")
CONSTRAINT_ERROR = RuntimeError("constraint failed")


def make_state() -> EnergySystemState:
    return EnergySystemState(
        battery=BatteryState(
            soc=0.5,
            soh=0.9,
            voltage_v=700.0,
            current_a=10.0,
            temperature_c=25.0,
            available_charge_power_kw=50.0,
            available_discharge_power_kw=50.0,
        ),
        pcs=PCSState(
            active_power_kw=0.0,
            reactive_power_kvar=0.0,
            operating_state="ready",
            fault_state="none",
        ),
        pv=PVState(
            available_power_kw=30.0,
            actual_power_kw=25.0,
        ),
        grid=GridState(
            grid_power_kw=-5.0,
            voltage_v=400.0,
            frequency_hz=50.0,
        ),
    )


def evaluate(
    state: EnergySystemState,
    policy: DecisionContextPolicy,
    constraint: DecisionConstraintBoundary,
) -> DecisionEvaluationCycle:
    return DecisionEvaluationOrchestrator.evaluate(
        state,
        policy,
        constraint,
        timestamp=FIXED_TIME,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        load_power_kw=20.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


class RecordingPolicy(DecisionContextPolicy):
    __slots__ = ("calls", "contexts", "result")

    def __init__(self, result: DecisionContextResult) -> None:
        self.calls = 0
        self.contexts: list[DecisionContext] = []
        self.result = result

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        self.calls += 1
        self.contexts.append(context)
        return self.result


class RecordingConstraint(DecisionConstraintBoundary):
    __slots__ = ("calls", "intents", "result")

    def __init__(self, result: FeasibleDecisionIntent) -> None:
        self.calls = 0
        self.intents: list[DecisionIntent] = []
        self.result = result

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        self.calls += 1
        self.intents.append(intent)
        return self.result


class RaisingPolicy(DecisionContextPolicy):
    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        raise POLICY_ERROR


class RaisingConstraint(DecisionConstraintBoundary):
    __slots__ = ()

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        raise CONSTRAINT_ERROR


def test_evaluate_preserves_complete_identity_chain() -> None:
    state = make_state()
    intent = DecisionIntent(5.0)
    result = DecisionContextResult(intent)
    feasible_intent = FeasibleDecisionIntent(intent)
    policy = RecordingPolicy(result)
    constraint = RecordingConstraint(feasible_intent)

    cycle = evaluate(state, policy, constraint)

    assert policy.calls == 1
    assert constraint.calls == 1
    assert policy.contexts == [cycle.context]
    assert policy.contexts[0] is cycle.context
    assert cycle.result is result
    assert cycle.intent is result.intent
    assert constraint.intents == [cycle.intent]
    assert constraint.intents[0] is cycle.intent
    assert cycle.feasible_intent is feasible_intent
    assert cycle.feasible_intent.intent is cycle.intent
    assert cycle.explanation.feasible_intent is cycle.feasible_intent
    assert cycle.explanation.source_intent is cycle.intent


def test_evaluate_maps_state_and_explicit_facts_without_hidden_defaults() -> None:
    state = make_state()
    intent = DecisionIntent(0.0)

    cycle = DecisionEvaluationOrchestrator.evaluate(
        state,
        RecordingPolicy(DecisionContextResult(intent)),
        RecordingConstraint(FeasibleDecisionIntent(intent)),
        timestamp=FIXED_TIME,
        battery_power_limit_kw=45.0,
        battery_energy_capacity_kwh=90.0,
        load_power_kw=21.0,
        electricity_price_cny_per_kwh=-0.1,
        reserve_soc=0.15,
        export_limit_kw=8.0,
    )

    assert cycle.context.timestamp is FIXED_TIME
    assert cycle.context.soc == state.battery.soc
    assert cycle.context.pv_power_kw == state.pv.actual_power_kw
    assert cycle.context.grid_power_kw == state.grid.grid_power_kw
    assert cycle.context.battery_power_limit_kw == 45.0
    assert cycle.context.battery_energy_capacity_kwh == 90.0
    assert cycle.context.load_power_kw == 21.0
    assert cycle.context.electricity_price_cny_per_kwh == -0.1
    assert cycle.context.reserve_soc == 0.15
    assert cycle.context.export_limit_kw == 8.0


def test_evaluate_reuses_every_boundary_once_and_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = make_state()
    context = cast(DecisionContext, object())
    intent = DecisionIntent(1.0)
    result = DecisionContextResult(intent)
    feasible_intent = FeasibleDecisionIntent(intent)
    explanation = ConstraintExplanation.create(feasible_intent)
    expected = cast(DecisionEvaluationCycle, object())
    order: list[str] = []

    class OrderedPolicy(DecisionContextPolicy):
        __slots__ = ()

        def evaluate(
            self,
            supplied_context: DecisionContext,
        ) -> DecisionContextResult:
            order.append("policy")
            assert supplied_context is context
            return result

    class OrderedConstraint(DecisionConstraintBoundary):
        __slots__ = ()

        def evaluate(
            self,
            supplied_intent: DecisionIntent,
        ) -> FeasibleDecisionIntent:
            order.append("constraint")
            assert supplied_intent is intent
            return feasible_intent

    def assemble(*args: object, **kwargs: object) -> DecisionContext:
        order.append("assemble")
        assert args == (state,)
        return context

    def explain(
        supplied_feasible_intent: FeasibleDecisionIntent,
    ) -> ConstraintExplanation:
        order.append("explain")
        assert supplied_feasible_intent is feasible_intent
        return explanation

    def create_cycle(
        supplied_context: DecisionContext,
        supplied_result: DecisionContextResult,
        supplied_feasible_intent: FeasibleDecisionIntent,
        supplied_explanation: ConstraintExplanation,
    ) -> DecisionEvaluationCycle:
        order.append("cycle")
        assert supplied_context is context
        assert supplied_result is result
        assert supplied_feasible_intent is feasible_intent
        assert supplied_explanation is explanation
        return expected

    monkeypatch.setattr(DecisionContextAssembler, "assemble", assemble)
    monkeypatch.setattr(ConstraintExplanation, "create", explain)
    monkeypatch.setattr(DecisionEvaluationCycle, "create", create_cycle)

    actual = evaluate(state, OrderedPolicy(), OrderedConstraint())

    assert order == ["assemble", "policy", "constraint", "explain", "cycle"]
    assert actual is expected


def test_policy_failure_prevents_constraint_evaluation() -> None:
    intent = DecisionIntent(0.0)
    constraint = RecordingConstraint(FeasibleDecisionIntent(intent))

    with pytest.raises(RuntimeError) as raised:
        evaluate(make_state(), RaisingPolicy(), constraint)

    assert raised.value is POLICY_ERROR
    assert constraint.calls == 0


def test_constraint_failure_propagates_unchanged() -> None:
    policy = RecordingPolicy(DecisionContextResult(DecisionIntent(0.0)))

    with pytest.raises(RuntimeError) as raised:
        evaluate(make_state(), policy, RaisingConstraint())

    assert raised.value is CONSTRAINT_ERROR
    assert policy.calls == 1


def test_invalid_boundary_inputs_fail_before_assembly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_assembled(*args: object, **kwargs: object) -> DecisionContext:
        raise AssertionError("invalid input reached assembly")

    monkeypatch.setattr(
        DecisionContextAssembler,
        "assemble",
        fail_if_assembled,
    )
    intent = DecisionIntent(0.0)
    policy = RecordingPolicy(DecisionContextResult(intent))
    constraint = RecordingConstraint(FeasibleDecisionIntent(intent))

    invalid_cases = (
        (cast(EnergySystemState, object()), policy, constraint, "state"),
        (make_state(), cast(DecisionContextPolicy, object()), constraint, "policy"),
        (
            make_state(),
            policy,
            cast(DecisionConstraintBoundary, object()),
            "constraint",
        ),
    )

    for state, supplied_policy, supplied_constraint, field_name in invalid_cases:
        with pytest.raises(TypeError, match=field_name):
            evaluate(state, supplied_policy, supplied_constraint)


def test_invalid_policy_result_stops_before_constraint() -> None:
    class InvalidPolicy(DecisionContextPolicy):
        __slots__ = ()

        def evaluate(
            self,
            context: DecisionContext,
        ) -> DecisionContextResult:
            return cast(DecisionContextResult, object())

    intent = DecisionIntent(0.0)
    constraint = RecordingConstraint(FeasibleDecisionIntent(intent))

    with pytest.raises(TypeError, match="DecisionContextResult"):
        evaluate(make_state(), InvalidPolicy(), constraint)

    assert constraint.calls == 0


def test_invalid_constraint_result_is_rejected() -> None:
    class InvalidConstraint(DecisionConstraintBoundary):
        __slots__ = ()

        def evaluate(
            self,
            intent: DecisionIntent,
        ) -> FeasibleDecisionIntent:
            return cast(FeasibleDecisionIntent, object())

    policy = RecordingPolicy(DecisionContextResult(DecisionIntent(0.0)))

    with pytest.raises(TypeError, match="FeasibleDecisionIntent"):
        evaluate(make_state(), policy, InvalidConstraint())


def test_orchestrator_is_stateless_and_does_not_own_boundaries() -> None:
    orchestrator = DecisionEvaluationOrchestrator()

    assert DecisionEvaluationOrchestrator.__slots__ == ()
    assert not hasattr(orchestrator, "__dict__")
    for forbidden in (
        "policy",
        "constraint",
        "runtime",
        "dispatcher",
        "device",
        "cache",
        "history",
        "storage",
    ):
        assert not hasattr(orchestrator, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, orchestrator).policy = object()


def test_all_external_facts_are_required_keyword_only_parameters() -> None:
    parameters = inspect.signature(DecisionEvaluationOrchestrator.evaluate).parameters

    assert list(parameters) == [
        "state",
        "policy",
        "constraint",
        "timestamp",
        "battery_power_limit_kw",
        "battery_energy_capacity_kwh",
        "load_power_kw",
        "electricity_price_cny_per_kwh",
        "reserve_soc",
        "export_limit_kw",
    ]
    for name in list(parameters)[3:]:
        parameter = parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_orchestration_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(orchestration_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    for forbidden in (
        "kernel.runtime",
        "kernel.dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert forbidden not in imported_modules


def test_public_import_works() -> None:
    assert DecisionEvaluationOrchestrator.__name__ == ("DecisionEvaluationOrchestrator")
