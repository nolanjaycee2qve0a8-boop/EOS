"""Immutable P0.12 cross-member command-correlation audit values."""

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


class DeviceFactCommandCorrelationContinuityStatus(StrEnum):
    """Audit status, never an execution or physical-completion result."""

    PASS = "pass"
    GAP = "gap"


class DeviceFactCommandCorrelationContinuityGapCode(StrEnum):
    """Closed fail-closed findings for P0.12 finite audit series."""

    TOO_FEW_MEMBERS = "too_few_members"
    MALFORMED_OR_HISTORICAL_MEMBER = "malformed_or_historical_member"
    MEMBER_P0_11_GAP = "member_p0_11_gap"
    SCOPE_UNDECLARED_OR_MALFORMED = "scope_undeclared_or_malformed"
    SCOPE_MISMATCH = "scope_mismatch"
    ASSESSMENT_IDENTITY_REUSED = "assessment_identity_reused"
    TRANSMISSION_IDENTITY_REUSED = "transmission_identity_reused"
    ACTUAL_OBSERVATION_IDENTITY_REUSED = "actual_observation_identity_reused"
    TRANSACTION_SEQUENCE_NOT_STRICT = "transaction_sequence_not_strict"
    ASSESSMENT_TIME_NOT_STRICT = "assessment_time_not_strict"
    CONTINUITY_TIME_SCOPE_INVALID = "continuity_time_scope_invalid"


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationContinuityScope:
    """Caller-declared audit scope, not a device lifecycle or transport scope."""

    scope_identity: str
    transmission_origin: str
    source_epoch_relationship: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scope_identity",
            _require_non_empty(self.scope_identity, "scope_identity"),
        )
        object.__setattr__(
            self,
            "transmission_origin",
            _require_non_empty(self.transmission_origin, "transmission_origin"),
        )


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationContinuityInput:
    """One finite caller-owned P0.12 audit request with no execution authority."""

    assessment_identity: str
    assessment_as_of: datetime
    maximum_age: timedelta
    scope: object
    members: tuple[object, ...]

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
        if not isinstance(self.members, tuple):
            raise TypeError("members must be a tuple")


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationContinuityFinding:
    """One immutable P0.12 audit GAP without input or execution authority."""

    member_index: int | None
    gap_code: DeviceFactCommandCorrelationContinuityGapCode
    detail: str

    def __post_init__(self) -> None:
        if self.member_index is not None and (
            not isinstance(self.member_index, int)
            or isinstance(self.member_index, bool)
            or self.member_index < 0
        ):
            raise ValueError("member_index must be a non-negative int or None")
        if not isinstance(self.gap_code, DeviceFactCommandCorrelationContinuityGapCode):
            raise TypeError(
                "gap_code must be DeviceFactCommandCorrelationContinuityGapCode"
            )
        object.__setattr__(self, "detail", _require_non_empty(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationContinuityAssessment:
    """Audit evidence only; it retains no members, P0.11 results, or authority."""

    assessment_identity: str
    assessment_as_of: datetime
    status: DeviceFactCommandCorrelationContinuityStatus
    findings: tuple[DeviceFactCommandCorrelationContinuityFinding, ...]

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
        if not isinstance(self.status, DeviceFactCommandCorrelationContinuityStatus):
            raise TypeError(
                "status must be DeviceFactCommandCorrelationContinuityStatus"
            )
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DeviceFactCommandCorrelationContinuityFinding)
            for finding in self.findings
        ):
            raise TypeError(
                "findings must be a tuple of "
                "DeviceFactCommandCorrelationContinuityFinding"
            )
        expected = (
            DeviceFactCommandCorrelationContinuityStatus.PASS
            if not self.findings
            else DeviceFactCommandCorrelationContinuityStatus.GAP
        )
        if self.status is not expected:
            raise ValueError("assessment status must match findings")
