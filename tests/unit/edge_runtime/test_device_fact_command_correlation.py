"""Focused P0.11 tests for audit-only device-fact command correlation."""

from __future__ import annotations

import ast
import copy
import inspect
import pickle
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edge_runtime.device_fact_command_correlation import (
    DeterministicDeviceFactCommandCorrelationAuditor,
    DeviceFactAcknowledgementObservation,
    DeviceFactActualObservation,
    DeviceFactCommandCorrelationAssessment,
    DeviceFactCommandCorrelationAvailability,
    DeviceFactCommandCorrelationGapCode,
    DeviceFactCommandCorrelationInput,
    DeviceFactCommandCorrelationStatus,
    DeviceFactSourceEpochRelationship,
    DeviceFactTransmissionIdentity,
)

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def _transmission(**changes: object) -> DeviceFactTransmissionIdentity:
    values: dict[str, object] = {
        "transmission_identity": "tx-001",
        "sequence": 7,
        "origin": "caller-owned",
        "declared_at": NOW - timedelta(minutes=2),
        "source_identity": "adapter-a",
        "identity_epoch": "epoch-1",
    }
    values.update(changes)
    return DeviceFactTransmissionIdentity(**values)  # type: ignore[arg-type]


def _acknowledgement(**changes: object) -> DeviceFactAcknowledgementObservation:
    values: dict[str, object] = {
        "transmission_identity": "tx-001",
        "sequence": 7,
        "origin": "caller-owned",
        "observed_at": NOW - timedelta(minutes=1),
        "source_identity": "adapter-a",
        "identity_epoch": "epoch-1",
        "availability": DeviceFactCommandCorrelationAvailability.AVAILABLE,
    }
    values.update(changes)
    return DeviceFactAcknowledgementObservation(**values)  # type: ignore[arg-type]


def _actual(**changes: object) -> DeviceFactActualObservation:
    values: dict[str, object] = {
        "observation_identity": "actual-001",
        "observed_at": NOW - timedelta(minutes=1),
        "source_identity": "adapter-a",
        "identity_epoch": "epoch-1",
        "availability": DeviceFactCommandCorrelationAvailability.AVAILABLE,
        "actual_power_kw": 1.25,
    }
    values.update(changes)
    return DeviceFactActualObservation(**values)  # type: ignore[arg-type]


def _relationship(**changes: object) -> DeviceFactSourceEpochRelationship:
    values: dict[str, object] = {
        "transmission_source_identity": "adapter-a",
        "transmission_identity_epoch": "epoch-1",
        "acknowledgement_source_identity": "adapter-a",
        "acknowledgement_identity_epoch": "epoch-1",
        "actual_source_identity": "adapter-a",
        "actual_identity_epoch": "epoch-1",
    }
    values.update(changes)
    return DeviceFactSourceEpochRelationship(**values)  # type: ignore[arg-type]


def _input(**changes: object) -> DeviceFactCommandCorrelationInput:
    values: dict[str, object] = {
        "assessment_identity": "assessment-001",
        "assessment_as_of": NOW,
        "maximum_age": timedelta(minutes=5),
        "transmission": _transmission(),
        "acknowledgement": _acknowledgement(),
        "actual": _actual(),
        "source_epoch_relationship": _relationship(),
    }
    values.update(changes)
    return DeviceFactCommandCorrelationInput(**values)  # type: ignore[arg-type]


def _codes(assessment: DeviceFactCommandCorrelationAssessment) -> set[str]:
    return {finding.gap_code.value for finding in assessment.findings}


def test_public_api_is_auditor_and_inert_contracts_only() -> None:
    import edge_runtime.device_fact_command_correlation as public_api

    assert set(public_api.__all__) == {
        "DeterministicDeviceFactCommandCorrelationAuditor",
        "DeviceFactAcknowledgementObservation",
        "DeviceFactActualObservation",
        "DeviceFactCommandCorrelationAssessment",
        "DeviceFactCommandCorrelationAvailability",
        "DeviceFactCommandCorrelationFinding",
        "DeviceFactCommandCorrelationGapCode",
        "DeviceFactCommandCorrelationInput",
        "DeviceFactCommandCorrelationStatus",
        "DeviceFactSourceEpochRelationship",
        "DeviceFactTransmissionIdentity",
    }


def test_matching_finite_facts_pass_without_claiming_execution() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(_input())

    assert assessment.status is DeviceFactCommandCorrelationStatus.PASS
    assert assessment.findings == ()
    assert tuple(field.name for field in fields(assessment)) == (
        "assessment_identity",
        "assessment_as_of",
        "status",
        "findings",
    )


