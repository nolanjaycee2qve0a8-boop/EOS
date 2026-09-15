"""Pure, deterministic P0.10 lifecycle-continuity audit evaluation."""

from __future__ import annotations

from datetime import datetime

from edge_runtime.device_fact_lifecycle_continuity.contracts import (
    DeviceFactLifecycleAssessment,
    DeviceFactLifecycleAvailability,
    DeviceFactLifecycleContinuityInput,
    DeviceFactLifecycleFinding,
    DeviceFactLifecycleGapCode,
    DeviceFactLifecycleSnapshot,
    DeviceFactLifecycleStatus,
    DeviceFactLifecycleTransition,
)


class DeterministicDeviceFactLifecycleContinuityEvaluator:
    """Stateless audit evaluator with no clock, authority, or replay capability."""

    __slots__ = ()

    @staticmethod
    def _gap(
        transition_index: int | None,
        gap_code: DeviceFactLifecycleGapCode,
        detail: str,
    ) -> DeviceFactLifecycleFinding:
        return DeviceFactLifecycleFinding(transition_index, gap_code, detail)

    @staticmethod
    def _assessment(
        assessment_identity: str,
        assessment_as_of: datetime,
        findings: list[DeviceFactLifecycleFinding],
    ) -> DeviceFactLifecycleAssessment:
        return DeviceFactLifecycleAssessment(
            assessment_identity,
            assessment_as_of,
            (
                DeviceFactLifecycleStatus.PASS
                if not findings
                else DeviceFactLifecycleStatus.GAP
            ),
            tuple(findings),
        )

    @staticmethod
    def _has_complete_ack_and_actual(snapshot: DeviceFactLifecycleSnapshot) -> bool:
        fields = (
            snapshot.request_id,
            snapshot.request_sequence,
            snapshot.request_correlation_id,
            snapshot.acknowledgement_request_id,
            snapshot.acknowledgement_sequence,
            snapshot.acknowledgement_correlation_id,
        )
        if any(value is None for value in fields):
            return False
        if snapshot.actual_present is not True:
            return False
        if not all(
            isinstance(value, str) and value
            for value in (fields[0], fields[2], fields[3], fields[5])
        ):
            return False
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (fields[1], fields[4])
        ):
            return False
        return (
            snapshot.request_id == snapshot.acknowledgement_request_id
            and snapshot.request_sequence == snapshot.acknowledgement_sequence
            and snapshot.request_correlation_id
            == snapshot.acknowledgement_correlation_id
        )

    @staticmethod
    def _is_fresh(
        input_value: DeviceFactLifecycleContinuityInput,
        snapshot: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            snapshot.observed_at <= input_value.assessment_as_of
            and input_value.assessment_as_of - snapshot.observed_at
            <= input_value.maximum_age
        )

    def _historical_rejection(
        self, value: DeviceFactLifecycleAssessment
    ) -> DeviceFactLifecycleAssessment:
        return DeviceFactLifecycleAssessment(
            "rejected-historical-assessment",
            value.assessment_as_of,
            DeviceFactLifecycleStatus.GAP,
            (
                self._gap(
                    None,
                    DeviceFactLifecycleGapCode.HISTORICAL_ASSESSMENT_INPUT_REJECTED,
                    "a historical lifecycle assessment cannot be a new audit input",
                ),
            ),
        )

    def _validate_identity(
        self, input_value: DeviceFactLifecycleContinuityInput
    ) -> list[DeviceFactLifecycleFinding]:
        findings: list[DeviceFactLifecycleFinding] = []
        identities = [input_value.assessment_identity]
        for index, snapshot in enumerate(input_value.snapshots):
            if isinstance(snapshot, DeviceFactLifecycleAssessment):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.HISTORICAL_ASSESSMENT_INPUT_REJECTED,
                        "a historical lifecycle assessment cannot appear in snapshots",
                    )
                )
                continue
            if not isinstance(snapshot, DeviceFactLifecycleSnapshot):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.HISTORICAL_ASSESSMENT_INPUT_REJECTED,
                        "snapshot is not a caller-owned lifecycle fact value",
                    )
                )
                continue
            identities.extend((snapshot.snapshot_identity, snapshot.evidence_identity))
        if len(set(identities)) != len(identities):
            findings.append(
                self._gap(
                    None,
                    DeviceFactLifecycleGapCode.ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED,
                    "assessment, snapshot, and evidence identities must be unique",
                )
            )
        return findings

    def _transition_findings(
        self, input_value: DeviceFactLifecycleContinuityInput
    ) -> list[DeviceFactLifecycleFinding]:
        snapshots = input_value.snapshots
        findings: list[DeviceFactLifecycleFinding] = []
        if len(input_value.transitions) != len(snapshots) - 1:
            return [
                self._gap(
                    None,
                    DeviceFactLifecycleGapCode.UNLABELLED_OR_UNKNOWN_TRANSITION,
                    "exactly one closed-set transition label is required per pair",
                )
            ]
        for index, label in enumerate(input_value.transitions):
            prior = snapshots[index]
            current = snapshots[index + 1]
            if not isinstance(label, DeviceFactLifecycleTransition):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.UNLABELLED_OR_UNKNOWN_TRANSITION,
                        "transition label is absent, duplicated, or unknown",
                    )
                )
                continue
            if not isinstance(prior, DeviceFactLifecycleSnapshot) or not isinstance(
                current, DeviceFactLifecycleSnapshot
            ):
                continue
            if label is DeviceFactLifecycleTransition.CONTINUITY:
                if not self._is_valid_continuity(input_value, prior, current):
                    findings.append(
                        self._gap(
                            index,
                            DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                            "continuity requires available same-epoch fresh facts",
                        )
                    )
            elif label is DeviceFactLifecycleTransition.DISCONNECT:
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.DISCONNECT_RECORDED,
                        "declared disconnect remains an explicit lifecycle GAP",
                    )
                )
                if not self._is_valid_disconnect(prior, current):
                    findings.append(
                        self._gap(
                            index,
                            DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                            "disconnect requires same source/epoch and increasing time",
                        )
                    )
            elif label is DeviceFactLifecycleTransition.REBOOT:
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.REBOOT_RECORDED,
                        "declared reboot remains an explicit lifecycle GAP",
                    )
                )
                if not self._is_valid_reboot(prior, current):
                    findings.append(
                        self._gap(
                            index,
                            DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                            "reboot requires same source/new epoch/increasing time",
                        )
                    )
            elif label is DeviceFactLifecycleTransition.IDENTITY_EPOCH_CHANGE:
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.IDENTITY_EPOCH_DISCONTINUITY,
                        "declared identity epoch change remains an explicit GAP",
                    )
                )
                if not self._is_valid_identity_epoch_change(prior, current):
                    findings.append(
                        self._gap(
                            index,
                            DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                            "epoch change requires source/new-epoch/time ordering",
                        )
                    )
            elif label is DeviceFactLifecycleTransition.TIME_DISCONTINUITY:
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.TIME_DISCONTINUITY_RECORDED,
                        "declared time discontinuity remains an explicit GAP",
                    )
                )
                if not self._is_valid_time_discontinuity(input_value, prior, current):
                    findings.append(
                        self._gap(
                            index,
                            DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                            "time discontinuity requires an invalid time relation",
                        )
                    )
            elif not self._is_valid_reconnect(input_value, index, prior, current):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.RECONNECT_PRECONDITION_UNMET,
                        "reconnect requires an immediate declared discontinuity",
                    )
                )
        return findings

    def _available_fact_findings(
        self, input_value: DeviceFactLifecycleContinuityInput
    ) -> list[DeviceFactLifecycleFinding]:
        """Validate every declared available fact without inferring availability."""

        findings: list[DeviceFactLifecycleFinding] = []
        for index, snapshot in enumerate(input_value.snapshots):
            if not isinstance(snapshot, DeviceFactLifecycleSnapshot):
                continue
            if snapshot.availability is not DeviceFactLifecycleAvailability.AVAILABLE:
                continue
            if not self._has_complete_ack_and_actual(snapshot):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.ACK_ACTUAL_FACT_MISSING_OR_FUSED,
                        "available facts require exact ACK correlation and actual",
                    )
                )
            if not self._is_fresh(input_value, snapshot):
                findings.append(
                    self._gap(
                        index,
                        DeviceFactLifecycleGapCode.CONTINUITY_FACT_MISMATCH,
                        "available facts must be fresh at assessment time",
                    )
                )
        return findings

    @staticmethod
    def _is_valid_disconnect(
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            current.availability is DeviceFactLifecycleAvailability.DISCONNECTED
            and prior.source_identity == current.source_identity
            and prior.identity_epoch == current.identity_epoch
            and prior.observed_at < current.observed_at
        )

    @staticmethod
    def _is_valid_reboot(
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            current.availability is DeviceFactLifecycleAvailability.REBOOTED
            and prior.source_identity == current.source_identity
            and prior.identity_epoch != current.identity_epoch
            and prior.observed_at < current.observed_at
        )

    @staticmethod
    def _is_valid_identity_epoch_change(
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            prior.source_identity == current.source_identity
            and prior.identity_epoch != current.identity_epoch
            and prior.observed_at < current.observed_at
        )

    def _is_valid_time_discontinuity(
        self,
        input_value: DeviceFactLifecycleContinuityInput,
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            prior.observed_at >= current.observed_at
            or not self._is_fresh(input_value, prior)
            or not self._is_fresh(input_value, current)
        )

    def _is_valid_continuity(
        self,
        input_value: DeviceFactLifecycleContinuityInput,
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        return (
            prior.availability is DeviceFactLifecycleAvailability.AVAILABLE
            and current.availability is DeviceFactLifecycleAvailability.AVAILABLE
            and prior.source_identity == current.source_identity
            and prior.identity_epoch == current.identity_epoch
            and prior.observed_at < current.observed_at
            and self._is_fresh(input_value, prior)
            and self._is_fresh(input_value, current)
            and self._has_complete_ack_and_actual(prior)
            and self._has_complete_ack_and_actual(current)
        )

    def _is_valid_reconnect(
        self,
        input_value: DeviceFactLifecycleContinuityInput,
        index: int,
        prior: DeviceFactLifecycleSnapshot,
        current: DeviceFactLifecycleSnapshot,
    ) -> bool:
        if index == 0:
            return False
        preceding = input_value.transitions[index - 1]
        return (
            preceding
            in {
                DeviceFactLifecycleTransition.DISCONNECT,
                DeviceFactLifecycleTransition.REBOOT,
                DeviceFactLifecycleTransition.IDENTITY_EPOCH_CHANGE,
            }
            and current.availability is DeviceFactLifecycleAvailability.AVAILABLE
            and prior.source_identity == current.source_identity
            and prior.identity_epoch != current.identity_epoch
            and prior.observed_at < current.observed_at
            and self._is_fresh(input_value, current)
            and self._has_complete_ack_and_actual(current)
        )

    def evaluate(self, value: object) -> DeviceFactLifecycleAssessment:
        """Audit one explicit finite input without reading state or external facts."""

        if isinstance(value, DeviceFactLifecycleAssessment):
            return self._historical_rejection(value)
        if not isinstance(value, DeviceFactLifecycleContinuityInput):
            raise TypeError("value must be DeviceFactLifecycleContinuityInput")
        findings = self._validate_identity(value)
        findings.extend(self._available_fact_findings(value))
        findings.extend(self._transition_findings(value))
        return self._assessment(
            value.assessment_identity, value.assessment_as_of, findings
        )
