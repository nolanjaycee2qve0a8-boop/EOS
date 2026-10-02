"""Immutable caller facts and audit-only P0.13 evidence; no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo


def _identity(value: object) -> bool:
    return (
        type(value) is str
        and bool(value.strip())
        and value.strip().casefold() != "unknown"
    )


def _aware(value: object) -> bool:
    """Check inert time representation before dispatching any timezone behavior."""
    if type(value) is not datetime:
        return False
    zone = value.tzinfo
    if type(zone) is timezone:
        # Builtin timezone can retain a caller's str/timedelta subclass.
        if (
            type(zone.tzname(None)) is not str
            or type(zone.utcoffset(None)) is not timedelta
        ):
            return False
    elif type(zone) is ZoneInfo:
        # from_file also accepts arbitrary key objects; do not retain those.
        if zone.key is not None and type(zone.key) is not str:
            return False
        # File-stream ZoneInfo retains an opaque caller-supplied file repr too.
        # Its exact builtin reduction method refuses that representation without
        # dispatching the file/key/repr or running the returned reconstruction.
        try:
            ZoneInfo.__reduce__(zone)
        except Exception:
            return False
    else:
        return False
    return type(value.utcoffset()) is timedelta


def _instant(value: datetime) -> timedelta:
    """Exact absolute-time coordinate for an already checked inert datetime.

    Ordinal arithmetic avoids float timestamps and astimezone overflow near
    datetime.min/max. No timezone conversion, caller hook, or clock is involved.
    """
    offset = value.utcoffset()
    assert offset is not None
    return (
        timedelta(
            days=value.toordinal(),
            seconds=value.hour * 3600 + value.minute * 60 + value.second,
            microseconds=value.microsecond,
        )
        - offset
    )


def _envelope(identity: object, as_of: object) -> None:
    if not _identity(identity):
        raise ValueError("assessment_identity must be a known non-empty string")
    if not _aware(as_of):
        raise TypeError(
            "assessment_as_of must use an inert builtin timezone or ZoneInfo"
        )


class DeviceFactCommandCorrelationScopeHandoffStatus(StrEnum):
    """Audit result only, never completion, readiness, or future authority."""

    PASS = "pass"
    GAP = "gap"


class DeviceFactCommandCorrelationScopeHandoffGapCode(StrEnum):
    """Closed reasons for refusing a declared handoff."""

    INVALID_SCOPE = "invalid_scope"
    P0_12_GAP = "p0_12_gap"
    DUPLICATE_SCOPE = "duplicate_scope"
    DECLARATION_MISMATCH = "declaration_mismatch"
    IDENTITY_MISMATCH = "identity_mismatch"
    BOUNDARY_MISMATCH = "boundary_mismatch"
    SEQUENCE_RELATION_INVALID = "sequence_relation_invalid"
    TIME_RELATION_INVALID = "time_relation_invalid"
    TIME_SCOPE_INVALID = "time_scope_invalid"


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationScopeFacts:
    """Exact P0.12 request, including its declaration and ordered P0.11 inputs.

    The auditor rejects anything other than a raw ContinuityInput. No historical
    assessment is converted, and no duplicate member or range summary is stored.
    """

    continuity_input: object


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationScopeHandoffDeclaration:
    """Explicit ordered relation, checked against actual terminal/initial facts.

    Scope fields must be exact P0.12 declarations. Member identity relation must
    be 'distinct': assessment, transmission and actual identities cannot recur.
    Advances are exact caller-declared positive deltas, without default tolerance.
    Object slots permit malformed declarations to receive an explicit GAP.
    """

    previous_scope: object
    next_scope: object
    previous_terminal_identity: object
    next_initial_identity: object
    previous_terminal_sequence: object
    next_initial_sequence: object
    previous_terminal_as_of: object
    next_initial_as_of: object
    sequence_advance: object
    time_advance: object
    member_identity_relationship: object


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationScopeHandoffInput:
    """Finite caller-owned facts. Invalid nested facts are rejected, not retained."""

    assessment_identity: str
    assessment_as_of: datetime
    maximum_age: timedelta
    scopes: tuple[object, ...]
    declaration: object

    def __post_init__(self) -> None:
        _envelope(self.assessment_identity, self.assessment_as_of)
        if type(self.maximum_age) is not timedelta or self.maximum_age < timedelta(0):
            raise ValueError("maximum_age must be a non-negative timedelta")
        if type(self.scopes) is not tuple:
            raise TypeError("scopes must be a finite tuple")


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationScopeHandoffFinding:
    """An immutable closed finding, with no reference to input facts."""

    scope_index: int | None
    gap_code: DeviceFactCommandCorrelationScopeHandoffGapCode
    detail: str

    def __post_init__(self) -> None:
        if self.scope_index is not None and (
            type(self.scope_index) is not int or self.scope_index not in (0, 1)
        ):
            raise ValueError("scope_index must be 0, 1 or None")
        if type(self.gap_code) is not DeviceFactCommandCorrelationScopeHandoffGapCode:
            raise TypeError("gap_code must be a P0.13 gap code")
        if not _identity(self.detail):
            raise ValueError("detail must be a non-empty string")


@dataclass(frozen=True, slots=True)
class DeviceFactCommandCorrelationScopeHandoffAssessment:
    """Evidence only: no raw facts, predecessor objects or authority to restore."""

    assessment_identity: str
    assessment_as_of: datetime
    status: DeviceFactCommandCorrelationScopeHandoffStatus
    findings: tuple[DeviceFactCommandCorrelationScopeHandoffFinding, ...]

    def __post_init__(self) -> None:
        _envelope(self.assessment_identity, self.assessment_as_of)
        if type(self.status) is not DeviceFactCommandCorrelationScopeHandoffStatus:
            raise TypeError("status must be a P0.13 status")
        if type(self.findings) is not tuple or any(
            type(finding) is not DeviceFactCommandCorrelationScopeHandoffFinding
            for finding in self.findings
        ):
            raise TypeError("findings must be a tuple of P0.13 findings")
        expected = (
            DeviceFactCommandCorrelationScopeHandoffStatus.GAP
            if self.findings
            else DeviceFactCommandCorrelationScopeHandoffStatus.PASS
        )
        if self.status is not expected:
            raise ValueError("status must agree with findings")
