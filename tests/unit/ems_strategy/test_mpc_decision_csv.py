"""Tests for deterministic in-memory CSV export of MPC journal records."""

import ast
import csv
import inspect
import io
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    EXPLAINABLE_MPC_DECISION_CSV_COLUMNS,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    ExplainableMPCDecisionCSVRow,
    ExplainableMPCDecisionCSVRowMappingBoundary,
    ExplainableMPCDecisionCSVRowMappingInput,
    ExplainableMPCDecisionCSVSerializerBoundary,
    ExplainableMPCDecisionJournalRecordInput,
)
from ems_strategy.mpc_decision_journal import ExplainableMPCDecisionJournalRecord
from tests.unit.ems_strategy.test_mpc_decision_journal import _artifacts


def _record(*, power: float = 6.0) -> ExplainableMPCDecisionJournalRecord:
    cycle, explanation, formatted = _artifacts(power=power)
    return DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
        ExplainableMPCDecisionJournalRecordInput(cycle, explanation, formatted)
    )


def test_row_is_primitive_immutable_and_maps_exact_record_values() -> None:
    record = _record()
    mapping_input = ExplainableMPCDecisionCSVRowMappingInput(record)
    row = DeterministicExplainableMPCDecisionCSVRowMapper().map(mapping_input)

    assert [field.name for field in fields(ExplainableMPCDecisionCSVRow)] == list(
        EXPLAINABLE_MPC_DECISION_CSV_COLUMNS
    )
    assert not hasattr(row, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, row).timestamp = "changed"
    assert row.timestamp == record.timestamp.isoformat()
    assert row.strategy_name == record.strategy.name
    assert row.strategy_version == record.strategy.version
    assert row.candidate_action == "discharge"
    assert row.candidate_requested_power_kw == 6.0
    assert row.final_action == "discharge"
    assert row.final_requested_power_kw == 4.0
    assert row.revision_reasons == "discharge_power_limit"
    assert row.candidate_soc_violation_kinds == ""
    assert row.candidate_power_violation_kinds == "discharge_power_above_max"
    assert row.formatted_text == record.formatted_text
    assert all(
        type(getattr(row, field.name)) in (str, float, bool) for field in fields(row)
    )


def test_mapper_is_deterministic_and_no_revision_has_blank_reason_cells() -> None:
    record = _record(power=2.0)
    mapper = DeterministicExplainableMPCDecisionCSVRowMapper()
    mapping_input = ExplainableMPCDecisionCSVRowMappingInput(record)

    assert mapper.map(mapping_input) == mapper.map(mapping_input)
    row = mapper.map(mapping_input)
    assert row.revision_applied is False
    assert row.revision_reasons == ""
    assert row.candidate_soc_violation_kinds == ""
    assert row.candidate_power_violation_kinds == ""


def test_serializer_uses_exact_header_and_preserves_caller_order() -> None:
    first = DeterministicExplainableMPCDecisionCSVRowMapper().map(
        ExplainableMPCDecisionCSVRowMappingInput(_record())
    )
    second = DeterministicExplainableMPCDecisionCSVRowMapper().map(
        ExplainableMPCDecisionCSVRowMappingInput(_record(power=2.0))
    )
    serializer = DeterministicExplainableMPCDecisionCSVSerializer()
    text = serializer.serialize((second, first))

    assert "\r\n" not in text
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == list(EXPLAINABLE_MPC_DECISION_CSV_COLUMNS)
    assert rows[1][0] == second.timestamp
    assert rows[2][0] == first.timestamp
    assert rows[2][8] == "discharge_power_limit"
    assert rows[2][10] == "discharge_power_above_max"
    assert rows[2][11:15] == ["false", "true", "true", "true"]
    assert rows[2][-1] == first.formatted_text
    assert '"' in text
    assert (
        serializer.serialize(())
        == ",".join(EXPLAINABLE_MPC_DECISION_CSV_COLUMNS) + "\n"
    )


def test_serializer_rejects_non_tuple_and_non_row_inputs() -> None:
    serializer = DeterministicExplainableMPCDecisionCSVSerializer()
    with pytest.raises(TypeError, match="tuple"):
        serializer.serialize(cast(Any, []))
    with pytest.raises(TypeError, match="contain"):
        serializer.serialize(cast(Any, (object(),)))


def test_boundaries_are_abstract_stateless_and_isolated_from_execution() -> None:
    mapping_signature = inspect.signature(
        ExplainableMPCDecisionCSVRowMappingBoundary.map
    )
    mapping_hints = get_type_hints(ExplainableMPCDecisionCSVRowMappingBoundary.map)
    serializer_signature = inspect.signature(
        ExplainableMPCDecisionCSVSerializerBoundary.serialize
    )
    serializer_hints = get_type_hints(
        ExplainableMPCDecisionCSVSerializerBoundary.serialize
    )
    module_path = Path(ems_strategy.__file__).parent / "mpc_decision_csv.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert issubclass(ExplainableMPCDecisionCSVRowMappingBoundary, ABC)
    assert inspect.isabstract(ExplainableMPCDecisionCSVRowMappingBoundary)
    assert ExplainableMPCDecisionCSVRowMappingBoundary.__slots__ == ()
    assert list(mapping_signature.parameters) == ["self", "mapping_input"]
    assert mapping_hints["return"] is ExplainableMPCDecisionCSVRow
    assert issubclass(ExplainableMPCDecisionCSVSerializerBoundary, ABC)
    assert inspect.isabstract(ExplainableMPCDecisionCSVSerializerBoundary)
    assert ExplainableMPCDecisionCSVSerializerBoundary.__slots__ == ()
    assert list(serializer_signature.parameters) == ["self", "rows"]
    assert serializer_hints["return"] is str
    assert not hasattr(DeterministicExplainableMPCDecisionCSVRowMapper(), "__dict__")
    assert not hasattr(DeterministicExplainableMPCDecisionCSVSerializer(), "__dict__")
    for forbidden in (
        "optimization",
        "kernel.event",
        "ems_simulator",
        "runtime",
        "device",
    ):
        assert forbidden not in imported_modules


def test_public_api_exports_csv_contracts() -> None:
    for name in (
        "EXPLAINABLE_MPC_DECISION_CSV_COLUMNS",
        "ExplainableMPCDecisionCSVRow",
        "ExplainableMPCDecisionCSVRowMappingInput",
        "ExplainableMPCDecisionCSVRowMappingBoundary",
        "DeterministicExplainableMPCDecisionCSVRowMapper",
        "ExplainableMPCDecisionCSVSerializerBoundary",
        "DeterministicExplainableMPCDecisionCSVSerializer",
    ):
        assert name in ems_strategy.__all__
