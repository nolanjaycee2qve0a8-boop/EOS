"""Immutable caller facts and audit-only results for P0.9 readiness checks."""

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


class DeviceFactRequirement(StrEnum):
    IDENTITY_PROVENANCE = "identity_provenance"
    AVAILABILITY_TIME = "availability_time"
    ACK_CORRELATION = "ack_correlation"
    ACTUAL_TELEMETRY = "actual_telemetry"
    DISCONNECT_REBOOT = "disconnect_reboot"
    FRESH_REASSESSMENT = "fresh_reassessment"


class DeviceFactAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"
    REBOOTED = "rebooted"


class DeviceFactReadinessStatus(StrEnum):
    PASS = "pass"
    GAP = "gap"


class DeviceFactGapCode(StrEnum):
    CAPABILITY_NOT_DECLARED = "capability_not_declared"
    IDENTITY_MISMATCH = "identity_mismatch"
    PROVENANCE_MISMATCH = "provenance_mismatch"
    AVAILABILITY_NOT_PROVEN = "availability_not_proven"
    TIME_AFTER_AS_OF = "time_after_as_of"
    STALE = "stale"
    ACK_CORRELATION_MISMATCH = "ack_correlation_mismatch"
    ACTUAL_NOT_PROVEN = "actual_not_proven"
    DISCONNECTED = "disconnected"
    REBOOT_DISCONTINUITY = "reboot_discontinuity"
    FRESH_REASSESSMENT_NOT_PROVEN = "fresh_reassessment_not_proven"


@dataclass(frozen=True, slots=True)
class DeviceFactCapabilityProfile:
    """Caller declarations with no endpoint, credential, or device authority."""

    profile_id: str
    source_identity: str
    provenance_id: str
    continuity_id: str
    declared_requirements: frozenset[DeviceFactRequirement]

    def __post_init__(self) -> None:
        for name in ("profile_id", "source_identity", "provenance_id", "continuity_id"):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        if (
            not isinstance(self.declared_requirements, frozenset)
            or not self.declared_requirements
        ):
            raise TypeError("declared_requirements must be a non-empty frozenset")
        if any(
            not isinstance(requirement, DeviceFactRequirement)
            for requirement in self.declared_requirements
        ):
            raise TypeError("declared_requirements must contain DeviceFactRequirement")


@dataclass(frozen=True, slots=True)
class DeviceFactRequirementPolicy:
    """Caller-supplied freshness rule; P0.9 owns no clock or default threshold."""

    requirement: DeviceFactRequirement
    maximum_age: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, DeviceFactRequirement):
            raise TypeError("requirement must be a DeviceFactRequirement")
        if not isinstance(self.maximum_age, timedelta) or self.maximum_age < timedelta(
            0
        ):
            raise ValueError("maximum_age must be a non-negative timedelta")


@dataclass(frozen=True, slots=True)
class DeviceFactEvidenceSample:
    """One deterministic audit fact, never a command, adapter, or transport request."""

    fact_id: str
    requirement: DeviceFactRequirement
    source_identity: str
    provenance_id: str
    continuity_id: str
    assessment_id: str
    evidence_set_id: str
    observed_at: datetime
    availability: DeviceFactAvailability
    request_id: str | None = None
    request_sequence: int | None = None
    request_correlation_id: str | None = None
    acknowledgement_request_id: str | None = None
    acknowledgement_sequence: int | None = None
    acknowledgement_correlation_id: str | None = None
    actual_present: bool = False

    def __post_init__(self) -> None:
        for name in (
            "fact_id",
            "source_identity",
            "provenance_id",
            "continuity_id",
            "assessment_id",
            "evidence_set_id",
        ):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        if not isinstance(self.requirement, DeviceFactRequirement):
            raise TypeError("requirement must be a DeviceFactRequirement")
        object.__setattr__(
            self, "observed_at", _require_aware(self.observed_at, "observed_at")
        )
        if not isinstance(self.availability, DeviceFactAvailability):
            raise TypeError("availability must be a DeviceFactAvailability")
        if not isinstance(self.actual_present, bool):
            raise TypeError("actual_present must be bool")
        fields = (
            self.request_id,
            self.request_sequence,
            self.request_correlation_id,
            self.acknowledgement_request_id,
            self.acknowledgement_sequence,
            self.acknowledgement_correlation_id,
        )
        if any(value is not None for value in fields):
            if any(value is None for value in fields):
                raise ValueError("ACK correlation fields must be supplied together")
            for name in (
                "request_id",
                "request_correlation_id",
                "acknowledgement_request_id",
                "acknowledgement_correlation_id",
            ):
                _require_non_empty(getattr(self, name), name)
            for name in ("request_sequence", "acknowledgement_sequence"):
                value = getattr(self, name)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{name} must be a non-negative int")


