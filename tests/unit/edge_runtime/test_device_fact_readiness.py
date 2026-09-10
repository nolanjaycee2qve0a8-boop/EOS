"""Focused P0.9 tests for a pure, audit-only device-fact readiness evaluator."""

import ast
import copy
import inspect
import pickle
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from edge_runtime.device_fact_readiness import (
    DeterministicDeviceFactReadinessEvaluator,
    DeviceFactAvailability,
    DeviceFactCapabilityProfile,
    DeviceFactEvidenceSample,
    DeviceFactGapCode,
    DeviceFactReadinessAssessment,
    DeviceFactReadinessFinding,
    DeviceFactReadinessInput,
    DeviceFactReadinessStatus,
    DeviceFactRequirement,
    DeviceFactRequirementPolicy,
)

NOW = datetime(2034, 1, 1, 12, tzinfo=UTC)


def _profile() -> DeviceFactCapabilityProfile:
    return DeviceFactCapabilityProfile(
        "profile-a",
        "pcs-bms-fact-source-a",
        "caller-provenance-a",
        "boot-epoch-a",
        frozenset(DeviceFactRequirement),
    )


def _policies() -> tuple[DeviceFactRequirementPolicy, ...]:
    return tuple(
        DeviceFactRequirementPolicy(requirement, timedelta(minutes=5))
        for requirement in DeviceFactRequirement
    )


def _sample(
    requirement: DeviceFactRequirement,
    *,
    observed_at: datetime = NOW,
    availability: DeviceFactAvailability = DeviceFactAvailability.AVAILABLE,
    source_identity: str = "pcs-bms-fact-source-a",
    provenance_id: str = "caller-provenance-a",
    continuity_id: str = "boot-epoch-a",
    assessment_id: str = "assessment-a",
    evidence_set_id: str = "evidence-a",
    actual_present: bool = True,
    ack_matches: bool = True,
) -> DeviceFactEvidenceSample:
    request_id = (
        "request-a" if requirement is DeviceFactRequirement.ACK_CORRELATION else None
    )
    sequence = 7 if requirement is DeviceFactRequirement.ACK_CORRELATION else None
    correlation_id = (
        "correlation-a"
        if requirement is DeviceFactRequirement.ACK_CORRELATION
        else None
    )
    acknowledgement_id = request_id if ack_matches else "request-other"
    return DeviceFactEvidenceSample(
        f"fact-{requirement.value}",
        requirement,
        source_identity,
        provenance_id,
        continuity_id,
        assessment_id,
        evidence_set_id,
        observed_at,
        availability,
        request_id,
        sequence,
        correlation_id,
        acknowledgement_id,
        sequence,
        correlation_id,
        actual_present,
    )


def _input(
    *,
    samples: tuple[DeviceFactEvidenceSample, ...] | None = None,
    profile: DeviceFactCapabilityProfile | None = None,
    as_of: datetime = NOW,
) -> DeviceFactReadinessInput:
    return DeviceFactReadinessInput(
        "assessment-a",
        "evidence-a",
        profile or _profile(),
        _policies(),
        samples or tuple(_sample(requirement) for requirement in DeviceFactRequirement),
        as_of,
    )


def _finding(
    assessment: DeviceFactReadinessAssessment,
    requirement: DeviceFactRequirement,
) -> DeviceFactReadinessFinding:
    return next(
        finding for finding in assessment.findings if finding.requirement is requirement
    )


def test_complete_explicit_evidence_returns_audit_only_pass() -> None:
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(_input())

    assert assessment.status is DeviceFactReadinessStatus.PASS
    assert {finding.status for finding in assessment.findings} == {
        DeviceFactReadinessStatus.PASS
    }
    assert not hasattr(assessment, "profile")
    assert not hasattr(assessment, "evidence")


