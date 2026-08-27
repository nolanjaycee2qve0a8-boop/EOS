"""Focused P0.3 caller-driven runtime regressions."""

import copy
import json
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from edge_runtime import (
    AcknowledgementStatus,
    FaultEvent,
    OperatingMode,
    PowerCommand,
    RuntimeHealth,
    RuntimeState,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.controlled_runtime import (
    CommandOrigin,
    CommandReconciliation,
    ControlledEdgeRuntime,
    ReconciliationStatus,
)
from edge_runtime.controlled_runtime.runtime import (
    _ALLOWED_RUNTIME_TRANSITIONS,
    _transition,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceSimulator,
    DeviceSimulatorConfiguration,
    FaultSchedule,
    FaultSpecification,
    FaultTarget,
    FaultType,
    PreparedDeviceSimulatorStep,
    VirtualClock,
)

NOW = datetime(2032, 1, 1, tzinfo=UTC)
POLICY = TimingPolicy(
    timedelta(seconds=30),
    timedelta(seconds=30),
    timedelta(minutes=5),
    timedelta(seconds=2),
    timedelta(seconds=5),
    timedelta(seconds=30),
)


def _runtime(*faults: FaultSpecification) -> ControlledEdgeRuntime:
    simulator = DeterministicDeviceSimulator.start(
        DeviceSimulatorConfiguration(
            10, 0.5, 0.2, 1, 3, 3, 0.95, 0.95, POLICY, FaultSchedule(faults)
        ),
        at=VirtualClock(NOW),
    )
    return ControlledEdgeRuntime.start(simulator)


def _command(runtime: ControlledEdgeRuntime, sequence: int = 1) -> PowerCommand:
    now = runtime.simulator.clock.now
    return PowerCommand(
        "edge-power-command/v1",
        f"p0-3-{sequence}",
        sequence,
        "step",
        now,
        now,
        now + timedelta(minutes=1),
        1.0,
        OperatingMode.NORMAL,
        "test",
        "test",
        f"p0-3-{sequence}",
    )


def _fault(
    fault_id: str,
    fault_type: FaultType,
    target: FaultTarget,
    *,
    clear_at: datetime | None = None,
    parameters: tuple[tuple[str, float], ...] = (),
) -> FaultSpecification:
    return FaultSpecification(
        fault_id, fault_type, target, NOW, clear_at, parameters, "test"
    )


def _runtime_with_state(
    runtime: ControlledEdgeRuntime, state: RuntimeState
) -> ControlledEdgeRuntime:
    """Test-only persisted-state fixture; it never exposes a runtime transition API."""
    return ControlledEdgeRuntime(
        runtime.simulator, runtime.lifecycle_book, state, runtime.trace
    )


def _identity_sets(runtime: ControlledEdgeRuntime) -> tuple[set[str], set[int]]:
    return (
        {record.command.command_id for record in runtime.lifecycle_book.records},
        {record.command.sequence for record in runtime.lifecycle_book.records},
    )


def _assert_no_command_tick(
    before: ControlledEdgeRuntime,
    after: ControlledEdgeRuntime,
) -> None:
    """Assert a caller-free tick cannot turn audit history into authority."""
    step = after.trace.steps[-1]
    assert step.caller_command is None
    assert step.admitted_command is None
    assert step.command_origin is CommandOrigin.NONE
    assert not step.automatic_command_generated
    assert step.device_step.command is None
    assert not step.device_step.command_application_authorized
    assert step.device_step.acknowledgement is None
    assert step.device_step.actual_power_kw == 0.0
    assert (
        step.device_step.ending_soc_fraction
        == step.device_step.starting_soc_fraction
        == before.simulator.soc_fraction
    )
    assert _identity_sets(after) == _identity_sets(before)
    assert len(after.lifecycle_book.records) == len(before.lifecycle_book.records)


def test_starting_waiting_ready_then_actual_matched_completion() -> None:
    runtime = _runtime().tick(None, duration=timedelta(seconds=1))
    assert runtime.state.value == "ready"
    completed = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert (
        completed.trace.steps[-1].reconciliation.status
        is ReconciliationStatus.COMPLETED_FROM_MATCHING_ACTUAL
    )
    assert completed.trace.steps[-1].device_step.actual_power_kw == 1.0


def test_starting_observation_tick_never_admits_active_command() -> None:
    runtime = _runtime()
    observed = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    step = observed.trace.steps[-1]
    assert observed.state.value == "ready"
    assert step.caller_command is not None
    assert step.device_step.command is None
    assert step.device_step.actual_power_kw == 0.0
    admitted = observed.tick(_command(observed, 2), duration=timedelta(seconds=1))
    assert admitted.trace.steps[-1].device_step.actual_power_kw == 1.0


def test_delayed_ack_is_not_authorized_or_executed() -> None:
    fault = FaultSpecification(
        "delay",
        FaultType.ACK_DELAYED,
        FaultTarget.PCS,
        NOW,
        None,
        (("seconds", 1.0),),
        "test",
    )
    runtime = _runtime(fault).tick(None, duration=timedelta(seconds=1))
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=10))
    step = result.trace.steps[-1]
    assert step.reconciliation.status is ReconciliationStatus.ACK_DELAYED
    assert not step.device_step.command_application_authorized
    assert step.device_step.actual_power_kw == 0.0


