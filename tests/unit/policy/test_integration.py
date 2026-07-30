"""Tests for the complete decision evaluation integration boundary."""

import ast
import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import (
    ConstraintEvaluationPipeline,
    ConstraintExplanation,
    ConstraintExplanationChain,
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
    DecisionEvaluationIntegration,
    DecisionEvaluationIntegrationResult,
)
from kernel.policy import integration as integration_module
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
    constraints: tuple[DecisionConstraintBoundary, ...],
    reasons: tuple[str, ...],
) -> DecisionEvaluationIntegrationResult:
    return DecisionEvaluationIntegration.evaluate(
        state,
        policy,
        constraints,
        constraint_adjustment_reasons=reasons,
        timestamp=FIXED_TIME,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        load_power_kw=20.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


class RecordingPolicy(DecisionContextPolicy):
    __slots__ = ("calls", "contexts", "order", "result")

    def __init__(
        self,
        result: DecisionContextResult,
        order: list[str] | None = None,
    ) -> None:
        self.calls = 0
        self.contexts: list[DecisionContext] = []
        self.order = order
        self.result = result

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        self.calls += 1
        self.contexts.append(context)
        if self.order is not None:
            self.order.append("policy")
        return self.result


class RecordingConstraint(DecisionConstraintBoundary):
    __slots__ = ("calls", "inputs", "name", "order", "transform")

    def __init__(
        self,
        name: str,
        transform: Callable[[DecisionIntent], FeasibleDecisionIntent],
        order: list[str] | None = None,
    ) -> None:
        self.calls = 0
        self.inputs: list[DecisionIntent] = []
        self.name = name
        self.order = order
        self.transform = transform

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        self.calls += 1
        self.inputs.append(intent)
        if self.order is not None:
            self.order.append(self.name)
        return self.transform(intent)


class RaisingPolicy(DecisionContextPolicy):
    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        raise POLICY_ERROR


class RaisingConstraint(DecisionConstraintBoundary):
    __slots__ = ()

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        raise CONSTRAINT_ERROR


def test_complete_evaluation_preserves_exact_cycle_and_chain() -> None:
    source_intent = DecisionIntent(8.0)
    policy_result = DecisionContextResult(source_intent)
    battery_intent = DecisionIntent(5.0)
    battery_result = FeasibleDecisionIntent(battery_intent)
    final_result = FeasibleDecisionIntent(battery_intent)
    battery_reason = "battery power limit"
    unused_grid_reason = "grid import limit"
    policy = RecordingPolicy(policy_result)
    battery_constraint = RecordingConstraint(
        "battery",
        lambda intent: battery_result,
    )
    grid_constraint = RecordingConstraint(
        "grid",
        lambda intent: final_result,
    )

    integrated = evaluate(
        make_state(),
        policy,
        (battery_constraint, grid_constraint),
        (battery_reason, unused_grid_reason),
    )

    cycle = integrated.cycle
    chain = integrated.explanation_chain
    assert policy.calls == 1
    assert policy.contexts == [cycle.context]
    assert policy.contexts[0] is cycle.context
    assert cycle.result is policy_result
    assert cycle.source_intent is source_intent
    assert battery_constraint.calls == 1
    assert battery_constraint.inputs[0] is source_intent
    assert grid_constraint.calls == 1
    assert grid_constraint.inputs[0] is battery_intent
    assert chain.source_intent is source_intent
    assert chain.entries[0].source_intent is source_intent
    assert chain.entries[0].feasible_intent is battery_result
    assert chain.entries[0].adjusted is True
    assert chain.entries[0].adjustment_reason is battery_reason
    assert chain.entries[1].source_intent is battery_intent
    assert chain.entries[1].feasible_intent is final_result
    assert chain.entries[1].adjusted is False
    assert chain.entries[1].adjustment_reason is None
    assert chain.feasible_intent is final_result
    assert cycle.feasible_intent is final_result


def test_multiple_adjustments_preserve_stage_order_and_identity() -> None:
    source_intent = DecisionIntent(9.0)
    first_intent = DecisionIntent(6.0)
    second_intent = DecisionIntent(2.0)
    first_result = FeasibleDecisionIntent(first_intent)
    second_result = FeasibleDecisionIntent(second_intent)
    order: list[str] = []
    first = RecordingConstraint("first", lambda intent: first_result, order)
    second = RecordingConstraint("second", lambda intent: second_result, order)

    integrated = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (first, second),
        ("first reason", "second reason"),
    )

    entries = integrated.explanation_chain.entries
    assert order == ["first", "second"]
    assert entries[0].source_intent is source_intent
    assert entries[0].feasible_intent is first_result
    assert entries[1].source_intent is first_result.intent
    assert entries[1].feasible_intent is second_result
    assert integrated.explanation_chain.feasible_intent is second_result
    assert integrated.cycle.feasible_intent is second_result


