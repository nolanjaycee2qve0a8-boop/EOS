"""P0.4 transport-neutral adapter boundary and authority regressions."""

import copy
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from edge_runtime import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    OperatingMode,
    PowerCommand,
    TimingPolicy,
    evaluate_recovery_readiness,
)
from edge_runtime.controlled_runtime import ControlledEdgeRuntime
from edge_runtime.device_adapter import (
    AdapterFactAvailability,
    AdapterFailureCode,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterFailure,
    DeviceAdapterStepEvidence,
    DeviceObservation,
    DeviceTransmissionRequest,
    P03DeviceAdapterIntegration,
    ScriptedResidentialDeviceAdapter,
    ScriptedTransmissionOutcome,
    TransmissionStatus,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceSimulator,
    DeviceSimulatorConfiguration,
    DeviceSimulatorStep,
    FaultSchedule,
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


def _runtime() -> ControlledEdgeRuntime:
    simulator = DeterministicDeviceSimulator.start(
        DeviceSimulatorConfiguration(
            10, 0.5, 0.2, 1, 3, 3, 0.95, 0.95, POLICY, FaultSchedule(())
        ),
        at=VirtualClock(NOW),
    )
    return ControlledEdgeRuntime.start(simulator).tick(
        None, duration=timedelta(seconds=1)
    )


def _command(
    runtime: ControlledEdgeRuntime, *, power: float = 1.0, sequence: int = 1
) -> PowerCommand:
    now = runtime.simulator.clock.now
    return PowerCommand(
        "edge-power-command/v1",
        f"p04-{sequence}",
        sequence,
        "p04",
        now,
        now,
        now + timedelta(minutes=1),
        power,
        OperatingMode.SAFE_IDLE if power == 0 else OperatingMode.NORMAL,
        "test",
        "test",
        f"p04-{sequence}",
    )


def _facts(
    *, power: float = 1.0
) -> tuple[
    ControlledEdgeRuntime,
    PowerCommand,
    DeviceSimulatorStep,
    DeviceObservation,
    DeviceTransmissionRequest,
]:
    runtime = _runtime()
    command = _command(runtime, power=power)
    _, step = runtime.simulator.prepare_step().execute(
        command, duration=timedelta(seconds=1)
    )
    assert step.safety_decision is not None
    observation = DeviceObservation(
        NOW + timedelta(seconds=1),
        AdapterFactAvailability.AVAILABLE,
        step.raw_telemetry,
        step.bms_capability,
        step.pcs_capability,
        step.runtime_health,
        None,
    )
    request = P03DeviceAdapterIntegration.transmission_request(
        command, command, step.safety_decision
    )
    return runtime, command, step, observation, request


def _ack(
    command: PowerCommand,
    *,
    status: AcknowledgementStatus = AcknowledgementStatus.ACCEPTED,
    received_at: datetime = NOW + timedelta(seconds=2),
    command_id: str | None = None,
    sequence: int | None = None,
    correlation_id: str | None = None,
) -> CommandAcknowledgement:
    return CommandAcknowledgement(
        command_id or command.command_id,
        command.sequence if sequence is None else sequence,
        status,
        received_at,
        received_at,
        command.requested_battery_power_kw
        if status is AcknowledgementStatus.ACCEPTED
        else None,
        None if status is AcknowledgementStatus.ACCEPTED else "rejected",
        None,
        command.correlation_id if correlation_id is None else correlation_id,
    )


def _missing_ack() -> DeviceAckObservation:
    return DeviceAckObservation(
        NOW + timedelta(seconds=2), AdapterFactAvailability.MISSING, None, None
    )


def test_observation_freshness_is_explicit_and_p01_owned() -> None:
    runtime, _, _, observation, _ = _facts()
    ready = evaluate_recovery_readiness(
        P03DeviceAdapterIntegration.readiness_input(
            observation,
            timing_policy=POLICY,
            lifecycle_book=runtime.lifecycle_book,
            evaluated_at=NOW + timedelta(seconds=1),
            emergency_stop_active=False,
        )
    )
    assert ready.ready_for_new_command
    assert observation.telemetry is not None
    stale = DeviceObservation(
        observation.observed_at,
        AdapterFactAvailability.AVAILABLE,
        replace(observation.telemetry, observed_at=NOW - timedelta(minutes=1)),
        observation.bms_capability,
        observation.pcs_capability,
        observation.runtime_health,
        None,
    )
    stale_ready = evaluate_recovery_readiness(
        P03DeviceAdapterIntegration.readiness_input(
            stale,
            timing_policy=POLICY,
            lifecycle_book=runtime.lifecycle_book,
            evaluated_at=NOW + timedelta(seconds=1),
            emergency_stop_active=False,
        )
    )
    assert not stale_ready.telemetry_fresh
    missing = DeviceObservation(
        NOW, AdapterFactAvailability.MISSING, None, None, None, None, None
    )
    with pytest.raises(ValueError, match="cannot form readiness"):
        P03DeviceAdapterIntegration.readiness_input(
            missing,
            timing_policy=POLICY,
            lifecycle_book=runtime.lifecycle_book,
            evaluated_at=NOW,
            emergency_stop_active=False,
        )


@pytest.mark.parametrize("field_name", ["pcs_connected", "bms_connected"])
def test_disconnected_device_is_explicit_p01_health_evidence(field_name: str) -> None:
    runtime, _, _, observation, _ = _facts()
    assert observation.runtime_health is not None
    health = (
        replace(observation.runtime_health, pcs_connected=False)
        if field_name == "pcs_connected"
        else replace(observation.runtime_health, bms_connected=False)
    )
    disconnected = DeviceObservation(
        observation.observed_at,
        AdapterFactAvailability.AVAILABLE,
        observation.telemetry,
        observation.bms_capability,
        observation.pcs_capability,
        health,
        None,
    )
    readiness = evaluate_recovery_readiness(
        P03DeviceAdapterIntegration.readiness_input(
            disconnected,
            timing_policy=POLICY,
            lifecycle_book=runtime.lifecycle_book,
            evaluated_at=NOW + timedelta(seconds=1),
            emergency_stop_active=False,
        )
    )
    assert "runtime_link_not_healthy" in readiness.reason_codes


def test_transmission_is_exactly_once_and_safe_zero_is_explicit() -> None:
    _, command, _, observation, request = _facts(power=0)
    assert request.safety_final_power_kw == 0.0
    assert request.operating_mode is OperatingMode.SAFE_IDLE
    adapter = ScriptedResidentialDeviceAdapter(
        observations=(observation,),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(
                NOW + timedelta(seconds=2), TransmissionStatus.TRANSMITTED
            ),
        ),
        acknowledgements=(_missing_ack(),),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                NOW + timedelta(seconds=2), AdapterFactAvailability.MISSING, None, None
            ),
        ),
    )
    evidence = adapter.transmit(request)
    assert evidence.command_id == command.command_id
    assert evidence.safety_final_power_kw == 0.0
    assert adapter.transmission_attempt_count == 1
    with pytest.raises(ValueError, match="already consumed"):
        adapter.transmit(request)
    assert adapter.transmission_attempt_count == 1


