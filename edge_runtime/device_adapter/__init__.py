"""P0.4 transport-neutral device adapter contract and deterministic test double."""

from edge_runtime.device_adapter.adapter import (
    ResidentialDeviceAdapterBoundary,
    ScriptedResidentialDeviceAdapter,
    ScriptedTransmissionOutcome,
)
from edge_runtime.device_adapter.contracts import (
    AdapterFactAvailability,
    AdapterFailureCode,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterFailure,
    DeviceAdapterStepEvidence,
    DeviceObservation,
    DeviceTransmissionEvidence,
    DeviceTransmissionRequest,
    TransmissionStatus,
)
from edge_runtime.device_adapter.integration import P03DeviceAdapterIntegration

__all__ = [
    "AdapterFactAvailability",
    "AdapterFailureCode",
    "DeviceAckObservation",
    "DeviceActualTelemetryObservation",
    "DeviceAdapterFailure",
    "DeviceAdapterStepEvidence",
    "DeviceObservation",
    "DeviceTransmissionEvidence",
    "DeviceTransmissionRequest",
    "P03DeviceAdapterIntegration",
    "ResidentialDeviceAdapterBoundary",
    "ScriptedResidentialDeviceAdapter",
    "ScriptedTransmissionOutcome",
    "TransmissionStatus",
]