def test_empty_constraint_pipeline_preserves_source_identity() -> None:
    source_intent = DecisionIntent(0.0)

    integrated = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (),
        (),
    )

    assert integrated.explanation_chain.entries == ()
    assert integrated.explanation_chain.source_intent is source_intent
    assert integrated.explanation_chain.feasible_intent.intent is source_intent
    assert (
        integrated.cycle.feasible_intent is integrated.explanation_chain.feasible_intent
    )


def test_every_boundary_runs_once_in_required_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    source_intent = DecisionIntent(3.0)
    policy = RecordingPolicy(DecisionContextResult(source_intent), order)
    constraint = RecordingConstraint(
        "constraint",
        lambda intent: FeasibleDecisionIntent(intent),
        order,
    )
    original_assemble = cast(
        Callable[..., DecisionContext],
        DecisionContextAssembler.assemble,
    )
    original_pipeline = ConstraintEvaluationPipeline.evaluate
    original_chain = ConstraintExplanationChain.create
    original_explanation = ConstraintExplanation.create
    original_cycle = DecisionEvaluationCycle.create

    def assemble(*args: object, **kwargs: object) -> DecisionContext:
        order.append("assemble")
        return original_assemble(*args, **kwargs)

    def pipeline(
        intent: DecisionIntent,
        constraints: tuple[DecisionConstraintBoundary, ...],
    ) -> FeasibleDecisionIntent:
        order.append("pipeline")
        return original_pipeline(intent, constraints)

    def create_chain(
        intent: DecisionIntent,
        entries: tuple[Any, ...],
        feasible_intent: FeasibleDecisionIntent,
    ) -> ConstraintExplanationChain:
        order.append("chain")
        return original_chain(
            intent,
            cast(Any, entries),
            feasible_intent,
        )

    def create_explanation(
        feasible_intent: FeasibleDecisionIntent,
        intent: DecisionIntent,
    ) -> ConstraintExplanation:
        order.append("explanation")
        return original_explanation(feasible_intent, intent)

    def create_cycle(
        context: DecisionContext,
        result: DecisionContextResult,
        feasible_intent: FeasibleDecisionIntent,
        explanation: ConstraintExplanation,
    ) -> DecisionEvaluationCycle:
        order.append("cycle")
        return original_cycle(context, result, feasible_intent, explanation)

    monkeypatch.setattr(DecisionContextAssembler, "assemble", assemble)
    monkeypatch.setattr(ConstraintEvaluationPipeline, "evaluate", pipeline)
    monkeypatch.setattr(ConstraintExplanationChain, "create", create_chain)
    monkeypatch.setattr(ConstraintExplanation, "create", create_explanation)
    monkeypatch.setattr(DecisionEvaluationCycle, "create", create_cycle)

    evaluate(make_state(), policy, (constraint,), ("physical limit",))

    assert order == [
        "assemble",
        "policy",
        "pipeline",
        "constraint",
        "chain",
        "explanation",
        "cycle",
    ]
    assert policy.calls == 1
    assert constraint.calls == 1


def test_caller_reason_is_used_only_for_an_adjusted_stage() -> None:
    source_intent = DecisionIntent(5.0)
    adjusted_intent = DecisionIntent(1.0)
    reason = "caller supplied physical reason"
    constraint = RecordingConstraint(
        "constraint",
        lambda intent: FeasibleDecisionIntent(adjusted_intent),
    )

    integrated = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (constraint,),
        (reason,),
    )

    entry = integrated.explanation_chain.entries[0]
    assert entry.adjusted is True
    assert entry.adjustment_reason is reason


