"""Mutation-sensitive P0.1 transport-neutral Edge contract regressions."""

import ast
import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from math import inf, nan
from pathlib import Path
from typing import Protocol

import pytest

import edge_runtime
from edge_runtime import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    CommandLifecycleBook,
    CommandLifecycleRecord,
    CommandLifecycleState,
    CommandSubmissionResult,
    DeterministicEdgeSafetyEvaluator,
    DeviceCapability,
    DeviceCapabilitySource,
    EdgeSafetyEvaluationInput,
    ExecutionCompletionEvidence,
    FaultEvent,
    FaultSeverity,
    FaultSource,
    OperatingMode,
    PowerCommand,
    RecoveryReadinessInput,
    RuntimeHealth,
    RuntimeState,
    SafetyConstraint,
    SafetyOutcome,
    SafetyPrecedence,
    TelemetryQualityStatus,
    TelemetrySnapshot,
    TimingPolicy,
    evaluate_freshness,
    evaluate_recovery_readiness,
    merge_device_capabilities,
)

NOW = datetime(2030, 1, 2, 3, 4, tzinfo=UTC)
POLICY = TimingPolicy(
    timedelta(seconds=60),
    timedelta(seconds=60),
    timedelta(minutes=5),
    timedelta(seconds=5),
    timedelta(seconds=10),
    timedelta(seconds=30),
)


class _SerializableContract(Protocol):
    def to_dict(self) -> dict[str, object]: ...

    @classmethod
    def from_dict(cls, value: object) -> object: ...


def _command(
    command_id: str = "command-1",
    sequence: int = 1,
    power_kw: float = 1.0,
    *,
    issued_at: datetime = NOW,
    not_before: datetime = NOW,
    expires_at: datetime | None = None,
    mode: OperatingMode | None = None,
) -> PowerCommand:
    return PowerCommand(
        "edge-power-command/v1",
        command_id,
        sequence,
        "plan-step-7",
        issued_at,
        not_before,
        expires_at or NOW + timedelta(minutes=1),
        power_kw,
        mode or (OperatingMode.SAFE_IDLE if power_kw == 0 else OperatingMode.NORMAL),
        "ems_plan",
        "residential-ems",
        "cycle-22",
    )


def _telemetry(
    actual_power_kw: float | None = 0.0,
    observed_at: datetime = NOW,
    *,
    received_at: datetime | None = None,
    soc_fraction: float | None = 0.5,
) -> TelemetrySnapshot:
    return TelemetrySnapshot(
        "edge-telemetry/v1",
        "pcs-1",
        8,
        observed_at,
        received_at or observed_at,
        actual_power_kw,
        soc_fraction,
        None,
        0.2,
        0.1,
        0.3,
        "running",
        "ready",
        (),
        TelemetryQualityStatus.VALID,
    )


def _capability(
    source: DeviceCapabilitySource,
    *,
    max_charge_kw: float = 3.0,
    max_discharge_kw: float = 3.0,
    charge_allowed: bool = True,
    discharge_allowed: bool = True,
    available: bool = True,
    valid_from: datetime = NOW - timedelta(seconds=1),
    expires_at: datetime = NOW + timedelta(minutes=1),
) -> DeviceCapability:
    return DeviceCapability(
        source,
        f"{source.value}-1",
        4,
        valid_from,
        expires_at,
        max_charge_kw,
        max_discharge_kw,
        charge_allowed,
        discharge_allowed,
        available,
        None,
    )


def _fault(severity: FaultSeverity) -> FaultEvent:
    return FaultEvent(
        "fault-1",
        FaultSource.BMS,
        severity,
        "BMS_TEST",
        NOW,
        NOW,
        False,
        True,
        None,
        None,
        ("test",),
    )


def _health(
    state: RuntimeState = RuntimeState.READY,
    faults: tuple[FaultEvent, ...] = (),
) -> RuntimeHealth:
    return RuntimeHealth(
        state,
        NOW,
        True,
        True,
        True,
        True,
        True,
        0,
        0,
        state is RuntimeState.SAFE_IDLE,
        faults,
    )


