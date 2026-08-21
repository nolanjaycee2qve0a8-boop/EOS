"""Immutable, serializable, transport-neutral Edge Runtime contracts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, StrEnum
from typing import ClassVar

from edge_runtime.validation import (
    SerializableContract,
    parse_utc_datetime,
    require_aware_datetime,
    require_exact_fields,
    require_fraction,
    require_non_empty_string,
    require_non_negative_int,
    require_non_negative_number,
    require_number,
    require_optional_aware_datetime,
    require_positive_timedelta,
    utc_isoformat,
)


class OperatingMode(StrEnum):
    """Semantic active-power mode, independent of a wire protocol."""

    NORMAL = "normal"
    SAFE_IDLE = "safe_idle"


class AcknowledgementStatus(StrEnum):
    """A device response, never proof of actual executed power."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"
    OUT_OF_ORDER = "out_of_order"
    UNSUPPORTED = "unsupported"
    SAFETY_BLOCKED = "safety_blocked"


class TelemetryQualityStatus(StrEnum):
    """Quality of a validly parsed snapshot; invalid external data is rejected."""

    VALID = "valid"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class DeviceCapabilitySource(StrEnum):
    """Authority that supplied a capability assertion."""

    BMS = "bms"
    PCS = "pcs"


class FaultSeverity(StrEnum):
    """Severity is an explicit fact, not a safety-standard certification."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FaultSource(StrEnum):
    """Transport-neutral fault origin categories."""

    COMMUNICATION = "communication"
    DATA_QUALITY = "data_quality"
    PCS = "pcs"
    BMS = "bms"
    EDGE_RUNTIME = "edge_runtime"
    CONFIGURATION = "configuration"


class RuntimeState(StrEnum):
    """Software Runtime state; it does not describe hardware safety state."""

    STARTING = "starting"
    WAITING_FOR_FRESH_TELEMETRY = "waiting_for_fresh_telemetry"
    READY = "ready"
    ACTIVE = "active"
    DEGRADED = "degraded"
    SAFE_IDLE = "safe_idle"
    FAULTED = "faulted"
    SHUTTING_DOWN = "shutting_down"


class SafetyPrecedence(StrEnum):
    """Ordered authorities; lower entries may never override higher entries."""

    HARDWARE_PROTECTION = "hardware_protection"
    BMS = "bms"
    PCS = "pcs"
    EDGE_RUNTIME = "edge_runtime"
    USER_SAFETY = "user_safety"
    EMS_PLAN = "ems_plan"
    ECONOMIC_OPPORTUNITY = "economic_opportunity"


class SafetyOutcome(StrEnum):
    """Software decision about a requested command, not actual execution."""

    ALLOWED = "allowed"
    CLAMPED = "clamped"
    BLOCKED = "blocked"
    FORCED_IDLE = "forced_idle"


def _require_enum(value: object, expected: type[Enum], field_name: str) -> Enum:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be a {expected.__name__}")
    return value


def _require_optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    return require_number(value, field_name)


def _require_optional_fraction(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    return require_fraction(value, field_name)


def _require_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_string(value, field_name)


@dataclass(frozen=True, slots=True)
class TimingPolicy(SerializableContract):
    """Caller-owned development policy; values are not hardware-certified limits."""

    max_telemetry_age: timedelta
    max_capability_age: timedelta
    max_command_lifetime: timedelta
    max_clock_skew: timedelta
    acknowledgement_timeout: timedelta
    command_execution_timeout: timedelta

    SCHEMA_VERSION: ClassVar[str] = "edge-timing-policy/v1"

    def __post_init__(self) -> None:
        for field_name in (
            "max_telemetry_age",
            "max_capability_age",
            "max_command_lifetime",
            "max_clock_skew",
            "acknowledgement_timeout",
            "command_execution_timeout",
        ):
            object.__setattr__(
                self,
                field_name,
                require_positive_timedelta(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class PowerCommand:
    """One requested signed battery power command, never an actual-power fact.

    Internal P0.1 convention is raw kW: positive requests charging, negative
    requests discharging, and zero requests idle. Protocol adapters alone own
    a future protocol-specific sign conversion.
    """

    schema_version: str
    command_id: str
    sequence: int
    provenance_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    requested_battery_power_kw: float
    operating_mode: OperatingMode
    reason_code: str
    source: str
    correlation_id: str

    def __post_init__(self) -> None:
        if self.schema_version != "edge-power-command/v1":
            raise ValueError("unsupported PowerCommand schema_version")
        for field_name in (
            "schema_version",
            "command_id",
            "provenance_id",
            "reason_code",
            "source",
            "correlation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_non_empty_string(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self, "sequence", require_non_negative_int(self.sequence, "sequence")
        )
        for field_name in ("issued_at", "not_before", "expires_at"):
            object.__setattr__(
                self,
                field_name,
                require_aware_datetime(getattr(self, field_name), field_name),
            )
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        if self.not_before > self.expires_at:
            raise ValueError("not_before must not be later than expires_at")
        object.__setattr__(
            self,
            "requested_battery_power_kw",
            require_number(
                self.requested_battery_power_kw, "requested_battery_power_kw"
            ),
        )
        _require_enum(self.operating_mode, OperatingMode, "operating_mode")
        if self.requested_battery_power_kw == 0:
            object.__setattr__(self, "requested_battery_power_kw", 0.0)
            if self.operating_mode is not OperatingMode.SAFE_IDLE:
                raise ValueError("zero requested_battery_power_kw requires safe_idle")
        elif self.operating_mode is not OperatingMode.NORMAL:
            raise ValueError("non-zero requested_battery_power_kw requires normal")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready UTC representation without changing facts."""
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "sequence": self.sequence,
            "provenance_id": self.provenance_id,
            "issued_at": utc_isoformat(self.issued_at),
            "not_before": utc_isoformat(self.not_before),
            "expires_at": utc_isoformat(self.expires_at),
            "requested_battery_power_kw": self.requested_battery_power_kw,
            "operating_mode": self.operating_mode.value,
            "reason_code": self.reason_code,
            "source": self.source,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PowerCommand":
        """Parse one supported schema without guessing omitted fields."""
        payload = require_exact_fields(
            value,
            "PowerCommand",
            (
                "schema_version",
                "command_id",
                "sequence",
                "provenance_id",
                "issued_at",
                "not_before",
                "expires_at",
                "requested_battery_power_kw",
                "operating_mode",
                "reason_code",
                "source",
                "correlation_id",
            ),
        )
        if payload["schema_version"] != "edge-power-command/v1":
            raise ValueError("unsupported PowerCommand schema_version")
        return cls(
            schema_version="edge-power-command/v1",
            command_id=require_non_empty_string(payload["command_id"], "command_id"),
            sequence=require_non_negative_int(payload["sequence"], "sequence"),
            provenance_id=require_non_empty_string(
                payload["provenance_id"], "provenance_id"
            ),
            issued_at=parse_utc_datetime(payload["issued_at"], "issued_at"),
            not_before=parse_utc_datetime(payload["not_before"], "not_before"),
            expires_at=parse_utc_datetime(payload["expires_at"], "expires_at"),
            requested_battery_power_kw=require_number(
                payload["requested_battery_power_kw"], "requested_battery_power_kw"
            ),
            operating_mode=OperatingMode(
                require_non_empty_string(payload["operating_mode"], "operating_mode")
            ),
            reason_code=require_non_empty_string(payload["reason_code"], "reason_code"),
            source=require_non_empty_string(payload["source"], "source"),
            correlation_id=require_non_empty_string(
                payload["correlation_id"], "correlation_id"
            ),
        )


