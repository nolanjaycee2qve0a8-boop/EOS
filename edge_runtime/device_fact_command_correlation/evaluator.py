"""Pure, deterministic P0.11 command-correlation audit evaluation."""

from __future__ import annotations

from datetime import datetime

from edge_runtime.device_fact_command_correlation.contracts import (
    DeviceFactAcknowledgementObservation,
    DeviceFactActualObservation,
    DeviceFactCommandCorrelationAssessment,
    DeviceFactCommandCorrelationAvailability,
    DeviceFactCommandCorrelationFinding,
    DeviceFactCommandCorrelationGapCode,
    DeviceFactCommandCorrelationInput,
    DeviceFactCommandCorrelationStatus,
    DeviceFactSourceEpochRelationship,
    DeviceFactTransmissionIdentity,
)

_GapCode = DeviceFactCommandCorrelationGapCode


class DeterministicDeviceFactCommandCorrelationAuditor:
    """Stateless audit-only evaluator with no command, clock, or replay authority."""

    __slots__ = ()

    @staticmethod
    def _gap(
        gap_code: DeviceFactCommandCorrelationGapCode, detail: str
    ) -> DeviceFactCommandCorrelationFinding:
        return DeviceFactCommandCorrelationFinding(gap_code, detail)

    @staticmethod
    def _assessment(
        value: DeviceFactCommandCorrelationInput,
        findings: list[DeviceFactCommandCorrelationFinding],
    ) -> DeviceFactCommandCorrelationAssessment:
        return DeviceFactCommandCorrelationAssessment(
            value.assessment_identity,
            value.assessment_as_of,
            (
                DeviceFactCommandCorrelationStatus.PASS
                if not findings
                else DeviceFactCommandCorrelationStatus.GAP
            ),
            tuple(findings),
        )

    @staticmethod
    def _is_fresh(
        value: DeviceFactCommandCorrelationInput, observed_at: datetime
    ) -> bool:
        return (
            observed_at <= value.assessment_as_of
            and value.assessment_as_of - observed_at <= value.maximum_age
        )

    def _type_findings(
        self, value: DeviceFactCommandCorrelationInput
    ) -> list[DeviceFactCommandCorrelationFinding]:
        findings: list[DeviceFactCommandCorrelationFinding] = []
        expected = (
            (value.transmission, DeviceFactTransmissionIdentity, "transmission"),
            (
                value.acknowledgement,
                DeviceFactAcknowledgementObservation,
                "acknowledgement",
            ),
            (value.actual, DeviceFactActualObservation, "actual observation"),
            (
                value.source_epoch_relationship,
                DeviceFactSourceEpochRelationship,
                "source/epoch relationship",
            ),
        )
        for fact, fact_type, label in expected:
            if isinstance(fact, DeviceFactCommandCorrelationAssessment):
                findings.append(
                    self._gap(
                        DeviceFactCommandCorrelationGapCode.MALFORMED_OR_HISTORICAL_FACT,
                        f"historical assessment cannot be {label} input",
                    )
                )
            elif not isinstance(fact, fact_type):
                if fact_type is DeviceFactSourceEpochRelationship:
                    gap_code = _GapCode.SOURCE_EPOCH_RELATIONSHIP_UNDECLARED
                else:
                    gap_code = (
                        DeviceFactCommandCorrelationGapCode.MALFORMED_OR_HISTORICAL_FACT
                    )
                findings.append(
                    self._gap(gap_code, f"{label} is not a caller-owned inert fact")
                )
        return findings

    def _identity_and_time_findings(
        self,
        value: DeviceFactCommandCorrelationInput,
        transmission: DeviceFactTransmissionIdentity,
        acknowledgement: DeviceFactAcknowledgementObservation,
        actual: DeviceFactActualObservation,
    ) -> list[DeviceFactCommandCorrelationFinding]:
        findings: list[DeviceFactCommandCorrelationFinding] = []
        identities = (
            value.assessment_identity,
            transmission.transmission_identity,
            actual.observation_identity,
        )
        if len(set(identities)) != len(identities):
            findings.append(
                self._gap(
                    DeviceFactCommandCorrelationGapCode.ASSESSMENT_IDENTITY_REUSED,
                    "assessment, transmission, and actual identities must differ",
                )
            )
        timestamps = (
            transmission.declared_at,
            acknowledgement.observed_at,
            actual.observed_at,
        )
        if (
            any(not self._is_fresh(value, timestamp) for timestamp in timestamps)
            or acknowledgement.observed_at < transmission.declared_at
            or actual.observed_at < transmission.declared_at
        ):
            findings.append(
                self._gap(
                    DeviceFactCommandCorrelationGapCode.TIME_SCOPE_INVALID,
                    "facts must be fresh, non-future, and not precede transmission "
                    "declaration",
                )
            )
        return findings

    def _acknowledgement_findings(
        self,
        transmission: DeviceFactTransmissionIdentity,
        acknowledgement: DeviceFactAcknowledgementObservation,
    ) -> list[DeviceFactCommandCorrelationFinding]:
        findings: list[DeviceFactCommandCorrelationFinding] = []
        if (
            acknowledgement.availability
            is not DeviceFactCommandCorrelationAvailability.AVAILABLE
        ):
            findings.append(
                self._gap(
                    DeviceFactCommandCorrelationGapCode.ACKNOWLEDGEMENT_UNAVAILABLE,
                    "acknowledgement availability is explicit GAP, never completion "
                    "evidence",
                )
            )
        if (
            acknowledgement.transmission_identity != transmission.transmission_identity
            or acknowledgement.sequence != transmission.sequence
            or acknowledgement.origin != transmission.origin
        ):
            findings.append(
                self._gap(
                    DeviceFactCommandCorrelationGapCode.ACKNOWLEDGEMENT_CORRELATION_MISMATCH,
                    "acknowledgement identity, sequence, and origin must exactly match "
                    "transmission",
                )
            )
        return findings

    def _relationship_findings(
        self,
        transmission: DeviceFactTransmissionIdentity,
        acknowledgement: DeviceFactAcknowledgementObservation,
        actual: DeviceFactActualObservation,
        relationship: DeviceFactSourceEpochRelationship,
    ) -> list[DeviceFactCommandCorrelationFinding]:
        declared = (
            (
                relationship.transmission_source_identity,
                relationship.transmission_identity_epoch,
            ),
            (
                relationship.acknowledgement_source_identity,
                relationship.acknowledgement_identity_epoch,
            ),
            (relationship.actual_source_identity, relationship.actual_identity_epoch),
        )
        observed = (
            (transmission.source_identity, transmission.identity_epoch),
            (acknowledgement.source_identity, acknowledgement.identity_epoch),
            (actual.source_identity, actual.identity_epoch),
        )
        if declared != observed:
            return [
                self._gap(
                    DeviceFactCommandCorrelationGapCode.SOURCE_EPOCH_RELATIONSHIP_MISMATCH,
                    "every source/epoch fact must exactly match the caller-declared "
                    "relationship",
                )
            ]
        return []

    def _actual_findings(
        self, actual: DeviceFactActualObservation
    ) -> list[DeviceFactCommandCorrelationFinding]:
        if (
            actual.availability
            is not DeviceFactCommandCorrelationAvailability.AVAILABLE
            or actual.actual_power_kw is None
        ):
            return [
                self._gap(
                    DeviceFactCommandCorrelationGapCode.ACTUAL_UNAVAILABLE,
                    "actual observation is explicit GAP and cannot be inferred from "
                    "acknowledgement",
                )
            ]
        return []

    def evaluate(self, value: object) -> DeviceFactCommandCorrelationAssessment:
        """Audit one finite caller input without state, I/O, or authority recovery."""

        if not isinstance(value, DeviceFactCommandCorrelationInput):
            raise TypeError("value must be DeviceFactCommandCorrelationInput")
        findings = self._type_findings(value)
        if findings:
            return self._assessment(value, findings)
        transmission = value.transmission
        acknowledgement = value.acknowledgement
        actual = value.actual
        relationship = value.source_epoch_relationship
        assert isinstance(transmission, DeviceFactTransmissionIdentity)
        assert isinstance(acknowledgement, DeviceFactAcknowledgementObservation)
        assert isinstance(actual, DeviceFactActualObservation)
        assert isinstance(relationship, DeviceFactSourceEpochRelationship)
        findings.extend(
            self._identity_and_time_findings(
                value, transmission, acknowledgement, actual
            )
        )
        findings.extend(self._acknowledgement_findings(transmission, acknowledgement))
        findings.extend(
            self._relationship_findings(
                transmission, acknowledgement, actual, relationship
            )
        )
        findings.extend(self._actual_findings(actual))
        return self._assessment(value, findings)