def _input(
    *,
    command: PowerCommand | None = None,
    bms: DeviceCapability | None = None,
    pcs: DeviceCapability | None = None,
    health: RuntimeHealth | None = None,
    telemetry: TelemetrySnapshot | None = None,
    emergency_stop_active: bool = False,
) -> EdgeSafetyEvaluationInput:
    return EdgeSafetyEvaluationInput(
        command or _command(),
        telemetry or _telemetry(),
        bms or _capability(DeviceCapabilitySource.BMS),
        pcs or _capability(DeviceCapabilitySource.PCS),
        health or _health(),
        POLICY,
        NOW,
        emergency_stop_active,
        None,
    )


def _ack(
    command: PowerCommand, at: datetime = NOW + timedelta(seconds=1)
) -> CommandAcknowledgement:
    return CommandAcknowledgement(
        command.command_id,
        command.sequence,
        AcknowledgementStatus.ACCEPTED,
        at,
        None,
        command.requested_battery_power_kw,
        None,
        "accepted",
        command.correlation_id,
    )


def _accepted_book(command: PowerCommand) -> CommandLifecycleBook:
    book, _ = CommandLifecycleBook().submit(command, received_at=NOW, policy=POLICY)
    return book.acknowledge(_ack(command), received_at=NOW + timedelta(seconds=1))


def _executing_book(
    command: PowerCommand,
    started_at: datetime = NOW + timedelta(seconds=2),
) -> CommandLifecycleBook:
    return _accepted_book(command).begin_execution(command.command_id, at=started_at)


def test_public_api_exports_edge_contracts_and_package_imports() -> None:
    expected = {
        "AcknowledgementStatus",
        "CommandAcknowledgement",
        "CommandLifecycleBook",
        "CommandLifecycleRecord",
        "CommandLifecycleState",
        "CommandSubmissionResult",
        "DeterministicEdgeSafetyEvaluator",
        "DeviceCapability",
        "DeviceCapabilitySource",
        "EdgeSafetyEvaluationInput",
        "EffectiveDeviceCapability",
        "ExecutionCompletionEvidence",
        "FaultEvent",
        "FaultSeverity",
        "FaultSource",
        "FreshnessEvaluation",
        "OperatingMode",
        "PowerCommand",
        "RecoveryReadiness",
        "RecoveryReadinessInput",
        "RuntimeHealth",
        "RuntimeState",
        "SafetyConstraint",
        "SafetyDecision",
        "SafetyOutcome",
        "SafetyPrecedence",
        "TelemetryQualityStatus",
        "TelemetrySnapshot",
        "TimingPolicy",
        "evaluate_freshness",
        "evaluate_recovery_readiness",
        "merge_device_capabilities",
    }
    assert set(edge_runtime.__all__) == expected