@pytest.mark.parametrize(
    ("sample_factory", "expected"),
    [
        (
            lambda requirement: _sample(requirement, source_identity="wrong-source"),
            DeviceFactGapCode.IDENTITY_MISMATCH,
        ),
        (
            lambda requirement: _sample(requirement, provenance_id="wrong-provenance"),
            DeviceFactGapCode.PROVENANCE_MISMATCH,
        ),
        (
            lambda requirement: _sample(
                requirement, availability=DeviceFactAvailability.MISSING
            ),
            DeviceFactGapCode.AVAILABILITY_NOT_PROVEN,
        ),
    ],
)
def test_missing_or_conflicting_identity_and_provenance_fail_closed(
    sample_factory: Callable[[DeviceFactRequirement], DeviceFactEvidenceSample],
    expected: DeviceFactGapCode,
) -> None:
    requirement = DeviceFactRequirement.IDENTITY_PROVENANCE
    samples = tuple(
        sample_factory(item) if item is requirement else _sample(item)
        for item in DeviceFactRequirement
    )
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    finding = _finding(assessment, requirement)
    assert assessment.status is DeviceFactReadinessStatus.GAP
    assert finding.gap_code is expected


def test_caller_freshness_policy_marks_stale_and_future_evidence_as_gaps() -> None:
    stale_samples = tuple(
        _sample(item, observed_at=NOW - timedelta(minutes=6))
        if item is DeviceFactRequirement.AVAILABILITY_TIME
        else _sample(item)
        for item in DeviceFactRequirement
    )
    stale = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=stale_samples)
    )
    assert (
        _finding(stale, DeviceFactRequirement.AVAILABILITY_TIME).gap_code
        is DeviceFactGapCode.STALE
    )

    future_samples = tuple(
        _sample(item, observed_at=NOW + timedelta(seconds=1))
        if item is DeviceFactRequirement.AVAILABILITY_TIME
        else _sample(item)
        for item in DeviceFactRequirement
    )
    future = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=future_samples)
    )
    assert (
        _finding(future, DeviceFactRequirement.AVAILABILITY_TIME).gap_code
        is DeviceFactGapCode.TIME_AFTER_AS_OF
    )


def test_ack_correlation_mismatch_is_a_gap_not_completion() -> None:
    samples = tuple(
        _sample(item, ack_matches=False)
        if item is DeviceFactRequirement.ACK_CORRELATION
        else _sample(item)
        for item in DeviceFactRequirement
    )
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    finding = _finding(assessment, DeviceFactRequirement.ACK_CORRELATION)
    assert assessment.status is DeviceFactReadinessStatus.GAP
    assert finding.gap_code is DeviceFactGapCode.ACK_CORRELATION_MISMATCH
    assert "completion" not in finding.detail


def test_missing_ack_correlation_fields_fail_closed() -> None:
    missing_ack = DeviceFactEvidenceSample(
        "fact-ack-missing",
        DeviceFactRequirement.ACK_CORRELATION,
        "pcs-bms-fact-source-a",
        "caller-provenance-a",
        "boot-epoch-a",
        "assessment-a",
        "evidence-a",
        NOW,
        DeviceFactAvailability.AVAILABLE,
        request_id=None,
        request_sequence=None,
        request_correlation_id=None,
        acknowledgement_request_id=None,
        acknowledgement_sequence=None,
        acknowledgement_correlation_id=None,
    )
    samples = tuple(
        missing_ack if item is DeviceFactRequirement.ACK_CORRELATION else _sample(item)
        for item in DeviceFactRequirement
    )

    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    finding = _finding(assessment, DeviceFactRequirement.ACK_CORRELATION)
    assert assessment.status is DeviceFactReadinessStatus.GAP
    assert finding.gap_code is DeviceFactGapCode.ACK_CORRELATION_MISMATCH


def test_actual_is_distinct_and_never_substitutes_another_fact_layer() -> None:
    samples = tuple(
        _sample(item, actual_present=False)
        if item is DeviceFactRequirement.ACTUAL_TELEMETRY
        else _sample(item)
        for item in DeviceFactRequirement
    )
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    assert (
        _finding(assessment, DeviceFactRequirement.ACTUAL_TELEMETRY).gap_code
        is DeviceFactGapCode.ACTUAL_NOT_PROVEN
    )
    assert "reconciliation" not in inspect.getsource(
        DeterministicDeviceFactReadinessEvaluator
    )