def test_policy_failure_prevents_pipeline_and_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraint = RecordingConstraint(
        "unused",
        lambda intent: FeasibleDecisionIntent(intent),
    )

    def fail_pipeline(*args: object, **kwargs: object) -> FeasibleDecisionIntent:
        raise AssertionError("policy failure reached pipeline")

    monkeypatch.setattr(
        ConstraintEvaluationPipeline,
        "evaluate",
        fail_pipeline,
    )

    with pytest.raises(RuntimeError) as raised:
        evaluate(
            make_state(),
            RaisingPolicy(),
            (constraint,),
            ("unused reason",),
        )

    assert raised.value is POLICY_ERROR
    assert constraint.calls == 0


def test_constraint_failure_stops_chain_and_later_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later = RecordingConstraint(
        "later",
        lambda intent: FeasibleDecisionIntent(intent),
    )

    def fail_chain(*args: object, **kwargs: object) -> ConstraintExplanationChain:
        raise AssertionError("constraint failure reached explanation chain")

    monkeypatch.setattr(ConstraintExplanationChain, "create", fail_chain)

    with pytest.raises(RuntimeError) as raised:
        evaluate(
            make_state(),
            RecordingPolicy(DecisionContextResult(DecisionIntent(0.0))),
            (RaisingConstraint(), later),
            ("first reason", "later reason"),
        )

    assert raised.value is CONSTRAINT_ERROR
    assert later.calls == 0


def test_invalid_policy_result_is_rejected_before_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidPolicy(DecisionContextPolicy):
        __slots__ = ()

        def evaluate(
            self,
            context: DecisionContext,
        ) -> DecisionContextResult:
            return cast(DecisionContextResult, object())

    def fail_pipeline(*args: object, **kwargs: object) -> FeasibleDecisionIntent:
        raise AssertionError("invalid policy result reached pipeline")

    monkeypatch.setattr(
        ConstraintEvaluationPipeline,
        "evaluate",
        fail_pipeline,
    )

    with pytest.raises(TypeError, match="DecisionContextResult"):
        evaluate(make_state(), InvalidPolicy(), (), ())


def test_invalid_constraint_result_is_rejected() -> None:
    class InvalidConstraint(DecisionConstraintBoundary):
        __slots__ = ()

        def evaluate(
            self,
            intent: DecisionIntent,
        ) -> FeasibleDecisionIntent:
            return cast(FeasibleDecisionIntent, object())

    with pytest.raises(TypeError, match="FeasibleDecisionIntent"):
        evaluate(
            make_state(),
            RecordingPolicy(DecisionContextResult(DecisionIntent(0.0))),
            (InvalidConstraint(),),
            ("invalid result reason",),
        )