@pytest.mark.parametrize("power", [nan, inf, -inf, True, "1.0"])
def test_power_command_rejects_non_finite_and_non_numeric_power(power: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _command(power_kw=power)  # type: ignore[arg-type]


def test_power_command_zero_frozen_slotted_and_time_contract() -> None:
    command = _command(power_kw=-1.25)
    assert PowerCommand.from_dict(command.to_dict()) == command
    assert not hasattr(command, "__dict__")
    with pytest.raises(FrozenInstanceError):
        command.command_id = "changed"  # type: ignore[misc]
    assert _command(power_kw=-0.0).requested_battery_power_kw == 0.0
    with pytest.raises(ValueError, match="zero requested"):
        _command(power_kw=0.0, mode=OperatingMode.NORMAL)
    with pytest.raises(ValueError, match="timezone-aware"):
        _command(issued_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="later than issued"):
        _command(expires_at=NOW)


def test_telemetry_unknown_and_freshness_use_observed_not_received_time() -> None:
    telemetry = _telemetry(None, NOW - timedelta(minutes=2), received_at=NOW)
    effective = merge_device_capabilities(
        _capability(DeviceCapabilitySource.BMS), _capability(DeviceCapabilitySource.PCS)
    )
    freshness = evaluate_freshness(telemetry, effective, POLICY, evaluated_at=NOW)
    assert telemetry.actual_battery_power_kw is None
    assert (freshness.telemetry_fresh, freshness.telemetry_reason) == (
        False,
        "telemetry_stale",
    )
    with pytest.raises(ValueError, match="earlier than observed"):
        _telemetry(0.0, NOW, received_at=NOW - timedelta(microseconds=1))


def test_capability_intersection_is_exact_and_effective_input_cannot_be_forged() -> (
    None
):
    bms = _capability(
        DeviceCapabilitySource.BMS, max_charge_kw=1.0, max_discharge_kw=2.0
    )
    pcs = _capability(
        DeviceCapabilitySource.PCS, max_charge_kw=3.0, max_discharge_kw=1.5
    )
    effective = merge_device_capabilities(bms, pcs)
    assert effective.bms_capability is bms and effective.pcs_capability is pcs
    assert (effective.max_charge_power_kw, effective.max_discharge_power_kw) == (
        1.0,
        1.5,
    )
    with pytest.raises(ValueError, match="BMS"):
        merge_device_capabilities(pcs, bms)
    with pytest.raises(TypeError, match="derived only"):
        type(effective)(
            bms, pcs, NOW, NOW + timedelta(seconds=1), 9.0, 9.0, True, True, True
        )


@pytest.mark.parametrize(
    ("health", "bms", "pcs", "power"),
    [
        (_health(RuntimeState.STARTING), None, None, 0.0),
        (_health(RuntimeState.WAITING_FOR_FRESH_TELEMETRY), None, None, 0.0),
        (_health(RuntimeState.DEGRADED), None, None, 0.0),
        (_health(RuntimeState.SAFE_IDLE), None, None, 0.0),
        (_health(RuntimeState.FAULTED), None, None, 0.0),
        (_health(RuntimeState.SHUTTING_DOWN), None, None, 0.0),
        (
            _health(),
            _capability(DeviceCapabilitySource.BMS, charge_allowed=False),
            None,
            0.0,
        ),
        (
            _health(),
            _capability(DeviceCapabilitySource.BMS, max_charge_kw=0.5),
            None,
            0.5,
        ),
    ],
)
def test_safety_state_and_capability_intersection_fail_closed(
    health: RuntimeHealth,
    bms: DeviceCapability | None,
    pcs: DeviceCapability | None,
    power: float,
) -> None:
    assert (
        DeterministicEdgeSafetyEvaluator()
        .evaluate(_input(health=health, bms=bms, pcs=pcs))
        .final_requested_battery_power_kw
        == power
    )


@pytest.mark.parametrize(
    "source", [FaultSource.BMS, FaultSource.PCS, FaultSource.EDGE_RUNTIME]
)
def test_critical_faults_fail_closed_but_warning_is_explicitly_non_blocking(
    source: FaultSource,
) -> None:
    critical = replace(_fault(FaultSeverity.CRITICAL), source=source)
    result = DeterministicEdgeSafetyEvaluator().evaluate(
        _input(health=_health(faults=(critical,)))
    )
    assert result.final_requested_battery_power_kw == 0.0
    assert "blocking_active_fault" in {
        item.reason_code for item in result.applied_constraints
    }
    assert (
        DeterministicEdgeSafetyEvaluator()
        .evaluate(_input(health=_health(faults=(_fault(FaultSeverity.WARNING),))))
        .outcome
        is SafetyOutcome.ALLOWED
    )


def test_safety_retains_multi_constraint_evidence_after_forced_idle() -> None:
    decision = DeterministicEdgeSafetyEvaluator().evaluate(
        _input(
            bms=_capability(DeviceCapabilitySource.BMS, charge_allowed=False),
            pcs=_capability(DeviceCapabilitySource.PCS, max_charge_kw=0.5),
            health=_health(faults=(_fault(FaultSeverity.CRITICAL),)),
            telemetry=_telemetry(1.0, NOW - timedelta(minutes=2), received_at=NOW),
            emergency_stop_active=True,
        )
    )
    assert decision.final_requested_battery_power_kw == 0.0
    assert [item.reason_code for item in decision.applied_constraints] == [
        "emergency_stop_active",
        "telemetry_stale",
        "blocking_active_fault",
        "charge_not_allowed",
        "charge_power_limited",
    ]


def test_stale_capability_and_unknown_soc_fail_closed() -> None:
    stale_bms = _capability(
        DeviceCapabilitySource.BMS,
        valid_from=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(microseconds=1),
    )
    stale_pcs = _capability(
        DeviceCapabilitySource.PCS,
        valid_from=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(microseconds=1),
    )
    stale = DeterministicEdgeSafetyEvaluator().evaluate(
        _input(bms=stale_bms, pcs=stale_pcs)
    )
    unknown_soc = DeterministicEdgeSafetyEvaluator().evaluate(
        _input(telemetry=_telemetry(soc_fraction=None))
    )
    assert "capability_stale" in {
        item.reason_code for item in stale.applied_constraints
    }
    assert "soc_unknown" in {
        item.reason_code for item in unknown_soc.applied_constraints
    }
    assert stale.final_requested_battery_power_kw == 0.0
    assert unknown_soc.final_requested_battery_power_kw == 0.0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda health: replace(health, telemetry_fresh=False),
        lambda health: replace(health, capability_fresh=False),
        lambda health: replace(health, safe_fallback_active=True),
        lambda health: replace(health, command_channel_healthy=False),
    ],
)
def test_runtime_health_signals_fail_closed(
    mutate: Callable[[RuntimeHealth], RuntimeHealth],
) -> None:
    assert (
        DeterministicEdgeSafetyEvaluator()
        .evaluate(_input(health=mutate(_health())))
        .final_requested_battery_power_kw
        == 0.0
    )


