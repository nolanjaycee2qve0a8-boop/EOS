"""Focused public-contract coverage for the P0.10 lifecycle audit."""

from __future__ import annotations

import ast
import copy
import inspect
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import edge_runtime.device_fact_lifecycle_continuity as public
from edge_runtime.device_fact_lifecycle_continuity import (
    DeterministicDeviceFactLifecycleContinuityEvaluator,
    DeviceFactLifecycleAssessment,
    DeviceFactLifecycleAvailability,
    DeviceFactLifecycleContinuityInput,
    DeviceFactLifecycleGapCode,
    DeviceFactLifecycleSnapshot,
    DeviceFactLifecycleStatus,
    DeviceFactLifecycleTransition,
)

NOW = datetime(2026, 9, 11, 9, tzinfo=UTC)


def _snapshot(
    index: int,
    *,
    availability: DeviceFactLifecycleAvailability = (
        DeviceFactLifecycleAvailability.AVAILABLE
    ),
    source_identity: str = "source-a",
    identity_epoch: str = "epoch-a",
    observed_at: datetime | None = None,
    correlated: bool = True,
    actual_present: bool | None = True,
) -> DeviceFactLifecycleSnapshot:
    observed = (
        observed_at if observed_at is not None else NOW + timedelta(minutes=index)
    )
    request_id = f"request-{index}"
    correlation = f"correlation-{index}"
    return DeviceFactLifecycleSnapshot(
        snapshot_identity=f"snapshot-{index}",
        evidence_identity=f"evidence-{index}",
        source_identity=source_identity,
        identity_epoch=identity_epoch,
        availability=availability,
        observed_at=observed,
        request_id=request_id if correlated else None,
        request_sequence=index if correlated else None,
        request_correlation_id=correlation if correlated else None,
        acknowledgement_request_id=request_id if correlated else None,
        acknowledgement_sequence=index if correlated else None,
        acknowledgement_correlation_id=correlation if correlated else None,
        actual_present=actual_present,
    )


def _input(
    snapshots: tuple[object, ...],
    transitions: tuple[object, ...],
    *,
    assessment_identity: str = "assessment-a",
    assessment_as_of: datetime = NOW + timedelta(minutes=10),
    maximum_age: timedelta = timedelta(minutes=20),
) -> DeviceFactLifecycleContinuityInput:
    return DeviceFactLifecycleContinuityInput(
        assessment_identity=assessment_identity,
        assessment_as_of=assessment_as_of,
        maximum_age=maximum_age,
        snapshots=snapshots,
        transitions=transitions,
    )


def _codes(
    assessment: DeviceFactLifecycleAssessment,
) -> set[DeviceFactLifecycleGapCode]:
    return {finding.gap_code for finding in assessment.findings}


def test_all_continuity_is_audit_only_pass() -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input(
            (_snapshot(0), _snapshot(1)),
            (DeviceFactLifecycleTransition.CONTINUITY,),
        )
    )

    assert assessment.status is DeviceFactLifecycleStatus.PASS
    assert assessment.findings == ()
    assert not hasattr(assessment, "runtime")
    assert not hasattr(assessment, "adapter")
    assert not hasattr(assessment, "session")
    assert not hasattr(assessment, "command")


