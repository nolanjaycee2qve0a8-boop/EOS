"""Immutable command lifecycle with actual-telemetry completion evidence."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from edge_runtime.contracts import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    PowerCommand,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.validation import (
    SerializableContract,
    require_aware_datetime,
    require_exact_fields,
    require_non_negative_number,
    require_number,
    utc_isoformat,
)


class CommandLifecycleState(StrEnum):
    ISSUED = "issued"
    ACK_ACCEPTED = "ack_accepted"
    ACK_REJECTED = "ack_rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


_TERMINAL = frozenset(
    {
        CommandLifecycleState.ACK_REJECTED,
        CommandLifecycleState.COMPLETED,
        CommandLifecycleState.EXPIRED,
        CommandLifecycleState.SUPERSEDED,
    }
)
_ALLOWED = {
    CommandLifecycleState.ISSUED: frozenset(
        {
            CommandLifecycleState.ACK_ACCEPTED,
            CommandLifecycleState.ACK_REJECTED,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        }
    ),
    CommandLifecycleState.ACK_ACCEPTED: frozenset(
        {
            CommandLifecycleState.EXECUTING,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        }
    ),
    CommandLifecycleState.EXECUTING: frozenset(
        {
            CommandLifecycleState.COMPLETED,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        }
    ),
    CommandLifecycleState.ACK_REJECTED: frozenset(),
    CommandLifecycleState.COMPLETED: frozenset(),
    CommandLifecycleState.EXPIRED: frozenset(),
    CommandLifecycleState.SUPERSEDED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ExecutionCompletionEvidence(SerializableContract):
    """Derived proof that actual telemetry matched the issued final command."""

    source_command: PowerCommand
    source_telemetry: TelemetrySnapshot
    evaluated_at: datetime
    tolerance_kw: float
    actual_power_kw: float

    SCHEMA_VERSION: ClassVar[str] = "edge-execution-completion-evidence/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.source_command, PowerCommand):
            raise TypeError("source_command must be a PowerCommand")
        if not isinstance(self.source_telemetry, TelemetrySnapshot):
            raise TypeError("source_telemetry must be a TelemetrySnapshot")
        object.__setattr__(
            self,
            "evaluated_at",
            require_aware_datetime(self.evaluated_at, "evaluated_at"),
        )
        object.__setattr__(
            self,
            "tolerance_kw",
            require_non_negative_number(self.tolerance_kw, "tolerance_kw"),
        )
        if self.source_telemetry.actual_battery_power_kw is None:
            raise ValueError(
                "completion telemetry requires known actual_battery_power_kw"
            )
        object.__setattr__(
            self,
            "actual_power_kw",
            require_number(self.actual_power_kw, "actual_power_kw"),
        )
        if self.actual_power_kw != self.source_telemetry.actual_battery_power_kw:
            raise ValueError("actual_power_kw must equal source telemetry actual power")


@dataclass(frozen=True, slots=True, init=False)
class CommandLifecycleRecord(SerializableContract):
    """Read-only snapshot. Only CommandLifecycleBook creates authoritative records."""

    command: PowerCommand
    state: CommandLifecycleState
    updated_at: datetime
    acknowledgement: CommandAcknowledgement | None
    execution_started_at: datetime | None
    completion_evidence: ExecutionCompletionEvidence | None
    superseded_by_command_id: str | None

    SCHEMA_VERSION: ClassVar[str] = "edge-command-lifecycle-record/v1"

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "CommandLifecycleRecord is created only by CommandLifecycleBook"
        )

    @classmethod
    def _create(
        cls,
        command: PowerCommand,
        state: CommandLifecycleState,
        updated_at: datetime,
        acknowledgement: CommandAcknowledgement | None = None,
        execution_started_at: datetime | None = None,
        completion_evidence: ExecutionCompletionEvidence | None = None,
        superseded_by_command_id: str | None = None,
    ) -> "CommandLifecycleRecord":
        if not isinstance(command, PowerCommand) or not isinstance(
            state, CommandLifecycleState
        ):
            raise TypeError("invalid lifecycle record types")
        timestamp = require_aware_datetime(updated_at, "updated_at")
        if timestamp < command.issued_at:
            raise ValueError("updated_at must not be earlier than command issued_at")
        if state in {
            CommandLifecycleState.ACK_ACCEPTED,
            CommandLifecycleState.EXECUTING,
            CommandLifecycleState.COMPLETED,
        } and (
            acknowledgement is None
            or acknowledgement.acknowledgement_status
            not in {AcknowledgementStatus.ACCEPTED, AcknowledgementStatus.DUPLICATE}
        ):
            raise ValueError("ack_accepted requires accepted acknowledgement")
        if state is CommandLifecycleState.ACK_REJECTED and (
            acknowledgement is None
            or acknowledgement.acknowledgement_status
            in {AcknowledgementStatus.ACCEPTED, AcknowledgementStatus.DUPLICATE}
        ):
            raise ValueError("ack_rejected requires rejected acknowledgement")
        if acknowledgement is not None and (
            acknowledgement.command_id != command.command_id
            or acknowledgement.sequence != command.sequence
        ):
            raise ValueError("acknowledgement must match command identity")
        execution_started = (
            None
            if execution_started_at is None
            else require_aware_datetime(execution_started_at, "execution_started_at")
        )
        if state in {
            CommandLifecycleState.EXECUTING,
            CommandLifecycleState.COMPLETED,
        }:
            if execution_started is None:
                raise ValueError("executing record requires execution_started_at")
            if (
                acknowledgement is None
                or execution_started < acknowledgement.received_at
            ):
                raise ValueError("execution must not predate accepted acknowledgement")
            if (
                execution_started < command.not_before
                or execution_started >= command.expires_at
                or execution_started > timestamp
            ):
                raise ValueError("execution_started_at must be inside command window")
        elif execution_started is not None:
            raise ValueError("execution_started_at is only valid for executing states")
        if state is CommandLifecycleState.COMPLETED:
            if execution_started is None:
                raise ValueError("completed record requires execution_started_at")
            if (
                completion_evidence is None
                or completion_evidence.source_command is not command
            ):
                raise ValueError(
                    "completed requires matching actual completion evidence"
                )
            telemetry = completion_evidence.source_telemetry
            if (
                completion_evidence.evaluated_at != timestamp
                or telemetry.observed_at < execution_started
                or telemetry.received_at < telemetry.observed_at
                or telemetry.observed_at > timestamp
                or telemetry.received_at > timestamp
                or telemetry.observed_at >= command.expires_at
                or telemetry.received_at >= command.expires_at
            ):
                raise ValueError("completion evidence must be within execution window")
        elif completion_evidence is not None:
            raise ValueError("completion evidence is only valid for completed state")
        if state is CommandLifecycleState.SUPERSEDED:
            if (
                not isinstance(superseded_by_command_id, str)
                or not superseded_by_command_id.strip()
            ):
                raise ValueError("superseded requires successor command id")
        elif superseded_by_command_id is not None:
            raise ValueError("successor id is only valid for superseded state")
        instance = object.__new__(cls)
        for name, value in {
            "command": command,
            "state": state,
            "updated_at": timestamp,
            "acknowledgement": acknowledgement,
            "execution_started_at": execution_started,
            "completion_evidence": completion_evidence,
            "superseded_by_command_id": superseded_by_command_id,
        }.items():
            object.__setattr__(instance, name, value)
        return instance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "command": self.command.to_dict(),
            "state": self.state.value,
            "updated_at": utc_isoformat(self.updated_at),
            "acknowledgement": None
            if self.acknowledgement is None
            else self.acknowledgement.to_dict(),
            "execution_started_at": None
            if self.execution_started_at is None
            else utc_isoformat(self.execution_started_at),
            "completion_evidence": None
            if self.completion_evidence is None
            else self.completion_evidence.to_dict(),
            "superseded_by_command_id": self.superseded_by_command_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> "CommandLifecycleRecord":
        from edge_runtime.validation import parse_utc_datetime

        payload = require_exact_fields(
            value,
            "CommandLifecycleRecord",
            (
                "schema_version",
                "command",
                "state",
                "updated_at",
                "acknowledgement",
                "execution_started_at",
                "completion_evidence",
                "superseded_by_command_id",
            ),
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported CommandLifecycleRecord schema_version")
        acknowledgement_value = payload["acknowledgement"]
        completion_value = payload["completion_evidence"]
        acknowledgement = (
            None
            if acknowledgement_value is None
            else CommandAcknowledgement.from_dict(acknowledgement_value)
        )
        completion_evidence = (
            None
            if completion_value is None
            else ExecutionCompletionEvidence.from_dict(completion_value)
        )
        execution_started_value = payload["execution_started_at"]
        execution_started = (
            None
            if execution_started_value is None
            else parse_utc_datetime(execution_started_value, "execution_started_at")
        )
        if not isinstance(payload["state"], str):
            raise TypeError("state must be a string")
        successor = payload["superseded_by_command_id"]
        if successor is not None and not isinstance(successor, str):
            raise TypeError("superseded_by_command_id must be a string or None")
        command = PowerCommand.from_dict(payload["command"])
        if completion_evidence is not None:
            if completion_evidence.source_command != command:
                raise ValueError(
                    "completion evidence command must match record command"
                )
            completion_evidence = ExecutionCompletionEvidence(
                command,
                completion_evidence.source_telemetry,
                completion_evidence.evaluated_at,
                completion_evidence.tolerance_kw,
                completion_evidence.actual_power_kw,
            )
        return cls._create(
            command,
            CommandLifecycleState(payload["state"]),
            parse_utc_datetime(payload["updated_at"], "updated_at"),
            acknowledgement,
            execution_started,
            completion_evidence,
            successor,
        )


@dataclass(frozen=True, slots=True)
class RecoveryReadiness(SerializableContract):
    telemetry_fresh: bool
    capability_fresh: bool
    ready_for_new_command: bool
    reason_codes: tuple[str, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-recovery-readiness/v1"

    def __post_init__(self) -> None:
        for name in ("telemetry_fresh", "capability_fresh", "ready_for_new_command"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(item, str) or not item for item in self.reason_codes
        ):
            raise TypeError("reason_codes must be tuple[str, ...]")
        if self.ready_for_new_command and (
            not self.telemetry_fresh or not self.capability_fresh or self.reason_codes
        ):
            raise ValueError("ready recovery requires no failed checks")


@dataclass(frozen=True, slots=True)
class CommandSubmissionResult(SerializableContract):
    record: CommandLifecycleRecord
    idempotent_duplicate: bool

    SCHEMA_VERSION: ClassVar[str] = "edge-command-submission-result/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.record, CommandLifecycleRecord):
            raise TypeError("record must be a CommandLifecycleRecord")
        if not isinstance(self.idempotent_duplicate, bool):
            raise TypeError("idempotent_duplicate must be a bool")


@dataclass(frozen=True, slots=True, init=False)
class CommandLifecycleBook:
    """Only public writer for lifecycle history; no caller-supplied records."""

    records: tuple[CommandLifecycleRecord, ...]

    def __init__(self) -> None:
        object.__setattr__(self, "records", ())

    @staticmethod
    def _assert_transition_allowed(
        current_state: CommandLifecycleState,
        target_state: CommandLifecycleState,
    ) -> None:
        """Guard the state matrix; specialized methods retain all evidence checks."""
        if target_state not in _ALLOWED[current_state]:
            raise ValueError(
                f"lifecycle transition is not allowed: {current_state.value} -> "
                f"{target_state.value}"
            )

    @property
    def has_nonterminal_records(self) -> bool:
        return any(record.state not in _TERMINAL for record in self.records)

    def submit(
        self, command: PowerCommand, *, received_at: datetime, policy: TimingPolicy
    ) -> tuple["CommandLifecycleBook", CommandSubmissionResult]:
        if not isinstance(command, PowerCommand) or not isinstance(
            policy, TimingPolicy
        ):
            raise TypeError("command and policy are required contracts")
        now = require_aware_datetime(received_at, "received_at")
        existing = next(
            (
                item
                for item in self.records
                if item.command.command_id == command.command_id
            ),
            None,
        )
        if existing is not None:
            if existing.command != command:
                raise ValueError("command_id replay must preserve exact payload")
            return self, CommandSubmissionResult(existing, True)
        if any(item.command.sequence == command.sequence for item in self.records):
            raise ValueError("same sequence with a different command is rejected")
        if self.records and command.sequence <= self.records[-1].command.sequence:
            raise ValueError("sequence rollback is rejected")
        if command.issued_at > now + policy.max_clock_skew:
            raise ValueError("command issued_at exceeds max_clock_skew")
        if command.expires_at - command.issued_at > policy.max_command_lifetime:
            raise ValueError("command lifetime exceeds max_command_lifetime")
        if now >= command.expires_at:
            record = CommandLifecycleRecord._create(
                command, CommandLifecycleState.EXPIRED, now
            )
        elif now < command.not_before:
            raise ValueError("command received before not_before")
        else:
            record = CommandLifecycleRecord._create(
                command, CommandLifecycleState.ISSUED, now
            )
        book = CommandLifecycleBook()
        object.__setattr__(book, "records", (*self.records, record))
        return book, CommandSubmissionResult(record, False)

    def acknowledge(
        self, acknowledgement: CommandAcknowledgement, *, received_at: datetime
    ) -> "CommandLifecycleBook":
        if not isinstance(acknowledgement, CommandAcknowledgement):
            raise TypeError("acknowledgement must be a CommandAcknowledgement")
        now = require_aware_datetime(received_at, "received_at")
        index = next(
            (
                i
                for i, item in enumerate(self.records)
                if item.command.command_id == acknowledgement.command_id
            ),
            None,
        )
        if index is None:
            raise ValueError("acknowledgement for unknown command is rejected")
        record = self.records[index]
        if acknowledgement.sequence != record.command.sequence:
            raise ValueError("acknowledgement sequence does not match known command")
        if now >= record.command.expires_at:
            if record.state in _TERMINAL:
                return self
            self._assert_transition_allowed(record.state, CommandLifecycleState.EXPIRED)
            expired = CommandLifecycleRecord._create(
                record.command,
                CommandLifecycleState.EXPIRED,
                now,
                record.acknowledgement,
            )
            book = CommandLifecycleBook()
            object.__setattr__(
                book,
                "records",
                (*self.records[:index], expired, *self.records[index + 1 :]),
            )
            return book
        if record.state in _TERMINAL:
            return self
        if record.acknowledgement is not None:
            if record.acknowledgement == acknowledgement:
                return self
            raise ValueError("conflicting duplicate acknowledgement is rejected")
        state = (
            CommandLifecycleState.ACK_ACCEPTED
            if acknowledgement.acknowledgement_status
            in {AcknowledgementStatus.ACCEPTED, AcknowledgementStatus.DUPLICATE}
            else CommandLifecycleState.ACK_REJECTED
        )
        self._assert_transition_allowed(record.state, state)
        updated = CommandLifecycleRecord._create(
            record.command, state, now, acknowledgement
        )
        book = CommandLifecycleBook()
        object.__setattr__(
            book,
            "records",
            (*self.records[:index], updated, *self.records[index + 1 :]),
        )
        return book

    def begin_execution(
        self, command_id: str, *, at: datetime
    ) -> "CommandLifecycleBook":
        now = require_aware_datetime(at, "at")
        index = next(
            (
                i
                for i, item in enumerate(self.records)
                if item.command.command_id == command_id
            ),
            None,
        )
        if (
            index is None
            or self.records[index].state is not CommandLifecycleState.ACK_ACCEPTED
        ):
            raise ValueError("execution requires ack_accepted record")
        record = self.records[index]
        if now >= record.command.expires_at:
            self._assert_transition_allowed(record.state, CommandLifecycleState.EXPIRED)
            expired = CommandLifecycleRecord._create(
                record.command,
                CommandLifecycleState.EXPIRED,
                now,
                record.acknowledgement,
            )
            book = CommandLifecycleBook()
            object.__setattr__(
                book,
                "records",
                (*self.records[:index], expired, *self.records[index + 1 :]),
            )
            return book
        if now < record.updated_at:
            raise ValueError("execution time must not predate acknowledgement")
        self._assert_transition_allowed(record.state, CommandLifecycleState.EXECUTING)
        executing = CommandLifecycleRecord._create(
            record.command,
            CommandLifecycleState.EXECUTING,
            now,
            record.acknowledgement,
            now,
        )
        book = CommandLifecycleBook()
        object.__setattr__(
            book,
            "records",
            (*self.records[:index], executing, *self.records[index + 1 :]),
        )
        return book

    def complete(
        self,
        command_id: str,
        *,
        telemetry: TelemetrySnapshot,
        tolerance_kw: float,
        at: datetime,
    ) -> "CommandLifecycleBook":
        now = require_aware_datetime(at, "at")
        tolerance = require_non_negative_number(tolerance_kw, "tolerance_kw")
        if not isinstance(telemetry, TelemetrySnapshot):
            raise TypeError("telemetry must be a TelemetrySnapshot")
        index = next(
            (
                i
                for i, item in enumerate(self.records)
                if item.command.command_id == command_id
            ),
            None,
        )
        if (
            index is None
            or self.records[index].state is not CommandLifecycleState.EXECUTING
        ):
            raise ValueError("completion requires executing record")
        record = self.records[index]
        if now >= record.command.expires_at:
            self._assert_transition_allowed(record.state, CommandLifecycleState.EXPIRED)
            expired = CommandLifecycleRecord._create(
                record.command,
                CommandLifecycleState.EXPIRED,
                now,
                record.acknowledgement,
            )
            book = CommandLifecycleBook()
            object.__setattr__(
                book,
                "records",
                (*self.records[:index], expired, *self.records[index + 1 :]),
            )
            return book
        if now < record.updated_at:
            raise ValueError("completion time must not predate execution")
        if record.execution_started_at is None:
            raise ValueError("executing record requires execution_started_at")
        if telemetry.observed_at < record.execution_started_at:
            raise ValueError("completion telemetry predates execution boundary")
        if (
            telemetry.observed_at > now
            or telemetry.received_at > now
            or telemetry.observed_at >= record.command.expires_at
            or telemetry.received_at >= record.command.expires_at
        ):
            raise ValueError("completion telemetry must be inside completion window")
        if telemetry.actual_battery_power_kw is None:
            raise ValueError("completion requires known actual telemetry power")
        if (
            abs(
                telemetry.actual_battery_power_kw
                - record.command.requested_battery_power_kw
            )
            > tolerance
        ):
            raise ValueError("actual telemetry power is outside completion tolerance")
        evidence = ExecutionCompletionEvidence(
            record.command, telemetry, now, tolerance, telemetry.actual_battery_power_kw
        )
        self._assert_transition_allowed(record.state, CommandLifecycleState.COMPLETED)
        completed = CommandLifecycleRecord._create(
            record.command,
            CommandLifecycleState.COMPLETED,
            now,
            record.acknowledgement,
            record.execution_started_at,
            evidence,
        )
        book = CommandLifecycleBook()
        object.__setattr__(
            book,
            "records",
            (*self.records[:index], completed, *self.records[index + 1 :]),
        )
        return book

    def supersede_with(
        self,
        predecessor_command_id: str,
        *,
        successor: PowerCommand,
        at: datetime,
        policy: TimingPolicy,
    ) -> "CommandLifecycleBook":
        now = require_aware_datetime(at, "at")
        if not isinstance(successor, PowerCommand) or not isinstance(
            policy, TimingPolicy
        ):
            raise TypeError("successor and policy are required contracts")
        index = next(
            (
                i
                for i, item in enumerate(self.records)
                if item.command.command_id == predecessor_command_id
            ),
            None,
        )
        if index is None:
            raise ValueError("cannot supersede an unknown command")
        record = self.records[index]
        if record.state in _TERMINAL:
            raise ValueError("terminal command cannot be superseded")
        if now >= record.command.expires_at:
            self._assert_transition_allowed(record.state, CommandLifecycleState.EXPIRED)
            expired = CommandLifecycleRecord._create(
                record.command,
                CommandLifecycleState.EXPIRED,
                now,
                record.acknowledgement,
            )
            book = CommandLifecycleBook()
            object.__setattr__(
                book,
                "records",
                (*self.records[:index], expired, *self.records[index + 1 :]),
            )
            return book
        if now < record.updated_at:
            raise ValueError("supersede time must not predate current record")
        if successor.command_id == record.command.command_id:
            raise ValueError("command cannot supersede itself")
        if successor.sequence <= record.command.sequence:
            raise ValueError("successor sequence must strictly increase")
        if any(
            item.command.command_id == successor.command_id for item in self.records
        ):
            raise ValueError("successor command_id is already registered")
        if any(item.command.sequence == successor.sequence for item in self.records):
            raise ValueError("successor sequence is already registered")
        if self.records and successor.sequence <= self.records[-1].command.sequence:
            raise ValueError("successor sequence rollback is rejected")
        if successor.issued_at > now + policy.max_clock_skew:
            raise ValueError("successor issued_at exceeds max_clock_skew")
        if successor.expires_at - successor.issued_at > policy.max_command_lifetime:
            raise ValueError("successor lifetime exceeds max_command_lifetime")
        if now < successor.not_before or now >= successor.expires_at:
            raise ValueError("successor must be active at supersede time")
        self._assert_transition_allowed(record.state, CommandLifecycleState.SUPERSEDED)
        superseded = CommandLifecycleRecord._create(
            record.command,
            CommandLifecycleState.SUPERSEDED,
            now,
            record.acknowledgement,
            superseded_by_command_id=successor.command_id,
        )
        successor_record = CommandLifecycleRecord._create(
            successor, CommandLifecycleState.ISSUED, now
        )
        book = CommandLifecycleBook()
        object.__setattr__(
            book,
            "records",
            (
                *self.records[:index],
                superseded,
                *self.records[index + 1 :],
                successor_record,
            ),
        )
        return book

    def expire(self, *, at: datetime) -> "CommandLifecycleBook":
        now = require_aware_datetime(at, "at")
        records: list[CommandLifecycleRecord] = []
        for item in self.records:
            if item.state not in _TERMINAL and now >= item.command.expires_at:
                self._assert_transition_allowed(
                    item.state, CommandLifecycleState.EXPIRED
                )
                records.append(
                    CommandLifecycleRecord._create(
                        item.command,
                        CommandLifecycleState.EXPIRED,
                        now,
                        item.acknowledgement,
                    )
                )
            else:
                records.append(item)
        records_tuple = tuple(records)
        if records_tuple == self.records:
            return self
        book = CommandLifecycleBook()
        object.__setattr__(book, "records", records_tuple)
        return book
