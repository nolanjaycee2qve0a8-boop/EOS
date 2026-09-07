"""Pure deterministic P0.9 readiness evaluation over caller-supplied values."""

from __future__ import annotations

from edge_runtime.device_fact_readiness.contracts import (
    DeviceFactAvailability,
    DeviceFactEvidenceSample,
    DeviceFactGapCode,
    DeviceFactReadinessAssessment,
    DeviceFactReadinessFinding,
    DeviceFactReadinessInput,
    DeviceFactReadinessStatus,
    DeviceFactRequirement,
    DeviceFactRequirementPolicy,
)


class DeterministicDeviceFactReadinessEvaluator:
    """Stateless evaluator with no adapter, command, clock, or transport authority."""

    __slots__ = ()

    @staticmethod
    def _gap(
        requirement: DeviceFactRequirement,
        code: DeviceFactGapCode,
        detail: str,
    ) -> DeviceFactReadinessFinding:
        return DeviceFactReadinessFinding(
            requirement, DeviceFactReadinessStatus.GAP, code, detail
        )

    @staticmethod
    def _availability_gap(sample: DeviceFactEvidenceSample) -> DeviceFactGapCode:
        if sample.availability is DeviceFactAvailability.DISCONNECTED:
            return DeviceFactGapCode.DISCONNECTED
        if sample.availability is DeviceFactAvailability.REBOOTED:
            return DeviceFactGapCode.REBOOT_DISCONTINUITY
        return DeviceFactGapCode.AVAILABILITY_NOT_PROVEN

    def _evaluate_one(
        self,
        readiness_input: DeviceFactReadinessInput,
        policy: DeviceFactRequirementPolicy,
        sample: DeviceFactEvidenceSample,
    ) -> DeviceFactReadinessFinding:
        requirement = policy.requirement
        profile = readiness_input.profile
        if requirement not in profile.declared_requirements:
            return self._gap(
                requirement,
                DeviceFactGapCode.CAPABILITY_NOT_DECLARED,
                "profile does not declare this required fact capability",
            )
        if sample.source_identity != profile.source_identity:
            return self._gap(
                requirement,
                DeviceFactGapCode.IDENTITY_MISMATCH,
                "evidence source identity does not match the caller profile",
            )
        if sample.provenance_id != profile.provenance_id:
            return self._gap(
                requirement,
                DeviceFactGapCode.PROVENANCE_MISMATCH,
                "evidence provenance does not match the caller profile",
            )
        if sample.continuity_id != profile.continuity_id:
            return self._gap(
                requirement,
                DeviceFactGapCode.REBOOT_DISCONTINUITY,
                "evidence continuity identity does not match the caller profile",
            )
        if (
            sample.assessment_id != readiness_input.assessment_id
            or sample.evidence_set_id != readiness_input.evidence_set_id
        ):
            return self._gap(
                requirement,
                DeviceFactGapCode.FRESH_REASSESSMENT_NOT_PROVEN,
                "evidence is not explicitly bound to this caller reassessment",
            )
        if sample.availability is not DeviceFactAvailability.AVAILABLE:
            return self._gap(
                requirement,
                self._availability_gap(sample),
                "availability is not explicitly proven as available",
            )
        if sample.observed_at > readiness_input.as_of:
            return self._gap(
                requirement,
                DeviceFactGapCode.TIME_AFTER_AS_OF,
                "evidence observation time is after the caller as_of time",
            )
        if readiness_input.as_of - sample.observed_at > policy.maximum_age:
            return self._gap(
                requirement,
                DeviceFactGapCode.STALE,
                "evidence exceeds the caller-provided maximum age",
            )
        if requirement is DeviceFactRequirement.ACK_CORRELATION and (
            sample.request_id != sample.acknowledgement_request_id
            or sample.request_sequence != sample.acknowledgement_sequence
            or sample.request_correlation_id != sample.acknowledgement_correlation_id
        ):
            return self._gap(
                requirement,
                DeviceFactGapCode.ACK_CORRELATION_MISMATCH,
                "ACK correlation does not match the declared request fact",
            )
        if (
            requirement is DeviceFactRequirement.ACTUAL_TELEMETRY
            and not sample.actual_present
        ):
            return self._gap(
                requirement,
                DeviceFactGapCode.ACTUAL_NOT_PROVEN,
                "actual telemetry presence is not explicitly proven",
            )
        return DeviceFactReadinessFinding(
            requirement,
            DeviceFactReadinessStatus.PASS,
            None,
            "caller-supplied deterministic evidence satisfies this explicit "
            "requirement",
        )

    def evaluate(
        self, readiness_input: DeviceFactReadinessInput
    ) -> DeviceFactReadinessAssessment:
        """Assess one caller snapshot without reading time or external state."""

        if not isinstance(readiness_input, DeviceFactReadinessInput):
            raise TypeError("readiness_input must be a DeviceFactReadinessInput")
        policies = {policy.requirement: policy for policy in readiness_input.policies}
        samples = {sample.requirement: sample for sample in readiness_input.evidence}
        findings = tuple(
            self._evaluate_one(
                readiness_input, policies[requirement], samples[requirement]
            )
            for requirement in DeviceFactRequirement
        )
        status = (
            DeviceFactReadinessStatus.PASS
            if all(
                finding.status is DeviceFactReadinessStatus.PASS for finding in findings
            )
            else DeviceFactReadinessStatus.GAP
        )
        return DeviceFactReadinessAssessment(
            readiness_input.assessment_id,
            readiness_input.profile.profile_id,
            readiness_input.profile.source_identity,
            readiness_input.as_of,
            status,
            findings,
        )
