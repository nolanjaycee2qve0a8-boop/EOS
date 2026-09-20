"""Immutable P0.11 caller facts and audit-only command-correlation values."""

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


def _require_sequence(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


class DeviceFactCommandCorrelationAvailability(StrEnum):
    """Explicit caller availability; P0.11 never infers it."""

    AVAILABLE = "available"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DeviceFactCommandCorrelationStatus(StrEnum):
    """Audit status, never an execution or physical-completion result."""

    PASS = "pass"
    GAP = "gap"


class DeviceFactCommandCorrelationGapCode(StrEnum):
    """Closed fail-closed findings for finite P0.11 audit facts."""

    MALFORMED_OR_HISTORICAL_FACT = "malformed_or_historical_fact"
    ASSESSMENT_IDENTITY_REUSED = "assessment_identity_reused"
    TIME_SCOPE_INVALID = "time_scope_invalid"
    ACKNOWLEDGEMENT_UNAVAILABLE = "acknowledgement_unavailable"
    ACKNOWLEDGEMENT_CORRELATION_MISMATCH = "acknowledgement_correlation_mismatch"
    SOURCE_EPOCH_RELATIONSHIP_UNDECLARED = "source_epoch_relationship_undeclared"
    SOURCE_EPOCH_RELATIONSHIP_MISMATCH = "source_epoch_relationship_mismatch"
    ACTUAL_UNAVAILABLE = "actual_unavailable"


@dataclass(frozen=True, slots=True)
class DeviceFactTransmissionIdentity:
    """Inert caller-declared transmission identity; never a command or request."""

    transmission_identity: str
    sequence: int
    origin: str
    declared_at: datetime
    source_identity: str
    identity_epoch: str

    def __post_init__(self) -> None:
        for name in (
            "transmission_identity",
            "origin",
            "source_identity",
            "identity_epoch",
        ):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        object.__setattr__(
            self, "sequence", _require_sequence(self.sequence, "sequence")
        )
        object.__setattr__(
            self, "declared_at", _require_aware(self.declared_at, "declared_at")
        )


@dataclass(frozen=True, slots=True)
class DeviceFactAcknowledgementObservation:
    """An inert acknowledgement observation, not transmission or completion proof."""

    transmission_identity: str
    sequence: int
    origin: str
    observed_at: datetime
    source_identity: str
    identity_epoch: str
    availability: DeviceFactCommandCorrelationAvailability

    def __post_init__(self) -> None:
        for name in (
            "transmission_identity",
            "origin",
            "source_identity",
            "identity_epoch",
        ):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        object.__setattr__(
            self, "sequence", _require_sequence(self.sequence, "sequence")
        )
        object.__setattr__(
            self, "observed_at", _require_aware(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, DeviceFactCommandCorrelationAvailability):
            raise TypeError(
                "availability must be DeviceFactCommandCorrelationAvailability"
            )


@dataclass(frozen=True, slots=True)
class DeviceFactActualObservation:
    """A distinct inert actual observation; it never replaces P0.3 reconciliation."""

    observation_identity: str
    observed_at: datetime
    source_identity: str
    identity_epoch: str
    availability: DeviceFactCommandCorrelationAvailability
    actual_power_kw: float | None

    def __post_init__(self) -> None:
        for name in ("observation_identity", "source_identity", "identity_epoch"):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        object.__setattr__(
            self, "observed_at", _require_aware(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, DeviceFactCommandCorrelationAvailability):
            raise TypeError(
                "availability must be DeviceFactCommandCorrelationAvailability"
            )
        if self.actual_power_kw is not None and (
            not isinstance(self.actual_power_kw, (int, float))
            or isinstance(self.actual_power_kw, bool)
        ):
            raise TypeError("actual_power_kw must be a numeric value or None")


@dataclass(frozen=True, slots=True)
class DeviceFactSourceEpochRelationship:
    """Caller-declared permitted source/epoch relation for this audit only."""

    transmission_source_identity: str
    transmission_identity_epoch: str
    acknowledgement_source_identity: str
    acknowledgement_identity_epoch: str
    actual_source_identity: str
    actual_identity_epoch: str

    def __post_init__(self) -> None:
        for name in (
            "transmission_source_identity",
            "transmission_identity_epoch",
            "acknowledgement_source_identity",
            "acknowledgement_identity_epoch",
            "actual_source_identity",
            "actual_identity_epoch",
        ):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationInput:
    """One finite caller-owned P0.11 audit input with no execution authority."""

    assessment_identity: str
    assessment_as_of: datetime
    maximum_age: timedelta
    transmission: object
    acknowledgement: object
    actual: object
    source_epoch_relationship: object

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


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationFinding:
    """One non-executable immutable P0.11 audit GAP."""

    gap_code: DeviceFactCommandCorrelationGapCode
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.gap_code, DeviceFactCommandCorrelationGapCode):
            raise TypeError("gap_code must be DeviceFactCommandCorrelationGapCode")
        object.__setattr__(self, "detail", _require_non_empty(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationAssessment:
    """Audit evidence only; no input, command, runtime, or transport reference."""

    assessment_identity: str
    assessment_as_of: datetime
    status: DeviceFactCommandCorrelationStatus
    findings: tuple[DeviceFactCommandCorrelationFinding, ...]

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
        if not isinstance(self.status, DeviceFactCommandCorrelationStatus):
            raise TypeError("status must be DeviceFactCommandCorrelationStatus")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DeviceFactCommandCorrelationFinding)
            for finding in self.findings
        ):
            raise TypeError(
                "findings must be a tuple of DeviceFactCommandCorrelationFinding"
            )
        expected = (
            DeviceFactCommandCorrelationStatus.PASS
            if not self.findings
            else DeviceFactCommandCorrelationStatus.GAP
        )
        if self.status is not expected:
            raise ValueError("assessment status must match findings")