def test_critical_fault_blocks_admission_and_no_command_replay_after_clear() -> None:
    fault = FaultSpecification(
        "critical",
        FaultType.CRITICAL_FAULT,
        FaultTarget.BMS,
        NOW,
        NOW + timedelta(seconds=1),
        (),
        "test",
    )
    blocked = _runtime(fault).tick(None, duration=timedelta(seconds=1))
    assert blocked.state.value == "faulted"
    recovered = blocked.tick(None, duration=timedelta(seconds=1))
    assert recovered.state.value == "ready"
    assert recovered.trace.steps[-1].device_step.actual_power_kw == 0.0


@pytest.mark.parametrize(
    "fault",
    [
        FaultSpecification(
            "bms", FaultType.CRITICAL_FAULT, FaultTarget.BMS, NOW, None, (), "test"
        ),
        FaultSpecification(
            "pcs", FaultType.CRITICAL_FAULT, FaultTarget.PCS, NOW, None, (), "test"
        ),
        FaultSpecification(
            "edge", FaultType.CRITICAL_FAULT, FaultTarget.EDGE, NOW, None, (), "test"
        ),
        FaultSpecification(
            "estop", FaultType.ESTOP, FaultTarget.PCS, NOW, None, (), "test"
        ),
    ],
)
def test_blocking_faults_fail_closed_before_admission(
    fault: FaultSpecification,
) -> None:
    runtime = _runtime(fault)
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert result.state.value == "faulted"
    assert result.trace.steps[-1].device_step.command is None
    assert result.trace.steps[-1].device_step.actual_power_kw == 0.0


def test_prepared_step_is_single_snapshot_and_one_shot() -> None:
    simulator = _runtime().simulator
    prepared = simulator.prepare_step()
    assert prepared.raw_telemetry.actual_battery_power_kw == 0.0
    assert simulator.clock.now == NOW
    next_simulator, step = prepared.execute(None, duration=timedelta(seconds=1))
    assert step.active_faults is prepared.active_faults
    assert next_simulator.clock.now == NOW + timedelta(seconds=1)
    with pytest.raises(ValueError, match="already executed"):
        prepared.execute(None, duration=timedelta(seconds=1))


def test_runtime_tick_uses_prepared_snapshot_for_final_step() -> None:
    runtime = _runtime().tick(None, duration=timedelta(seconds=1))
    step = runtime.trace.steps[-1]
    assert step.device_step.started_at == NOW
    assert step.device_step.ended_at == NOW + timedelta(seconds=1)
    assert step.transition_reasons == ()


def test_prepared_authority_cannot_be_constructed_copied_or_serialized() -> None:
    prepared = _runtime().simulator.prepare_step()
    with pytest.raises(TypeError):
        type(prepared)()
    with pytest.raises(TypeError):
        replace(prepared)
    with pytest.raises(TypeError):
        copy.copy(prepared)
    with pytest.raises(TypeError):
        copy.deepcopy(prepared)
    with pytest.raises(TypeError):
        pickle.dumps(prepared)
    with pytest.raises(TypeError, match="cannot be serialized"):
        prepared.__reduce__()
    with pytest.raises(TypeError, match="cannot be serialized"):
        prepared.__reduce_ex__(4)
    for name in ("to_dict", "from_dict", "serialize", "deserialize"):
        assert not hasattr(prepared, name)


def test_prepare_is_side_effect_free_and_validation_failure_does_not_consume() -> None:
    simulator = _runtime().simulator
    prepared = simulator.prepare_step()
    assert simulator.clock.now == NOW
    assert simulator.soc_fraction == 0.5
    assert simulator.previous_actual_power_kw == 0.0
    with pytest.raises(ValueError):
        prepared.execute(None, duration=timedelta())
    next_simulator, _ = prepared.execute(None, duration=timedelta(seconds=1))
    assert next_simulator.clock.now == NOW + timedelta(seconds=1)


def test_prepared_session_is_bound_to_its_creating_snapshot_and_branch() -> None:
    source = _runtime().simulator
    independent_branch = replace(source, soc_fraction=0.8)
    prepared = source.prepare_step()
    assert prepared.simulator is source
    next_simulator, step = prepared.execute(None, duration=timedelta(seconds=1))
    assert step.starting_soc_fraction == source.soc_fraction
    assert next_simulator.soc_fraction == source.soc_fraction
    assert independent_branch.soc_fraction == 0.8


def test_p03_tick_samples_fault_schedule_once_and_hides_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    schedule = runtime.simulator.configuration.fault_schedule
    calls = 0
    original = type(schedule).active_at

    def counted(self: FaultSchedule, at: datetime) -> tuple[FaultSpecification, ...]:
        nonlocal calls
        calls += 1
        return original(self, at)

    monkeypatch.setattr(type(schedule), "active_at", counted)
    after = runtime.tick(None, duration=timedelta(seconds=1))
    assert calls == 1
    assert not hasattr(after, "prepared")
    assert after.trace.steps[-1].device_step.active_faults == ()


