"""Immutable P0.10 caller facts and audit-only lifecycle-continuity values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


def _require_non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError(f"{name} must be an aware datetime")
    return value


class DeviceFactLifecycleAvailability(StrEnum):
    """Explicit caller-provided availability; never inferred by P0.10."""

    AVAILABLE = "available"
    DISCONNECTED = "disconnected"
    REBOOTED = "rebooted"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DeviceFactLifecycleTransition(StrEnum):
    """The closed set of one-label-per-adjacent-pair lifecycle transitions."""

    CONTINUITY = "continuity"
    DISCONNECT = "disconnect"
    REBOOT = "reboot"
    RECONNECT = "reconnect"
    IDENTITY_EPOCH_CHANGE = "identity_epoch_change"
    TIME_DISCONTINUITY = "time_discontinuity"


class DeviceFactLifecycleStatus(StrEnum):
    """Overall audit status, never a device-execution result."""

    PASS = "pass"
    GAP = "gap"


class DeviceFactLifecycleGapCode(StrEnum):
    """Explicit fail-closed lifecycle audit gaps."""

    UNLABELLED_OR_UNKNOWN_TRANSITION = "unlabelled_or_unknown_transition"
    ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED = "assessment_or_evidence_identity_reused"
    CONTINUITY_FACT_MISMATCH = "continuity_fact_mismatch"
    DISCONNECT_RECORDED = "disconnect_recorded"
    REBOOT_RECORDED = "reboot_recorded"
    RECONNECT_PRECONDITION_UNMET = "reconnect_precondition_unmet"
    IDENTITY_EPOCH_DISCONTINUITY = "identity_epoch_discontinuity"
    TIME_DISCONTINUITY_RECORDED = "time_discontinuity_recorded"
    HISTORICAL_ASSESSMENT_INPUT_REJECTED = "historical_assessment_input_rejected"
    ACK_ACTUAL_FACT_MISSING_OR_FUSED = "ack_actual_fact_missing_or_fused"


@dataclass(frozen=True, slots=True)
class DeviceFactLifecycleSnapshot:
    """One caller fact snapshot with no command, adapter, or runtime authority."""

    snapshot_identity: str
    evidence_identity: str
    source_identity: str
    identity_epoch: str
    availability: DeviceFactLifecycleAvailability
    observed_at: datetime
    request_id: str | None = None
    request_sequence: int | None = None
    request_correlation_id: str | None = None
    acknowledgement_request_id: str | None = None
    acknowledgement_sequence: int | None = None
    acknowledgement_correlation_id: str | None = None
    actual_present: bool | None = None

    def __post_init__(self) -> None:
        for name in (
            "snapshot_identity",
            "evidence_identity",
            "source_identity",
            "identity_epoch",
        ):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        if not isinstance(self.availability, DeviceFactLifecycleAvailability):
            raise TypeError("availability must be DeviceFactLifecycleAvailability")
        object.__setattr__(
            self, "observed_at", _require_aware(self.observed_at, "observed_at")
        )
        if self.actual_present is not None and not isinstance(
            self.actual_present, bool
        ):
            raise TypeError("actual_present must be bool or None")


@dataclass(frozen=True, slots=True)
class DeviceFactLifecycleContinuityInput:
    """One explicit, finite, caller-owned lifecycle audit request."""

    assessment_identity: str
    assessment_as_of: datetime
    maximum_age: timedelta
    snapshots: tuple[object, ...]
    transitions: tuple[object, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_identity",
            _require_non_empty(self.assessment_identity, "assessment_identity"),
        )
        object.__setattr__(
            self,
            "assessment_as_of",
            _require_aware(self.assessment_as_of, "assessment_as_of"),
        )
        if not isinstance(self.maximum_age, timedelta) or self.maximum_age < timedelta(
            0
        ):
            raise ValueError("maximum_age must be a non-negative timedelta")
        if not isinstance(self.snapshots, tuple) or not self.snapshots:
            raise ValueError("snapshots must be a non-empty tuple")
        if not isinstance(self.transitions, tuple):
            raise TypeError("transitions must be a tuple")


@dataclass(frozen=True, slots=True)
class DeviceFactLifecycleFinding:
    """One immutable audit GAP with no input or execution authority."""

    transition_index: int | None
    gap_code: DeviceFactLifecycleGapCode
    detail: str

    def __post_init__(self) -> None:
        if self.transition_index is not None and (
            not isinstance(self.transition_index, int)
            or isinstance(self.transition_index, bool)
            or self.transition_index < 0
        ):
            raise ValueError("transition_index must be a non-negative int or None")
        if not isinstance(self.gap_code, DeviceFactLifecycleGapCode):
            raise TypeError("gap_code must be DeviceFactLifecycleGapCode")
        object.__setattr__(self, "detail", _require_non_empty(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class DeviceFactLifecycleAssessment:
    """Audit-only result; it holds no snapshots, input, or authority objects."""

    assessment_identity: str
    assessment_as_of: datetime
    status: DeviceFactLifecycleStatus
    findings: tuple[DeviceFactLifecycleFinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_identity",
            _require_non_empty(self.assessment_identity, "assessment_identity"),
        )
        object.__setattr__(
            self,
            "assessment_as_of",
            _require_aware(self.assessment_as_of, "assessment_as_of"),
        )
        if not isinstance(self.status, DeviceFactLifecycleStatus):
            raise TypeError("status must be DeviceFactLifecycleStatus")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DeviceFactLifecycleFinding) for finding in self.findings
        ):
            raise TypeError("findings must be a tuple of DeviceFactLifecycleFinding")
        expected = (
            DeviceFactLifecycleStatus.PASS
            if not self.findings
            else DeviceFactLifecycleStatus.GAP
        )
        if self.status is not expected:
            raise ValueError("assessment status must match findings")