@pytest.mark.parametrize(
    ("label", "current", "required_code"),
    [
        (
            DeviceFactLifecycleTransition.DISCONNECT,
            _snapshot(1, availability=DeviceFactLifecycleAvailability.DISCONNECTED),
            DeviceFactLifecycleGapCode.DISCONNECT_RECORDED,
        ),
        (
            DeviceFactLifecycleTransition.REBOOT,
            _snapshot(
                1,
                availability=DeviceFactLifecycleAvailability.REBOOTED,
                identity_epoch="epoch-b",
            ),
            DeviceFactLifecycleGapCode.REBOOT_RECORDED,
        ),
        (
            DeviceFactLifecycleTransition.IDENTITY_EPOCH_CHANGE,
            _snapshot(1, identity_epoch="epoch-b"),
            DeviceFactLifecycleGapCode.IDENTITY_EPOCH_DISCONTINUITY,
        ),
        (
            DeviceFactLifecycleTransition.TIME_DISCONTINUITY,
            _snapshot(1, observed_at=NOW - timedelta(minutes=1)),
            DeviceFactLifecycleGapCode.TIME_DISCONTINUITY_RECORDED,
        ),
    ],
)
def test_discontinuity_labels_are_explicit_non_erasable_gaps(
    label: DeviceFactLifecycleTransition,
    current: DeviceFactLifecycleSnapshot,
    required_code: DeviceFactLifecycleGapCode,
) -> None:
    evaluator = DeterministicDeviceFactLifecycleContinuityEvaluator()
    assessment = evaluator.evaluate(_input((_snapshot(0), current), (label,)))

    assert assessment.status is DeviceFactLifecycleStatus.GAP
    assert required_code in _codes(assessment)

    if label is not DeviceFactLifecycleTransition.TIME_DISCONTINUITY:
        later = _snapshot(2, identity_epoch="epoch-c")
        recovered = evaluator.evaluate(
            _input(
                (_snapshot(0), current, later),
                (label, DeviceFactLifecycleTransition.RECONNECT),
            )
        )
        assert required_code in _codes(recovered)
        assert recovered.status is DeviceFactLifecycleStatus.GAP


def test_reconnect_requires_immediate_declared_discontinuity_and_complete_facts() -> (
    None
):
    invalid = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input(
            (
                _snapshot(0),
                _snapshot(1),
                _snapshot(2, identity_epoch="epoch-b"),
            ),
            (
                DeviceFactLifecycleTransition.CONTINUITY,
                DeviceFactLifecycleTransition.RECONNECT,
            ),
        )
    )

    assert DeviceFactLifecycleGapCode.RECONNECT_PRECONDITION_UNMET in _codes(invalid)


def test_reconnect_after_disconnect_requires_new_epoch_and_does_not_erase_gap() -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input(
            (
                _snapshot(0),
                _snapshot(1, availability=DeviceFactLifecycleAvailability.DISCONNECTED),
                _snapshot(2, identity_epoch="epoch-b"),
            ),
            (
                DeviceFactLifecycleTransition.DISCONNECT,
                DeviceFactLifecycleTransition.RECONNECT,
            ),
        )
    )

    assert DeviceFactLifecycleGapCode.DISCONNECT_RECORDED in _codes(assessment)
    assert DeviceFactLifecycleGapCode.RECONNECT_PRECONDITION_UNMET not in _codes(
        assessment
    )


@pytest.mark.parametrize(
    ("label", "current"),
    [
        (DeviceFactLifecycleTransition.DISCONNECT, _snapshot(1)),
        (
            DeviceFactLifecycleTransition.REBOOT,
            _snapshot(1, availability=DeviceFactLifecycleAvailability.REBOOTED),
        ),
        (
            DeviceFactLifecycleTransition.IDENTITY_EPOCH_CHANGE,
            _snapshot(1, source_identity="source-b", identity_epoch="epoch-b"),
        ),
        (DeviceFactLifecycleTransition.TIME_DISCONTINUITY, _snapshot(1)),
    ],
)
def test_discontinuity_labels_also_validate_documented_pair_facts(
    label: DeviceFactLifecycleTransition,
    current: DeviceFactLifecycleSnapshot,
) -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input((_snapshot(0), current), (label,))
    )

    assert DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH in _codes(assessment)


@pytest.mark.parametrize(
    "transitions",
    [(), (object(),), (DeviceFactLifecycleTransition.CONTINUITY, object())],
)
def test_absent_unknown_or_duplicate_transition_labels_fail_closed(
    transitions: tuple[object, ...],
) -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input((_snapshot(0), _snapshot(1)), transitions)
    )

    assert DeviceFactLifecycleGapCode.UNLABELLED_OR_UNKNOWN_TRANSITION in _codes(
        assessment
    )


@pytest.mark.parametrize(
    "replacement",
    [
        replace(_snapshot(1), source_identity="source-b"),
        replace(_snapshot(1), identity_epoch="epoch-b"),
        replace(_snapshot(1), observed_at=NOW),
        replace(_snapshot(1), observed_at=NOW - timedelta(minutes=30)),
    ],
)
def test_continuity_requires_source_epoch_strict_time_and_freshness(
    replacement: DeviceFactLifecycleSnapshot,
) -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input((_snapshot(0), replacement), (DeviceFactLifecycleTransition.CONTINUITY,))
    )

    assert DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH in _codes(assessment)


