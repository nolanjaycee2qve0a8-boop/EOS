"""Synchronous P0.13 audit of two independently validated raw-input scopes."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta
from typing import cast

from edge_runtime.device_fact_command_correlation import (
    DeviceFactAcknowledgementObservation,
    DeviceFactActualObservation,
    DeviceFactCommandCorrelationAvailability,
    DeviceFactCommandCorrelationInput,
    DeviceFactSourceEpochRelationship,
    DeviceFactTransmissionIdentity,
)
from edge_runtime.device_fact_command_correlation_continuity import (
    DeterministicDeviceFactCommandCorrelationContinuityAuditor,
    DeviceFactCommandCorrelationContinuityInput,
    DeviceFactCommandCorrelationContinuityScope,
    DeviceFactCommandCorrelationContinuityStatus,
)
from edge_runtime.device_fact_command_correlation_scope_handoff.contracts import (
    DeviceFactCommandCorrelationScopeFacts,
    DeviceFactCommandCorrelationScopeHandoffAssessment,
    DeviceFactCommandCorrelationScopeHandoffDeclaration,
    DeviceFactCommandCorrelationScopeHandoffFinding,
    DeviceFactCommandCorrelationScopeHandoffGapCode,
    DeviceFactCommandCorrelationScopeHandoffInput,
    DeviceFactCommandCorrelationScopeHandoffStatus,
    _aware,
    _identity,
    _instant,
)

_Gap = DeviceFactCommandCorrelationScopeHandoffGapCode
_Finding = DeviceFactCommandCorrelationScopeHandoffFinding


def _plain_leaves(
    value: (
        DeviceFactCommandCorrelationContinuityInput
        | DeviceFactCommandCorrelationContinuityScope
        | DeviceFactCommandCorrelationInput
        | DeviceFactTransmissionIdentity
        | DeviceFactAcknowledgementObservation
        | DeviceFactActualObservation
        | DeviceFactSourceEpochRelationship
    ),
    nested: tuple[str, ...] = (),
) -> bool:
    """Inspect exact contract slots, never recurse into arbitrary caller objects.

    This is a representation gate, not a replacement for predecessor semantics.
    Exact builtin numeric values (including None) are left to P0.11 to assess.
    """
    for field in fields(value):
        if field.name in nested:
            continue
        leaf = getattr(value, field.name)
        if type(leaf) is datetime:
            if not _aware(leaf):
                return False
        elif not any(
            type(leaf) is kind
            for kind in (
                str,
                int,
                float,
                timedelta,
                type(None),
                DeviceFactCommandCorrelationAvailability,
            )
        ):
            return False
    return True


def _raw_shape(value: DeviceFactCommandCorrelationContinuityInput) -> bool:
    """Accept inert public contracts only; leave all P0.12 semantics upstream."""
    if type(value.members) is not tuple or not _plain_leaves(
        value, ("scope", "members")
    ):
        return False
    if type(value.scope) is not DeviceFactCommandCorrelationContinuityScope:
        return False
    if (
        type(value.scope.source_epoch_relationship)
        is not DeviceFactSourceEpochRelationship
    ):
        return False
    if not _plain_leaves(
        value.scope, ("source_epoch_relationship",)
    ) or not _plain_leaves(value.scope.source_epoch_relationship):
        return False
    for member in value.members:
        if type(member) is not DeviceFactCommandCorrelationInput:
            return False
        if (
            type(member.transmission) is not DeviceFactTransmissionIdentity
            or type(member.acknowledgement) is not DeviceFactAcknowledgementObservation
            or type(member.actual) is not DeviceFactActualObservation
            or type(member.source_epoch_relationship)
            is not DeviceFactSourceEpochRelationship
        ):
            return False
        if not _plain_leaves(
            member,
            ("transmission", "acknowledgement", "actual", "source_epoch_relationship"),
        ) or not all(
            _plain_leaves(fact)
            for fact in (
                member.transmission,
                member.acknowledgement,
                member.actual,
                member.source_epoch_relationship,
            )
        ):
            return False
        if not all(
            _aware(time)
            for time in (
                member.assessment_as_of,
                member.transmission.declared_at,
                member.acknowledgement.observed_at,
                member.actual.observed_at,
            )
        ):
            return False
    return _aware(value.assessment_as_of)


def _scope_known(scope: DeviceFactCommandCorrelationContinuityScope) -> bool:
    relationship = scope.source_epoch_relationship
    return (
        _identity(scope.scope_identity)
        and _identity(scope.transmission_origin)
        and type(relationship) is DeviceFactSourceEpochRelationship
        and all(
            _identity(getattr(relationship, field.name))
            for field in fields(relationship)
        )
    )


class DeterministicDeviceFactCommandCorrelationScopeHandoffAuditor:
    """No I/O, clock, registry, history, lifecycle inference or future authority."""

    __slots__ = ()

    @staticmethod
    def _assessment(
        value: DeviceFactCommandCorrelationScopeHandoffInput,
        findings: list[DeviceFactCommandCorrelationScopeHandoffFinding],
    ) -> DeviceFactCommandCorrelationScopeHandoffAssessment:
        return DeviceFactCommandCorrelationScopeHandoffAssessment(
            value.assessment_identity,
            value.assessment_as_of,
            (
                DeviceFactCommandCorrelationScopeHandoffStatus.GAP
                if findings
                else DeviceFactCommandCorrelationScopeHandoffStatus.PASS
            ),
            tuple(findings),
        )

    @staticmethod
    def _handoff(
        value: DeviceFactCommandCorrelationScopeHandoffInput,
        previous: DeviceFactCommandCorrelationContinuityInput,
        following: DeviceFactCommandCorrelationContinuityInput,
    ) -> list[DeviceFactCommandCorrelationScopeHandoffFinding]:
        findings: list[DeviceFactCommandCorrelationScopeHandoffFinding] = []
        previous_scope = cast(
            DeviceFactCommandCorrelationContinuityScope, previous.scope
        )
        next_scope = cast(DeviceFactCommandCorrelationContinuityScope, following.scope)
        if (
            previous is following
            or previous_scope.scope_identity == next_scope.scope_identity
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.DUPLICATE_SCOPE,
                    "two distinct scope identities and instances are required",
                )
            )
        declaration = value.declaration
        if type(declaration) is not DeviceFactCommandCorrelationScopeHandoffDeclaration:
            return [
                *findings,
                _Finding(
                    None,
                    _Gap.DECLARATION_MISMATCH,
                    "an explicit inert handoff declaration is required",
                ),
            ]
        if (
            type(declaration.previous_scope)
            is not DeviceFactCommandCorrelationContinuityScope
            or type(declaration.next_scope)
            is not DeviceFactCommandCorrelationContinuityScope
            or not _scope_known(declaration.previous_scope)
            or not _scope_known(declaration.next_scope)
            or declaration.previous_scope != previous_scope
            or declaration.next_scope != next_scope
            or not _scope_known(previous_scope)
            or not _scope_known(next_scope)
            or type(declaration.member_identity_relationship) is not str
            or declaration.member_identity_relationship != "distinct"
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.DECLARATION_MISMATCH,
                    "ordered scope identity, origin, source/epoch "
                    "and distinct-member relation must match exactly",
                )
            )

        earlier = cast(tuple[DeviceFactCommandCorrelationInput, ...], previous.members)
        later = cast(tuple[DeviceFactCommandCorrelationInput, ...], following.members)
        members = (*earlier, *later)
        assessment_ids = [
            value.assessment_identity,
            previous.assessment_identity,
            following.assessment_identity,
        ]
        assessment_ids.extend(member.assessment_identity for member in members)
        transmission_ids = [
            cast(
                DeviceFactTransmissionIdentity, member.transmission
            ).transmission_identity
            for member in members
        ]
        actual_ids = [
            cast(DeviceFactActualObservation, member.actual).observation_identity
            for member in members
        ]
        if any(
            not all(_identity(identity) for identity in identities)
            or len(set(identities)) != len(identities)
            for identities in (assessment_ids, transmission_ids, actual_ids)
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.IDENTITY_MISMATCH,
                    "new assessment and all member identities "
                    "must be known and distinct within their identity domains",
                )
            )

        terminal, initial = earlier[-1], later[0]
        terminal_sequence = cast(
            DeviceFactTransmissionIdentity, terminal.transmission
        ).sequence
        initial_sequence = cast(
            DeviceFactTransmissionIdentity, initial.transmission
        ).sequence
        if (
            type(declaration.previous_terminal_identity) is not str
            or type(declaration.next_initial_identity) is not str
            or type(declaration.previous_terminal_sequence) is not int
            or type(declaration.next_initial_sequence) is not int
            or not _aware(declaration.previous_terminal_as_of)
            or not _aware(declaration.next_initial_as_of)
            or (
                declaration.previous_terminal_identity,
                declaration.next_initial_identity,
                declaration.previous_terminal_sequence,
                declaration.next_initial_sequence,
                _instant(cast(datetime, declaration.previous_terminal_as_of)),
                _instant(cast(datetime, declaration.next_initial_as_of)),
            )
            != (
                terminal.assessment_identity,
                initial.assessment_identity,
                terminal_sequence,
                initial_sequence,
                _instant(terminal.assessment_as_of),
                _instant(initial.assessment_as_of),
            )
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.BOUNDARY_MISMATCH,
                    "declaration must name actual terminal and "
                    "initial member identity, sequence and assessment time",
                )
            )
        if (
            type(declaration.sequence_advance) is not int
            or declaration.sequence_advance <= 0
            or initial_sequence <= terminal_sequence
            or initial_sequence - terminal_sequence != declaration.sequence_advance
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.SEQUENCE_RELATION_INVALID,
                    "sequence must strictly increase by the exact "
                    "declared positive advance",
                )
            )
        if (
            type(declaration.time_advance) is not timedelta
            or declaration.time_advance <= timedelta(0)
            or _instant(initial.assessment_as_of) <= _instant(terminal.assessment_as_of)
            or _instant(initial.assessment_as_of) - _instant(terminal.assessment_as_of)
            != declaration.time_advance
            or max(_instant(member.assessment_as_of) for member in earlier)
            >= min(_instant(member.assessment_as_of) for member in later)
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.TIME_RELATION_INVALID,
                    "assessment time must strictly increase by "
                    "the exact declared positive advance; "
                    "the complete scope time ranges must be separated",
                )
            )
        times: tuple[datetime, ...] = (
            previous.assessment_as_of,
            following.assessment_as_of,
            *(member.assessment_as_of for member in members),
        )
        if any(
            _instant(time) > _instant(value.assessment_as_of)
            or _instant(value.assessment_as_of) - _instant(time) > value.maximum_age
            for time in times
        ):
            findings.append(
                _Finding(
                    None,
                    _Gap.TIME_SCOPE_INVALID,
                    "both scope assessments and all member times "
                    "must be fresh and non-future at handoff as_of",
                )
            )
        return findings

    def evaluate(
        self, value: object
    ) -> DeviceFactCommandCorrelationScopeHandoffAssessment:
        """Audit exactly two scopes once each, then their actual ordered boundary."""
        if type(value) is not DeviceFactCommandCorrelationScopeHandoffInput:
            raise TypeError(
                "value must be DeviceFactCommandCorrelationScopeHandoffInput"
            )
        findings: list[DeviceFactCommandCorrelationScopeHandoffFinding] = []
        if len(value.scopes) != 2:
            return self._assessment(
                value,
                [
                    _Finding(
                        None,
                        _Gap.INVALID_SCOPE,
                        "exactly two raw-input scopes are required",
                    )
                ],
            )
        accepted: list[DeviceFactCommandCorrelationContinuityInput] = []
        auditor = DeterministicDeviceFactCommandCorrelationContinuityAuditor()
        for index, facts in enumerate(value.scopes):
            if (
                type(facts) is not DeviceFactCommandCorrelationScopeFacts
                or type(facts.continuity_input)
                is not DeviceFactCommandCorrelationContinuityInput
                or not _raw_shape(facts.continuity_input)
            ):
                findings.append(
                    _Finding(
                        index,
                        _Gap.INVALID_SCOPE,
                        "scope must contain exact inert P0.12 raw "
                        "input and public P0.11 facts, never historical evidence",
                    )
                )
                continue
            raw = facts.continuity_input
            result = auditor.evaluate(raw)
            if result.status is not DeviceFactCommandCorrelationContinuityStatus.PASS:
                findings.append(
                    _Finding(
                        index,
                        _Gap.P0_12_GAP,
                        "frozen P0.12 audit returned GAP; this "
                        "scope cannot be repaired here",
                    )
                )
                continue
            accepted.append(raw)
        if findings:
            return self._assessment(value, findings)
        findings.extend(self._handoff(value, accepted[0], accepted[1]))
        return self._assessment(value, findings)