@pytest.mark.parametrize(
    ("availability", "continuity_id", "expected"),
    [
        (
            DeviceFactAvailability.DISCONNECTED,
            "boot-epoch-a",
            DeviceFactGapCode.DISCONNECTED,
        ),
        (
            DeviceFactAvailability.REBOOTED,
            "boot-epoch-a",
            DeviceFactGapCode.REBOOT_DISCONTINUITY,
        ),
        (
            DeviceFactAvailability.AVAILABLE,
            "boot-epoch-b",
            DeviceFactGapCode.REBOOT_DISCONTINUITY,
        ),
    ],
)
def test_disconnect_reboot_and_fresh_reassessment_remain_explicit(
    availability: DeviceFactAvailability,
    continuity_id: str,
    expected: DeviceFactGapCode,
) -> None:
    samples = tuple(
        _sample(item, availability=availability, continuity_id=continuity_id)
        if item is DeviceFactRequirement.DISCONNECT_REBOOT
        else _sample(item)
        for item in DeviceFactRequirement
    )
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    assert (
        _finding(assessment, DeviceFactRequirement.DISCONNECT_REBOOT).gap_code
        is expected
    )


def test_fresh_reassessment_requires_current_caller_assessment_and_evidence_ids() -> (
    None
):
    samples = tuple(
        _sample(item, assessment_id="historical", evidence_set_id="historical-evidence")
        if item is DeviceFactRequirement.FRESH_REASSESSMENT
        else _sample(item)
        for item in DeviceFactRequirement
    )
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(
        _input(samples=samples)
    )

    finding = _finding(assessment, DeviceFactRequirement.FRESH_REASSESSMENT)
    assert finding.gap_code is DeviceFactGapCode.FRESH_REASSESSMENT_NOT_PROVEN


def test_assessment_values_can_serialize_but_cannot_create_execution_authority() -> (
    None
):
    assessment = DeterministicDeviceFactReadinessEvaluator().evaluate(_input())
    restored = pickle.loads(pickle.dumps(copy.deepcopy(assessment)))

    assert restored == assessment
    assert not any(
        name in dir(restored)
        for name in ("runtime", "session", "adapter", "handoff", "command", "evaluate")
    )


def test_public_surface_has_no_transport_or_predecessor_runtime_imports() -> None:
    import edge_runtime.device_fact_readiness as public

    assert set(public.__all__) == {
        "DeterministicDeviceFactReadinessEvaluator",
        "DeviceFactAvailability",
        "DeviceFactCapabilityProfile",
        "DeviceFactEvidenceSample",
        "DeviceFactGapCode",
        "DeviceFactReadinessAssessment",
        "DeviceFactReadinessFinding",
        "DeviceFactReadinessInput",
        "DeviceFactReadinessStatus",
        "DeviceFactRequirement",
        "DeviceFactRequirementPolicy",
    }
    package = Path(inspect.getfile(public)).parent
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
        "edge_runtime.controlled_composition_session",
        "edge_runtime.adapter_conformance",
        "ems_strategy.edge_command_handoff",
    }
    imports: set[str] = set()
    for source_path in package.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not any(
        imported == forbidden_name or imported.startswith(f"{forbidden_name}.")
        for imported in imports
        for forbidden_name in forbidden
    )


def test_input_rejects_non_contract_profile_before_evaluation() -> None:
    invalid_profile = object()
    with pytest.raises(TypeError, match="DeviceFactCapabilityProfile"):
        DeviceFactReadinessInput(
            "assessment-a",
            "evidence-a",
            cast(DeviceFactCapabilityProfile, invalid_profile),
            _policies(),
            (),
            NOW,
        )
