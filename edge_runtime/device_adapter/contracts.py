"""P0.4 transport-neutral adapter facts and bounded transmission authority."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, NoReturn, SupportsIndex

from edge_runtime.contracts import (
    CommandAcknowledgement,
    DeviceCapability,
    DeviceCapabilitySource,
    OperatingMode,
    PowerCommand,
    RuntimeHealth,
    SafetyDecision,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.lifecycle import CommandLifecycleBook
from edge_runtime.safety import RecoveryReadinessInput
from edge_runtime.validation import (
    SerializableContract,
    require_aware_datetime,
    require_non_empty_string,
    require_non_negative_int,
    require_number,
)


class AdapterFactAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class AdapterFailureCode(StrEnum):
    CHANNEL_UNAVAILABLE = "channel_unavailable"
    TRANSMISSION_FAILED = "transmission_failed"
    ACK_UNAVAILABLE = "ack_unavailable"
    OBSERVATION_UNAVAILABLE = "observation_unavailable"


class TransmissionStatus(StrEnum):
    TRANSMITTED = "transmitted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DeviceAdapterFailure(SerializableContract):
    """Sanitized boundary fact; protocol exceptions never cross this contract."""

    code: AdapterFailureCode
    observed_at: datetime
    detail: str
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-failure/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.code, AdapterFailureCode):
            raise TypeError("code must be AdapterFailureCode")
        object.__setattr__(
            self, "observed_at", require_aware_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self, "detail", require_non_empty_string(self.detail, "detail")
        )


@dataclass(frozen=True, slots=True)
class DeviceObservation(SerializableContract):
    """Complete P0.1-compatible facts or explicit missing/unavailable evidence.

    Capture times remain facts.  P0.1, not this adapter, determines freshness.
    """

    observed_at: datetime
    availability: AdapterFactAvailability
    telemetry: TelemetrySnapshot | None
    bms_capability: DeviceCapability | None
    pcs_capability: DeviceCapability | None
    runtime_health: RuntimeHealth | None
    failure: DeviceAdapterFailure | None
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-observation/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_aware_datetime(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, AdapterFactAvailability):
            raise TypeError("availability must be AdapterFactAvailability")
        if self.telemetry is not None and not isinstance(
            self.telemetry, TelemetrySnapshot
        ):
            raise TypeError("telemetry must be TelemetrySnapshot or None")
        if self.bms_capability is not None and (
            not isinstance(self.bms_capability, DeviceCapability)
            or self.bms_capability.source is not DeviceCapabilitySource.BMS
        ):
            raise TypeError("bms_capability must be BMS DeviceCapability or None")
        if self.pcs_capability is not None and (
            not isinstance(self.pcs_capability, DeviceCapability)
            or self.pcs_capability.source is not DeviceCapabilitySource.PCS
        ):
            raise TypeError("pcs_capability must be PCS DeviceCapability or None")
        if self.runtime_health is not None and not isinstance(
            self.runtime_health, RuntimeHealth
        ):
            raise TypeError("runtime_health must be RuntimeHealth or None")
        if self.failure is not None and not isinstance(
            self.failure, DeviceAdapterFailure
        ):
            raise TypeError("failure must be DeviceAdapterFailure or None")
        complete = all(
            item is not None
            for item in (
                self.telemetry,
                self.bms_capability,
                self.pcs_capability,
                self.runtime_health,
            )
        )
        if self.availability is AdapterFactAvailability.AVAILABLE and (
            not complete or self.failure is not None
        ):
            raise ValueError(
                "available observation requires complete facts and no failure"
            )
        if self.availability is not AdapterFactAvailability.AVAILABLE and complete:
            raise ValueError("non-available observation cannot claim complete facts")
        if (
            self.availability is AdapterFactAvailability.UNAVAILABLE
            and self.failure is None
        ):
            raise ValueError("unavailable observation requires failure evidence")
        if (
            self.availability is not AdapterFactAvailability.UNAVAILABLE
            and self.failure is not None
        ):
            raise ValueError("only unavailable observation includes failure evidence")

    def to_recovery_readiness_input(
        self,
        *,
        timing_policy: TimingPolicy,
        lifecycle_book: CommandLifecycleBook,
        evaluated_at: datetime,
        emergency_stop_active: bool,
    ) -> RecoveryReadinessInput:
        """Map facts to P0.1 readiness input without applying freshness policy."""
        if self.availability is not AdapterFactAvailability.AVAILABLE:
            raise ValueError("unavailable observation cannot form readiness input")
        assert (
            self.telemetry
            and self.bms_capability
            and self.pcs_capability
            and self.runtime_health
        )
        return RecoveryReadinessInput(
            self.telemetry,
            self.bms_capability,
            self.pcs_capability,
            self.runtime_health,
            timing_policy,
            lifecycle_book,
            evaluated_at,
            emergency_stop_active,
        )


@dataclass(frozen=True, slots=True, init=False)
class DeviceTransmissionRequest:
    """One-shot non-serializable carrier derived from current P0.3 authority only."""

    command_id: str
    sequence: int
    provenance_id: str
    correlation_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    operating_mode: OperatingMode
    safety_final_power_kw: float
    safety_evaluated_at: datetime
    _used: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("DeviceTransmissionRequest is created only from P0.3 authority")

    @classmethod
    def from_authorized_p03(
        cls,
        caller_command: PowerCommand,
        admitted_command: PowerCommand,
        safety_decision: SafetyDecision,
    ) -> "DeviceTransmissionRequest":
        if not isinstance(caller_command, PowerCommand) or not isinstance(
            admitted_command, PowerCommand
        ):
            raise TypeError("caller and admitted command must be PowerCommand")
        if caller_command is not admitted_command:
            raise ValueError("adapter request requires current caller command identity")
        if not isinstance(safety_decision, SafetyDecision):
            raise TypeError("safety_decision must be SafetyDecision")
        if safety_decision.source_command is not admitted_command:
            raise ValueError("safety decision must retain admitted command identity")
        issued_at = require_aware_datetime(admitted_command.issued_at, "issued_at")
        not_before = require_aware_datetime(admitted_command.not_before, "not_before")
        expires_at = require_aware_datetime(admitted_command.expires_at, "expires_at")
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "command_id": require_non_empty_string(
                admitted_command.command_id, "command_id"
            ),
            "sequence": require_non_negative_int(admitted_command.sequence, "sequence"),
            "provenance_id": require_non_empty_string(
                admitted_command.provenance_id, "provenance_id"
            ),
            "correlation_id": require_non_empty_string(
                admitted_command.correlation_id, "correlation_id"
            ),
            "issued_at": issued_at,
            "not_before": not_before,
            "expires_at": expires_at,
            "operating_mode": safety_decision.final_operating_mode,
            "safety_final_power_kw": require_number(
                safety_decision.final_requested_battery_power_kw,
                "safety_final_power_kw",
            ),
            "safety_evaluated_at": require_aware_datetime(
                safety_decision.evaluated_at, "safety_evaluated_at"
            ),
            "_used": False,
        }
        if not isinstance(values["operating_mode"], OperatingMode):
            raise TypeError("operating_mode must be OperatingMode")
        if expires_at <= issued_at or not_before > expires_at:
            raise ValueError("invalid command timing evidence")
        if (
            values["safety_final_power_kw"] == 0
            and values["operating_mode"] is not OperatingMode.SAFE_IDLE
        ):
            raise ValueError("zero safety final power requires safe_idle")
        if (
            values["safety_final_power_kw"] != 0
            and values["operating_mode"] is not OperatingMode.NORMAL
        ):
            raise ValueError("non-zero safety final power requires normal")
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        return instance

    def _consume_once(self) -> None:
        if self._used:
            raise ValueError("DeviceTransmissionRequest is already consumed")
        object.__setattr__(self, "_used", True)

    def __copy__(self) -> NoReturn:
        raise TypeError("DeviceTransmissionRequest cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("DeviceTransmissionRequest cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("DeviceTransmissionRequest cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("DeviceTransmissionRequest cannot be serialized")


@dataclass(frozen=True, slots=True)
class DeviceTransmissionEvidence(SerializableContract):
    """Audit-only outcome of exactly one request attempt."""

    attempted_at: datetime
    command_id: str
    sequence: int
    provenance_id: str
    correlation_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    operating_mode: OperatingMode
    safety_final_power_kw: float
    status: TransmissionStatus
    failure: DeviceAdapterFailure | None
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-transmission-evidence/v1"

    def __post_init__(self) -> None:
        for name in ("attempted_at", "issued_at", "not_before", "expires_at"):
            object.__setattr__(
                self, name, require_aware_datetime(getattr(self, name), name)
            )
        for name in ("command_id", "provenance_id", "correlation_id"):
            object.__setattr__(
                self, name, require_non_empty_string(getattr(self, name), name)
            )
        object.__setattr__(
            self, "sequence", require_non_negative_int(self.sequence, "sequence")
        )
        object.__setattr__(
            self,
            "safety_final_power_kw",
            require_number(self.safety_final_power_kw, "safety_final_power_kw"),
        )
        if not isinstance(self.operating_mode, OperatingMode) or not isinstance(
            self.status, TransmissionStatus
        ):
            raise TypeError("operating_mode/status has invalid type")
        if self.failure is not None and not isinstance(
            self.failure, DeviceAdapterFailure
        ):
            raise TypeError("failure must be DeviceAdapterFailure or None")
        if (self.status is TransmissionStatus.TRANSMITTED) != (self.failure is None):
            raise ValueError("transmission status/failure mismatch")
        if (
            self.safety_final_power_kw == 0
            and self.operating_mode is not OperatingMode.SAFE_IDLE
        ):
            raise ValueError("zero safety final power requires safe_idle")
        if (
            self.safety_final_power_kw != 0
            and self.operating_mode is not OperatingMode.NORMAL
        ):
            raise ValueError("non-zero safety final power requires normal")

    @classmethod
    def from_request(
        cls,
        request: DeviceTransmissionRequest,
        *,
        attempted_at: datetime,
        status: TransmissionStatus,
        failure: DeviceAdapterFailure | None,
    ) -> "DeviceTransmissionEvidence":
        if not isinstance(request, DeviceTransmissionRequest):
            raise TypeError("request must be DeviceTransmissionRequest")
        return cls(
            attempted_at,
            request.command_id,
            request.sequence,
            request.provenance_id,
            request.correlation_id,
            request.issued_at,
            request.not_before,
            request.expires_at,
            request.operating_mode,
            request.safety_final_power_kw,
            status,
            failure,
        )


@dataclass(frozen=True, slots=True)
class DeviceAckObservation(SerializableContract):
    """Separate ACK fact; it is never actual power evidence."""

    observed_at: datetime
    availability: AdapterFactAvailability
    acknowledgement: CommandAcknowledgement | None
    failure: DeviceAdapterFailure | None
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-ack-observation/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_aware_datetime(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, AdapterFactAvailability):
            raise TypeError("availability must be AdapterFactAvailability")
        if self.acknowledgement is not None and not isinstance(
            self.acknowledgement, CommandAcknowledgement
        ):
            raise TypeError("acknowledgement must be CommandAcknowledgement or None")
        if self.failure is not None and not isinstance(
            self.failure, DeviceAdapterFailure
        ):
            raise TypeError("failure must be DeviceAdapterFailure or None")
        if (self.availability is AdapterFactAvailability.AVAILABLE) != (
            self.acknowledgement is not None
        ):
            raise ValueError("ACK availability/evidence mismatch")
        if (self.availability is AdapterFactAvailability.UNAVAILABLE) != (
            self.failure is not None
        ):
            raise ValueError("ACK unavailable/failure mismatch")


@dataclass(frozen=True, slots=True)
class DeviceActualTelemetryObservation(SerializableContract):
    """Physical telemetry has no invented command correlation."""

    observed_at: datetime
    availability: AdapterFactAvailability
    telemetry: TelemetrySnapshot | None
    failure: DeviceAdapterFailure | None
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-actual-observation/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_aware_datetime(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, AdapterFactAvailability):
            raise TypeError("availability must be AdapterFactAvailability")
        if self.telemetry is not None and not isinstance(
            self.telemetry, TelemetrySnapshot
        ):
            raise TypeError("telemetry must be TelemetrySnapshot or None")
        if self.failure is not None and not isinstance(
            self.failure, DeviceAdapterFailure
        ):
            raise TypeError("failure must be DeviceAdapterFailure or None")
        if (self.availability is AdapterFactAvailability.AVAILABLE) != (
            self.telemetry is not None
        ):
            raise ValueError("actual availability/evidence mismatch")
        if (self.availability is AdapterFactAvailability.UNAVAILABLE) != (
            self.failure is not None
        ):
            raise ValueError("actual unavailable/failure mismatch")


@dataclass(frozen=True, slots=True)
class DeviceAdapterStepEvidence(SerializableContract):
    """Serializable audit aggregate; it cannot hydrate adapter execution authority."""

    observation: DeviceObservation
    transmission: DeviceTransmissionEvidence | None
    acknowledgement: DeviceAckObservation
    actual_telemetry: DeviceActualTelemetryObservation
    SCHEMA_VERSION: ClassVar[str] = "edge-device-adapter-step-evidence/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.observation, DeviceObservation):
            raise TypeError("observation must be DeviceObservation")
        if self.transmission is not None and not isinstance(
            self.transmission, DeviceTransmissionEvidence
        ):
            raise TypeError("transmission must be DeviceTransmissionEvidence or None")
        if not isinstance(self.acknowledgement, DeviceAckObservation):
            raise TypeError("acknowledgement must be DeviceAckObservation")
        if not isinstance(self.actual_telemetry, DeviceActualTelemetryObservation):
            raise TypeError("actual_telemetry must be DeviceActualTelemetryObservation")