@pytest.mark.parametrize(
    ("constraints", "reasons", "expected_error"),
    [
        ([], (), "constraints"),
        ((object(),), ("reason",), "DecisionConstraintBoundary"),
        ((), [], "constraint_adjustment_reasons"),
        ((object(),), (), "DecisionConstraintBoundary"),
        ((), ("extra",), "match constraints length"),
        ((object(),), (object(),), "DecisionConstraintBoundary"),
    ],
)
def test_invalid_constraint_configuration_fails_before_assembly(
    constraints: object,
    reasons: object,
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_assembly(*args: object, **kwargs: object) -> DecisionContext:
        raise AssertionError("invalid configuration reached assembly")

    monkeypatch.setattr(DecisionContextAssembler, "assemble", fail_assembly)
    policy = RecordingPolicy(DecisionContextResult(DecisionIntent(0.0)))

    with pytest.raises((TypeError, ValueError), match=expected_error):
        evaluate(
            make_state(),
            policy,
            cast(tuple[DecisionConstraintBoundary, ...], constraints),
            cast(tuple[str, ...], reasons),
        )


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_caller_reason_is_rejected_before_assembly(
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraint = RecordingConstraint(
        "unused",
        lambda intent: FeasibleDecisionIntent(intent),
    )

    def fail_assembly(*args: object, **kwargs: object) -> DecisionContext:
        raise AssertionError("blank reason reached assembly")

    monkeypatch.setattr(DecisionContextAssembler, "assemble", fail_assembly)

    with pytest.raises(ValueError, match="non-empty"):
        evaluate(
            make_state(),
            RecordingPolicy(DecisionContextResult(DecisionIntent(0.0))),
            (constraint,),
            (reason,),
        )

    assert constraint.calls == 0


def test_non_string_caller_reason_is_rejected_before_assembly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraint = RecordingConstraint(
        "unused",
        lambda intent: FeasibleDecisionIntent(intent),
    )

    def fail_assembly(*args: object, **kwargs: object) -> DecisionContext:
        raise AssertionError("non-string reason reached assembly")

    monkeypatch.setattr(DecisionContextAssembler, "assemble", fail_assembly)

    with pytest.raises(TypeError, match="str values"):
        evaluate(
            make_state(),
            RecordingPolicy(DecisionContextResult(DecisionIntent(0.0))),
            (constraint,),
            cast(tuple[str, ...], (object(),)),
        )

    assert constraint.calls == 0


def test_result_is_frozen_slotted_and_preserves_exact_artifacts() -> None:
    source_intent = DecisionIntent(0.0)
    integrated = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (),
        (),
    )

    assert cast(
        Any,
        DecisionEvaluationIntegrationResult,
    ).__dataclass_params__.frozen
    assert DecisionEvaluationIntegrationResult.__slots__ == (
        "cycle",
        "explanation_chain",
    )
    assert tuple(
        field.name for field in fields(DecisionEvaluationIntegrationResult)
    ) == ("cycle", "explanation_chain")
    assert not hasattr(integrated, "__dict__")
    assert integrated.explanation_chain.source_intent is integrated.cycle.source_intent
    assert (
        integrated.explanation_chain.feasible_intent is integrated.cycle.feasible_intent
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, integrated).cycle = object()


def test_result_rejects_invalid_or_mismatched_artifacts() -> None:
    source_intent = DecisionIntent(0.0)
    first = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (),
        (),
    )
    other = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(DecisionIntent(0.0))),
        (),
        (),
    )
    adjusted = evaluate(
        make_state(),
        RecordingPolicy(DecisionContextResult(source_intent)),
        (
            RecordingConstraint(
                "adjusted",
                lambda intent: FeasibleDecisionIntent(DecisionIntent(1.0)),
            ),
        ),
        ("adjusted reason",),
    )

    with pytest.raises(TypeError, match="cycle"):
        DecisionEvaluationIntegrationResult(
            cycle=cast(DecisionEvaluationCycle, object()),
            explanation_chain=first.explanation_chain,
        )
    with pytest.raises(TypeError, match="explanation_chain"):
        DecisionEvaluationIntegrationResult(
            cycle=first.cycle,
            explanation_chain=cast(ConstraintExplanationChain, object()),
        )
    with pytest.raises(ValueError, match="source intent"):
        DecisionEvaluationIntegrationResult(
            cycle=first.cycle,
            explanation_chain=other.explanation_chain,
        )
    with pytest.raises(ValueError, match="feasible intent"):
        DecisionEvaluationIntegrationResult(
            cycle=first.cycle,
            explanation_chain=adjusted.explanation_chain,
        )


def test_integration_is_stateless_and_external_facts_are_explicit() -> None:
    integration = DecisionEvaluationIntegration()
    parameters = inspect.signature(DecisionEvaluationIntegration.evaluate).parameters

    assert DecisionEvaluationIntegration.__slots__ == ()
    assert not hasattr(integration, "__dict__")
    assert list(parameters) == [
        "state",
        "policy",
        "constraints",
        "constraint_adjustment_reasons",
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


def test_integration_has_no_forbidden_dependencies() -> None:
    tree = ast.parse(inspect.getsource(integration_module))
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


def test_existing_public_contracts_are_unchanged() -> None:
    assert DecisionConstraintBoundary.__slots__ == ()
    assert ConstraintEvaluationPipeline.__slots__ == ()
    assert DecisionEvaluationCycle.__slots__ == (
        "context",
        "result",
        "source_intent",
        "feasible_intent",
        "explanation",
    )


def test_public_imports_work() -> None:
    assert DecisionEvaluationIntegration.__name__ == "DecisionEvaluationIntegration"
    assert DecisionEvaluationIntegrationResult.__name__ == (
        "DecisionEvaluationIntegrationResult"
    )
