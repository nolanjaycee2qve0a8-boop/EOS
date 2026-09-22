"""Pure, deterministic P0.12 cross-member command-correlation audit evaluation."""

from __future__ import annotations

from itertools import pairwise

from edge_runtime.device_fact_command_correlation import (
    DeterministicDeviceFactCommandCorrelationAuditor,
    DeviceFactActualObservation,
    DeviceFactCommandCorrelationAssessment,
    DeviceFactCommandCorrelationInput,
    DeviceFactCommandCorrelationStatus,
    DeviceFactSourceEpochRelationship,
    DeviceFactTransmissionIdentity,
)
from edge_runtime.device_fact_command_correlation_continuity.contracts import (
    DeviceFactCommandCorrelationContinuityAssessment,
    DeviceFactCommandCorrelationContinuityFinding,
    DeviceFactCommandCorrelationContinuityGapCode,
    DeviceFactCommandCorrelationContinuityInput,
    DeviceFactCommandCorrelationContinuityScope,
    DeviceFactCommandCorrelationContinuityStatus,
)

_GapCode = DeviceFactCommandCorrelationContinuityGapCode


class DeterministicDeviceFactCommandCorrelationContinuityAuditor:
    """Stateless audit-only evaluator with no command, device, or replay authority."""

    __slots__ = ()

    @staticmethod
    def _gap(
        member_index: int | None,
        gap_code: DeviceFactCommandCorrelationContinuityGapCode,
        detail: str,
    ) -> DeviceFactCommandCorrelationContinuityFinding:
        return DeviceFactCommandCorrelationContinuityFinding(
            member_index, gap_code, detail
        )

    @staticmethod
    def _assessment(
        value: DeviceFactCommandCorrelationContinuityInput,
        findings: list[DeviceFactCommandCorrelationContinuityFinding],
    ) -> DeviceFactCommandCorrelationContinuityAssessment:
        return DeviceFactCommandCorrelationContinuityAssessment(
            value.assessment_identity,
            value.assessment_as_of,
            (
                DeviceFactCommandCorrelationContinuityStatus.PASS
                if not findings
                else DeviceFactCommandCorrelationContinuityStatus.GAP
            ),
            tuple(findings),
        )

    @staticmethod
    def _has_repeated(values: list[str]) -> bool:
        return len(set(values)) != len(values)

    def _member_findings(
        self,
        value: DeviceFactCommandCorrelationContinuityInput,
    ) -> tuple[
        list[DeviceFactCommandCorrelationContinuityFinding],
        list[tuple[int, DeviceFactCommandCorrelationInput]],
    ]:
        """Delegate each valid member exactly once to the frozen P0.11 auditor."""

        findings: list[DeviceFactCommandCorrelationContinuityFinding] = []
        valid_members: list[tuple[int, DeviceFactCommandCorrelationInput]] = []
        auditor = DeterministicDeviceFactCommandCorrelationAuditor()
        for index, member in enumerate(value.members):
            if isinstance(member, DeviceFactCommandCorrelationAssessment):
                findings.append(
                    self._gap(
                        index,
                        _GapCode.MALFORMED_OR_HISTORICAL_MEMBER,
                        "a historical P0.11 assessment cannot be a new audit member",
                    )
                )
                continue
            if not isinstance(member, DeviceFactCommandCorrelationInput):
                findings.append(
                    self._gap(
                        index,
                        _GapCode.MALFORMED_OR_HISTORICAL_MEMBER,
                        "member is not a caller-owned P0.11 input",
                    )
                )
                continue
            result = auditor.evaluate(member)
            if result.status is not DeviceFactCommandCorrelationStatus.PASS:
                findings.append(
                    self._gap(
                        index,
                        _GapCode.MEMBER_P0_11_GAP,
                        "member has an explicit P0.11 GAP and cannot be repaired here",
                    )
                )
                continue
            valid_members.append((index, member))
        return findings, valid_members

    def _scope_and_cross_member_findings(
        self,
        value: DeviceFactCommandCorrelationContinuityInput,
        valid_members: list[tuple[int, DeviceFactCommandCorrelationInput]],
    ) -> list[DeviceFactCommandCorrelationContinuityFinding]:
        findings: list[DeviceFactCommandCorrelationContinuityFinding] = []
        scope = value.scope
        if not isinstance(scope, DeviceFactCommandCorrelationContinuityScope):
            return [
                self._gap(
                    None,
                    _GapCode.SCOPE_UNDECLARED_OR_MALFORMED,
                    "scope must declare an origin and P0.11 source/epoch relationship",
                )
            ]
        if not isinstance(
            scope.source_epoch_relationship, DeviceFactSourceEpochRelationship
        ):
            return [
                self._gap(
                    None,
                    _GapCode.SCOPE_UNDECLARED_OR_MALFORMED,
                    "scope must declare an origin and P0.11 source/epoch relationship",
                )
            ]
        assessment_identities = [value.assessment_identity]
        transmission_identities: list[str] = []
        actual_identities: list[str] = []
        sequences: list[int] = []
        assessment_times = []
        for index, member in valid_members:
            transmission = member.transmission
            actual = member.actual
            relationship = member.source_epoch_relationship
            if (
                not isinstance(transmission, DeviceFactTransmissionIdentity)
                or not isinstance(actual, DeviceFactActualObservation)
                or not isinstance(relationship, DeviceFactSourceEpochRelationship)
            ):
                findings.append(
                    self._gap(
                        index,
                        _GapCode.MEMBER_P0_11_GAP,
                        "a P0.11 PASS member must expose immutable public "
                        "fact contracts",
                    )
                )
                continue
            assessment_identities.append(member.assessment_identity)
            transmission_identities.append(transmission.transmission_identity)
            actual_identities.append(actual.observation_identity)
            sequences.append(transmission.sequence)
            assessment_times.append(member.assessment_as_of)
            if (
                transmission.origin != scope.transmission_origin
                or relationship != scope.source_epoch_relationship
            ):
                findings.append(
                    self._gap(
                        index,
                        _GapCode.SCOPE_MISMATCH,
                        "member origin and source/epoch relationship must match scope",
                    )
                )
            if (
                member.assessment_as_of > value.assessment_as_of
                or value.assessment_as_of - member.assessment_as_of > value.maximum_age
            ):
                findings.append(
                    self._gap(
                        index,
                        _GapCode.CONTINUITY_TIME_SCOPE_INVALID,
                        "member assessment time must be fresh and non-future "
                        "at continuity as_of",
                    )
                )
        if self._has_repeated(assessment_identities):
            findings.append(
                self._gap(
                    None,
                    _GapCode.ASSESSMENT_IDENTITY_REUSED,
                    "continuity and member assessment identities must be unique",
                )
            )
        if self._has_repeated(transmission_identities):
            findings.append(
                self._gap(
                    None,
                    _GapCode.TRANSMISSION_IDENTITY_REUSED,
                    "transmission identities must be unique within one scope",
                )
            )
        if self._has_repeated(actual_identities):
            findings.append(
                self._gap(
                    None,
                    _GapCode.ACTUAL_OBSERVATION_IDENTITY_REUSED,
                    "actual observation identities must be unique within one scope",
                )
            )
        if any(later <= earlier for earlier, later in pairwise(sequences)):
            findings.append(
                self._gap(
                    None,
                    _GapCode.TRANSACTION_SEQUENCE_NOT_STRICT,
                    "transaction sequence must strictly increase within declared scope",
                )
            )
        if any(later <= earlier for earlier, later in pairwise(assessment_times)):
            findings.append(
                self._gap(
                    None,
                    _GapCode.ASSESSMENT_TIME_NOT_STRICT,
                    "member assessment times must strictly increase within "
                    "declared scope",
                )
            )
        return findings

    def evaluate(
        self, value: object
    ) -> DeviceFactCommandCorrelationContinuityAssessment:
        """Audit one finite caller input without state, I/O, or authority recovery."""

        if not isinstance(value, DeviceFactCommandCorrelationContinuityInput):
            raise TypeError("value must be DeviceFactCommandCorrelationContinuityInput")
        findings: list[DeviceFactCommandCorrelationContinuityFinding] = []
        if len(value.members) < 2:
            findings.append(
                self._gap(
                    None,
                    _GapCode.TOO_FEW_MEMBERS,
                    "at least two caller-owned P0.11 inputs are required",
                )
            )
        member_findings, valid_members = self._member_findings(value)
        findings.extend(member_findings)
        findings.extend(self._scope_and_cross_member_findings(value, valid_members))
        return self._assessment(value, findings)
