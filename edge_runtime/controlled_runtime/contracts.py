"""Immutable, serializable P0.3 audit evidence; never runtime authority."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from edge_runtime.contracts import AcknowledgementStatus, PowerCommand, RuntimeState
from edge_runtime.device_simulator import DeviceSimulatorStep
from edge_runtime.lifecycle import (
    CommandLifecycleRecord,
    CommandLifecycleState,
    ExecutionCompletionEvidence,
)
from edge_runtime.validation import (
    SerializableContract,
    require_aware_datetime,
    require_non_empty_string,
    require_non_negative_int,
    require_non_negative_number,
    require_number,
)


class ReconciliationStatus(StrEnum):
    """One primary P0.3 actual-execution classification."""

    IDLE_NO_COMMAND = "idle_no_command"
    SAFETY_BLOCKED = "safety_blocked"
    ACK_REJECTED = "ack_rejected"
    ACK_MISSING = "ack_missing"
    ACK_DELAYED = "ack_delayed"
    COMMAND_EXPIRED = "command_expired"
    APPLICATION_NOT_AUTHORIZED = "application_not_authorized"
    ACTUAL_UNKNOWN = "actual_unknown"
    ACTUAL_MATCHED = "actual_matched"
    ACTUAL_MISMATCH = "actual_mismatch"
    UNEXPECTED_ACTUAL = "unexpected_actual"
    LIFECYCLE_INCOMPLETE = "lifecycle_incomplete"
    COMPLETED = "completed"

    # Stage-2A compatibility names. Serialization uses the stable values above.
    IDLE = IDLE_NO_COMMAND
    SAFE_REQUEST_BLOCKED = SAFETY_BLOCKED
    ACK_ACCEPTED_ACTUAL_MISMATCH = ACTUAL_MISMATCH
    COMPLETED_FROM_MATCHING_ACTUAL = COMPLETED


class CommandOrigin(StrEnum):
    """The only permitted P0.3 sources for an admitted tick command."""

    NONE = "none"
    CURRENT_CALLER = "current_caller"


_REASON_PRECEDENCE = {
    ReconciliationStatus.UNEXPECTED_ACTUAL.value: 0,
    ReconciliationStatus.ACTUAL_UNKNOWN.value: 1,
    ReconciliationStatus.ACTUAL_MISMATCH.value: 2,
    ReconciliationStatus.COMMAND_EXPIRED.value: 3,
    ReconciliationStatus.ACK_REJECTED.value: 4,
    ReconciliationStatus.ACK_DELAYED.value: 5,
    ReconciliationStatus.ACK_MISSING.value: 6,
    ReconciliationStatus.APPLICATION_NOT_AUTHORIZED.value: 7,
    ReconciliationStatus.LIFECYCLE_INCOMPLETE.value: 8,
    ReconciliationStatus.SAFETY_BLOCKED.value: 9,
    ReconciliationStatus.COMPLETED.value: 10,
    ReconciliationStatus.ACTUAL_MATCHED.value: 11,
    ReconciliationStatus.IDLE_NO_COMMAND.value: 12,
}


def canonical_reconciliation_reason_codes(
    reasons: set[ReconciliationStatus],
) -> tuple[str, ...]:
    """Return the one deterministic primary-and-secondary reason ordering."""
    if not reasons:
        raise ValueError("at least one reconciliation reason is required")
    return tuple(
        sorted(
            (item.value for item in reasons),
            key=lambda item: _REASON_PRECEDENCE[item],
        )
    )


def _optional_number(value: object, field_name: str) -> float | None:
    return None if value is None else require_number(value, field_name)


def _optional_non_negative_number(value: object, field_name: str) -> float | None:
    return None if value is None else require_non_negative_number(value, field_name)


@dataclass(frozen=True, slots=True)
class LifecycleEvidence(SerializableContract):
    """Serialized lifecycle facts, deliberately not a writable lifecycle book."""

    records: tuple[CommandLifecycleRecord, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-runtime-lifecycle-evidence/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(item, CommandLifecycleRecord) for item in self.records
        ):
            raise TypeError("records must be tuple[CommandLifecycleRecord, ...]")


@dataclass(frozen=True, slots=True)
class CommandReconciliation(SerializableContract):
    """Ordered evidence separating request, ACK, expectation and simulator actual."""

    status: ReconciliationStatus
    primary_reason: str
    reason_codes: tuple[str, ...]
    command_id: str | None
    command_sequence: int | None
    requested_power_kw: float | None
    final_safe_request_power_kw: float | None
    acknowledgement_status: AcknowledgementStatus | None
    acknowledged_power_kw: float | None
    acknowledgement_received_at: datetime | None
    command_application_authorized: bool
    actual_power_kw: float | None
    expected_actual_power_kw: float | None
    absolute_deviation_kw: float | None
    tolerance_kw: float
    lifecycle_state_before: CommandLifecycleState | None
    lifecycle_state_after: CommandLifecycleState | None
    completion_evidence: ExecutionCompletionEvidence | None
    fail_closed: bool

    SCHEMA_VERSION: ClassVar[str] = "edge-runtime-command-reconciliation/v2"

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReconciliationStatus):
            raise TypeError("status must be a ReconciliationStatus")
        object.__setattr__(
            self,
            "primary_reason",
            require_non_empty_string(self.primary_reason, "primary_reason"),
        )
        if self.primary_reason != self.status.value:
            raise ValueError("primary_reason must equal status.value")
        if not isinstance(self.reason_codes, tuple) or not self.reason_codes:
            raise TypeError("reason_codes must be a non-empty tuple[str, ...]")
        if any(
            not isinstance(item, str) or item not in _REASON_PRECEDENCE
            for item in self.reason_codes
        ):
            raise ValueError("reason_codes must contain known reconciliation reasons")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must not contain duplicates")
        if self.reason_codes[0] != self.primary_reason:
            raise ValueError("primary_reason must be the first reason code")
        canonical = canonical_reconciliation_reason_codes(
            {ReconciliationStatus(item) for item in self.reason_codes}
        )
        if canonical != self.reason_codes:
            raise ValueError("reason_codes must use canonical precedence order")
        if self.command_id is None:
            if self.command_sequence is not None:
                raise ValueError("command_sequence requires command_id")
        else:
            object.__setattr__(
                self,
                "command_id",
                require_non_empty_string(self.command_id, "command_id"),
            )
            object.__setattr__(
                self,
                "command_sequence",
                require_non_negative_int(self.command_sequence, "command_sequence"),
            )
        for name in (
            "requested_power_kw",
            "final_safe_request_power_kw",
            "acknowledged_power_kw",
            "actual_power_kw",
            "expected_actual_power_kw",
        ):
            object.__setattr__(self, name, _optional_number(getattr(self, name), name))
        object.__setattr__(
            self,
            "absolute_deviation_kw",
            _optional_non_negative_number(
                self.absolute_deviation_kw, "absolute_deviation_kw"
            ),
        )
        object.__setattr__(
            self,
            "tolerance_kw",
            require_non_negative_number(self.tolerance_kw, "tolerance_kw"),
        )
        if self.acknowledgement_status is not None and not isinstance(
            self.acknowledgement_status, AcknowledgementStatus
        ):
            raise TypeError("acknowledgement_status must be an AcknowledgementStatus")
        if self.acknowledgement_received_at is not None:
            object.__setattr__(
                self,
                "acknowledgement_received_at",
                require_aware_datetime(
                    self.acknowledgement_received_at,
                    "acknowledgement_received_at",
                ),
            )
        if not isinstance(self.command_application_authorized, bool):
            raise TypeError("command_application_authorized must be a bool")
        for name in ("lifecycle_state_before", "lifecycle_state_after"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, CommandLifecycleState):
                raise TypeError(f"{name} must be a CommandLifecycleState")
        if self.completion_evidence is not None and not isinstance(
            self.completion_evidence, ExecutionCompletionEvidence
        ):
            raise TypeError("completion_evidence must be ExecutionCompletionEvidence")
        if not isinstance(self.fail_closed, bool):
            raise TypeError("fail_closed must be a bool")
        if (
            self.actual_power_kw is not None
            and self.expected_actual_power_kw is not None
        ):
            expected = abs(self.actual_power_kw - self.expected_actual_power_kw)
            if self.absolute_deviation_kw != expected:
                raise ValueError("absolute_deviation_kw must match actual and expected")
        elif self.absolute_deviation_kw is not None:
            raise ValueError("absolute_deviation_kw requires actual and expected power")
        if self.status is ReconciliationStatus.COMPLETED and (
            self.completion_evidence is None
            or self.lifecycle_state_after is not CommandLifecycleState.COMPLETED
        ):
            raise ValueError(
                "completed reconciliation requires lifecycle completion evidence"
            )


@dataclass(frozen=True, slots=True)
class RuntimeLoopStep(SerializableContract):
    """One fully serializable P0.3 tick record without executable authority."""

    tick_index: int
    started_at: datetime
    ended_at: datetime
    state_before: RuntimeState
    state_after: RuntimeState
    caller_command: PowerCommand | None
    admitted_command: PowerCommand | None
    command_origin: CommandOrigin
    automatic_command_generated: bool
    device_step: DeviceSimulatorStep
    lifecycle_before: LifecycleEvidence
    lifecycle_after: LifecycleEvidence
    reconciliation: CommandReconciliation
    transition_reasons: tuple[str, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-runtime-loop-step/v3"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "tick_index", require_non_negative_int(self.tick_index, "tick_index")
        )
        for name in ("started_at", "ended_at"):
            object.__setattr__(
                self, name, require_aware_datetime(getattr(self, name), name)
            )
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be later than started_at")
        if not isinstance(self.state_before, RuntimeState) or not isinstance(
            self.state_after, RuntimeState
        ):
            raise TypeError("runtime states are required")
        if self.caller_command is not None and not isinstance(
            self.caller_command, PowerCommand
        ):
            raise TypeError("caller_command must be PowerCommand or None")
        if self.admitted_command is not None and not isinstance(
            self.admitted_command, PowerCommand
        ):
            raise TypeError("admitted_command must be PowerCommand or None")
        if not isinstance(self.command_origin, CommandOrigin):
            raise TypeError("command_origin must be a CommandOrigin")
        if not isinstance(self.automatic_command_generated, bool):
            raise TypeError("automatic_command_generated must be a bool")
        if self.automatic_command_generated:
            raise ValueError("P0.3 evidence must not contain automatic commands")
        if self.admitted_command is None:
            if self.command_origin is not CommandOrigin.NONE:
                raise ValueError("no admitted command requires command_origin none")
        else:
            if self.command_origin is not CommandOrigin.CURRENT_CALLER:
                raise ValueError("admitted command must originate from current caller")
            if (
                self.caller_command is None
                or self.admitted_command != self.caller_command
            ):
                raise ValueError("admitted command must preserve caller payload")
        if not isinstance(self.device_step, DeviceSimulatorStep):
            raise TypeError("device_step must be a DeviceSimulatorStep")
        if self.device_step.command != self.admitted_command:
            raise ValueError("device step command must equal admitted command")
        if not isinstance(self.lifecycle_before, LifecycleEvidence) or not isinstance(
            self.lifecycle_after, LifecycleEvidence
        ):
            raise TypeError("lifecycle evidence is required")
        if not isinstance(self.reconciliation, CommandReconciliation):
            raise TypeError("reconciliation is required")
        if not isinstance(self.transition_reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.transition_reasons
        ):
            raise TypeError("transition_reasons must be tuple[str, ...]")
        if len(set(self.transition_reasons)) != len(self.transition_reasons):
            raise ValueError("transition_reasons must not contain duplicates")


@dataclass(frozen=True, slots=True)
class RuntimeLoopTrace(SerializableContract):
    """Linked immutable evidence chain; it cannot recreate a runtime service."""

    steps: tuple[RuntimeLoopStep, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-runtime-loop-trace/v3"

    def __post_init__(self) -> None:
        if not isinstance(self.steps, tuple) or any(
            not isinstance(item, RuntimeLoopStep) for item in self.steps
        ):
            raise TypeError("steps must be tuple[RuntimeLoopStep, ...]")
        for index, step in enumerate(self.steps):
            if step.tick_index != index:
                raise ValueError("trace tick_index must be contiguous from zero")
            if index:
                previous = self.steps[index - 1]
                if previous.ended_at != step.started_at:
                    raise ValueError("trace timestamps must be contiguous")
                if previous.state_after is not step.state_before:
                    raise ValueError("trace runtime states must link")
                if (
                    previous.device_step.ending_soc_fraction
                    != step.device_step.starting_soc_fraction
                ):
                    raise ValueError("trace SOC evidence must link")