@pytest.mark.parametrize("mode", ["no_command", "blocked", "admitted"])
def test_each_tick_path_prepares_and_executes_one_fault_snapshot(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime = _runtime()
    if mode == "admitted":
        runtime = runtime.tick(None, duration=timedelta(seconds=1))
    schedule = runtime.simulator.configuration.fault_schedule
    calls = 0
    original = type(schedule).active_at

    def counted(self: FaultSchedule, at: datetime) -> tuple[FaultSpecification, ...]:
        nonlocal calls
        calls += 1
        return original(self, at)

    monkeypatch.setattr(type(schedule), "active_at", counted)
    command = None if mode == "no_command" else _command(runtime)
    after = runtime.tick(command, duration=timedelta(seconds=1))
    assert calls == 1
    step = after.trace.steps[-1]
    assert step.device_step.raw_telemetry.observed_at == step.started_at
    if mode == "admitted":
        assert step.device_step.command is not None
    else:
        assert step.device_step.command is None


@pytest.mark.parametrize(
    ("fault", "expected_state", "expected_reason"),
    [
        (
            _fault("telemetry", FaultType.TELEMETRY_FROZEN, FaultTarget.TELEMETRY),
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            "telemetry_stale",
        ),
        (
            _fault("bms-stale", FaultType.CAPABILITY_STALE, FaultTarget.BMS),
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            "capability_stale",
        ),
        (
            _fault("pcs-stale", FaultType.CAPABILITY_STALE, FaultTarget.PCS),
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            "capability_stale",
        ),
        (
            _fault("soc", FaultType.SOC_UNKNOWN, FaultTarget.BMS),
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            "soc_unknown",
        ),
        (
            _fault("bms-link", FaultType.DISCONNECTED, FaultTarget.BMS),
            RuntimeState.DEGRADED,
            "bms_disconnected",
        ),
        (
            _fault("pcs-link", FaultType.DISCONNECTED, FaultTarget.PCS),
            RuntimeState.DEGRADED,
            "pcs_disconnected",
        ),
        (
            _fault("bms-off", FaultType.UNAVAILABLE, FaultTarget.BMS),
            RuntimeState.DEGRADED,
            "bms_unavailable",
        ),
        (
            _fault("pcs-off", FaultType.UNAVAILABLE, FaultTarget.PCS),
            RuntimeState.DEGRADED,
            "pcs_unavailable",
        ),
        (
            _fault("channel", FaultType.DISCONNECTED, FaultTarget.COMMAND_CHANNEL),
            RuntimeState.DEGRADED,
            "command_channel_unhealthy",
        ),
        (
            _fault("warning", FaultType.WARNING_FAULT, FaultTarget.BMS),
            RuntimeState.READY,
            "warning_fault_active",
        ),
        (
            _fault("critical", FaultType.CRITICAL_FAULT, FaultTarget.BMS),
            RuntimeState.FAULTED,
            "critical_fault_active",
        ),
        (
            _fault("critical-pcs", FaultType.CRITICAL_FAULT, FaultTarget.PCS),
            RuntimeState.FAULTED,
            "critical_fault_active",
        ),
        (
            _fault("critical-edge", FaultType.CRITICAL_FAULT, FaultTarget.EDGE),
            RuntimeState.FAULTED,
            "critical_fault_active",
        ),
        (
            _fault("estop", FaultType.ESTOP, FaultTarget.PCS),
            RuntimeState.FAULTED,
            "emergency_stop_active",
        ),
    ],
)
def test_public_tick_maps_prepared_fault_and_fact_inputs_to_runtime_state(
    fault: FaultSpecification,
    expected_state: RuntimeState,
    expected_reason: str,
) -> None:
    runtime = _runtime(fault)
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    step = result.trace.steps[-1]
    assert result.state is expected_state
    assert expected_reason in step.transition_reasons
    assert step.device_step.command is None


def test_public_tick_maps_unknown_actual_power_to_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicDeviceSimulator._telemetry

    def unknown_actual(
        self: DeterministicDeviceSimulator,
        faults: tuple[FaultSpecification, ...],
        *,
        at_end: bool,
        actual_power_kw: float,
    ) -> TelemetrySnapshot:
        telemetry = original(
            self, faults, at_end=at_end, actual_power_kw=actual_power_kw
        )
        return replace(telemetry, actual_battery_power_kw=None)

    monkeypatch.setattr(DeterministicDeviceSimulator, "_telemetry", unknown_actual)
    runtime = _runtime()
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert result.state is RuntimeState.WAITING_FOR_FRESH_TELEMETRY
    assert "actual_power_unknown" in result.trace.steps[-1].transition_reasons
    assert result.trace.steps[-1].device_step.command is None


def test_public_tick_maps_explicit_runtime_fallback_to_safe_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicDeviceSimulator._health

    def fallback_health(
        self: DeterministicDeviceSimulator,
        faults: tuple[FaultSpecification, ...],
        events: tuple[FaultEvent, ...],
    ) -> RuntimeHealth:
        health = original(self, faults, events)
        return replace(
            health,
            runtime_state=RuntimeState.SAFE_IDLE,
            safe_fallback_active=True,
        )

    monkeypatch.setattr(DeterministicDeviceSimulator, "_health", fallback_health)
    runtime = _runtime()
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert result.state is RuntimeState.SAFE_IDLE
    assert "runtime_safe_fallback_active" in result.trace.steps[-1].transition_reasons
    assert result.trace.steps[-1].device_step.command is None


def test_public_tick_maps_runtime_link_health_to_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeterministicDeviceSimulator._health

    def degraded_health(
        self: DeterministicDeviceSimulator,
        faults: tuple[FaultSpecification, ...],
        events: tuple[FaultEvent, ...],
    ) -> RuntimeHealth:
        return replace(
            original(self, faults, events), runtime_state=RuntimeState.DEGRADED
        )

    monkeypatch.setattr(DeterministicDeviceSimulator, "_health", degraded_health)
    runtime = _runtime()
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert result.state is RuntimeState.DEGRADED
    assert "runtime_link_unhealthy" in result.trace.steps[-1].transition_reasons
    assert result.trace.steps[-1].device_step.command is None


@pytest.mark.parametrize(
    "state",
    [
        RuntimeState.STARTING,
        RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
        RuntimeState.DEGRADED,
        RuntimeState.SAFE_IDLE,
        RuntimeState.FAULTED,
        RuntimeState.ACTIVE,
        RuntimeState.SHUTTING_DOWN,
    ],
)
def test_non_ready_state_never_admits_nonzero_command(state: RuntimeState) -> None:
    runtime = _runtime_with_state(_runtime(), state)
    result = runtime.tick(_command(runtime), duration=timedelta(seconds=1))
    assert result.trace.steps[-1].device_step.command is None
    assert result.trace.steps[-1].device_step.actual_power_kw == 0.0


def test_ready_state_admits_zero_and_nonzero_commands() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    zero = replace(
        _command(ready),
        requested_battery_power_kw=0.0,
        operating_mode=OperatingMode.SAFE_IDLE,
    )
    idle = ready.tick(zero, duration=timedelta(seconds=1))
    assert idle.trace.steps[-1].device_step.command is zero
    assert idle.trace.steps[-1].device_step.actual_power_kw == 0.0
    active = idle.tick(_command(idle, 2), duration=timedelta(seconds=1))
    assert active.trace.steps[-1].device_step.command is not None
    assert active.trace.steps[-1].device_step.actual_power_kw == 1.0


def test_duplicate_identity_is_not_reexecuted_and_conflicts_raise() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    command = _command(ready)
    completed = ready.tick(command, duration=timedelta(seconds=1))
    duplicate = completed.tick(command, duration=timedelta(seconds=1))
    assert duplicate.trace.steps[-1].device_step.command is None
    assert "duplicate_command_id" in duplicate.trace.steps[-1].transition_reasons
    with pytest.raises(ValueError, match="payload"):
        duplicate.tick(
            replace(command, requested_battery_power_kw=2.0),
            duration=timedelta(seconds=1),
        )
    same_sequence = replace(_command(duplicate, 2), sequence=1)
    with pytest.raises(ValueError, match="same sequence"):
        duplicate.tick(same_sequence, duration=timedelta(seconds=1))
    with pytest.raises(ValueError, match="sequence rollback"):
        duplicate.tick(_command(duplicate, 0), duration=timedelta(seconds=1))


def test_expired_command_is_terminal_before_device_execution() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    expired = replace(
        _command(ready),
        issued_at=ready.simulator.clock.now - timedelta(seconds=2),
        not_before=ready.simulator.clock.now - timedelta(seconds=2),
        expires_at=ready.simulator.clock.now - timedelta(seconds=1),
    )
    result = ready.tick(expired, duration=timedelta(seconds=1))
    step = result.trace.steps[-1]
    assert step.device_step.command is None
    assert step.reconciliation.status is ReconciliationStatus.COMMAND_EXPIRED
    assert result.state is RuntimeState.SAFE_IDLE


def test_future_and_invalid_window_commands_are_rejected_before_execution() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    future = replace(
        _command(ready), issued_at=ready.simulator.clock.now + timedelta(seconds=3)
    )
    with pytest.raises(ValueError, match="max_clock_skew"):
        ready.tick(future, duration=timedelta(seconds=1))
    with pytest.raises(ValueError, match="expires_at must be later"):
        replace(_command(ready, 2), expires_at=ready.simulator.clock.now)


def test_inflight_ack_drop_blocks_new_command_then_expiry_requires_recovery_tick() -> (
    None
):
    dropped = _fault(
        "dropped",
        FaultType.ACK_DROPPED,
        FaultTarget.PCS,
        clear_at=NOW + timedelta(seconds=2),
    )
    ready = _runtime(dropped).tick(None, duration=timedelta(seconds=1))
    short = replace(
        _command(ready), expires_at=ready.simulator.clock.now + timedelta(seconds=1)
    )
    inflight = ready.tick(short, duration=timedelta(seconds=1))
    assert inflight.state is RuntimeState.SAFE_IDLE
    assert (
        inflight.trace.steps[-1].reconciliation.status
        is ReconciliationStatus.COMMAND_EXPIRED
    )
    blocked = inflight.tick(_command(inflight, 2), duration=timedelta(seconds=1))
    assert blocked.trace.steps[-1].device_step.command is None
    assert blocked.state is RuntimeState.READY
    assert blocked.lifecycle_book.records[-1].state.value == "expired"
    admitted = blocked.tick(_command(blocked, 2), duration=timedelta(seconds=1))
    assert admitted.trace.steps[-1].device_step.command is not None


def test_unresolved_inflight_lifecycle_never_admits_a_replacement_command() -> None:
    dropped = _fault("dropped", FaultType.ACK_DROPPED, FaultTarget.PCS)
    ready = _runtime(dropped).tick(None, duration=timedelta(seconds=1))
    inflight = ready.tick(_command(ready), duration=timedelta(seconds=1))
    assert inflight.state is RuntimeState.DEGRADED
    assert inflight.lifecycle_book.records[-1].state.value == "issued"

    replacement = inflight.tick(_command(inflight, 2), duration=timedelta(seconds=1))
    assert replacement.trace.steps[-1].device_step.command is None
    assert replacement.lifecycle_book.records[-1].command.sequence == 1


def test_ack_rejection_is_terminal_and_recovery_does_not_replay() -> None:
    rejected = _fault(
        "rejected",
        FaultType.ACK_REJECTED,
        FaultTarget.PCS,
        clear_at=NOW + timedelta(seconds=2),
    )
    ready = _runtime(rejected).tick(None, duration=timedelta(seconds=1))
    terminal = ready.tick(_command(ready), duration=timedelta(seconds=1))
    assert terminal.state is RuntimeState.SAFE_IDLE
    assert (
        terminal.trace.steps[-1].reconciliation.status
        is ReconciliationStatus.ACK_REJECTED
    )
    terminal_ids = _identity_sets(terminal)
    terminal_records = terminal.lifecycle_book.records
    recovered = terminal.tick(None, duration=timedelta(seconds=1))
    assert recovered.state is RuntimeState.READY
    _assert_no_command_tick(terminal, recovered)
    assert recovered.lifecycle_book.records == terminal_records
    assert _identity_sets(recovered) == terminal_ids

    still_idle = recovered.tick(None, duration=timedelta(seconds=1))
    assert still_idle.state is RuntimeState.READY
    _assert_no_command_tick(recovered, still_idle)

    new_caller_command = _command(still_idle, 2)
    admitted = still_idle.tick(new_caller_command, duration=timedelta(seconds=1))
    step = admitted.trace.steps[-1]
    assert step.caller_command is new_caller_command
    assert step.admitted_command is new_caller_command
    assert step.command_origin is CommandOrigin.CURRENT_CALLER
    assert not step.automatic_command_generated
    assert step.device_step.command is new_caller_command
    assert (
        step.device_step.actual_power_kw
        == new_caller_command.requested_battery_power_kw
    )
    assert _identity_sets(admitted) == (
        {*terminal_ids[0], new_caller_command.command_id},
        {1, 2},
    )


@pytest.mark.parametrize(
    ("label", "fault", "requires_terminal_command"),
    [
        (
            "ack_rejected",
            _fault(
                "reject",
                FaultType.ACK_REJECTED,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=2),
            ),
            True,
        ),
        (
            "ack_dropped_expiry",
            _fault(
                "dropped",
                FaultType.ACK_DROPPED,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=2),
            ),
            True,
        ),
        (
            "ack_delayed_expiry",
            _fault(
                "delayed",
                FaultType.ACK_DELAYED,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=2),
                parameters=(("seconds", 2.0),),
            ),
            True,
        ),
        (
            "critical_bms",
            _fault(
                "critical-bms",
                FaultType.CRITICAL_FAULT,
                FaultTarget.BMS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "critical_pcs",
            _fault(
                "critical-pcs",
                FaultType.CRITICAL_FAULT,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "critical_edge",
            _fault(
                "critical-edge",
                FaultType.CRITICAL_FAULT,
                FaultTarget.EDGE,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "estop",
            _fault(
                "estop",
                FaultType.ESTOP,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "telemetry_stale",
            _fault(
                "telemetry",
                FaultType.TELEMETRY_FROZEN,
                FaultTarget.TELEMETRY,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "capability_stale",
            _fault(
                "capability",
                FaultType.CAPABILITY_STALE,
                FaultTarget.BMS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "bms_disconnected",
            _fault(
                "disconnected",
                FaultType.DISCONNECTED,
                FaultTarget.BMS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "pcs_unavailable",
            _fault(
                "unavailable",
                FaultType.UNAVAILABLE,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=1),
            ),
            False,
        ),
        (
            "actual_mismatch",
            _fault(
                "mismatch",
                FaultType.ACTUAL_POWER_DEVIATION,
                FaultTarget.PCS,
                clear_at=NOW + timedelta(seconds=2),
                parameters=(("factor", 0.5),),
            ),
            True,
        ),
        (
            "ordinary_safety_block",
            _fault(
                "charge-prohibited",
                FaultType.CHARGE_PROHIBITED,
                FaultTarget.BMS,
                clear_at=NOW + timedelta(seconds=2),
            ),
            True,
        ),
    ],
)
def test_recovery_scenarios_never_generate_or_replay_commands(
    label: str,
    fault: FaultSpecification,
    requires_terminal_command: bool,
) -> None:
    runtime = _runtime(fault)
    if requires_terminal_command:
        ready = runtime.tick(None, duration=timedelta(seconds=1))
        command = _command(ready)
        if label in {"ack_dropped_expiry", "ack_delayed_expiry"}:
            command = replace(
                command, expires_at=ready.simulator.clock.now + timedelta(seconds=1)
            )
        before_recovery = ready.tick(command, duration=timedelta(seconds=1))
    else:
        before_recovery = runtime.tick(None, duration=timedelta(seconds=1))

    recovery = before_recovery.tick(None, duration=timedelta(seconds=1))
    _assert_no_command_tick(before_recovery, recovery)
    follow_up = recovery.tick(None, duration=timedelta(seconds=1))
    _assert_no_command_tick(recovery, follow_up)


def test_recovery_observation_with_new_command_never_replays_or_admits() -> None:
    fault = _fault(
        "critical",
        FaultType.CRITICAL_FAULT,
        FaultTarget.BMS,
        clear_at=NOW + timedelta(seconds=1),
    )
    faulted = _runtime(fault).tick(None, duration=timedelta(seconds=1))
    recovery_command = _command(faulted, 2)
    observed = faulted.tick(recovery_command, duration=timedelta(seconds=1))
    assert observed.state is RuntimeState.READY
    assert observed.trace.steps[-1].caller_command is recovery_command
    assert observed.trace.steps[-1].device_step.command is None
    assert observed.trace.steps[-1].device_step.actual_power_kw == 0.0


def test_current_caller_admission_preserves_exact_command_identity() -> None:
    """The normal admission path passes the caller object unchanged to P0.2."""
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    caller_command = _command(ready)

    after = ready.tick(caller_command, duration=timedelta(seconds=1))

    step = after.trace.steps[-1]
    assert step.caller_command is caller_command
    assert step.admitted_command is caller_command
    assert step.command_origin is CommandOrigin.CURRENT_CALLER
    assert step.device_step.command is caller_command
    assert (
        step.caller_command.command_id,
        step.caller_command.sequence,
        step.caller_command.issued_at,
        step.caller_command.expires_at,
        step.caller_command.requested_battery_power_kw,
        step.caller_command.operating_mode,
    ) == (
        caller_command.command_id,
        caller_command.sequence,
        caller_command.issued_at,
        caller_command.expires_at,
        caller_command.requested_battery_power_kw,
        caller_command.operating_mode,
    )


def test_admission_corruption_is_rejected_before_p02_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forged admission result cannot cross the runtime-to-plant boundary."""
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    caller_issued_at = ready.simulator.clock.now - timedelta(seconds=1)
    caller_command = replace(
        _command(ready),
        issued_at=caller_issued_at,
        not_before=caller_issued_at,
        expires_at=caller_issued_at + timedelta(minutes=1),
    )
    forged_issued_at = ready.simulator.clock.now
    forged_command = replace(
        caller_command,
        command_id="forged-admission-command",
        sequence=caller_command.sequence + 1,
        issued_at=forged_issued_at,
        not_before=forged_issued_at,
        expires_at=forged_issued_at + timedelta(minutes=1),
        requested_battery_power_kw=2.0,
        correlation_id="forged-admission-command",
    )
    simulator_before = ready.simulator
    lifecycle_before = ready.lifecycle_book
    trace_before = ready.trace
    execute_calls = 0
    original_execute = PreparedDeviceSimulatorStep.execute

    def counted_execute(
        self: PreparedDeviceSimulatorStep,
        command: PowerCommand | None,
        *,
        duration: timedelta,
    ) -> tuple[DeterministicDeviceSimulator, object]:
        nonlocal execute_calls
        execute_calls += 1
        return original_execute(self, command, duration=duration)

    def forged_admission(
        caller: PowerCommand | None, *, admission_open: bool
    ) -> PowerCommand | None:
        assert caller is caller_command
        assert admission_open
        return forged_command

    monkeypatch.setattr(
        PreparedDeviceSimulatorStep,
        "execute",
        counted_execute,
    )
    monkeypatch.setattr(
        ControlledEdgeRuntime,
        "_admit_current_caller_command",
        staticmethod(forged_admission),
    )

    try:
        ready.tick(caller_command, duration=timedelta(seconds=1))
    except ValueError as error:
        if str(error) != "admitted command must be the current caller command object":
            pytest.fail(
                "forged admission crossed the P0.2 execution boundary before "
                "post-execution audit rejection "
                f"(execute_calls={execute_calls}, error={error})"
            )
    else:
        pytest.fail(
            "forged admission reached the P0.2 execution boundary "
            f"(execute_calls={execute_calls})"
        )

    assert execute_calls == 0
    assert ready.simulator is simulator_before
    assert ready.simulator.clock == simulator_before.clock
    assert ready.simulator.soc_fraction == simulator_before.soc_fraction
    assert (
        ready.simulator.previous_actual_power_kw
        == simulator_before.previous_actual_power_kw
    )
    assert ready.lifecycle_book is lifecycle_before
    assert ready.lifecycle_book.records == lifecycle_before.records
    assert all(
        record.command.command_id != forged_command.command_id
        and record.command.sequence != forged_command.sequence
        for record in ready.lifecycle_book.records
    )
    assert ready.trace is trace_before


def test_actual_mismatch_is_degraded_and_is_not_lifecycle_completion() -> None:
    deviation = _fault(
        "deviation",
        FaultType.ACTUAL_POWER_DEVIATION,
        FaultTarget.PCS,
        parameters=(("factor", 0.5),),
    )
    ready = _runtime(deviation).tick(None, duration=timedelta(seconds=1))
    result = ready.tick(_command(ready), duration=timedelta(seconds=1))
    step = result.trace.steps[-1]
    assert (
        step.reconciliation.status is ReconciliationStatus.ACK_ACCEPTED_ACTUAL_MISMATCH
    )
    assert result.state is RuntimeState.DEGRADED
    assert step.lifecycle_after.records[-1].state.value == "executing"


def test_unexpected_actual_reconciliation_is_faulted_by_production_guard() -> None:
    # P0.2 cannot emit this combination for an unauthorized command, so this
    # checks the P0.3 guard that protects a future external actual source.
    state, reasons = ControlledEdgeRuntime._state_after_reconciliation(
        RuntimeState.READY,
        CommandReconciliation(
            ReconciliationStatus.UNEXPECTED_ACTUAL,
            "unexpected_actual",
            ("unexpected_actual",),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            1.0,
            0.0,
            1.0,
            0.01,
            None,
            None,
            None,
            True,
        ),
    )
    assert state is RuntimeState.FAULTED
    assert reasons == ("unexpected_nonzero_actual",)


def test_ordinary_direction_safety_block_is_safe_idle_not_device_fault() -> None:
    prohibited = _fault(
        "charge-prohibited", FaultType.CHARGE_PROHIBITED, FaultTarget.BMS
    )
    ready = _runtime(prohibited).tick(None, duration=timedelta(seconds=1))
    result = ready.tick(_command(ready), duration=timedelta(seconds=1))
    step = result.trace.steps[-1]
    assert step.device_step.safety_decision is not None
    assert step.device_step.safety_decision.final_requested_battery_power_kw == 0.0
    assert step.reconciliation.status is ReconciliationStatus.LIFECYCLE_INCOMPLETE
    assert ReconciliationStatus.SAFETY_BLOCKED.value in step.reconciliation.reason_codes
    assert result.state is RuntimeState.SAFE_IDLE


def test_shutdown_is_terminal_for_ordinary_ticks_and_never_admits() -> None:
    shutdown = _runtime().request_shutdown()
    after = shutdown.tick(_command(shutdown), duration=timedelta(seconds=1))
    assert after.state is RuntimeState.SHUTTING_DOWN
    assert after.trace.steps[-1].device_step.command is None
    assert after.trace.steps[-1].transition_reasons == ("shutdown_requested",)
    with pytest.raises(ValueError, match="not allowed"):
        _transition(RuntimeState.SHUTTING_DOWN, RuntimeState.READY)


def test_runtime_transition_guard_matches_public_state_matrix() -> None:
    expected_admission = {RuntimeState.READY}
    for state, allowed in _ALLOWED_RUNTIME_TRANSITIONS.items():
        for target in allowed:
            assert _transition(state, target) is target
        if state is RuntimeState.SHUTTING_DOWN:
            assert allowed == {RuntimeState.SHUTTING_DOWN}
        assert (state in expected_admission) is (state is RuntimeState.READY)


def test_reconciliation_precedence_retains_all_compound_evidence() -> None:
    command = _command(_runtime())
    rejected_nonzero = ControlledEdgeRuntime._reconcile(
        command,
        command,
        telemetry_actual_power_kw=1.0,
        final_safe_request_power_kw=0.0,
        acknowledgement_status=AcknowledgementStatus.REJECTED,
        acknowledged_power_kw=None,
        acknowledgement_received_at=NOW,
        application_authorized=False,
        safety_blocked=True,
        lifecycle_before=None,
        lifecycle_after=None,
        tolerance_kw=0.01,
        command_expired=False,
    )
    assert rejected_nonzero.status is ReconciliationStatus.UNEXPECTED_ACTUAL
    assert rejected_nonzero.reason_codes == (
        "unexpected_actual",
        "actual_mismatch",
        "ack_rejected",
        "application_not_authorized",
        "safety_blocked",
    )
    delayed_expired = ControlledEdgeRuntime._reconcile(
        command,
        command,
        telemetry_actual_power_kw=0.0,
        final_safe_request_power_kw=1.0,
        acknowledgement_status=AcknowledgementStatus.ACCEPTED,
        acknowledged_power_kw=1.0,
        acknowledgement_received_at=NOW + timedelta(seconds=1),
        application_authorized=False,
        safety_blocked=False,
        lifecycle_before=None,
        lifecycle_after=None,
        tolerance_kw=0.01,
        command_expired=True,
    )
    assert delayed_expired.status is ReconciliationStatus.COMMAND_EXPIRED
    assert delayed_expired.reason_codes == (
        "command_expired",
        "ack_delayed",
        "application_not_authorized",
    )


def test_reconciliation_unknown_actual_is_not_zero_and_fails_closed() -> None:
    command = _command(_runtime())
    reconciliation = ControlledEdgeRuntime._reconcile(
        command,
        command,
        telemetry_actual_power_kw=None,
        final_safe_request_power_kw=1.0,
        acknowledgement_status=AcknowledgementStatus.ACCEPTED,
        acknowledged_power_kw=1.0,
        acknowledgement_received_at=NOW,
        application_authorized=True,
        safety_blocked=False,
        lifecycle_before=None,
        lifecycle_after=None,
        tolerance_kw=0.01,
        command_expired=False,
    )
    assert reconciliation.status is ReconciliationStatus.ACTUAL_UNKNOWN
    assert reconciliation.actual_power_kw is None
    assert reconciliation.absolute_deviation_kw is None
    assert reconciliation.fail_closed
    assert type(reconciliation).from_dict(reconciliation.to_dict()) == reconciliation


def test_trace_and_reconciliation_serialization_are_strict_and_deterministic() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    runtime = ready.tick(_command(ready), duration=timedelta(seconds=1))
    trace = runtime.trace
    payload = trace.to_dict()
    assert type(trace).from_dict(payload) == trace
    assert json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) == json.dumps(
        trace.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert "PreparedDeviceSimulatorStep" not in str(payload)
    assert "DeterministicDeviceSimulator" not in str(payload)
    with pytest.raises(ValueError, match="missing fields"):
        type(trace).from_dict({"schema_version": trace.SCHEMA_VERSION})
    with pytest.raises(ValueError, match="unknown fields"):
        type(trace).from_dict({**payload, "unknown": True})
    wrong_nested_schema = copy.deepcopy(payload)
    nested_steps = wrong_nested_schema["steps"]
    assert isinstance(nested_steps, list)
    nested_step = nested_steps[0]
    assert isinstance(nested_step, dict)
    nested_device_step = nested_step["device_step"]
    assert isinstance(nested_device_step, dict)
    nested_device_step["schema_version"] = "forged/v1"
    with pytest.raises(ValueError, match="unsupported DeviceSimulatorStep"):
        type(trace).from_dict(wrong_nested_schema)
    reconciliation = trace.steps[-1].reconciliation
    wrong_enum = reconciliation.to_dict()
    wrong_enum["status"] = "not-a-status"
    with pytest.raises(ValueError):
        type(reconciliation).from_dict(wrong_enum)
    with pytest.raises(TypeError, match="tolerance_kw"):
        replace(reconciliation, tolerance_kw=True)
    with pytest.raises(ValueError, match="finite"):
        replace(reconciliation, tolerance_kw=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        replace(reconciliation, tolerance_kw=float("inf"))
    with pytest.raises(ValueError, match="finite"):
        replace(reconciliation, tolerance_kw=float("-inf"))
    with pytest.raises(ValueError, match="duplicates"):
        replace(reconciliation, reason_codes=("completed", "completed"))
    with pytest.raises(ValueError, match="canonical precedence"):
        replace(
            reconciliation,
            status=ReconciliationStatus.ACTUAL_MATCHED,
            primary_reason="actual_matched",
            reason_codes=("actual_matched", "completed"),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(reconciliation, acknowledgement_received_at=datetime(2032, 1, 1))


def test_trace_linkage_and_evidence_do_not_hydrate_runtime_authority() -> None:
    ready = _runtime().tick(None, duration=timedelta(seconds=1))
    runtime = ready.tick(_command(ready), duration=timedelta(seconds=1))
    trace = runtime.trace
    broken_index = replace(trace.steps[1], tick_index=4)
    with pytest.raises(ValueError, match="contiguous"):
        type(trace)((trace.steps[0], broken_index))
    broken_soc = replace(
        trace.steps[1].device_step,
        starting_soc_fraction=trace.steps[1].device_step.starting_soc_fraction + 0.01,
    )
    with pytest.raises(ValueError, match="SOC evidence must link"):
        type(trace)((trace.steps[0], replace(trace.steps[1], device_step=broken_soc)))
    assert not hasattr(ControlledEdgeRuntime, "from_dict")
    assert not hasattr(type(runtime.lifecycle_book), "from_dict")
    assert not hasattr(type(runtime.simulator), "from_dict")
    assert not hasattr(type(runtime.simulator.prepare_step()), "from_dict")