def test_submit_replay_sequence_and_invalid_command_timing() -> None:
    command = _command()
    book, first = CommandLifecycleBook().submit(command, received_at=NOW, policy=POLICY)
    same_book, duplicate = book.submit(command, received_at=NOW, policy=POLICY)
    assert first.record.state is CommandLifecycleState.ISSUED
    assert same_book is book and duplicate.idempotent_duplicate is True
    with pytest.raises(ValueError, match="command_id replay"):
        book.submit(_command(power_kw=2.0), received_at=NOW, policy=POLICY)
    with pytest.raises(ValueError, match="same sequence"):
        book.submit(_command("other", 1), received_at=NOW, policy=POLICY)
    with pytest.raises(ValueError, match="sequence rollback"):
        book.submit(_command("old", 0), received_at=NOW, policy=POLICY)
    with pytest.raises(ValueError, match="before not_before"):
        CommandLifecycleBook().submit(
            _command(not_before=NOW + timedelta(seconds=1)),
            received_at=NOW,
            policy=POLICY,
        )
    with pytest.raises(ValueError, match="max_clock_skew"):
        CommandLifecycleBook().submit(
            _command(
                issued_at=NOW + timedelta(seconds=6),
                not_before=NOW + timedelta(seconds=6),
            ),
            received_at=NOW,
            policy=POLICY,
        )


def test_acknowledgement_identity_duplicate_conflict_and_late_expiry() -> None:
    command = _command(expires_at=NOW + timedelta(seconds=2))
    book, _ = CommandLifecycleBook().submit(command, received_at=NOW, policy=POLICY)
    accepted = _ack(command)
    with pytest.raises(ValueError, match="unknown"):
        book.acknowledge(
            _ack(_command("unknown", 7)), received_at=NOW + timedelta(seconds=1)
        )
    with pytest.raises(ValueError, match="sequence"):
        book.acknowledge(
            replace(accepted, sequence=2), received_at=NOW + timedelta(seconds=1)
        )
    accepted_book = book.acknowledge(accepted, received_at=NOW + timedelta(seconds=1))
    assert (
        accepted_book.acknowledge(accepted, received_at=NOW + timedelta(seconds=1))
        is accepted_book
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        accepted_book.acknowledge(
            replace(accepted, device_state="other"),
            received_at=NOW + timedelta(seconds=1),
        )
    late = book.acknowledge(accepted, received_at=command.expires_at)
    assert late.records[0].state is CommandLifecycleState.EXPIRED
    assert (
        late.acknowledge(
            accepted, received_at=command.expires_at + timedelta(seconds=1)
        )
        is late
    )


def test_execution_started_at_is_strict_actual_telemetry_boundary() -> None:
    command = _command()
    started = NOW + timedelta(seconds=4)
    executing = _executing_book(command, started)
    assert executing.records[0].execution_started_at == started
    with pytest.raises(ValueError, match="predates execution"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(1.0, NOW + timedelta(seconds=2)),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=5),
        )
    with pytest.raises(ValueError, match="predates execution"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(1.0, started - timedelta(microseconds=1)),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=5),
        )
    equal = executing.complete(
        command.command_id,
        telemetry=_telemetry(1.0, started),
        tolerance_kw=0.01,
        at=NOW + timedelta(seconds=5),
    )
    assert equal.records[0].state is CommandLifecycleState.COMPLETED
    later = _executing_book(command, started).complete(
        command.command_id,
        telemetry=_telemetry(1.0, started + timedelta(microseconds=1)),
        tolerance_kw=0.01,
        at=NOW + timedelta(seconds=5),
    )
    assert later.records[0].state is CommandLifecycleState.COMPLETED


