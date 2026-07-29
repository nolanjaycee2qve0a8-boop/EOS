"""Tests for the immutable decision evaluation cycle."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import (
    ConstraintExplanation,
    DecisionConstraintBoundary,
    DecisionContext,
    DecisionContextResult,
    DecisionEvaluationCycle,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import evaluation_cycle as cycle_module
from kernel.policy import DecisionContextPolicy


def make_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=25.0,
        load_power_kw=20.0,
        grid_power_kw=-5.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


def make_artifacts() -> tuple[
    DecisionContext,
    DecisionContextResult,
    DecisionIntent,
    FeasibleDecisionIntent,
    ConstraintExplanation,
]:
    context = make_context()
    intent = DecisionIntent(5.0)
    result = DecisionContextResult(intent)
    feasible_intent = FeasibleDecisionIntent(intent)
    explanation = ConstraintExplanation.create(feasible_intent)
    return context, result, intent, feasible_intent, explanation


def make_cycle() -> DecisionEvaluationCycle:
    context, result, _, feasible_intent, explanation = make_artifacts()
    return DecisionEvaluationCycle.create(
        context,
        result,
        feasible_intent,
        explanation,
    )


def test_create_preserves_every_artifact_identity() -> None:
    context, result, intent, feasible_intent, explanation = make_artifacts()

    cycle = DecisionEvaluationCycle.create(
        context,
        result,
        feasible_intent,
        explanation,
    )

    assert cycle.context is context
    assert cycle.result is result
    assert cycle.intent is intent
    assert cycle.feasible_intent is feasible_intent
    assert cycle.explanation is explanation


def test_cycle_is_frozen_and_slotted() -> None:
    cycle = make_cycle()

    assert is_dataclass(cycle)
    assert cast(Any, DecisionEvaluationCycle).__dataclass_params__.frozen
    assert DecisionEvaluationCycle.__slots__ == (
        "context",
        "result",
        "intent",
        "feasible_intent",
        "explanation",
    )
    assert not hasattr(cycle, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cycle).context = make_context()


def test_cycle_contains_only_lifecycle_references() -> None:
    cycle = make_cycle()

    assert [field.name for field in fields(cycle)] == [
        "context",
        "result",
        "intent",
        "feasible_intent",
        "explanation",
    ]
    for forbidden in (
        "policy",
        "commands",
        "events",
        "runtime",
        "dispatcher",
        "cache",
        "history",
        "storage",
    ):
        assert not hasattr(cycle, forbidden)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("context", object()),
        ("result", object()),
        ("intent", object()),
        ("feasible_intent", object()),
        ("explanation", object()),
    ],
)
def test_cycle_rejects_invalid_artifact_types(
    field_name: str,
    invalid_value: object,
) -> None:
    context, result, intent, feasible_intent, explanation = make_artifacts()
    values: dict[str, object] = {
        "context": context,
        "result": result,
        "intent": intent,
        "feasible_intent": feasible_intent,
        "explanation": explanation,
    }
    values[field_name] = invalid_value

    with pytest.raises(TypeError, match=field_name):
        DecisionEvaluationCycle(
            context=cast(DecisionContext, values["context"]),
            result=cast(DecisionContextResult, values["result"]),
            intent=cast(DecisionIntent, values["intent"]),
            feasible_intent=cast(
                FeasibleDecisionIntent,
                values["feasible_intent"],
            ),
            explanation=cast(
                ConstraintExplanation,
                values["explanation"],
            ),
        )


def test_cycle_rejects_result_intent_identity_mismatch() -> None:
    context, result, _, feasible_intent, explanation = make_artifacts()

    with pytest.raises(ValueError, match="result intent"):
        DecisionEvaluationCycle(
            context,
            result,
            DecisionIntent(5.0),
            feasible_intent,
            explanation,
        )


def test_cycle_rejects_feasible_intent_identity_mismatch() -> None:
    context, result, intent, _, _ = make_artifacts()
    other_feasible_intent = FeasibleDecisionIntent(DecisionIntent(5.0))
    other_explanation = ConstraintExplanation.create(other_feasible_intent)

    with pytest.raises(ValueError, match="feasible_intent"):
        DecisionEvaluationCycle(
            context,
            result,
            intent,
            other_feasible_intent,
            other_explanation,
        )


def test_cycle_rejects_explanation_identity_mismatch() -> None:
    context, result, intent, feasible_intent, _ = make_artifacts()
    other_feasible_intent = FeasibleDecisionIntent(intent)
    other_explanation = ConstraintExplanation.create(other_feasible_intent)

    with pytest.raises(ValueError, match="explanation"):
        DecisionEvaluationCycle(
            context,
            result,
            intent,
            feasible_intent,
            other_explanation,
        )


def test_create_does_not_execute_policy_or_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, result, _, feasible_intent, explanation = make_artifacts()

    def fail(*_: object) -> None:
        raise AssertionError("execution boundary called")

    monkeypatch.setattr(DecisionContextPolicy, "evaluate", fail)
    monkeypatch.setattr(DecisionConstraintBoundary, "evaluate", fail)

    cycle = DecisionEvaluationCycle.create(
        context,
        result,
        feasible_intent,
        explanation,
    )

    assert cycle.context is context


def test_cycle_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(cycle_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.constraint",
        "kernel.decision.constraint_explanation",
        "kernel.decision.context",
        "kernel.decision.context_result",
        "kernel.decision.intent",
    }
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert forbidden not in imported_modules


def test_public_import_has_explicit_name() -> None:
    assert DecisionEvaluationCycle.__name__ == "DecisionEvaluationCycle"
