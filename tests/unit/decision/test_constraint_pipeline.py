"""Tests for deterministic constraint composition."""

import ast
import inspect
from collections.abc import Callable
from typing import cast, get_type_hints

import pytest

from kernel.decision import (
    ConstraintEvaluationPipeline,
    DecisionConstraintBoundary,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import constraint_pipeline as constraint_pipeline_module


class RecordingConstraint(DecisionConstraintBoundary):
    """Test-only constraint with explicit transformation behavior."""

    __slots__ = ("calls", "name", "transform")

    def __init__(
        self,
        name: str,
        transform: Callable[[DecisionIntent], FeasibleDecisionIntent],
    ) -> None:
        self.name = name
        self.transform = transform
        self.calls: list[DecisionIntent] = []

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        self.calls.append(intent)
        return self.transform(intent)


class InvalidResultConstraint(DecisionConstraintBoundary):
    """Test-only invalid implementation."""

    __slots__ = ()

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        return cast(FeasibleDecisionIntent, object())


class FailingConstraint(DecisionConstraintBoundary):
    """Test-only implementation that propagates a supplied failure."""

    __slots__ = ("error",)

    def __init__(self, error: RuntimeError) -> None:
        self.error = error

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        raise self.error


def preserve_intent(intent: DecisionIntent) -> FeasibleDecisionIntent:
    return FeasibleDecisionIntent(intent)


def test_pipeline_contract_is_stateless_and_explicit() -> None:
    parameters = list(
        inspect.signature(ConstraintEvaluationPipeline.evaluate).parameters
    )
    hints = get_type_hints(ConstraintEvaluationPipeline.evaluate)
    pipeline = ConstraintEvaluationPipeline()

    assert parameters == ["source_intent", "constraints"]
    assert hints == {
        "source_intent": DecisionIntent,
        "constraints": tuple[DecisionConstraintBoundary, ...],
        "return": FeasibleDecisionIntent,
    }
    assert ConstraintEvaluationPipeline.__slots__ == ()
    assert not hasattr(pipeline, "__dict__")


def test_constraints_execute_once_in_exact_caller_order() -> None:
    source_intent = DecisionIntent(10.0)
    first_output_intent = DecisionIntent(6.0)
    second_output_intent = DecisionIntent(2.0)
    first_result = FeasibleDecisionIntent(first_output_intent)
    second_result = FeasibleDecisionIntent(second_output_intent)
    third_result = FeasibleDecisionIntent(second_output_intent)
    order: list[str] = []

    def first_transform(intent: DecisionIntent) -> FeasibleDecisionIntent:
        order.append("first")
        return first_result

    def second_transform(intent: DecisionIntent) -> FeasibleDecisionIntent:
        order.append("second")
        return second_result

    def third_transform(intent: DecisionIntent) -> FeasibleDecisionIntent:
        order.append("third")
        return third_result

    first = RecordingConstraint("first", first_transform)
    second = RecordingConstraint("second", second_transform)
    third = RecordingConstraint("third", third_transform)

    result = ConstraintEvaluationPipeline.evaluate(
        source_intent,
        (first, second, third),
    )

    assert order == ["first", "second", "third"]
    assert first.calls == [source_intent]
    assert second.calls == [first_output_intent]
    assert third.calls == [second_output_intent]
    assert result is third_result


def test_each_stage_receives_exact_previous_inner_intent() -> None:
    source_intent = DecisionIntent(10.0)
    first_output_intent = DecisionIntent(7.0)
    second_output_intent = DecisionIntent(3.0)
    first_result = FeasibleDecisionIntent(first_output_intent)
    second_result = FeasibleDecisionIntent(second_output_intent)
    first = RecordingConstraint("first", lambda intent: first_result)
    second = RecordingConstraint("second", lambda intent: second_result)

    result = ConstraintEvaluationPipeline.evaluate(
        source_intent,
        (first, second),
    )

    assert first.calls[0] is source_intent
    assert second.calls[0] is first_output_intent
    assert result is second_result
    assert result.intent is second_output_intent


def test_all_unadjusted_constraints_preserve_source_identity() -> None:
    source_intent = DecisionIntent(4.0)
    first = RecordingConstraint("first", preserve_intent)
    second = RecordingConstraint("second", preserve_intent)

    result = ConstraintEvaluationPipeline.evaluate(
        source_intent,
        (first, second),
    )

    assert first.calls[0] is source_intent
    assert second.calls[0] is source_intent
    assert result.intent is source_intent


def test_empty_pipeline_returns_wrapper_for_exact_source_intent() -> None:
    source_intent = DecisionIntent(1.0)

    result = ConstraintEvaluationPipeline.evaluate(source_intent, ())

    assert result.intent is source_intent


def test_duplicate_constraint_is_not_deduplicated() -> None:
    constraint = RecordingConstraint("duplicate", preserve_intent)
    source_intent = DecisionIntent(1.0)

    result = ConstraintEvaluationPipeline.evaluate(
        source_intent,
        (constraint, constraint),
    )

    assert constraint.calls == [source_intent, source_intent]
    assert result.intent is source_intent


def test_constraint_exception_propagates_and_stops_pipeline() -> None:
    error = RuntimeError("constraint failure")
    first = RecordingConstraint("first", preserve_intent)
    failing = FailingConstraint(error)
    later = RecordingConstraint("later", preserve_intent)

    with pytest.raises(RuntimeError) as captured:
        ConstraintEvaluationPipeline.evaluate(
            DecisionIntent(1.0),
            (first, failing, later),
        )

    assert captured.value is error
    assert len(first.calls) == 1
    assert later.calls == []


def test_invalid_constraint_result_is_rejected() -> None:
    with pytest.raises(TypeError, match="FeasibleDecisionIntent"):
        ConstraintEvaluationPipeline.evaluate(
            DecisionIntent(1.0),
            (InvalidResultConstraint(),),
        )


def test_invalid_source_intent_is_rejected_before_execution() -> None:
    constraint = RecordingConstraint("unused", preserve_intent)

    with pytest.raises(TypeError, match="source_intent"):
        ConstraintEvaluationPipeline.evaluate(
            cast(DecisionIntent, object()),
            (constraint,),
        )

    assert constraint.calls == []


def test_mutable_constraint_collection_is_rejected() -> None:
    constraint = RecordingConstraint("unused", preserve_intent)

    with pytest.raises(TypeError, match="tuple"):
        ConstraintEvaluationPipeline.evaluate(
            DecisionIntent(1.0),
            cast(tuple[DecisionConstraintBoundary, ...], [constraint]),
        )

    assert constraint.calls == []


def test_invalid_constraint_member_is_rejected_before_execution() -> None:
    first = RecordingConstraint("unused", preserve_intent)

    with pytest.raises(TypeError, match="DecisionConstraintBoundary"):
        ConstraintEvaluationPipeline.evaluate(
            DecisionIntent(1.0),
            (
                first,
                cast(DecisionConstraintBoundary, object()),
            ),
        )

    assert first.calls == []


def test_module_has_only_decision_boundary_dependencies() -> None:
    tree = ast.parse(inspect.getsource(constraint_pipeline_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "kernel.decision.constraint",
        "kernel.decision.intent",
    }


def test_public_import_works() -> None:
    assert ConstraintEvaluationPipeline.__name__ == ("ConstraintEvaluationPipeline")