def test_completion_requires_actual_power_and_consistent_timing() -> None:
    command = _command()
    executing = _executing_book(command)
    with pytest.raises(ValueError, match="outside completion tolerance"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(0.0, NOW + timedelta(seconds=2)),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=3),
        )
    with pytest.raises(ValueError, match="completion telemetry must"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(1.0, NOW + timedelta(seconds=4)),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=3),
        )
    with pytest.raises(ValueError, match="completion telemetry must"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(
                1.0,
                NOW + timedelta(seconds=2),
                received_at=NOW + timedelta(seconds=4),
            ),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=3),
        )
    with pytest.raises(TypeError, match="number"):
        executing.complete(
            command.command_id,
            telemetry=_telemetry(1.0, NOW + timedelta(seconds=2)),
            tolerance_kw=True,
            at=NOW + timedelta(seconds=3),
        )
    with pytest.raises(TypeError, match="TelemetrySnapshot"):
        executing.complete(
            command.command_id,
            telemetry=_input(),  # type: ignore[arg-type]
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=3),
        )
    completed = executing.complete(
        command.command_id,
        telemetry=_telemetry(1.0, NOW + timedelta(seconds=2)),
        tolerance_kw=0.01,
        at=NOW + timedelta(seconds=3),
    )
    assert completed.records[0].completion_evidence is not None
    with pytest.raises(ValueError, match="completion requires executing"):
        completed.complete(
            command.command_id,
            telemetry=_telemetry(1.0, NOW + timedelta(seconds=3)),
            tolerance_kw=0.01,
            at=NOW + timedelta(seconds=4),
        )


def test_expiry_blocks_late_begin_and_completion_without_expire() -> None:
    command = _command(expires_at=NOW + timedelta(seconds=4))
    late_begin = _accepted_book(command).begin_execution(
        command.command_id, at=command.expires_at
    )
    assert late_begin.records[0].state is CommandLifecycleState.EXPIRED
    executing = _executing_book(command)
    late = executing.complete(
        command.command_id,
        telemetry=_telemetry(1.0, NOW + timedelta(seconds=3)),
        tolerance_kw=0.01,
        at=command.expires_at,
    )
    assert late.records[0].state is CommandLifecycleState.EXPIRED
    assert late.records[0].completion_evidence is None
    with pytest.raises(ValueError, match="completion requires executing"):
        late.complete(
            command.command_id,
            telemetry=_telemetry(1.0, NOW + timedelta(seconds=3)),
            tolerance_kw=0.01,
            at=command.expires_at + timedelta(seconds=1),
        )
    valid = _executing_book(command).complete(
        command.command_id,
        telemetry=_telemetry(1.0, NOW + timedelta(seconds=3)),
        tolerance_kw=0.01,
        at=NOW + timedelta(seconds=3),
    )
    assert valid.records[0].state is CommandLifecycleState.COMPLETED


def test_book_has_no_record_hydration_or_caller_collection_injection() -> None:
    command = _command()
    record = CommandLifecycleRecord.from_dict(
        _executing_book(command).records[0].to_dict()
    )
    assert record.state is CommandLifecycleState.EXECUTING
    assert not hasattr(CommandLifecycleBook, "_from_records")
    with pytest.raises(TypeError):
        CommandLifecycleBook(records=(record,))  # type: ignore[call-arg]
    book = CommandLifecycleBook()
    with pytest.raises(FrozenInstanceError):
        book.records = (record,)  # type: ignore[misc]
    assert book.records == ()
    assert CommandLifecycleRecord.from_dict(record.to_dict()) == record


def test_record_state_invariants_reject_forged_execution_and_completion() -> None:
    command = _command()
    with pytest.raises(TypeError, match="created only"):
        CommandLifecycleRecord()
    with pytest.raises(ValueError, match="execution_started_at"):
        CommandLifecycleRecord._create(
            command,
            CommandLifecycleState.EXECUTING,
            NOW + timedelta(seconds=2),
            _ack(command),
        )
    with pytest.raises(ValueError, match="completion evidence"):
        CommandLifecycleRecord._create(
            command,
            CommandLifecycleState.ACK_ACCEPTED,
            NOW + timedelta(seconds=1),
            _ack(command),
            completion_evidence=ExecutionCompletionEvidence(
                command, _telemetry(1.0), NOW, 0.01, 1.0
            ),
        )


