"""Focused P0.12 tests for audit-only command-correlation continuity."""

from __future__ import annotations

import ast
import copy
import inspect
import pickle
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edge_runtime.device_fact_command_correlation import (
    DeterministicDeviceFactCommandCorrelationAuditor,
    DeviceFactAcknowledgementObservation,
    DeviceFactActualObservation,
    DeviceFactCommandCorrelationAssessment,
    DeviceFactCommandCorrelationAvailability,
    DeviceFactCommandCorrelationInput,
    DeviceFactSourceEpochRelationship,
    DeviceFactTransmissionIdentity,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeterministicDeviceFactCommandCorrelationContinuityAuditor,
    DeviceFactCommandCorrelationContinuityAssessment,
    DeviceFactCommandCorrelationContinuityGapCode,
    DeviceFactCommandCorrelationContinuityInput,
    DeviceFactCommandCorrelationContinuityScope,
    DeviceFactCommandCorrelationContinuityStatus,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    evaluator as continuity_evaluator,
)

NOW = datetime(2026, 9, 22, 12, tzinfo=UTC)


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


def _member(
    index: int,
    *,
    assessment_as_of: datetime | None = None,
    sequence: int | None = None,
    transmission_identity: str | None = None,
    actual_identity: str | None = None,
    origin: str = "caller-owned",
    relationship: DeviceFactSourceEpochRelationship | None = None,
    acknowledgement_availability: DeviceFactCommandCorrelationAvailability = (
        DeviceFactCommandCorrelationAvailability.AVAILABLE
    ),
) -> DeviceFactCommandCorrelationInput:
    as_of = assessment_as_of or NOW - timedelta(minutes=3 - index)
    transaction_sequence = sequence if sequence is not None else index
    transaction_identity = transmission_identity or f"tx-{index}"
    actual_observation_identity = actual_identity or f"actual-{index}"
    source_relationship = relationship or _relationship()
    transmission = DeviceFactTransmissionIdentity(
        transaction_identity,
        transaction_sequence,
        origin,
        as_of - timedelta(minutes=2),
        source_relationship.transmission_source_identity,
        source_relationship.transmission_identity_epoch,
    )
    acknowledgement = DeviceFactAcknowledgementObservation(
        transaction_identity,
        transaction_sequence,
        origin,
        as_of - timedelta(minutes=1),
        source_relationship.acknowledgement_source_identity,
        source_relationship.acknowledgement_identity_epoch,
        acknowledgement_availability,
    )
    actual = DeviceFactActualObservation(
        actual_observation_identity,
        as_of - timedelta(minutes=1),
        source_relationship.actual_source_identity,
        source_relationship.actual_identity_epoch,
        DeviceFactCommandCorrelationAvailability.AVAILABLE,
        1.25,
    )
    return DeviceFactCommandCorrelationInput(
        f"member-assessment-{index}",
        as_of,
        timedelta(minutes=5),
        transmission,
        acknowledgement,
        actual,
        source_relationship,
    )


def _scope(**changes: object) -> DeviceFactCommandCorrelationContinuityScope:
    values: dict[str, object] = {
        "scope_identity": "scope-a",
        "transmission_origin": "caller-owned",
        "source_epoch_relationship": _relationship(),
    }
    values.update(changes)
    return DeviceFactCommandCorrelationContinuityScope(**values)  # type: ignore[arg-type]


def _input(**changes: object) -> DeviceFactCommandCorrelationContinuityInput:
    values: dict[str, object] = {
        "assessment_identity": "continuity-assessment-a",
        "assessment_as_of": NOW,
        "maximum_age": timedelta(minutes=5),
        "scope": _scope(),
        "members": (_member(1), _member(2)),
    }
    values.update(changes)
    return DeviceFactCommandCorrelationContinuityInput(**values)  # type: ignore[arg-type]


def _codes(value: DeviceFactCommandCorrelationContinuityAssessment) -> set[str]:
    return {finding.gap_code.value for finding in value.findings}


def test_public_api_is_exact_audit_only_contracts() -> None:
    import edge_runtime.device_fact_command_correlation_continuity as public_api

    assert set(public_api.__all__) == {
        "DeterministicDeviceFactCommandCorrelationContinuityAuditor",
        "DeviceFactCommandCorrelationContinuityAssessment",
        "DeviceFactCommandCorrelationContinuityFinding",
        "DeviceFactCommandCorrelationContinuityGapCode",
        "DeviceFactCommandCorrelationContinuityInput",
        "DeviceFactCommandCorrelationContinuityScope",
        "DeviceFactCommandCorrelationContinuityStatus",
    }