@pytest.mark.parametrize(
    "replacement",
    [
        replace(_snapshot(1), evidence_identity="evidence-0"),
        replace(_snapshot(1), snapshot_identity="assessment-a"),
    ],
)
def test_assessment_snapshot_and_evidence_identity_reuse_fail_closed(
    replacement: DeviceFactLifecycleSnapshot,
) -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input((_snapshot(0), replacement), (DeviceFactLifecycleTransition.CONTINUITY,))
    )

    assert DeviceFactLifecycleGapCode.ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED in _codes(
        assessment
    )


@pytest.mark.parametrize(
    "replacement",
    [
        replace(
            _snapshot(1),
            request_id=None,
            request_sequence=None,
            request_correlation_id=None,
            acknowledgement_request_id=None,
            acknowledgement_sequence=None,
            acknowledgement_correlation_id=None,
        ),
        replace(_snapshot(1), acknowledgement_sequence=999),
        replace(_snapshot(1), actual_present=None),
        replace(_snapshot(1), actual_present=False),
    ],
)
def test_ack_correlation_and_actual_presence_are_separate_required_facts(
    replacement: DeviceFactLifecycleSnapshot,
) -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input((_snapshot(0), replacement), (DeviceFactLifecycleTransition.CONTINUITY,))
    )

    assert DeviceFactLifecycleGapCode.ACK_ACTUAL_FACT_MISSING_OR_FUSED in _codes(
        assessment
    )


def test_historical_assessment_is_rejected_directly_and_when_embedded() -> None:
    evaluator = DeterministicDeviceFactLifecycleContinuityEvaluator()
    original = evaluator.evaluate(
        _input(
            (_snapshot(0), _snapshot(1)),
            (DeviceFactLifecycleTransition.CONTINUITY,),
        )
    )

    direct = evaluator.evaluate(original)
    embedded = evaluator.evaluate(_input((original,), ()))

    assert DeviceFactLifecycleGapCode.HISTORICAL_ASSESSMENT_INPUT_REJECTED in _codes(
        direct
    )
    assert DeviceFactLifecycleGapCode.HISTORICAL_ASSESSMENT_INPUT_REJECTED in _codes(
        embedded
    )


def test_assessment_values_copy_and_pickle_without_execution_authority() -> None:
    assessment = DeterministicDeviceFactLifecycleContinuityEvaluator().evaluate(
        _input(
            (_snapshot(0), _snapshot(1)),
            (DeviceFactLifecycleTransition.CONTINUITY,),
        )
    )
    restored = pickle.loads(pickle.dumps(copy.deepcopy(assessment)))

    assert restored == assessment
    assert not any(
        hasattr(restored, name)
        for name in ("runtime", "adapter", "handoff", "session", "continuation")
    )


def test_public_api_is_exact_and_has_no_execution_or_replay_surface() -> None:
    assert set(public.__all__) == {
        "DeterministicDeviceFactLifecycleContinuityEvaluator",
        "DeviceFactLifecycleAssessment",
        "DeviceFactLifecycleAvailability",
        "DeviceFactLifecycleContinuityInput",
        "DeviceFactLifecycleFinding",
        "DeviceFactLifecycleGapCode",
        "DeviceFactLifecycleSnapshot",
        "DeviceFactLifecycleStatus",
        "DeviceFactLifecycleTransition",
    }
    public_names = set(public.__all__)
    assert not public_names & {
        "PowerCommand",
        "ControlledEdgeRuntime",
        "ResidentialDeviceAdapterBoundary",
        "RuntimeSession",
        "replay",
    }


def test_production_sources_have_no_forbidden_transport_or_predecessor_imports() -> (
    None
):
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
        "edge_runtime.command_handoff",
        "edge_runtime.controlled_composition",
        "edge_runtime.controlled_composition_session",
        "edge_runtime.adapter_conformance",
    }
    imported: set[str] = set()
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
                imported.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert not any(
        name == prohibited or name.startswith(f"{prohibited}.")
        for name in imported
        for prohibited in forbidden
    )