def test_explicitly_declared_different_source_epoch_relationship_passes() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(
            acknowledgement=_acknowledgement(
                source_identity="ack-source", identity_epoch="ack-epoch"
            ),
            actual=_actual(
                source_identity="actual-source", identity_epoch="actual-epoch"
            ),
            source_epoch_relationship=_relationship(
                acknowledgement_source_identity="ack-source",
                acknowledgement_identity_epoch="ack-epoch",
                actual_source_identity="actual-source",
                actual_identity_epoch="actual-epoch",
            ),
        )
    )

    assert assessment.status is DeviceFactCommandCorrelationStatus.PASS


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"acknowledgement": object()},
            DeviceFactCommandCorrelationGapCode.MALFORMED_OR_HISTORICAL_FACT,
        ),
        (
            {"source_epoch_relationship": object()},
            DeviceFactCommandCorrelationGapCode.SOURCE_EPOCH_RELATIONSHIP_UNDECLARED,
        ),
        (
            {
                "acknowledgement": _acknowledgement(
                    availability=DeviceFactCommandCorrelationAvailability.UNKNOWN
                )
            },
            DeviceFactCommandCorrelationGapCode.ACKNOWLEDGEMENT_UNAVAILABLE,
        ),
        (
            {
                "actual": _actual(
                    availability=DeviceFactCommandCorrelationAvailability.MISSING,
                    actual_power_kw=None,
                )
            },
            DeviceFactCommandCorrelationGapCode.ACTUAL_UNAVAILABLE,
        ),
    ],
)
def test_missing_unknown_and_malformed_facts_fail_closed(
    changes: dict[str, object], expected: DeviceFactCommandCorrelationGapCode
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(**changes)
    )

    assert assessment.status is DeviceFactCommandCorrelationStatus.GAP
    assert expected.value in _codes(assessment)


@pytest.mark.parametrize(
    "acknowledgement",
    [
        _acknowledgement(transmission_identity="wrong"),
        _acknowledgement(sequence=8),
        _acknowledgement(origin="wrong-origin"),
    ],
)
def test_acknowledgement_identity_sequence_origin_mismatch_is_gap(
    acknowledgement: DeviceFactAcknowledgementObservation,
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(acknowledgement=acknowledgement)
    )

    assert (
        DeviceFactCommandCorrelationGapCode.ACKNOWLEDGEMENT_CORRELATION_MISMATCH.value
        in _codes(assessment)
    )


def test_acknowledgement_and_actual_relationship_conflicts_are_gaps() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(
            source_epoch_relationship=_relationship(actual_identity_epoch="wrong-epoch")
        )
    )

    assert (
        DeviceFactCommandCorrelationGapCode.SOURCE_EPOCH_RELATIONSHIP_MISMATCH.value
        in _codes(assessment)
    )


def test_acknowledgement_cannot_be_replaced_by_actual_observation() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(
            acknowledgement=_acknowledgement(
                availability=DeviceFactCommandCorrelationAvailability.UNAVAILABLE
            ),
            actual=_actual(actual_power_kw=4.0),
        )
    )

    assert assessment.status is DeviceFactCommandCorrelationStatus.GAP
    assert (
        DeviceFactCommandCorrelationGapCode.ACKNOWLEDGEMENT_UNAVAILABLE.value
        in _codes(assessment)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"assessment_identity": "tx-001"},
        {"assessment_identity": "actual-001"},
        {"acknowledgement": _acknowledgement(observed_at=NOW + timedelta(seconds=1))},
        {"actual": _actual(observed_at=NOW - timedelta(minutes=6))},
    ],
)
def test_assessment_identity_and_time_scope_fail_closed(
    changes: dict[str, object],
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(
        _input(**changes)
    )

    assert assessment.status is DeviceFactCommandCorrelationStatus.GAP
    assert _codes(assessment) & {
        DeviceFactCommandCorrelationGapCode.ASSESSMENT_IDENTITY_REUSED.value,
        DeviceFactCommandCorrelationGapCode.TIME_SCOPE_INVALID.value,
    }


def test_historical_assessment_cannot_be_reused_as_input_or_fact() -> None:
    auditor = DeterministicDeviceFactCommandCorrelationAuditor()
    prior = auditor.evaluate(_input())

    with pytest.raises(TypeError, match="DeviceFactCommandCorrelationInput"):
        auditor.evaluate(prior)

    assessment = auditor.evaluate(_input(actual=prior))
    assert (
        DeviceFactCommandCorrelationGapCode.MALFORMED_OR_HISTORICAL_FACT.value
        in _codes(assessment)
    )


def test_assessment_is_immutable_serializable_inert_evidence_only() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationAuditor().evaluate(_input())

    assert copy.copy(assessment) == assessment
    assert copy.deepcopy(assessment) == assessment
    assert pickle.loads(pickle.dumps(assessment)) == assessment
    with pytest.raises(ValueError, match="status must match findings"):
        replace(assessment, status=DeviceFactCommandCorrelationStatus.GAP)
    forbidden = {
        "command",
        "runtime",
        "adapter",
        "session",
        "continuation",
        "request",
        "input",
        "transmission",
    }
    assert forbidden.isdisjoint(field.name for field in fields(assessment))


def test_auditor_is_stateless_and_has_no_authority_parameters() -> None:
    auditor = DeterministicDeviceFactCommandCorrelationAuditor()

    assert auditor.__slots__ == ()
    assert tuple(inspect.signature(auditor.evaluate).parameters) == ("value",)


def test_source_has_no_transport_or_predecessor_runtime_imports() -> None:
    package = (
        Path(__file__).parents[3] / "edge_runtime" / "device_fact_command_correlation"
    )
    forbidden = {
        "socket",
        "http",
        "urllib",
        "requests",
        "can",
        "modbus",
        "serial",
        "threading",
        "asyncio",
        "subprocess",
        "edge_runtime.controlled_runtime",
        "edge_runtime.device_adapter",
        "edge_runtime.controlled_composition",
        "edge_runtime.device_fact_readiness",
        "edge_runtime.device_fact_lifecycle_continuity",
    }
    imported: set[str] = set()
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )

    assert not any(
        imported_name == blocked or imported_name.startswith(f"{blocked}.")
        for imported_name in imported
        for blocked in forbidden
    )
