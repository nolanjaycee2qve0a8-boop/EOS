"""Test-only P0.8 audit consumer over frozen P0.7/P0.6 contracts.

The harness has no transport, command, retry, or recovery authority.  It calls
the existing P0.7 public session once and compares its immutable audit evidence
to caller-supplied deterministic P0.4-style transcript facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import NoReturn, SupportsIndex

from edge_runtime.controlled_composition import ControlledEdgeCompositionEvidence
from edge_runtime.controlled_composition_session import (
    ControlledCompositionSession,
    ControlledCompositionSessionContinuation,
    ControlledCompositionSessionCycleInput,
    ControlledCompositionSessionFailureError,
)
from edge_runtime.device_adapter import (
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceObservation,
    DeviceTransmissionEvidence,
)
from ems_strategy.edge_command_handoff import EdgeCommandMetadata
from ems_strategy.feasibility import FeasibleDecision


def _reject_copy_or_serialization(name: str) -> NoReturn:
    raise TypeError(f"{name} cannot be copied or serialized")


class AdapterConformanceTranscriptKind(Enum):
    """The only ordered fact kinds accepted by the deterministic harness."""

    OBSERVATION = "observation"
    TRANSMISSION = "transmission"
    ACKNOWLEDGEMENT = "acknowledgement"
    ACTUAL_TELEMETRY = "actual_telemetry"


TranscriptValue = (
    DeviceObservation
    | DeviceTransmissionEvidence
    | DeviceAckObservation
    | DeviceActualTelemetryObservation
)


@dataclass(frozen=True, slots=True)
class AdapterConformanceTranscriptFact:
    """One non-executable caller-supplied fact in an explicit test transcript."""

    kind: AdapterConformanceTranscriptKind
    value: TranscriptValue

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AdapterConformanceTranscriptKind):
            raise TypeError("kind must be an AdapterConformanceTranscriptKind")
        expected_types: dict[AdapterConformanceTranscriptKind, type[object]] = {
            AdapterConformanceTranscriptKind.OBSERVATION: DeviceObservation,
            AdapterConformanceTranscriptKind.TRANSMISSION: DeviceTransmissionEvidence,
            AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT: DeviceAckObservation,
            AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY: (
                DeviceActualTelemetryObservation
            ),
        }
        if not isinstance(self.value, expected_types[self.kind]):
            raise TypeError(f"{self.kind.value} transcript fact has an invalid value")


@dataclass(frozen=True, slots=True)
class AdapterConformanceTranscript:
    """Finite, ordered audit facts; never an adapter, request, or command source."""

    facts: tuple[AdapterConformanceTranscriptFact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple) or not self.facts:
            raise TypeError("facts must be a non-empty tuple of transcript facts")
        if any(
            not isinstance(fact, AdapterConformanceTranscriptFact)
            for fact in self.facts
        ):
            raise TypeError("facts must be transcript facts")
        kinds = tuple(fact.kind for fact in self.facts)
        admitted = (
            AdapterConformanceTranscriptKind.OBSERVATION,
            AdapterConformanceTranscriptKind.TRANSMISSION,
            AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT,
            AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY,
        )
        non_admitted = (
            AdapterConformanceTranscriptKind.OBSERVATION,
            AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT,
            AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY,
        )
        if kinds not in (admitted, non_admitted):
            raise ValueError("transcript facts must be ordered and non-duplicated")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


@dataclass(frozen=True, slots=True)
class AdapterConformanceCycleInput:
    """Current-caller P0.7 inputs plus one non-authoritative test transcript."""

    session: ControlledCompositionSession
    continuation: ControlledCompositionSessionContinuation
    feasible_decision: FeasibleDecision
    metadata: EdgeCommandMetadata
    duration: timedelta
    tolerance_kw: float
    transcript: AdapterConformanceTranscript

    def __post_init__(self) -> None:
        if not isinstance(self.session, ControlledCompositionSession):
            raise TypeError("session must be a ControlledCompositionSession")
        if not isinstance(self.continuation, ControlledCompositionSessionContinuation):
            raise TypeError(
                "continuation must be a ControlledCompositionSessionContinuation"
            )
        if not isinstance(self.feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(self.metadata, EdgeCommandMetadata):
            raise TypeError("metadata must be an EdgeCommandMetadata")
        if not isinstance(self.duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if not isinstance(self.transcript, AdapterConformanceTranscript):
            raise TypeError("transcript must be an AdapterConformanceTranscript")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


@dataclass(frozen=True, slots=True)
class AdapterConformanceVerdict:
    """Immutable audit-only verdict with no session, command, or continuation."""

    session_id: str
    ordinal: int
    evidence: ControlledEdgeCompositionEvidence
    transcript: AdapterConformanceTranscript

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be non-empty")
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool):
            raise TypeError("ordinal must be an int")
        if self.ordinal <= 0:
            raise ValueError("ordinal must be positive")
        if not isinstance(self.evidence, ControlledEdgeCompositionEvidence):
            raise TypeError("evidence must be ControlledEdgeCompositionEvidence")
        if not isinstance(self.transcript, AdapterConformanceTranscript):
            raise TypeError("transcript must be an AdapterConformanceTranscript")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


class AdapterConformanceFailureError(RuntimeError):
    """Fail-closed result with no receipt, replay, or recovery authority."""

    __slots__ = ("failure_kind",)

    def __init__(self, cause: Exception) -> None:
        self.failure_kind = type(cause).__name__
        super().__init__(f"adapter conformance failed closed: {self.failure_kind}")


class DeterministicAdapterConformanceHarness:
    """Call frozen P0.7 once, then compare only immutable audit facts.

    This test-only consumer never constructs a P0.5 command or a P0.4 adapter.
    A post-cycle transcript mismatch terminates the current P0.7 session through
    its public terminal contract so no continuation can leak from a failed
    conformance attempt.
    """

    __slots__ = ()

    @staticmethod
    def _assert_transcript_matches(
        transcript: AdapterConformanceTranscript,
        evidence: ControlledEdgeCompositionEvidence,
    ) -> None:
        adapter = evidence.adapter_evidence
        if adapter.transmission is None:
            raise ValueError("non-admission cannot yield a successful verdict")
        expected: tuple[AdapterConformanceTranscriptFact, ...] = (
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.OBSERVATION, adapter.observation
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.TRANSMISSION,
                adapter.transmission,
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT,
                adapter.acknowledgement,
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY,
                adapter.actual_telemetry,
            ),
        )
        if transcript.facts != expected:
            raise ValueError("transcript does not match immutable adapter evidence")

    def evaluate(
        self, cycle_input: AdapterConformanceCycleInput
    ) -> AdapterConformanceVerdict:
        """Run exactly one P0.7 cycle and return audit-only conformance evidence."""

        if not isinstance(cycle_input, AdapterConformanceCycleInput):
            raise TypeError("cycle_input must be an AdapterConformanceCycleInput")
        try:
            receipt = cycle_input.session.run_cycle(
                ControlledCompositionSessionCycleInput(
                    cycle_input.feasible_decision,
                    cycle_input.metadata,
                    cycle_input.duration,
                    cycle_input.tolerance_kw,
                ),
                cycle_input.continuation,
            )
        except ControlledCompositionSessionFailureError as cause:
            raise AdapterConformanceFailureError(cause) from cause

        try:
            self._assert_transcript_matches(cycle_input.transcript, receipt.evidence)
        except Exception as cause:
            try:
                cycle_input.session.terminate(receipt.continuation)
            except Exception as termination_error:
                raise AdapterConformanceFailureError(termination_error) from cause
            raise AdapterConformanceFailureError(cause) from cause

        return AdapterConformanceVerdict(
            receipt.session_id,
            receipt.ordinal,
            receipt.evidence,
            cycle_input.transcript,
        )
