"""Tests for immutable ordered constraint explanation artifacts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.decision import (
    ConstraintExplanation,
    ConstraintExplanationChain,
    ConstraintExplanationEntry,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import (
    constraint_explanation_chain as explanation_chain_module,
)


def test_unchanged_entry_preserves_exact_artifacts() -> None:
    source_intent = DecisionIntent(2.0)
    feasible_intent = FeasibleDecisionIntent(source_intent)

    entry = ConstraintExplanationEntry.create(
        source_intent,
        feasible_intent,
        adjustment_reason=None,
    )

    assert entry.source_intent is source_intent
    assert entry.feasible_intent is feasible_intent
    assert entry.feasible_intent.intent is source_intent
    assert entry.adjusted is False
    assert entry.adjustment_reason is None


def test_adjusted_entry_preserves_exact_artifacts_and_supplied_reason() -> None:
    source_intent = DecisionIntent(4.0)
    adjusted_intent = DecisionIntent(1.0)
    feasible_intent = FeasibleDecisionIntent(adjusted_intent)
    reason = "battery charge power limit"

    entry = ConstraintExplanationEntry.create(
        source_intent,
        feasible_intent,
        adjustment_reason=reason,
    )

    assert entry.source_intent is source_intent
    assert entry.feasible_intent is feasible_intent
    assert entry.feasible_intent.intent is adjusted_intent
    assert entry.adjusted is True
    assert entry.adjustment_reason is reason


def test_entry_is_frozen_slotted_and_has_exact_fields() -> None:
    source_intent = DecisionIntent(0.0)
    entry = ConstraintExplanationEntry.create(
        source_intent,
        FeasibleDecisionIntent(source_intent),
        adjustment_reason=None,
    )

    assert cast(Any, ConstraintExplanationEntry).__dataclass_params__.frozen
    assert ConstraintExplanationEntry.__slots__ == (
        "source_intent",
        "feasible_intent",
        "adjusted",
        "adjustment_reason",
    )
    assert tuple(field.name for field in fields(ConstraintExplanationEntry)) == (
        "source_intent",
        "feasible_intent",
        "adjusted",
        "adjustment_reason",
    )
    assert not hasattr(entry, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, entry).adjusted = True


def test_entry_rejects_adjusted_flag_identity_mismatch() -> None:
    source_intent = DecisionIntent(1.0)

    with pytest.raises(ValueError, match="adjusted"):
        ConstraintExplanationEntry(
            source_intent=source_intent,
            feasible_intent=FeasibleDecisionIntent(source_intent),
            adjusted=True,
            adjustment_reason="not actually adjusted",
        )


def test_adjusted_entry_requires_non_empty_reason() -> None:
    source_intent = DecisionIntent(3.0)
    feasible_intent = FeasibleDecisionIntent(DecisionIntent(1.0))

    for reason in (None, "", "   "):
        with pytest.raises(ValueError, match="adjustment_reason"):
            ConstraintExplanationEntry.create(
                source_intent,
                feasible_intent,
                adjustment_reason=reason,
            )


def test_unchanged_entry_rejects_reason() -> None:
    source_intent = DecisionIntent(1.0)

    with pytest.raises(ValueError, match="adjustment_reason"):
        ConstraintExplanationEntry.create(
            source_intent,
            FeasibleDecisionIntent(source_intent),
            adjustment_reason="no adjustment occurred",
        )


@pytest.mark.parametrize(
    ("field_name", "value", "expected_error"),
    [
        ("source_intent", object(), "source_intent"),
        ("feasible_intent", object(), "feasible_intent"),
        ("adjusted", 1, "adjusted"),
        ("adjustment_reason", object(), "adjustment_reason"),
    ],
)
def test_entry_rejects_invalid_field_types(
    field_name: str,
    value: object,
    expected_error: str,
) -> None:
    source_intent = DecisionIntent(0.0)
    values: dict[str, object] = {
        "source_intent": source_intent,
        "feasible_intent": FeasibleDecisionIntent(source_intent),
        "adjusted": False,
        "adjustment_reason": None,
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=expected_error):
        ConstraintExplanationEntry(
            source_intent=cast(DecisionIntent, values["source_intent"]),
            feasible_intent=cast(
                FeasibleDecisionIntent,
                values["feasible_intent"],
            ),
            adjusted=cast(bool, values["adjusted"]),
            adjustment_reason=cast(str | None, values["adjustment_reason"]),
        )


def test_chain_preserves_order_and_exact_stage_lineage() -> None:
    source_intent = DecisionIntent(8.0)
    battery_intent = DecisionIntent(5.0)
    grid_intent = DecisionIntent(2.0)
    battery_result = FeasibleDecisionIntent(battery_intent)
    grid_result = FeasibleDecisionIntent(grid_intent)
    battery_entry = ConstraintExplanationEntry.create(
        source_intent,
        battery_result,
        adjustment_reason="battery power limit",
    )
    grid_entry = ConstraintExplanationEntry.create(
        battery_intent,
        grid_result,
        adjustment_reason="grid import limit",
    )
    entries = (battery_entry, grid_entry)

    chain = ConstraintExplanationChain.create(
        source_intent,
        entries,
        grid_result,
    )

    assert chain.source_intent is source_intent
    assert chain.entries is entries
    assert chain.entries == (battery_entry, grid_entry)
    assert chain.entries[0] is battery_entry
    assert chain.entries[1] is grid_entry
    assert chain.entries[1].source_intent is battery_result.intent
    assert chain.feasible_intent is grid_result
    assert chain.feasible_intent.intent is grid_intent


def test_chain_supports_unchanged_intermediate_stage() -> None:
    source_intent = DecisionIntent(4.0)
    first_result = FeasibleDecisionIntent(source_intent)
    adjusted_intent = DecisionIntent(2.0)
    final_result = FeasibleDecisionIntent(adjusted_intent)
    first_entry = ConstraintExplanationEntry.create(
        source_intent,
        first_result,
        adjustment_reason=None,
    )
    final_entry = ConstraintExplanationEntry.create(
        source_intent,
        final_result,
        adjustment_reason="grid export limit",
    )

    chain = ConstraintExplanationChain.create(
        source_intent,
        (first_entry, final_entry),
        final_result,
    )

    assert first_entry.adjusted is False
    assert final_entry.source_intent is first_result.intent
    assert chain.feasible_intent is final_result


def test_empty_chain_preserves_source_identity() -> None:
    source_intent = DecisionIntent(0.0)
    feasible_intent = FeasibleDecisionIntent(source_intent)

    chain = ConstraintExplanationChain.create(
        source_intent,
        (),
        feasible_intent,
    )

    assert chain.entries == ()
    assert chain.source_intent is source_intent
    assert chain.feasible_intent is feasible_intent
    assert chain.feasible_intent.intent is source_intent


def test_chain_is_frozen_slotted_and_has_exact_fields() -> None:
    source_intent = DecisionIntent(0.0)
    chain = ConstraintExplanationChain.create(
        source_intent,
        (),
        FeasibleDecisionIntent(source_intent),
    )

    assert cast(Any, ConstraintExplanationChain).__dataclass_params__.frozen
    assert ConstraintExplanationChain.__slots__ == (
        "source_intent",
        "entries",
        "feasible_intent",
    )
    assert tuple(field.name for field in fields(ConstraintExplanationChain)) == (
        "source_intent",
        "entries",
        "feasible_intent",
    )
    assert not hasattr(chain, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, chain).entries = ()


def test_chain_rejects_mutable_entry_collection() -> None:
    source_intent = DecisionIntent(0.0)

    with pytest.raises(TypeError, match="tuple"):
        ConstraintExplanationChain.create(
            source_intent,
            cast(tuple[ConstraintExplanationEntry, ...], []),
            FeasibleDecisionIntent(source_intent),
        )


def test_chain_rejects_invalid_entry_member() -> None:
    source_intent = DecisionIntent(0.0)

    with pytest.raises(TypeError, match="ConstraintExplanationEntry"):
        ConstraintExplanationChain.create(
            source_intent,
            (cast(ConstraintExplanationEntry, object()),),
            FeasibleDecisionIntent(source_intent),
        )


def test_chain_rejects_broken_first_source_identity() -> None:
    source_intent = DecisionIntent(2.0)
    other_source = DecisionIntent(2.0)
    entry = ConstraintExplanationEntry.create(
        other_source,
        FeasibleDecisionIntent(other_source),
        adjustment_reason=None,
    )

    with pytest.raises(ValueError, match="previous exact feasible intent"):
        ConstraintExplanationChain.create(
            source_intent,
            (entry,),
            entry.feasible_intent,
        )


def test_chain_rejects_broken_intermediate_identity() -> None:
    source_intent = DecisionIntent(4.0)
    first_intent = DecisionIntent(3.0)
    first_entry = ConstraintExplanationEntry.create(
        source_intent,
        FeasibleDecisionIntent(first_intent),
        adjustment_reason="first adjustment",
    )
    equal_but_distinct_intent = DecisionIntent(3.0)
    second_entry = ConstraintExplanationEntry.create(
        equal_but_distinct_intent,
        FeasibleDecisionIntent(equal_but_distinct_intent),
        adjustment_reason=None,
    )

    with pytest.raises(ValueError, match="previous exact feasible intent"):
        ConstraintExplanationChain.create(
            source_intent,
            (first_entry, second_entry),
            second_entry.feasible_intent,
        )


def test_chain_rejects_non_exact_final_wrapper() -> None:
    source_intent = DecisionIntent(3.0)
    adjusted_intent = DecisionIntent(1.0)
    entry = ConstraintExplanationEntry.create(
        source_intent,
        FeasibleDecisionIntent(adjusted_intent),
        adjustment_reason="physical limit",
    )

    with pytest.raises(ValueError, match="exact final entry result"):
        ConstraintExplanationChain.create(
            source_intent,
            (entry,),
            FeasibleDecisionIntent(adjusted_intent),
        )


def test_empty_chain_rejects_different_final_intent() -> None:
    with pytest.raises(ValueError, match="empty chain"):
        ConstraintExplanationChain.create(
            DecisionIntent(0.0),
            (),
            FeasibleDecisionIntent(DecisionIntent(0.0)),
        )


def test_chain_rejects_invalid_endpoint_types() -> None:
    source_intent = DecisionIntent(0.0)

    with pytest.raises(TypeError, match="source_intent"):
        ConstraintExplanationChain.create(
            cast(DecisionIntent, object()),
            (),
            FeasibleDecisionIntent(source_intent),
        )
    with pytest.raises(TypeError, match="feasible_intent"):
        ConstraintExplanationChain.create(
            source_intent,
            (),
            cast(FeasibleDecisionIntent, object()),
        )


def test_chain_module_has_only_domain_observation_dependencies() -> None:
    tree = ast.parse(inspect.getsource(explanation_chain_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.constraint",
        "kernel.decision.intent",
    }


def test_existing_constraint_explanation_contract_is_unchanged() -> None:
    assert ConstraintExplanation.__slots__ == (
        "feasible_intent",
        "source_intent",
    )


def test_public_imports_work() -> None:
    assert ConstraintExplanationEntry.__name__ == "ConstraintExplanationEntry"
    assert ConstraintExplanationChain.__name__ == "ConstraintExplanationChain"