def test_failed_attempt_neither_retries_nor_retains_replay_authority() -> None:
    _, _, _, observation, request = _facts()
    failure = DeviceAdapterFailure(
        AdapterFailureCode.TRANSMISSION_FAILED, NOW, "scripted failure"
    )
    adapter = ScriptedResidentialDeviceAdapter(
        observations=(observation,),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(NOW, TransmissionStatus.FAILED, failure),
        ),
        acknowledgements=(_missing_ack(),),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                NOW, AdapterFactAvailability.MISSING, None, None
            ),
        ),
    )
    assert adapter.transmit(request).status is TransmissionStatus.FAILED
    assert adapter.transmission_attempt_count == 1
    recreated = ScriptedResidentialDeviceAdapter(
        observations=(observation,),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(NOW, TransmissionStatus.TRANSMITTED),
        ),
        acknowledgements=(_missing_ack(),),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                NOW, AdapterFactAvailability.MISSING, None, None
            ),
        ),
    )
    with pytest.raises(ValueError, match="already consumed"):
        recreated.transmit(request)
    assert recreated.transmission_attempt_count == 0


def test_adapter_never_accepts_power_command_or_hydrates_request_authority() -> None:
    _, command, _, observation, request = _facts()
    adapter = ScriptedResidentialDeviceAdapter(
        observations=(observation,),
        transmission_outcomes=(),
        acknowledgements=(),
        actual_telemetry=(),
    )
    with pytest.raises(TypeError, match="DeviceTransmissionRequest"):
        adapter.transmit(command)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(request)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(request)
    assert not hasattr(type(request), "from_dict")