@dataclass(frozen=True, slots=True)
class DeviceFactReadinessInput:
    """Fresh caller request containing only deterministic, non-executable values."""

    assessment_id: str
    evidence_set_id: str
    profile: DeviceFactCapabilityProfile
    policies: tuple[DeviceFactRequirementPolicy, ...]
    evidence: tuple[DeviceFactEvidenceSample, ...]
    as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_id",
            _require_non_empty(self.assessment_id, "assessment_id"),
        )
        object.__setattr__(
            self,
            "evidence_set_id",
            _require_non_empty(self.evidence_set_id, "evidence_set_id"),
        )
        if not isinstance(self.profile, DeviceFactCapabilityProfile):
            raise TypeError("profile must be a DeviceFactCapabilityProfile")
        if not isinstance(self.policies, tuple) or not all(
            isinstance(policy, DeviceFactRequirementPolicy) for policy in self.policies
        ):
            raise TypeError("policies must be a tuple of DeviceFactRequirementPolicy")
        required = frozenset(DeviceFactRequirement)
        policy_requirements = tuple(policy.requirement for policy in self.policies)
        if frozenset(policy_requirements) != required or len(
            policy_requirements
        ) != len(required):
            raise ValueError(
                "policies must contain each DeviceFactRequirement exactly once"
            )
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(sample, DeviceFactEvidenceSample) for sample in self.evidence
        ):
            raise TypeError("evidence must be a tuple of DeviceFactEvidenceSample")
        evidence_requirements = tuple(sample.requirement for sample in self.evidence)
        if frozenset(evidence_requirements) != required or len(
            evidence_requirements
        ) != len(required):
            raise ValueError(
                "evidence must contain each DeviceFactRequirement exactly once"
            )
        fact_ids = tuple(sample.fact_id for sample in self.evidence)
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("evidence fact_id values must be unique")
        object.__setattr__(self, "as_of", _require_aware(self.as_of, "as_of"))


@dataclass(frozen=True, slots=True)
class DeviceFactReadinessFinding:
    """A non-executable PASS or GAP for one explicit fact requirement."""

    requirement: DeviceFactRequirement
    status: DeviceFactReadinessStatus
    gap_code: DeviceFactGapCode | None
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, DeviceFactRequirement):
            raise TypeError("requirement must be a DeviceFactRequirement")
        if not isinstance(self.status, DeviceFactReadinessStatus):
            raise TypeError("status must be a DeviceFactReadinessStatus")
        if self.status is DeviceFactReadinessStatus.PASS and self.gap_code is not None:
            raise ValueError("PASS finding cannot contain a gap code")
        if self.status is DeviceFactReadinessStatus.GAP and not isinstance(
            self.gap_code, DeviceFactGapCode
        ):
            raise TypeError("GAP finding requires DeviceFactGapCode")
        object.__setattr__(self, "detail", _require_non_empty(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class DeviceFactReadinessAssessment:
    """Audit-only value snapshot with no caller input or execution authority."""

    assessment_id: str
    profile_id: str
    source_identity: str
    as_of: datetime
    status: DeviceFactReadinessStatus
    findings: tuple[DeviceFactReadinessFinding, ...]

    def __post_init__(self) -> None:
        for name in ("assessment_id", "profile_id", "source_identity"):
            object.__setattr__(
                self, name, _require_non_empty(getattr(self, name), name)
            )
        object.__setattr__(self, "as_of", _require_aware(self.as_of, "as_of"))
        if not isinstance(self.status, DeviceFactReadinessStatus):
            raise TypeError("status must be a DeviceFactReadinessStatus")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DeviceFactReadinessFinding) for finding in self.findings
        ):
            raise TypeError("findings must be a tuple of DeviceFactReadinessFinding")
        requirements = tuple(finding.requirement for finding in self.findings)
        required = frozenset(DeviceFactRequirement)
        if frozenset(requirements) != required or len(requirements) != len(required):
            raise ValueError(
                "findings must contain each DeviceFactRequirement exactly once"
            )
        expected = (
            DeviceFactReadinessStatus.PASS
            if all(
                finding.status is DeviceFactReadinessStatus.PASS
                for finding in self.findings
            )
            else DeviceFactReadinessStatus.GAP
        )
        if self.status is not expected:
            raise ValueError("assessment status must match findings")
