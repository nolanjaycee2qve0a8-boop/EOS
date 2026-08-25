"""Mutation-sensitive P0.2 virtual device and fault-injection regressions."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest

from edge_runtime import (
    CommandLifecycleState,
    FaultSeverity,
    OperatingMode,
    PowerCommand,
    TimingPolicy,
    evaluate_freshness,
    merge_device_capabilities,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceScenarioHarness,
    DeterministicDeviceSimulator,
    DeviceSimulatorConfiguration,
    FaultSchedule,
    FaultSpecification,
    FaultTarget,
    FaultType,
    VirtualClock,
)
from edge_runtime.device_simulator.contracts import _FAULT_COMPATIBILITY

NOW = datetime(2031, 2, 3, 4, 5, tzinfo=UTC)
POLICY = TimingPolicy(
    timedelta(seconds=30),
    timedelta(seconds=30),
    timedelta(minutes=10),
    timedelta(seconds=2),
    timedelta(seconds=5),
    timedelta(seconds=30),
)


def _fault(
    fault_id: str,
    fault_type: FaultType,
    target: FaultTarget,
    *,
    activation_at: datetime = NOW,
    clear_at: datetime | None = None,
    parameters: tuple[tuple[str, float], ...] = (),
) -> FaultSpecification:
    return FaultSpecification(
        fault_id,
        fault_type,
        target,
        activation_at,
        clear_at,
        parameters,
        f"P0.2 test {fault_id}",
    )


def _configuration(
    *faults: FaultSpecification, initial_soc: float = 0.5
) -> DeviceSimulatorConfiguration:
    return DeviceSimulatorConfiguration(
        10.0,
        initial_soc,
        0.2,
        1.0,
        3.0,
        3.0,
        0.95,
        0.95,
        POLICY,
        FaultSchedule(tuple(faults)),
    )


def _command(
    command_id: str = "p0-2-command-1",
    sequence: int = 1,
    power_kw: float = 1.0,
    *,
    issued_at: datetime = NOW,
    lifetime: timedelta = timedelta(minutes=5),
) -> PowerCommand:
    return PowerCommand(
        "edge-power-command/v1",
        command_id,
        sequence,
        "p0-2-plan-step",
        issued_at,
        issued_at,
        issued_at + lifetime,
        power_kw,
        OperatingMode.SAFE_IDLE if power_kw == 0 else OperatingMode.NORMAL,
        "p0_2_test",
        "p0_2_test",
        command_id,
    )


def _simulator(
    *faults: FaultSpecification, initial_soc: float = 0.5
) -> DeterministicDeviceSimulator:
    return DeterministicDeviceSimulator.start(
        _configuration(*faults, initial_soc=initial_soc), at=VirtualClock(NOW)
    )


def test_public_api_nominal_command_ack_actual_and_lifecycle_are_distinct() -> None:
    harness = DeterministicDeviceScenarioHarness.start(_simulator()).advance(
        _command(), duration=timedelta(seconds=10)
    )
    step = harness.trace.steps[0]
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 1.0
    assert step.acknowledgement is not None
    assert step.acknowledgement.accepted_power_kw == 1.0
    assert step.command_application_authorized
    assert step.actual_telemetry.actual_battery_power_kw == 1.0
    assert (
        harness.trace.lifecycle_book.records[0].state is CommandLifecycleState.COMPLETED
    )
    assert step.ending_soc_fraction > step.starting_soc_fraction


def test_actual_power_drives_soc_and_stuck_zero_blocks_completion() -> None:
    simulator = _simulator(_fault("stuck", FaultType.STUCK_AT_ZERO, FaultTarget.PCS))
    harness = DeterministicDeviceScenarioHarness.start(simulator).advance(
        _command(power_kw=2.0), duration=timedelta(hours=1)
    )
    step = harness.trace.steps[0]
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 2.0
    assert step.acknowledgement is not None
    assert step.acknowledgement.acknowledgement_status.value == "accepted"
    assert step.actual_power_kw == 0.0
    assert step.ending_soc_fraction == 0.5
    assert "pcs_stuck_at_zero" in step.boundary_evidence
    assert (
        harness.trace.lifecycle_book.records[0].state is CommandLifecycleState.EXPIRED
    )


def test_charge_discharge_efficiency_and_soc_boundaries_use_actual_signed_power() -> (
    None
):
    charged, charge_step = _simulator().step(
        _command(power_kw=2.0), duration=timedelta(hours=1)
    )
    assert charge_step.actual_power_kw == 2.0
    assert charge_step.ending_soc_fraction == pytest.approx(0.69)
    _, discharge_step = charged.step(
        _command("discharge", 2, -2.0, issued_at=charged.clock.now),
        duration=timedelta(hours=1),
    )
    assert discharge_step.ending_soc_fraction == pytest.approx(0.69 - 2 / 0.95 / 10)
    _, upper = _simulator(initial_soc=0.99).step(
        _command(power_kw=3), duration=timedelta(hours=1)
    )
    assert upper.ending_soc_fraction == 1.0
    assert "max_soc_power_limited" in upper.boundary_evidence
    _, lower = _simulator(initial_soc=0.21).step(
        _command(power_kw=-3), duration=timedelta(hours=1)
    )
    assert lower.ending_soc_fraction == 0.2
    assert "min_soc_power_limited" in lower.boundary_evidence


@pytest.mark.parametrize(
    ("fault", "expected_reason"),
    [
        (
            _fault("pcs-down", FaultType.DISCONNECTED, FaultTarget.PCS),
            "runtime_link_not_healthy",
        ),
        (
            _fault("bms-down", FaultType.UNAVAILABLE, FaultTarget.BMS),
            "effective_capability_unavailable",
        ),
        (
            _fault("channel", FaultType.DISCONNECTED, FaultTarget.COMMAND_CHANNEL),
            "runtime_link_not_healthy",
        ),
        (
            _fault("critical", FaultType.CRITICAL_FAULT, FaultTarget.BMS),
            "blocking_active_fault",
        ),
        (_fault("estop", FaultType.ESTOP, FaultTarget.PCS), "emergency_stop_active"),
        (
            _fault("charge-ban", FaultType.CHARGE_PROHIBITED, FaultTarget.BMS),
            "charge_not_allowed",
        ),
    ],
)
def test_key_faults_change_real_p01_inputs_and_fail_closed(
    fault: FaultSpecification, expected_reason: str
) -> None:
    _, step = _simulator(fault).step(_command(), duration=timedelta(seconds=10))
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 0.0
    assert expected_reason in {
        item.reason_code for item in step.safety_decision.applied_constraints
    }


def test_overlap_preserves_stable_fault_and_p01_constraint_evidence() -> None:
    faults = (
        _fault("z-estop", FaultType.ESTOP, FaultTarget.PCS),
        _fault("a-stale", FaultType.TELEMETRY_FROZEN, FaultTarget.TELEMETRY),
        _fault("m-critical", FaultType.CRITICAL_FAULT, FaultTarget.BMS),
        _fault("b-ban", FaultType.CHARGE_PROHIBITED, FaultTarget.BMS),
        _fault(
            "p-clamp",
            FaultType.CHARGE_DERATE,
            FaultTarget.PCS,
            parameters=(("factor", 0.2),),
        ),
    )
    _, step = _simulator(*reversed(faults)).step(
        _command(power_kw=3.0), duration=timedelta(seconds=10)
    )
    assert [item.fault_id for item in step.active_faults] == [
        "b-ban",
        "m-critical",
        "p-clamp",
        "z-estop",
        "a-stale",
    ]
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 0.0
    assert step.actual_power_kw == 0.0
    reasons = [item.reason_code for item in step.safety_decision.applied_constraints]
    assert reasons[:4] == [
        "emergency_stop_active",
        "telemetry_stale",
        "telemetry_quality_not_valid",
        "runtime_health_telemetry_not_fresh",
    ]


def test_observed_time_not_received_time_makes_frozen_telemetry_stale() -> None:
    _, step = _simulator(
        _fault("frozen", FaultType.TELEMETRY_FROZEN, FaultTarget.TELEMETRY)
    ).step(_command(), duration=timedelta(seconds=1))
    assert step.raw_telemetry.received_at == NOW
    assert step.raw_telemetry.observed_at < NOW
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 0.0
    assert "telemetry_stale" in {
        item.reason_code for item in step.safety_decision.applied_constraints
    }


def test_derating_clamps_without_direction_flip_and_soc_unknown_fails_closed() -> None:
    derate = _fault(
        "derate",
        FaultType.DISCHARGE_DERATE,
        FaultTarget.PCS,
        parameters=(("factor", 0.25),),
    )
    _, step = _simulator(derate).step(
        _command(power_kw=-3), duration=timedelta(seconds=1)
    )
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == -0.75
    unknown = _fault("unknown", FaultType.SOC_UNKNOWN, FaultTarget.BMS)
    _, blocked = _simulator(unknown).step(_command(), duration=timedelta(seconds=1))
    assert blocked.raw_telemetry.soc_fraction is None
    assert blocked.safety_decision is not None
    assert blocked.safety_decision.final_requested_battery_power_kw == 0.0


def test_low_soc_blocks_discharge_and_safe_idle_remains_zero() -> None:
    _, low_soc = _simulator(initial_soc=0.2).step(
        _command(power_kw=-1.0), duration=timedelta(seconds=1)
    )
    assert low_soc.safety_decision is not None
    assert low_soc.safety_decision.final_requested_battery_power_kw == 0.0
    assert "minimum_soc_reserve" in {
        item.reason_code for item in low_soc.safety_decision.applied_constraints
    }
    _, idle = _simulator().step(_command(power_kw=0.0), duration=timedelta(seconds=1))
    assert idle.safety_decision is not None
    assert idle.safety_decision.final_operating_mode is OperatingMode.SAFE_IDLE
    assert idle.actual_power_kw == 0.0


def test_stuck_previous_and_actual_deviation_are_actual_response_faults() -> None:
    moving, first = _simulator().step(
        _command(power_kw=1.0), duration=timedelta(seconds=1)
    )
    assert first.actual_power_kw == 1.0
    stuck = _fault("previous", FaultType.STUCK_AT_PREVIOUS_POWER, FaultTarget.PCS)
    state = replace(
        moving,
        configuration=replace(
            moving.configuration, fault_schedule=FaultSchedule((stuck,))
        ),
    )
    _, stuck_step = state.step(
        _command("next", 2, -2.0, issued_at=state.clock.now),
        duration=timedelta(seconds=1),
    )
    assert stuck_step.actual_power_kw == 1.0
    assert "pcs_stuck_at_previous_power" in stuck_step.boundary_evidence
    deviation = _fault(
        "deviation",
        FaultType.ACTUAL_POWER_DEVIATION,
        FaultTarget.PCS,
        parameters=(("factor", 0.5),),
    )
    _, deviation_step = _simulator(deviation).step(
        _command(power_kw=2.0), duration=timedelta(seconds=1)
    )
    assert deviation_step.actual_power_kw == 1.0
    assert deviation_step.safety_decision is not None
    assert deviation_step.safety_decision.final_requested_battery_power_kw == 2.0


@pytest.mark.parametrize(
    ("fault", "expected_state"),
    [
        (
            _fault("reject", FaultType.ACK_REJECTED, FaultTarget.PCS),
            CommandLifecycleState.ACK_REJECTED,
        ),
        (
            _fault("drop", FaultType.ACK_DROPPED, FaultTarget.COMMAND_CHANNEL),
            CommandLifecycleState.ISSUED,
        ),
    ],
)
def test_ack_reject_and_drop_never_create_completion(
    fault: FaultSpecification, expected_state: CommandLifecycleState
) -> None:
    harness = DeterministicDeviceScenarioHarness.start(_simulator(fault)).advance(
        _command(), duration=timedelta(seconds=10)
    )
    assert harness.trace.lifecycle_book.records[0].state is expected_state
    assert harness.trace.lifecycle_book.records[0].completion_evidence is None
    assert harness.trace.steps[0].actual_power_kw == 0.0
    assert harness.trace.steps[0].ending_soc_fraction == 0.5
    assert not harness.trace.steps[0].command_application_authorized
    assert "command_not_applied" in harness.trace.steps[0].boundary_evidence[0]


def test_late_ack_expires_instead_of_reviving_command() -> None:
    late = _fault(
        "late", FaultType.ACK_DELAYED, FaultTarget.PCS, parameters=(("seconds", 61.0),)
    )
    command = _command(lifetime=timedelta(seconds=60))
    harness = DeterministicDeviceScenarioHarness.start(_simulator(late)).advance(
        command, duration=timedelta(seconds=10)
    )
    assert harness.trace.steps[0].acknowledgement is not None
    assert harness.trace.steps[0].acknowledgement.received_at > command.expires_at
    assert harness.trace.lifecycle_book.records[0].state is CommandLifecycleState.ISSUED
    assert harness.trace.steps[0].actual_power_kw == 0.0
    assert harness.trace.steps[0].ending_soc_fraction == 0.5
    assert (
        "command_not_applied:ack_not_immediate"
        in harness.trace.steps[0].boundary_evidence
    )
    expired = harness.advance(None, duration=timedelta(seconds=51))
    assert expired.trace.steps[-1].actual_power_kw == 0.0
    assert (
        expired.trace.lifecycle_book.records[0].state is CommandLifecycleState.EXPIRED
    )


def test_ack_delayed_to_expiry_never_executes_then_expires() -> None:
    delayed = _fault(
        "at-expiry",
        FaultType.ACK_DELAYED,
        FaultTarget.PCS,
        parameters=(("seconds", 60.0),),
    )
    harness = DeterministicDeviceScenarioHarness.start(_simulator(delayed)).advance(
        _command(lifetime=timedelta(seconds=60)), duration=timedelta(seconds=10)
    )
    first = harness.trace.steps[-1]
    assert not first.command_application_authorized
    assert first.actual_power_kw == 0.0
    assert first.ending_soc_fraction == first.starting_soc_fraction
    assert (
        harness.trace.lifecycle_book.records[-1].state is CommandLifecycleState.ISSUED
    )
    expired = harness.advance(None, duration=timedelta(seconds=50))
    record = expired.trace.lifecycle_book.records[-1]
    assert record.state is CommandLifecycleState.EXPIRED
    assert record.execution_started_at is None
    assert record.completion_evidence is None


def test_fault_clear_after_dropped_ack_requires_new_command() -> None:
    dropped = _fault(
        "drop",
        FaultType.ACK_DROPPED,
        FaultTarget.COMMAND_CHANNEL,
        clear_at=NOW + timedelta(seconds=10),
    )
    harness = DeterministicDeviceScenarioHarness.start(_simulator(dropped)).advance(
        _command(lifetime=timedelta(seconds=10)), duration=timedelta(seconds=10)
    )
    assert harness.trace.steps[-1].actual_power_kw == 0.0
    cleared = harness.advance(None, duration=timedelta(seconds=1))
    assert cleared.trace.steps[-1].actual_power_kw == 0.0
    renewed = cleared.advance(
        _command("renewed", 2, issued_at=cleared.trace.simulator.clock.now),
        duration=timedelta(seconds=1),
    )
    assert renewed.trace.steps[-1].actual_power_kw == 1.0


def test_fault_compatibility_rejects_every_invalid_target_and_parameter_shape() -> None:
    valid = {
        FaultType.DISCONNECTED: (FaultTarget.PCS, ()),
        FaultType.UNAVAILABLE: (FaultTarget.PCS, ()),
        FaultType.TELEMETRY_FROZEN: (FaultTarget.TELEMETRY, ()),
        FaultType.CAPABILITY_STALE: (FaultTarget.PCS, ()),
        FaultType.CHARGE_DERATE: (FaultTarget.PCS, (("factor", 0.5),)),
        FaultType.DISCHARGE_DERATE: (FaultTarget.PCS, (("factor", 0.5),)),
        FaultType.CHARGE_PROHIBITED: (FaultTarget.BMS, ()),
        FaultType.DISCHARGE_PROHIBITED: (FaultTarget.BMS, ()),
        FaultType.CRITICAL_FAULT: (FaultTarget.BMS, ()),
        FaultType.WARNING_FAULT: (FaultTarget.BMS, ()),
        FaultType.ESTOP: (FaultTarget.PCS, ()),
        FaultType.ACK_REJECTED: (FaultTarget.PCS, ()),
        FaultType.ACK_DROPPED: (FaultTarget.COMMAND_CHANNEL, ()),
        FaultType.ACK_DELAYED: (FaultTarget.PCS, (("seconds", 0.0),)),
        FaultType.STUCK_AT_ZERO: (FaultTarget.PCS, ()),
        FaultType.STUCK_AT_PREVIOUS_POWER: (FaultTarget.PCS, ()),
        FaultType.ACTUAL_POWER_DEVIATION: (FaultTarget.PCS, (("factor", 0.5),)),
        FaultType.SOC_UNKNOWN: (FaultTarget.BMS, ()),
    }
    assert set(valid) == set(FaultType)
    for index, (fault_type, (target, parameters)) in enumerate(valid.items()):
        item = _fault(f"valid-{index}", fault_type, target, parameters=parameters)
        assert FaultSpecification.from_dict(item.to_dict()) == item
    for fault_type, (target, parameters) in valid.items():
        rejected_targets: list[FaultTarget] = []
        for candidate in FaultTarget:
            if candidate is target:
                continue
            try:
                _fault("candidate", fault_type, candidate, parameters=parameters)
            except ValueError:
                rejected_targets.append(candidate)
        assert rejected_targets
        encoded = _fault("encoded", fault_type, target, parameters=parameters).to_dict()
        encoded["target"] = rejected_targets[0].value
        with pytest.raises(ValueError):
            FaultSpecification.from_dict(encoded)
    with pytest.raises(ValueError):
        _fault("estop-bms", FaultType.ESTOP, FaultTarget.BMS)
    with pytest.raises(ValueError):
        _fault("stuck-bms", FaultType.STUCK_AT_ZERO, FaultTarget.BMS)
    with pytest.raises(ValueError):
        _fault("missing", FaultType.ACK_DELAYED, FaultTarget.PCS)
    with pytest.raises(ValueError):
        _fault("extra", FaultType.ESTOP, FaultTarget.PCS, parameters=(("factor", 0.5),))
    with pytest.raises(ValueError):
        _fault(
            "bad-factor",
            FaultType.CHARGE_DERATE,
            FaultTarget.PCS,
            parameters=(("factor", 1.1),),
        )
    with pytest.raises(ValueError):
        _fault(
            "bad-delay",
            FaultType.ACK_DELAYED,
            FaultTarget.PCS,
            parameters=(("seconds", -1.0),),
        )


def test_warning_fault_is_retained_but_critical_still_fails_closed() -> None:
    warning = _fault("warning", FaultType.WARNING_FAULT, FaultTarget.BMS)
    _, warning_step = _simulator(warning).step(
        _command(), duration=timedelta(seconds=1)
    )
    assert warning_step.actual_power_kw == 1.0
    assert warning_step.fault_events[0].severity is FaultSeverity.WARNING
    critical = _fault("critical", FaultType.CRITICAL_FAULT, FaultTarget.BMS)
    _, combined = _simulator(warning, critical).step(
        _command(), duration=timedelta(seconds=1)
    )
    assert combined.actual_power_kw == 0.0
    assert {item.severity for item in combined.fault_events} == {
        FaultSeverity.WARNING,
        FaultSeverity.CRITICAL,
    }


def test_overlapping_fault_clear_keeps_remaining_fault_independently_active() -> None:
    estop = _fault(
        "estop",
        FaultType.ESTOP,
        FaultTarget.PCS,
        clear_at=NOW + timedelta(seconds=10),
    )
    prohibited = _fault(
        "prohibited",
        FaultType.CHARGE_PROHIBITED,
        FaultTarget.BMS,
        clear_at=NOW + timedelta(seconds=20),
    )
    after_first_clear, _ = _simulator(estop, prohibited).step(
        None, duration=timedelta(seconds=10)
    )
    _, step = after_first_clear.step(
        _command(issued_at=after_first_clear.clock.now), duration=timedelta(seconds=1)
    )
    assert [item.fault_id for item in step.active_faults] == ["prohibited"]
    assert not step.bms_capability.charge_allowed
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 0.0
    assert step.actual_power_kw == 0.0


def test_step_start_fault_sampling_has_explicit_activation_and_clear_boundaries() -> (
    None
):
    starts_now = _fault("starts", FaultType.ESTOP, FaultTarget.PCS)
    _, active = _simulator(starts_now).step(_command(), duration=timedelta(seconds=1))
    assert active.actual_power_kw == 0.0
    starts_later = _fault(
        "later",
        FaultType.ESTOP,
        FaultTarget.PCS,
        activation_at=NOW + timedelta(microseconds=1),
    )
    _, not_retroactive = _simulator(starts_later).step(
        _command(), duration=timedelta(seconds=1)
    )
    assert not_retroactive.actual_power_kw == 1.0
    clears_now = _fault(
        "cleared",
        FaultType.ESTOP,
        FaultTarget.PCS,
        activation_at=NOW - timedelta(seconds=1),
        clear_at=NOW,
    )
    _, inactive = _simulator(clears_now).step(_command(), duration=timedelta(seconds=1))
    assert inactive.actual_power_kw == 1.0
    clears_later = _fault(
        "still-active",
        FaultType.ESTOP,
        FaultTarget.PCS,
        activation_at=NOW - timedelta(seconds=1),
        clear_at=NOW + timedelta(microseconds=1),
    )
    _, active_until_next_step = _simulator(clears_later).step(
        _command(), duration=timedelta(seconds=1)
    )
    assert active_until_next_step.actual_power_kw == 0.0


def test_fault_clear_requires_new_command_and_never_replays_old_command() -> None:
    estop = _fault(
        "estop", FaultType.ESTOP, FaultTarget.PCS, clear_at=NOW + timedelta(seconds=10)
    )
    harness = DeterministicDeviceScenarioHarness.start(_simulator(estop)).advance(
        _command(lifetime=timedelta(seconds=10)), duration=timedelta(seconds=10)
    )
    assert (
        harness.trace.lifecycle_book.records[0].state is CommandLifecycleState.EXPIRED
    )
    cleared = harness.advance(None, duration=timedelta(seconds=1))
    assert cleared.trace.steps[-1].command is None
    assert cleared.trace.steps[-1].actual_power_kw == 0.0
    renewed = cleared.advance(
        _command("new-command", 2, issued_at=cleared.trace.simulator.clock.now),
        duration=timedelta(seconds=1),
    )
    assert renewed.trace.steps[-1].actual_power_kw == 1.0
    assert [
        item.command.command_id for item in renewed.trace.lifecycle_book.records
    ] == ["p0-2-command-1", "new-command"]


@pytest.mark.parametrize(
    ("target", "fault_id"),
    [
        (FaultTarget.BMS, "stale-bms"),
        (FaultTarget.PCS, "stale-pcs"),
        (FaultTarget.CAPABILITY, "stale-capability"),
    ],
)
def test_capability_stale_targets_keep_legal_intersection_and_fail_closed(
    target: FaultTarget, fault_id: str
) -> None:
    _, step = _simulator(_fault(fault_id, FaultType.CAPABILITY_STALE, target)).step(
        _command(power_kw=1.0), duration=timedelta(seconds=1)
    )
    effective = merge_device_capabilities(step.bms_capability, step.pcs_capability)
    assert step.bms_capability.expires_at > step.bms_capability.valid_from
    assert step.pcs_capability.expires_at > step.pcs_capability.valid_from
    assert effective.expires_at > effective.valid_from
    stale = evaluate_freshness(
        step.raw_telemetry, effective, POLICY, evaluated_at=step.started_at
    )
    assert not stale.capability_fresh
    assert stale.capability_reason == "capability_stale"
    assert step.safety_decision is not None
    assert step.safety_decision.final_requested_battery_power_kw == 0.0
    assert step.actual_power_kw == 0.0
    assert step.ending_soc_fraction == step.starting_soc_fraction
    assert [(item.fault_id, item.target) for item in step.active_faults] == [
        (fault_id, target)
    ]


def test_capability_stale_expiry_boundary_is_strict_and_structurally_valid() -> None:
    _, step = _simulator(
        _fault("stale", FaultType.CAPABILITY_STALE, FaultTarget.BMS)
    ).step(_command(), duration=timedelta(seconds=1))
    effective = merge_device_capabilities(step.bms_capability, step.pcs_capability)
    assert effective.expires_at == step.started_at
    assert not evaluate_freshness(
        step.raw_telemetry, effective, POLICY, evaluated_at=step.started_at
    ).capability_fresh
    still_valid = merge_device_capabilities(
        replace(
            step.bms_capability,
            expires_at=step.started_at + timedelta(microseconds=1),
        ),
        step.pcs_capability,
    )
    assert still_valid.expires_at > still_valid.valid_from
    assert evaluate_freshness(
        step.raw_telemetry, still_valid, POLICY, evaluated_at=step.started_at
    ).capability_fresh


@pytest.mark.parametrize(
    ("delay", "expected_state"),
    [
        (timedelta(seconds=1), CommandLifecycleState.ACK_ACCEPTED),
        (timedelta(seconds=10), CommandLifecycleState.ACK_ACCEPTED),
        (timedelta(seconds=10, microseconds=1), CommandLifecycleState.ISSUED),
    ],
)
def test_delayed_ack_never_authorizes_current_step_lifecycle(
    delay: timedelta, expected_state: CommandLifecycleState
) -> None:
    delayed = _fault(
        "delayed",
        FaultType.ACK_DELAYED,
        FaultTarget.PCS,
        parameters=(("seconds", delay.total_seconds()),),
    )
    harness = DeterministicDeviceScenarioHarness.start(_simulator(delayed)).advance(
        _command(lifetime=timedelta(seconds=60)), duration=timedelta(seconds=10)
    )
    step = harness.trace.steps[-1]
    record = harness.trace.lifecycle_book.records[-1]
    assert not step.command_application_authorized
    assert step.actual_power_kw == 0.0
    assert step.ending_soc_fraction == step.starting_soc_fraction
    assert record.state is expected_state
    assert record.execution_started_at is None
    assert record.completion_evidence is None
    next_harness = harness.advance(None, duration=timedelta(seconds=1))
    assert next_harness.trace.steps[-1].actual_power_kw == 0.0


def test_application_authorization_rejects_mismatched_ack_identity() -> None:
    simulator = _simulator()
    command = _command()
    acknowledgement = simulator._acknowledgement(command, 1.0, ())
    assert acknowledgement is not None
    for mismatched in (
        replace(acknowledgement, command_id="different"),
        replace(acknowledgement, sequence=2),
        replace(acknowledgement, correlation_id="different"),
    ):
        assert simulator._command_applies_in_current_step(command, mismatched) == (
            False,
            "ack_mismatch",
        )


def test_step_start_fault_snapshot_controls_end_telemetry_until_next_step() -> None:
    clearing = _fault(
        "clearing-stuck",
        FaultType.STUCK_AT_ZERO,
        FaultTarget.PCS,
        clear_at=NOW + timedelta(microseconds=1),
    )
    after_first, first = _simulator(clearing).step(
        _command(), duration=timedelta(seconds=10)
    )
    assert first.command_application_authorized
    assert first.actual_power_kw == 0.0
    assert [item.fault_id for item in first.active_faults] == ["clearing-stuck"]
    assert first.actual_telemetry.alarm_codes == ("clearing-stuck",)
    _, after_clear = after_first.step(
        _command("after-clear", 2, issued_at=after_first.clock.now),
        duration=timedelta(seconds=1),
    )
    assert after_clear.actual_power_kw == 1.0
    assert after_clear.active_faults == ()
    assert after_clear.actual_telemetry.alarm_codes == ()

    activating = _fault(
        "activating-stuck",
        FaultType.STUCK_AT_ZERO,
        FaultTarget.PCS,
        activation_at=NOW + timedelta(microseconds=1),
    )
    after_inactive, inactive = _simulator(activating).step(
        _command(), duration=timedelta(seconds=10)
    )
    assert inactive.actual_power_kw == 1.0
    assert inactive.active_faults == ()
    assert inactive.actual_telemetry.alarm_codes == ()
    _, active = after_inactive.step(
        _command("after-activation", 2, issued_at=after_inactive.clock.now),
        duration=timedelta(seconds=1),
    )
    assert active.actual_power_kw == 0.0
    assert [item.fault_id for item in active.active_faults] == ["activating-stuck"]
    assert active.actual_telemetry.alarm_codes == ("activating-stuck",)


@pytest.mark.parametrize(
    "fault",
    [
        _fault("reject", FaultType.ACK_REJECTED, FaultTarget.PCS),
        _fault("drop", FaultType.ACK_DROPPED, FaultTarget.COMMAND_CHANNEL),
        _fault(
            "delay",
            FaultType.ACK_DELAYED,
            FaultTarget.PCS,
            parameters=(("seconds", 1.0),),
        ),
        _fault("critical", FaultType.CRITICAL_FAULT, FaultTarget.BMS),
        _fault("estop", FaultType.ESTOP, FaultTarget.PCS),
        _fault("stale", FaultType.CAPABILITY_STALE, FaultTarget.BMS),
        _fault("stuck", FaultType.STUCK_AT_ZERO, FaultTarget.PCS),
    ],
)
def test_failed_or_zero_actual_never_contaminates_stuck_previous_power(
    fault: FaultSpecification,
) -> None:
    after_failure, failed = _simulator(fault).step(
        _command(power_kw=1.0), duration=timedelta(seconds=1)
    )
    assert failed.actual_power_kw == 0.0
    assert after_failure.previous_actual_power_kw == 0.0
    stuck = _fault("previous", FaultType.STUCK_AT_PREVIOUS_POWER, FaultTarget.PCS)
    state = replace(
        after_failure,
        configuration=replace(
            after_failure.configuration, fault_schedule=FaultSchedule((stuck,))
        ),
    )
    _, next_step = state.step(
        _command("next", 2, issued_at=state.clock.now), duration=timedelta(seconds=1)
    )
    assert next_step.actual_power_kw == 0.0
    assert next_step.ending_soc_fraction == state.soc_fraction


def test_every_legal_fault_target_changes_real_step_evidence() -> None:
    for index, (fault_type, compatibility) in enumerate(_FAULT_COMPATIBILITY.items()):
        parameters = (
            (("factor", 0.5),)
            if "factor" in compatibility.required_parameters
            else (("seconds", 1.0),)
            if "seconds" in compatibility.required_parameters
            else ()
        )
        power_kw = (
            -3.0
            if fault_type
            in {FaultType.DISCHARGE_DERATE, FaultType.DISCHARGE_PROHIBITED}
            else 3.0
        )
        baseline = _simulator().step(
            _command("baseline", index + 1, power_kw), duration=timedelta(seconds=1)
        )[1]
        baseline_facts = (
            baseline.bms_capability,
            baseline.pcs_capability,
            baseline.runtime_health,
            baseline.raw_telemetry,
            baseline.safety_decision,
            baseline.acknowledgement,
            baseline.command_application_authorized,
            baseline.actual_power_kw,
            baseline.actual_telemetry,
            baseline.fault_events,
        )
        for target in compatibility.targets:
            fault = _fault(
                f"audit-{fault_type.value}-{target.value}",
                fault_type,
                target,
                parameters=parameters,
            )
            step = _simulator(fault).step(
                _command("audit", index + 1, power_kw), duration=timedelta(seconds=1)
            )[1]
            actual_facts = (
                step.bms_capability,
                step.pcs_capability,
                step.runtime_health,
                step.raw_telemetry,
                step.safety_decision,
                step.acknowledgement,
                step.command_application_authorized,
                step.actual_power_kw,
                step.actual_telemetry,
                step.fault_events,
            )
            assert actual_facts != baseline_facts


def test_absent_new_command_never_continues_previous_actual_power() -> None:
    moving, first = _simulator().step(
        _command(power_kw=1.0), duration=timedelta(seconds=1)
    )
    assert first.actual_power_kw == 1.0
    _, no_replay = moving.step(None, duration=timedelta(seconds=1))
    assert no_replay.command is None
    assert no_replay.actual_power_kw == 0.0


def test_fault_schedule_contract_is_immutable_sorted_and_strictly_serialized() -> None:
    second = _fault("b", FaultType.UNAVAILABLE, FaultTarget.PCS)
    first = _fault("a", FaultType.SOC_UNKNOWN, FaultTarget.BMS)
    schedule = FaultSchedule((second, first))
    assert [item.fault_id for item in schedule.specifications] == ["a", "b"]
    with pytest.raises(FrozenInstanceError):
        first.fault_id = "changed"  # type: ignore[misc]
    encoded = first.to_dict()
    assert FaultSpecification.from_dict(encoded) == first
    with pytest.raises(ValueError):
        FaultSpecification.from_dict({**encoded, "unknown": True})
    with pytest.raises(ValueError):
        FaultSpecification.from_dict({**encoded, "schema_version": "wrong/v1"})
    with pytest.raises(ValueError, match="duplicate"):
        FaultSchedule((first, replace(first, description="duplicate")))
    with pytest.raises(ValueError, match="conflicting"):
        FaultSchedule((first, replace(first, fault_id="other")))


@pytest.mark.parametrize("value", [True, nan, inf, -inf])
def test_fault_and_configuration_reject_bool_and_nonfinite_inputs(
    value: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        FaultSpecification(
            "bad",
            FaultType.CHARGE_DERATE,
            FaultTarget.PCS,
            NOW,
            None,
            (("factor", value),),  # type: ignore[arg-type]
            "invalid test fault",
        )
    with pytest.raises((TypeError, ValueError)):
        replace(_configuration(), capacity_kwh=value)  # type: ignore[arg-type]


def test_virtual_time_rejects_zero_negative_and_naive_progression() -> None:
    with pytest.raises(ValueError):
        VirtualClock(NOW).advance(timedelta())
    with pytest.raises(ValueError):
        VirtualClock(NOW).advance(-timedelta(seconds=1))
    with pytest.raises(ValueError):
        VirtualClock(NOW.replace(tzinfo=None))


def test_same_inputs_are_deterministic_without_shared_state() -> None:
    left = DeterministicDeviceScenarioHarness.start(_simulator()).advance(
        _command(), duration=timedelta(seconds=10)
    )
    right = DeterministicDeviceScenarioHarness.start(_simulator()).advance(
        _command(), duration=timedelta(seconds=10)
    )
    assert left.trace.steps == right.trace.steps
    assert left.trace.simulator is not right.trace.simulator
    assert left.trace.lifecycle_book is not right.trace.lifecycle_book


def test_transport_neutral_module_has_no_network_protocol_or_thread_dependency() -> (
    None
):
    import ast
    from pathlib import Path

    root = Path(__file__).parents[3] / "edge_runtime" / "device_simulator"
    imports = {
        node.module or ""
        for path in root.glob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = {
        "socket",
        "serial",
        "can",
        "modbus",
        "mqtt",
        "requests",
        "threading",
        "asyncio",
        "ems_strategy",
        "optimization",
        "simulator",
    }
    assert not any(item.split(".")[0] in forbidden for item in imports)