def test_completed_record_requires_actual_evidence_directly_and_when_deserialized() -> (
    None
):
    command = _command()
    started_at = NOW + timedelta(seconds=2)
    completed_at = NOW + timedelta(seconds=3)
    acknowledgement = _ack(command)
    with pytest.raises(ValueError, match="matching actual completion evidence"):
        CommandLifecycleRecord._create(
            command,
            CommandLifecycleState.COMPLETED,
            completed_at,
            acknowledgement,
            started_at,
        )

    executing = _executing_book(command, started_at).records[0]
    payload = executing.to_dict()
    payload["state"] = CommandLifecycleState.COMPLETED.value
    payload["completion_evidence"] = None
    with pytest.raises(ValueError, match="matching actual completion evidence"):
        CommandLifecycleRecord.from_dict(payload)

    telemetry = _telemetry(1.0, started_at)
    evidence = ExecutionCompletionEvidence(command, telemetry, completed_at, 0.01, 1.0)
    for state, execution_started_at in (
        (CommandLifecycleState.EXECUTING, started_at),
        (CommandLifecycleState.ACK_ACCEPTED, None),
        (CommandLifecycleState.EXPIRED, None),
    ):
        with pytest.raises(ValueError, match="completion evidence is only valid"):
            CommandLifecycleRecord._create(
                command,
                state,
                completed_at,
                acknowledgement,
                execution_started_at,
                evidence,
            )

    completed = (
        _executing_book(command, started_at)
        .complete(
            command.command_id,
            telemetry=telemetry,
            tolerance_kw=0.01,
            at=completed_at,
        )
        .records[0]
    )
    assert completed.state is CommandLifecycleState.COMPLETED
    assert completed.completion_evidence is not None
    assert completed.completion_evidence.source_command is command
    assert completed.completion_evidence.source_telemetry is telemetry
    assert completed.completion_evidence.actual_power_kw == 1.0
    assert completed.execution_started_at == started_at
    assert CommandLifecycleRecord.from_dict(completed.to_dict()) == completed


def test_supersede_with_requires_valid_new_successor_and_is_atomic() -> None:
    predecessor = _command()
    book, _ = CommandLifecycleBook().submit(predecessor, received_at=NOW, policy=POLICY)
    with pytest.raises(ValueError, match="strictly increase"):
        book.supersede_with(
            predecessor.command_id,
            successor=_command("same", 1),
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )
    with pytest.raises(ValueError, match="itself"):
        book.supersede_with(
            predecessor.command_id,
            successor=_command(predecessor.command_id, 2),
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )
    with pytest.raises(ValueError, match="active"):
        book.supersede_with(
            predecessor.command_id,
            successor=_command("expired", 2, expires_at=NOW + timedelta(seconds=1)),
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )
    assert book.records[0].state is CommandLifecycleState.ISSUED
    successor = _command("command-2", 2)
    superseded = book.supersede_with(
        predecessor.command_id,
        successor=successor,
        at=NOW + timedelta(seconds=1),
        policy=POLICY,
    )
    assert [record.state for record in superseded.records] == [
        CommandLifecycleState.SUPERSEDED,
        CommandLifecycleState.ISSUED,
    ]
    assert superseded.records[0].superseded_by_command_id == successor.command_id
    with pytest.raises(ValueError, match="terminal"):
        superseded.supersede_with(
            predecessor.command_id,
            successor=_command("command-3", 3),
            at=NOW + timedelta(seconds=2),
            policy=POLICY,
        )


def test_supersede_rejects_registered_id_sequence_and_expired_predecessor() -> None:
    first, second = _command(), _command("command-2", 2)
    book, _ = CommandLifecycleBook().submit(first, received_at=NOW, policy=POLICY)
    book, _ = book.submit(second, received_at=NOW, policy=POLICY)
    with pytest.raises(ValueError, match="already registered"):
        book.supersede_with(
            first.command_id,
            successor=_command("command-2", 3),
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )
    with pytest.raises(ValueError, match="already registered"):
        book.supersede_with(
            first.command_id,
            successor=_command("command-3", 2),
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )
    expires = _command(expires_at=NOW + timedelta(seconds=2))
    result = (
        _accepted_book(expires)
        .begin_execution(expires.command_id, at=NOW + timedelta(seconds=1))
        .supersede_with(
            expires.command_id,
            successor=_command("command-9", 9),
            at=expires.expires_at,
            policy=POLICY,
        )
    )
    assert result.records[0].state is CommandLifecycleState.EXPIRED


