"""Narrow fact-only bridge for a future P0.3/device-adapter composition."""

from datetime import datetime

from edge_runtime.contracts import (
    CommandAcknowledgement,
    PowerCommand,
    SafetyDecision,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.device_adapter.contracts import (
    AdapterFactAvailability,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceObservation,
    DeviceTransmissionRequest,
)
from edge_runtime.lifecycle import CommandLifecycleBook
from edge_runtime.safety import RecoveryReadinessInput


class P03DeviceAdapterIntegration:
    """Maps facts only; it never ticks P0.3, sends I/O or changes lifecycle."""

    @staticmethod
    def readiness_input(
        observation: DeviceObservation,
        *,
        timing_policy: TimingPolicy,
        lifecycle_book: CommandLifecycleBook,
        evaluated_at: datetime,
        emergency_stop_active: bool,
    ) -> RecoveryReadinessInput:
        if not isinstance(observation, DeviceObservation):
            raise TypeError("observation must be DeviceObservation")
        return observation.to_recovery_readiness_input(
            timing_policy=timing_policy,
            lifecycle_book=lifecycle_book,
            evaluated_at=evaluated_at,
            emergency_stop_active=emergency_stop_active,
        )

    @staticmethod
    def transmission_request(
        caller_command: PowerCommand,
        admitted_command: PowerCommand,
        safety_decision: SafetyDecision,
    ) -> DeviceTransmissionRequest:
        return DeviceTransmissionRequest.from_authorized_p03(
            caller_command, admitted_command, safety_decision
        )

    @staticmethod
    def correlated_acknowledgement(
        request: DeviceTransmissionRequest,
        observation: DeviceAckObservation,
    ) -> CommandAcknowledgement | None:
        if not isinstance(request, DeviceTransmissionRequest) or not isinstance(
            observation, DeviceAckObservation
        ):
            raise TypeError("request and observation have invalid type")
        if observation.availability is not AdapterFactAvailability.AVAILABLE:
            return None
        assert observation.acknowledgement is not None
        acknowledgement = observation.acknowledgement
        if (
            acknowledgement.command_id,
            acknowledgement.sequence,
            acknowledgement.correlation_id,
        ) != (
            request.command_id,
            request.sequence,
            request.correlation_id,
        ):
            raise ValueError("ACK does not correlate to transmission request")
        return acknowledgement

    @staticmethod
    def actual_telemetry(
        observation: DeviceActualTelemetryObservation,
    ) -> TelemetrySnapshot | None:
        if not isinstance(observation, DeviceActualTelemetryObservation):
            raise TypeError("observation must be DeviceActualTelemetryObservation")
        return (
            observation.telemetry
            if observation.availability is AdapterFactAvailability.AVAILABLE
            else None
        )