@dataclass(frozen=True, slots=True)
class CommandAcknowledgement(SerializableContract):
    """A device receipt; acceptance does not prove actual executed power."""

    command_id: str
    sequence: int
    acknowledgement_status: AcknowledgementStatus
    received_at: datetime
    device_timestamp: datetime | None
    accepted_power_kw: float | None
    rejection_reason: str | None
    device_state: str | None
    correlation_id: str

    SCHEMA_VERSION: ClassVar[str] = "edge-command-acknowledgement/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "command_id", require_non_empty_string(self.command_id, "command_id")
        )
        object.__setattr__(
            self, "sequence", require_non_negative_int(self.sequence, "sequence")
        )
        _require_enum(
            self.acknowledgement_status, AcknowledgementStatus, "acknowledgement_status"
        )
        object.__setattr__(
            self, "received_at", require_aware_datetime(self.received_at, "received_at")
        )
        object.__setattr__(
            self,
            "device_timestamp",
            require_optional_aware_datetime(self.device_timestamp, "device_timestamp"),
        )
        object.__setattr__(
            self,
            "accepted_power_kw",
            _require_optional_number(self.accepted_power_kw, "accepted_power_kw"),
        )
        for field_name in ("rejection_reason", "device_state"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self, field_name, require_non_empty_string(value, field_name)
                )
        object.__setattr__(
            self,
            "correlation_id",
            require_non_empty_string(self.correlation_id, "correlation_id"),
        )


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    """One parsed actual-state observation; unknown remains explicit ``None``.

    ``actual_battery_power_kw`` is a measured fact using the internal signed
    convention, not planned or acknowledged command power. ``grid_power_kw``
    follows the existing EOS convention: positive import, negative export.
    """

    schema_version: str
    source_id: str
    source_sequence: int
    observed_at: datetime
    received_at: datetime
    actual_battery_power_kw: float | None
    soc_fraction: float | None
    soh_fraction: float | None
    grid_power_kw: float | None
    pv_power_kw: float | None
    load_power_kw: float | None
    pcs_state: str | None
    bms_state: str | None
    alarm_codes: tuple[str, ...]
    quality_status: TelemetryQualityStatus

    def __post_init__(self) -> None:
        if self.schema_version != "edge-telemetry/v1":
            raise ValueError("unsupported TelemetrySnapshot schema_version")
        for field_name in ("schema_version", "source_id"):
            object.__setattr__(
                self,
                field_name,
                require_non_empty_string(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "source_sequence",
            require_non_negative_int(self.source_sequence, "source_sequence"),
        )
        object.__setattr__(
            self, "observed_at", require_aware_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self, "received_at", require_aware_datetime(self.received_at, "received_at")
        )
        if self.received_at < self.observed_at:
            raise ValueError("received_at must not be earlier than observed_at")
        for field_name in (
            "actual_battery_power_kw",
            "grid_power_kw",
            "pv_power_kw",
            "load_power_kw",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_optional_number(getattr(self, field_name), field_name),
            )
        for field_name in ("soc_fraction", "soh_fraction"):
            object.__setattr__(
                self,
                field_name,
                _require_optional_fraction(getattr(self, field_name), field_name),
            )
        for field_name in ("pcs_state", "bms_state"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self, field_name, require_non_empty_string(value, field_name)
                )
        if not isinstance(self.alarm_codes, tuple):
            raise TypeError("alarm_codes must be a tuple")
        if any(
            not isinstance(code, str) or not code.strip() for code in self.alarm_codes
        ):
            raise ValueError("alarm_codes must contain non-empty strings")
        _require_enum(self.quality_status, TelemetryQualityStatus, "quality_status")

    def age_at(self, reference_time: datetime) -> timedelta:
        """Return observation age from ``observed_at``, not receipt time."""
        now = require_aware_datetime(reference_time, "reference_time")
        return now - self.observed_at

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation that preserves explicit unknowns."""
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "observed_at": utc_isoformat(self.observed_at),
            "received_at": utc_isoformat(self.received_at),
            "actual_battery_power_kw": self.actual_battery_power_kw,
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "grid_power_kw": self.grid_power_kw,
            "pv_power_kw": self.pv_power_kw,
            "load_power_kw": self.load_power_kw,
            "pcs_state": self.pcs_state,
            "bms_state": self.bms_state,
            "alarm_codes": list(self.alarm_codes),
            "quality_status": self.quality_status.value,
        }

    @classmethod
    def from_dict(cls, value: object) -> "TelemetrySnapshot":
        """Parse a supported telemetry schema without silently inventing values."""
        payload = require_exact_fields(
            value,
            "TelemetrySnapshot",
            (
                "schema_version",
                "source_id",
                "source_sequence",
                "observed_at",
                "received_at",
                "actual_battery_power_kw",
                "soc_fraction",
                "soh_fraction",
                "grid_power_kw",
                "pv_power_kw",
                "load_power_kw",
                "pcs_state",
                "bms_state",
                "alarm_codes",
                "quality_status",
            ),
        )
        if payload["schema_version"] != "edge-telemetry/v1":
            raise ValueError("unsupported TelemetrySnapshot schema_version")
        alarm_codes = payload["alarm_codes"]
        if not isinstance(alarm_codes, list):
            raise TypeError("alarm_codes must be a list")
        return cls(
            schema_version="edge-telemetry/v1",
            source_id=require_non_empty_string(payload["source_id"], "source_id"),
            source_sequence=require_non_negative_int(
                payload["source_sequence"], "source_sequence"
            ),
            observed_at=parse_utc_datetime(payload["observed_at"], "observed_at"),
            received_at=parse_utc_datetime(payload["received_at"], "received_at"),
            actual_battery_power_kw=_require_optional_number(
                payload["actual_battery_power_kw"], "actual_battery_power_kw"
            ),
            soc_fraction=_require_optional_fraction(
                payload["soc_fraction"], "soc_fraction"
            ),
            soh_fraction=_require_optional_fraction(
                payload["soh_fraction"], "soh_fraction"
            ),
            grid_power_kw=_require_optional_number(
                payload["grid_power_kw"], "grid_power_kw"
            ),
            pv_power_kw=_require_optional_number(payload["pv_power_kw"], "pv_power_kw"),
            load_power_kw=_require_optional_number(
                payload["load_power_kw"], "load_power_kw"
            ),
            pcs_state=_require_optional_string(payload["pcs_state"], "pcs_state"),
            bms_state=_require_optional_string(payload["bms_state"], "bms_state"),
            alarm_codes=tuple(alarm_codes),
            quality_status=TelemetryQualityStatus(
                require_non_empty_string(payload["quality_status"], "quality_status")
            ),
        )


@dataclass(frozen=True, slots=True)
class DeviceCapability(SerializableContract):
    """One BMS or PCS capability fact, using non-negative power magnitudes."""

    source: DeviceCapabilitySource
    source_id: str
    capability_sequence: int
    valid_from: datetime
    expires_at: datetime
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_allowed: bool
    discharge_allowed: bool
    available: bool
    derating_reason: str | None

    SCHEMA_VERSION: ClassVar[str] = "edge-device-capability/v1"

    def __post_init__(self) -> None:
        _require_enum(self.source, DeviceCapabilitySource, "source")
        object.__setattr__(
            self, "source_id", require_non_empty_string(self.source_id, "source_id")
        )
        object.__setattr__(
            self,
            "capability_sequence",
            require_non_negative_int(self.capability_sequence, "capability_sequence"),
        )
        object.__setattr__(
            self, "valid_from", require_aware_datetime(self.valid_from, "valid_from")
        )
        object.__setattr__(
            self, "expires_at", require_aware_datetime(self.expires_at, "expires_at")
        )
        if self.expires_at <= self.valid_from:
            raise ValueError("expires_at must be later than valid_from")
        for field_name in ("max_charge_power_kw", "max_discharge_power_kw"):
            object.__setattr__(
                self,
                field_name,
                require_non_negative_number(getattr(self, field_name), field_name),
            )
        for field_name in ("charge_allowed", "discharge_allowed", "available"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        if self.derating_reason is not None:
            object.__setattr__(
                self,
                "derating_reason",
                require_non_empty_string(self.derating_reason, "derating_reason"),
            )


@dataclass(frozen=True, slots=True, init=False)
class EffectiveDeviceCapability(SerializableContract):
    """Intersection of exact BMS and PCS facts; neither source is discarded."""

    bms_capability: DeviceCapability
    pcs_capability: DeviceCapability
    valid_from: datetime
    expires_at: datetime
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_allowed: bool
    discharge_allowed: bool
    available: bool

    SCHEMA_VERSION: ClassVar[str] = "edge-effective-device-capability/v1"

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "EffectiveDeviceCapability is derived only from BMS and PCS capabilities"
        )

    @classmethod
    def _derive(
        cls,
        bms_capability: DeviceCapability,
        pcs_capability: DeviceCapability,
    ) -> "EffectiveDeviceCapability":
        instance = object.__new__(cls)
        values = {
            "bms_capability": bms_capability,
            "pcs_capability": pcs_capability,
            "valid_from": max(bms_capability.valid_from, pcs_capability.valid_from),
            "expires_at": min(bms_capability.expires_at, pcs_capability.expires_at),
            "max_charge_power_kw": min(
                bms_capability.max_charge_power_kw,
                pcs_capability.max_charge_power_kw,
            ),
            "max_discharge_power_kw": min(
                bms_capability.max_discharge_power_kw,
                pcs_capability.max_discharge_power_kw,
            ),
            "charge_allowed": (
                bms_capability.charge_allowed and pcs_capability.charge_allowed
            ),
            "discharge_allowed": (
                bms_capability.discharge_allowed and pcs_capability.discharge_allowed
            ),
            "available": bms_capability.available and pcs_capability.available,
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        instance._validate_derived()
        return instance

    def _validate_derived(self) -> None:
        if (
            not isinstance(self.bms_capability, DeviceCapability)
            or self.bms_capability.source is not DeviceCapabilitySource.BMS
        ):
            raise TypeError("bms_capability must be a BMS DeviceCapability")
        if (
            not isinstance(self.pcs_capability, DeviceCapability)
            or self.pcs_capability.source is not DeviceCapabilitySource.PCS
        ):
            raise TypeError("pcs_capability must be a PCS DeviceCapability")
        for field_name in ("valid_from", "expires_at"):
            object.__setattr__(
                self,
                field_name,
                require_aware_datetime(getattr(self, field_name), field_name),
            )
        if self.expires_at <= self.valid_from:
            raise ValueError("expires_at must be later than valid_from")
        for field_name in ("max_charge_power_kw", "max_discharge_power_kw"):
            object.__setattr__(
                self,
                field_name,
                require_non_negative_number(getattr(self, field_name), field_name),
            )
        for field_name in ("charge_allowed", "discharge_allowed", "available"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        expected = (
            max(self.bms_capability.valid_from, self.pcs_capability.valid_from),
            min(self.bms_capability.expires_at, self.pcs_capability.expires_at),
            min(
                self.bms_capability.max_charge_power_kw,
                self.pcs_capability.max_charge_power_kw,
            ),
            min(
                self.bms_capability.max_discharge_power_kw,
                self.pcs_capability.max_discharge_power_kw,
            ),
            self.bms_capability.charge_allowed and self.pcs_capability.charge_allowed,
            self.bms_capability.discharge_allowed
            and self.pcs_capability.discharge_allowed,
            self.bms_capability.available and self.pcs_capability.available,
        )
        actual = (
            self.valid_from,
            self.expires_at,
            self.max_charge_power_kw,
            self.max_discharge_power_kw,
            self.charge_allowed,
            self.discharge_allowed,
            self.available,
        )
        if actual != expected:
            raise ValueError(
                "EffectiveDeviceCapability must equal the BMS/PCS intersection"
            )

    @classmethod
    def from_dict(cls, value: object) -> "EffectiveDeviceCapability":
        expected_fields = (
            "schema_version",
            "bms_capability",
            "pcs_capability",
            "valid_from",
            "expires_at",
            "max_charge_power_kw",
            "max_discharge_power_kw",
            "charge_allowed",
            "discharge_allowed",
            "available",
        )
        payload = require_exact_fields(
            value, "EffectiveDeviceCapability", expected_fields
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported EffectiveDeviceCapability schema_version")
        bms_capability = DeviceCapability.from_dict(payload["bms_capability"])
        pcs_capability = DeviceCapability.from_dict(payload["pcs_capability"])
        effective = cls._derive(bms_capability, pcs_capability)
        if effective.to_dict() != payload:
            raise ValueError(
                "EffectiveDeviceCapability payload is not derived evidence"
            )
        return effective


@dataclass(frozen=True, slots=True)
class SafetyConstraint(SerializableContract):
    """One auditable applied safety fact in explicit authority precedence."""

    precedence: SafetyPrecedence
    reason_code: str
    evidence_references: tuple[str, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-safety-constraint/v1"

    def __post_init__(self) -> None:
        _require_enum(self.precedence, SafetyPrecedence, "precedence")
        object.__setattr__(
            self,
            "reason_code",
            require_non_empty_string(self.reason_code, "reason_code"),
        )
        if not isinstance(self.evidence_references, tuple):
            raise TypeError("evidence_references must be a tuple")
        if not self.evidence_references:
            raise ValueError("evidence_references must not be empty")
        if any(
            not isinstance(reference, str) or not reference.strip()
            for reference in self.evidence_references
        ):
            raise ValueError("evidence_references must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class SafetyDecision(SerializableContract):
    """Trace a command request through safety revision, never to actual power."""

    source_command: PowerCommand
    source_telemetry: TelemetrySnapshot
    source_capability: EffectiveDeviceCapability
    source_health: "RuntimeHealth"
    evaluated_at: datetime
    final_requested_battery_power_kw: float
    final_operating_mode: OperatingMode
    outcome: SafetyOutcome
    applied_constraints: tuple[SafetyConstraint, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-safety-decision/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.source_command, PowerCommand):
            raise TypeError("source_command must be a PowerCommand")
        if not isinstance(self.source_telemetry, TelemetrySnapshot):
            raise TypeError("source_telemetry must be a TelemetrySnapshot")
        if not isinstance(self.source_capability, EffectiveDeviceCapability):
            raise TypeError("source_capability must be an EffectiveDeviceCapability")
        if not isinstance(self.source_health, RuntimeHealth):
            raise TypeError("source_health must be a RuntimeHealth")
        object.__setattr__(
            self,
            "evaluated_at",
            require_aware_datetime(self.evaluated_at, "evaluated_at"),
        )
        object.__setattr__(
            self,
            "final_requested_battery_power_kw",
            require_number(
                self.final_requested_battery_power_kw,
                "final_requested_battery_power_kw",
            ),
        )
        _require_enum(self.outcome, SafetyOutcome, "outcome")
        _require_enum(self.final_operating_mode, OperatingMode, "final_operating_mode")
        if self.final_requested_battery_power_kw == 0:
            object.__setattr__(self, "final_requested_battery_power_kw", 0.0)
            if self.final_operating_mode is not OperatingMode.SAFE_IDLE:
                raise ValueError("zero final requested power requires safe_idle")
        elif self.final_operating_mode is not OperatingMode.NORMAL:
            raise ValueError("non-zero final requested power requires normal")
        if not isinstance(self.applied_constraints, tuple) or any(
            not isinstance(item, SafetyConstraint) for item in self.applied_constraints
        ):
            raise TypeError("applied_constraints must be a tuple of SafetyConstraint")
        if (
            self.outcome is SafetyOutcome.ALLOWED
            and self.final_requested_battery_power_kw
            != self.source_command.requested_battery_power_kw
        ):
            raise ValueError("allowed outcome must preserve requested power")
        if (
            self.outcome in (SafetyOutcome.BLOCKED, SafetyOutcome.FORCED_IDLE)
            and self.final_requested_battery_power_kw != 0
        ):
            raise ValueError(
                "blocked or forced_idle outcome requires zero final requested power"
            )


@dataclass(frozen=True, slots=True)
class FaultEvent(SerializableContract):
    """Immutable fault evidence; no claim of functional-safety certification."""

    fault_id: str
    source: FaultSource
    severity: FaultSeverity
    code: str
    raised_at: datetime
    observed_at: datetime
    latched: bool
    recoverable: bool
    cleared_at: datetime | None
    related_command_id: str | None
    evidence: tuple[str, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-fault-event/v1"

    def __post_init__(self) -> None:
        for field_name in ("fault_id", "code"):
            object.__setattr__(
                self,
                field_name,
                require_non_empty_string(getattr(self, field_name), field_name),
            )
        _require_enum(self.source, FaultSource, "source")
        _require_enum(self.severity, FaultSeverity, "severity")
        for field_name in ("raised_at", "observed_at"):
            object.__setattr__(
                self,
                field_name,
                require_aware_datetime(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "cleared_at",
            require_optional_aware_datetime(self.cleared_at, "cleared_at"),
        )
        if self.cleared_at is not None and self.cleared_at < self.raised_at:
            raise ValueError("cleared_at must not be earlier than raised_at")
        for field_name in ("latched", "recoverable"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        if self.related_command_id is not None:
            object.__setattr__(
                self,
                "related_command_id",
                require_non_empty_string(self.related_command_id, "related_command_id"),
            )
        if (
            not isinstance(self.evidence, tuple)
            or not self.evidence
            or any(
                not isinstance(item, str) or not item.strip() for item in self.evidence
            )
        ):
            raise TypeError("evidence must be a tuple of non-empty strings")


@dataclass(frozen=True, slots=True)
class RuntimeHealth(SerializableContract):
    """Caller-observed software health, distinct from PCS/BMS actual telemetry."""

    runtime_state: RuntimeState
    last_control_cycle_at: datetime | None
    telemetry_fresh: bool
    capability_fresh: bool
    pcs_connected: bool
    bms_connected: bool
    command_channel_healthy: bool
    consecutive_failures: int
    restart_count: int
    safe_fallback_active: bool
    active_faults: tuple[FaultEvent, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-runtime-health/v1"

    def __post_init__(self) -> None:
        _require_enum(self.runtime_state, RuntimeState, "runtime_state")
        object.__setattr__(
            self,
            "last_control_cycle_at",
            require_optional_aware_datetime(
                self.last_control_cycle_at, "last_control_cycle_at"
            ),
        )
        for field_name in (
            "telemetry_fresh",
            "capability_fresh",
            "pcs_connected",
            "bms_connected",
            "command_channel_healthy",
            "safe_fallback_active",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        for field_name in ("consecutive_failures", "restart_count"):
            object.__setattr__(
                self,
                field_name,
                require_non_negative_int(getattr(self, field_name), field_name),
            )
        if not isinstance(self.active_faults, tuple) or any(
            not isinstance(fault, FaultEvent) for fault in self.active_faults
        ):
            raise TypeError("active_faults must be a tuple of FaultEvent")
        if (
            self.runtime_state is RuntimeState.SAFE_IDLE
            and not self.safe_fallback_active
        ):
            raise ValueError("safe_idle RuntimeHealth requires safe_fallback_active")