def test_supersede_requires_global_sequence_monotonicity_and_is_atomic() -> None:
    predecessor = _command("command-5", 5)
    current_highest = _command("command-10", 10)
    book, _ = CommandLifecycleBook().submit(predecessor, received_at=NOW, policy=POLICY)
    book, _ = book.submit(current_highest, received_at=NOW, policy=POLICY)
    before = book.records
    rejected_successor = _command("command-6", 6)

    with pytest.raises(ValueError, match="successor sequence rollback"):
        book.supersede_with(
            predecessor.command_id,
            successor=rejected_successor,
            at=NOW + timedelta(seconds=1),
            policy=POLICY,
        )

    assert book.records == before
    assert book.records[0].state is CommandLifecycleState.ISSUED
    assert book.records[0].superseded_by_command_id is None
    assert len(book.records) == 2
    assert rejected_successor.command_id not in {
        record.command.command_id for record in book.records
    }
    assert max(record.command.sequence for record in book.records) == 10
    assert {record.command.command_id for record in book.records} == {
        "command-5",
        "command-10",
    }
    assert {record.command.sequence for record in book.records} == {5, 10}

    successor = _command("command-11", 11)
    superseded = book.supersede_with(
        predecessor.command_id,
        successor=successor,
        at=NOW + timedelta(seconds=1),
        policy=POLICY,
    )
    assert [record.state for record in superseded.records] == [
        CommandLifecycleState.SUPERSEDED,
        CommandLifecycleState.ISSUED,
        CommandLifecycleState.ISSUED,
    ]
    assert superseded.records[0].superseded_by_command_id == successor.command_id
    assert superseded.records[-1].command is successor
    assert max(record.command.sequence for record in superseded.records) == 11
    assert {record.command.command_id for record in superseded.records} == {
        "command-5",
        "command-10",
        "command-11",
    }
    assert {record.command.sequence for record in superseded.records} == {5, 10, 11}


def test_lifecycle_state_matrix_is_guarded_and_has_no_dead_or_generic_states() -> None:
    expected = {
        CommandLifecycleState.ISSUED: {
            CommandLifecycleState.ACK_ACCEPTED,
            CommandLifecycleState.ACK_REJECTED,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        },
        CommandLifecycleState.ACK_ACCEPTED: {
            CommandLifecycleState.EXECUTING,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        },
        CommandLifecycleState.EXECUTING: {
            CommandLifecycleState.COMPLETED,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        },
        CommandLifecycleState.ACK_REJECTED: set(),
        CommandLifecycleState.COMPLETED: set(),
        CommandLifecycleState.EXPIRED: set(),
        CommandLifecycleState.SUPERSEDED: set(),
    }
    book = CommandLifecycleBook()
    assert set(CommandLifecycleState) == set(expected)
    assert not hasattr(book, "transition")
    for source, allowed_targets in expected.items():
        for target in CommandLifecycleState:
            if target in allowed_targets:
                book._assert_transition_allowed(source, target)
            else:
                with pytest.raises(ValueError, match="transition is not allowed"):
                    book._assert_transition_allowed(source, target)

    payload = _executing_book(_command()).records[0].to_dict()
    for obsolete_state in ("created", "validated", "failed"):
        payload["state"] = obsolete_state
        with pytest.raises(ValueError):
            CommandLifecycleRecord.from_dict(payload)