def test_valid_scope_passes_and_delegates_each_member_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = DeterministicDeviceFactCommandCorrelationAuditor()
    calls: list[DeviceFactCommandCorrelationInput] = []

    class CountingAuditor:
        def evaluate(
            self, value: DeviceFactCommandCorrelationInput
        ) -> DeviceFactCommandCorrelationAssessment:
            calls.append(value)
            return upstream.evaluate(value)

    monkeypatch.setattr(
        continuity_evaluator,
        "DeterministicDeviceFactCommandCorrelationAuditor",
        CountingAuditor,
    )
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input()
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.PASS
    assert assessment.findings == ()
    assert calls == list(_input().members)


def test_member_p0_11_gap_cannot_be_repaired_by_actual_or_other_member() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input(
            members=(
                _member(
                    1,
                    acknowledgement_availability=(
                        DeviceFactCommandCorrelationAvailability.UNAVAILABLE
                    ),
                ),
                _member(2),
            )
        )
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.GAP
    expected = DeviceFactCommandCorrelationContinuityGapCode.MEMBER_P0_11_GAP
    assert expected.value in _codes(assessment)


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        (
            (_member(1), _member(2, transmission_identity="tx-1")),
            DeviceFactCommandCorrelationContinuityGapCode.TRANSMISSION_IDENTITY_REUSED,
        ),
        (
            (_member(1), _member(2, actual_identity="actual-1")),
            DeviceFactCommandCorrelationContinuityGapCode.ACTUAL_OBSERVATION_IDENTITY_REUSED,
        ),
        (
            (
                _member(1),
                _member(2, assessment_as_of=NOW - timedelta(minutes=2)),
            ),
            DeviceFactCommandCorrelationContinuityGapCode.ASSESSMENT_TIME_NOT_STRICT,
        ),
        (
            (_member(1), _member(2, sequence=1)),
            DeviceFactCommandCorrelationContinuityGapCode.TRANSACTION_SEQUENCE_NOT_STRICT,
        ),
    ],
)
def test_cross_member_identity_and_order_violations_fail_closed(
    members: tuple[DeviceFactCommandCorrelationInput, ...],
    expected: DeviceFactCommandCorrelationContinuityGapCode,
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input(members=members)
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.GAP
    assert expected.value in _codes(assessment)


def test_scope_relationship_mismatch_is_gap_not_lifecycle_event() -> None:
    changed = _relationship(actual_identity_epoch="epoch-2")
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input(members=(_member(1), _member(2, relationship=changed)))
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.GAP
    assert DeviceFactCommandCorrelationContinuityGapCode.SCOPE_MISMATCH.value in _codes(
        assessment
    )
    assert "reboot" not in " ".join(finding.detail for finding in assessment.findings)


@pytest.mark.parametrize(
    "members",
    [
        (_member(1),),
        (object(), _member(2)),
        (
            DeterministicDeviceFactCommandCorrelationAuditor().evaluate(_member(1)),
            _member(2),
        ),
    ],
)
def test_too_few_malformed_and_historical_members_fail_closed(
    members: tuple[object, ...],
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input(members=members)
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.GAP
    assert _codes(assessment) & {
        DeviceFactCommandCorrelationContinuityGapCode.TOO_FEW_MEMBERS.value,
        DeviceFactCommandCorrelationContinuityGapCode.MALFORMED_OR_HISTORICAL_MEMBER.value,
    }


@pytest.mark.parametrize(
    "assessment_as_of",
    [NOW - timedelta(minutes=10), NOW + timedelta(minutes=1)],
)
def test_continuity_time_scope_rejects_stale_or_future_members(
    assessment_as_of: datetime,
) -> None:
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input(members=(_member(1), _member(2, assessment_as_of=assessment_as_of)))
    )

    assert assessment.status is DeviceFactCommandCorrelationContinuityStatus.GAP
    expected = (
        DeviceFactCommandCorrelationContinuityGapCode.CONTINUITY_TIME_SCOPE_INVALID
    )
    assert expected.value in _codes(assessment)


def test_assessment_is_inert_serializable_evidence_without_authority() -> None:
    assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
        _input()
    )

    assert copy.copy(assessment) == assessment
    assert copy.deepcopy(assessment) == assessment
    assert pickle.loads(pickle.dumps(assessment)) == assessment
    forbidden = {
        "command",
        "device",
        "runtime",
        "adapter",
        "session",
        "continuation",
        "input",
        "member",
        "transmission",
        "actual",
    }
    assert forbidden.isdisjoint(field.name for field in fields(assessment))


def test_auditor_is_stateless_and_has_one_caller_input() -> None:
    auditor = DeterministicDeviceFactCommandCorrelationContinuityAuditor()

    assert auditor.__slots__ == ()
    assert tuple(inspect.signature(auditor.evaluate).parameters) == ("value",)


def test_source_has_no_forbidden_transport_or_execution_imports() -> None:
    package = (
        Path(__file__).parents[3]
        / "edge_runtime"
        / "device_fact_command_correlation_continuity"
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