@pytest.mark.parametrize(
    "status", [AcknowledgementStatus.ACCEPTED, AcknowledgementStatus.REJECTED]
)
def test_ack_is_separate_from_actual_and_is_exactly_correlated(
    status: AcknowledgementStatus,
) -> None:
    _, command, step, _observation, request = _facts()
    ack = DeviceAckObservation(
        NOW + timedelta(seconds=2),
        AdapterFactAvailability.AVAILABLE,
        _ack(command, status=status),
        None,
    )
    actual = DeviceActualTelemetryObservation(
        NOW + timedelta(seconds=3),
        AdapterFactAvailability.AVAILABLE,
        step.actual_telemetry,
        None,
    )
    assert (
        P03DeviceAdapterIntegration.correlated_acknowledgement(request, ack)
        is ack.acknowledgement
    )
    assert P03DeviceAdapterIntegration.actual_telemetry(actual) is step.actual_telemetry
    assert ack.acknowledgement is not None
    assert ack.acknowledgement.acknowledgement_status is status
    assert actual.telemetry is not None


def test_ack_missing_actual_before_ack_and_ack_without_actual_are_representable() -> (
    None
):
    _, command, step, _, request = _facts()
    actual_first = DeviceActualTelemetryObservation(
        NOW + timedelta(seconds=2),
        AdapterFactAvailability.AVAILABLE,
        step.actual_telemetry,
        None,
    )
    assert (
        P03DeviceAdapterIntegration.actual_telemetry(actual_first)
        is step.actual_telemetry
    )
    assert (
        P03DeviceAdapterIntegration.correlated_acknowledgement(request, _missing_ack())
        is None
    )
    late_ack = DeviceAckObservation(
        NOW + timedelta(minutes=1),
        AdapterFactAvailability.AVAILABLE,
        _ack(command, received_at=NOW + timedelta(minutes=1)),
        None,
    )
    assert (
        P03DeviceAdapterIntegration.correlated_acknowledgement(request, late_ack)
        is late_ack.acknowledgement
    )


def test_mismatched_ack_is_blocked_and_mutation_proves_correlation_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, command, _, _, request = _facts()
    forged = DeviceAckObservation(
        NOW + timedelta(seconds=2),
        AdapterFactAvailability.AVAILABLE,
        _ack(command, command_id="forged", sequence=99, correlation_id="forged"),
        None,
    )
    with pytest.raises(ValueError, match="does not correlate"):
        P03DeviceAdapterIntegration.correlated_acknowledgement(request, forged)
    monkeypatch.setattr(
        P03DeviceAdapterIntegration,
        "correlated_acknowledgement",
        staticmethod(lambda _request, observation: observation.acknowledgement),
    )
    assert (
        P03DeviceAdapterIntegration.correlated_acknowledgement(request, forged)
        is forged.acknowledgement
    )


@pytest.mark.parametrize("actual_power", [1.0, 0.0, -1.0, 2.0, None])
def test_actual_power_is_physical_evidence_without_command_provenance(
    actual_power: float | None,
) -> None:
    _, _, step, _, _ = _facts()
    telemetry = replace(step.actual_telemetry, actual_battery_power_kw=actual_power)
    actual = DeviceActualTelemetryObservation(
        NOW, AdapterFactAvailability.AVAILABLE, telemetry, None
    )
    assert P03DeviceAdapterIntegration.actual_telemetry(actual) is telemetry


def test_evidence_only_and_tick_none_stay_outside_adapter_authority() -> None:
    runtime, _, step, observation, _ = _facts()
    evidence = DeviceAdapterStepEvidence(
        observation,
        None,
        _missing_ack(),
        DeviceActualTelemetryObservation(
            NOW, AdapterFactAvailability.AVAILABLE, step.actual_telemetry, None
        ),
    )
    restored = DeviceAdapterStepEvidence.from_dict(evidence.to_dict())
    assert restored.to_dict() == evidence.to_dict()
    assert not hasattr(type(restored), "transmit")
    after = runtime.tick(None, duration=timedelta(seconds=1))
    assert after.trace.steps[-1].admitted_command is None