@pytest.mark.parametrize(
    "condition",
    [
        lambda: RecoveryReadinessInput(
            _telemetry(),
            _capability(DeviceCapabilitySource.BMS),
            _capability(DeviceCapabilitySource.PCS),
            _health(),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            True,
        ),
        lambda: RecoveryReadinessInput(
            _telemetry(),
            _capability(DeviceCapabilitySource.BMS),
            _capability(DeviceCapabilitySource.PCS),
            _health(faults=(_fault(FaultSeverity.CRITICAL),)),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        ),
        lambda: RecoveryReadinessInput(
            _telemetry(),
            _capability(DeviceCapabilitySource.BMS),
            _capability(DeviceCapabilitySource.PCS),
            _health(RuntimeState.DEGRADED),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        ),
        lambda: RecoveryReadinessInput(
            _telemetry(),
            _capability(DeviceCapabilitySource.BMS),
            _capability(DeviceCapabilitySource.PCS),
            replace(_health(), command_channel_healthy=False),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        ),
        lambda: RecoveryReadinessInput(
            _telemetry(),
            _capability(DeviceCapabilitySource.BMS, available=False),
            _capability(DeviceCapabilitySource.PCS),
            _health(),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        ),
        lambda: RecoveryReadinessInput(
            _telemetry(soc_fraction=None),
            _capability(DeviceCapabilitySource.BMS),
            _capability(DeviceCapabilitySource.PCS),
            _health(),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        ),
    ],
)
def test_recovery_requires_complete_fresh_healthy_quiescent_state(
    condition: Callable[[], RecoveryReadinessInput],
) -> None:
    assert evaluate_recovery_readiness(condition()).ready_for_new_command is False


def test_fault_and_runtime_health_are_frozen_and_transport_neutral() -> None:
    fault = _fault(FaultSeverity.CRITICAL)
    health = _health(faults=(fault,))
    with pytest.raises(FrozenInstanceError):
        fault.code = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        health.runtime_state = RuntimeState.FAULTED  # type: ignore[misc]
    with pytest.raises(TypeError, match="faults must be a tuple"):
        replace(health, active_faults=[])  # type: ignore[arg-type]
    package = Path(inspect.getfile(DeterministicEdgeSafetyEvaluator)).parent
    imports: set[str] = set()
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
    forbidden = {
        "ems_simulator",
        "ems_strategy",
        "simulator",
        "optimization",
        "can",
        "modbus",
        "mqtt",
        "requests",
    }
    assert not any(item.split(".")[0] in forbidden for item in imports)


def test_all_public_immutable_data_contracts_round_trip_strictly() -> None:
    command, telemetry = _command(), _telemetry(1.0)
    bms, pcs = (
        _capability(DeviceCapabilitySource.BMS),
        _capability(DeviceCapabilitySource.PCS),
    )
    safety_input = _input(command=command, bms=bms, pcs=pcs, telemetry=telemetry)
    decision = DeterministicEdgeSafetyEvaluator().evaluate(safety_input)
    submitted_book, submission = CommandLifecycleBook().submit(
        command, received_at=NOW, policy=POLICY
    )
    completed = _executing_book(command).complete(
        command.command_id,
        telemetry=_telemetry(1.0, NOW + timedelta(seconds=2)),
        tolerance_kw=0.1,
        at=NOW + timedelta(seconds=3),
    )
    readiness = evaluate_recovery_readiness(
        RecoveryReadinessInput(
            _telemetry(),
            bms,
            pcs,
            _health(),
            POLICY,
            CommandLifecycleBook(),
            NOW,
            False,
        )
    )
    contracts: tuple[_SerializableContract, ...] = (
        command,
        telemetry,
        POLICY,
        bms,
        merge_device_capabilities(bms, pcs),
        _ack(command, NOW),
        SafetyConstraint(SafetyPrecedence.EDGE_RUNTIME, "test", ("test",)),
        _fault(FaultSeverity.WARNING),
        _health(),
        evaluate_freshness(
            telemetry, decision.source_capability, POLICY, evaluated_at=NOW
        ),
        safety_input,
        decision,
        ExecutionCompletionEvidence(command, telemetry, NOW, 0.1, 1.0),
        completed.records[0],
        CommandSubmissionResult(submission.record, False),
        readiness,
    )
    assert submitted_book.records[0] is submission.record
    for contract in contracts:
        encoded = contract.to_dict()
        assert type(contract).from_dict(encoded) == contract
        with pytest.raises(ValueError):
            type(contract).from_dict({**encoded, "unexpected": True})
        missing = dict(encoded)
        missing.pop(next(key for key in missing if key != "schema_version"))
        with pytest.raises(ValueError):
            type(contract).from_dict(missing)
        with pytest.raises(ValueError):
            type(contract).from_dict({**encoded, "schema_version": "wrong/v1"})
