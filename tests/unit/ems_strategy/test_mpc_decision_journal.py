"""Tests for read-only per-decision MPC explainability journal records."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    ExplainableMPCDecisionJournalRecord,
    ExplainableMPCDecisionJournalRecordBoundary,
    ExplainableMPCDecisionJournalRecordInput,
    FormattedMPCDecisionExplanation,
    MPCDecisionExplanation,
    MPCDecisionExplanationFormatInput,
    MPCDecisionExplanationInput,
    PhysicallyAwareMPCCycleResult,
)
from optimization import BatteryOptimizationModel
from tests.unit.ems_strategy.test_physically_aware_mpc_cycle import (
    make_orchestrator,
    make_physical_input,
    make_real_physical_optimizer,
)


def _artifacts(
    *, soc: float = 0.8, power: float = 6.0
) -> tuple[
    PhysicallyAwareMPCCycleResult,
    MPCDecisionExplanation,
    FormattedMPCDecisionExplanation,
]:
    cycle = (
        make_orchestrator().run_cycle(make_physical_input(soc=soc))
        if power == 6.0
        else make_orchestrator(make_real_physical_optimizer(power)).run_cycle(
            make_physical_input(soc=soc)
        )
    )
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(cycle)
    )
    formatted = DeterministicMPCDecisionExplanationFormatter().format(
        MPCDecisionExplanationFormatInput(explanation, "en-US")
    )
    return cycle, explanation, formatted


def test_record_contracts_are_frozen_slotted_and_preserve_exact_sources() -> None:
    cycle, explanation, formatted = _artifacts()
    record_input = ExplainableMPCDecisionJournalRecordInput(
        cycle, explanation, formatted
    )
    record = DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
        record_input
    )

    assert [
        field.name for field in fields(ExplainableMPCDecisionJournalRecordInput)
    ] == [
        "cycle_result",
        "explanation",
        "formatted_explanation",
    ]
    assert [field.name for field in fields(ExplainableMPCDecisionJournalRecord)] == [
        "source_input",
        "timestamp",
        "strategy",
        "final_action",
        "final_requested_power_kw",
        "candidate_action",
        "candidate_requested_power_kw",
        "revision_applied",
        "revision_reasons",
        "candidate_soc_violation_kinds",
        "candidate_power_violation_kinds",
        "candidate_battery_horizon_feasible",
        "final_soc_feasible",
        "final_power_feasible",
        "final_battery_horizon_feasible",
        "candidate_starting_soc_fraction",
        "candidate_ending_soc_fraction",
        "final_starting_soc_fraction",
        "final_ending_soc_fraction",
        "min_soc_fraction",
        "max_soc_fraction",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "formatted_text",
    ]
    assert record.source_input is record_input
    assert record.source_input.cycle_result is cycle
    assert record.source_input.explanation is explanation
    assert record.source_input.formatted_explanation is formatted
    assert (
        record.timestamp
        is cycle.source_input.cycle_input.context.source_context.timestamp
    )
    assert record.strategy is cycle.source_input.cycle_input.source_strategy
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, record).formatted_text = "changed"


def test_builder_reuses_power_revision_and_formatted_evidence_exactly() -> None:
    cycle, explanation, formatted = _artifacts()
    record = DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
        ExplainableMPCDecisionJournalRecordInput(cycle, explanation, formatted)
    )
    physical = explanation.physical_explanation

    assert record.candidate_action is explanation.candidate_action
    assert record.candidate_requested_power_kw == 6.0
    assert record.final_action is explanation.final_action
    assert record.final_requested_power_kw == 4.0
    assert record.revision_applied is True
    assert record.revision_reasons is physical.revision_reasons
    assert (
        record.candidate_power_violation_kinds
        is physical.candidate_power_violation_kinds
    )
    assert (
        record.candidate_soc_violation_kinds is physical.candidate_soc_violation_kinds
    )
    assert record.final_battery_horizon_feasible is True
    assert record.formatted_text == formatted.text


def test_soc_and_no_revision_evidence_remain_complete() -> None:
    soc_cycle = make_orchestrator().run_cycle(
        make_physical_input(
            soc=0.2,
            model=BatteryOptimizationModel(10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 0.9),
        )
    )
    soc_explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(soc_cycle)
    )
    soc_formatted = DeterministicMPCDecisionExplanationFormatter().format(
        MPCDecisionExplanationFormatInput(soc_explanation, "zh-CN")
    )
    soc_record = DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
        ExplainableMPCDecisionJournalRecordInput(
            soc_cycle, soc_explanation, soc_formatted
        )
    )
    no_revision_cycle, no_revision_explanation, no_revision_formatted = _artifacts(
        power=2.0
    )
    no_revision_record = (
        DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
            ExplainableMPCDecisionJournalRecordInput(
                no_revision_cycle, no_revision_explanation, no_revision_formatted
            )
        )
    )

    assert "min_soc_limit" in soc_record.revision_reasons
    assert soc_record.candidate_soc_violation_kinds == ("below_min_soc",)
    assert (
        soc_record.candidate_ending_soc_fraction
        == soc_explanation.physical_explanation.candidate_ending_soc_fraction
    )
    assert no_revision_record.revision_applied is False
    assert no_revision_record.revision_reasons == ()
    assert (
        no_revision_record.candidate_action is no_revision_explanation.candidate_action
    )
    assert no_revision_record.final_action is no_revision_explanation.final_action


def test_input_rejects_mismatched_exact_cycle_or_explanation() -> None:
    cycle, explanation, formatted = _artifacts()
    other_cycle, other_explanation, other_formatted = _artifacts(power=2.0)

    with pytest.raises(ValueError, match="cycle result identity"):
        ExplainableMPCDecisionJournalRecordInput(other_cycle, explanation, formatted)
    with pytest.raises(ValueError, match="explanation identity"):
        ExplainableMPCDecisionJournalRecordInput(cycle, explanation, other_formatted)
    assert other_explanation is not explanation


def test_boundary_is_abstract_stateless_and_has_no_event_or_execution_dependency() -> (
    None
):
    signature = inspect.signature(ExplainableMPCDecisionJournalRecordBoundary.build)
    hints = get_type_hints(ExplainableMPCDecisionJournalRecordBoundary.build)
    module_path = Path(ems_strategy.__file__).parent / "mpc_decision_journal.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert issubclass(ExplainableMPCDecisionJournalRecordBoundary, ABC)
    assert inspect.isabstract(ExplainableMPCDecisionJournalRecordBoundary)
    assert ExplainableMPCDecisionJournalRecordBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "record_input"]
    assert hints["record_input"] is ExplainableMPCDecisionJournalRecordInput
    assert hints["return"] is ExplainableMPCDecisionJournalRecord
    with pytest.raises(TypeError):
        ExplainableMPCDecisionJournalRecordBoundary()  # type: ignore[abstract]
    assert not hasattr(
        DeterministicExplainableMPCDecisionJournalRecordBuilder(), "__dict__"
    )
    for forbidden in (
        "kernel.event",
        "optimization",
        "ems_simulator",
        "runtime",
        "device",
        "execution",
    ):
        assert forbidden not in imported_modules


def test_public_api_exports_journal_contracts() -> None:
    for name in (
        "ExplainableMPCDecisionJournalRecordInput",
        "ExplainableMPCDecisionJournalRecord",
        "ExplainableMPCDecisionJournalRecordBoundary",
        "DeterministicExplainableMPCDecisionJournalRecordBuilder",
    ):
        assert name in ems_strategy.__all__
