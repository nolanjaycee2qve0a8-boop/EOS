"""A synchronous P0.7 facade over one P0.6 composition cycle at a time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn, SupportsIndex

from edge_runtime.controlled_composition import (
    ControlledEdgeCompositionBoundary,
    ControlledEdgeCompositionEvidence,
    ControlledEdgeCompositionInput,
    ControlledEdgeCompositionResult,
)
from edge_runtime.controlled_runtime import CommandOrigin, ControlledEdgeRuntime
from edge_runtime.device_adapter import (
    AdapterFactAvailability,
    ResidentialDeviceAdapterBoundary,
    TransmissionStatus,
)
from edge_runtime.validation import (
    require_non_empty_string,
    require_non_negative_number,
    require_positive_timedelta,
)
from ems_strategy.edge_command_handoff import (
    EdgeCommandHandoffBoundary,
    EdgeCommandMetadata,
)
from ems_strategy.feasibility import FeasibleDecision


def _reject_copy_or_serialization(name: str) -> NoReturn:
    raise TypeError(f"{name} cannot be copied or serialized")


@dataclass(frozen=True, slots=True)
class ControlledCompositionSessionCreationInput:
    """Caller-owned live boundaries for one explicitly created session."""

    session_id: str
    runtime: ControlledEdgeRuntime
    adapter: ResidentialDeviceAdapterBoundary
    handoff_boundary: EdgeCommandHandoffBoundary
    composition_boundary: ControlledEdgeCompositionBoundary

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_id", require_non_empty_string(self.session_id, "session_id")
        )
        if not isinstance(self.runtime, ControlledEdgeRuntime):
            raise TypeError("runtime must be a ControlledEdgeRuntime")
        if not isinstance(self.adapter, ResidentialDeviceAdapterBoundary):
            raise TypeError("adapter must be a ResidentialDeviceAdapterBoundary")
        if not isinstance(self.handoff_boundary, EdgeCommandHandoffBoundary):
            raise TypeError("handoff_boundary must be an EdgeCommandHandoffBoundary")
        if not isinstance(self.composition_boundary, ControlledEdgeCompositionBoundary):
            raise TypeError(
                "composition_boundary must be a ControlledEdgeCompositionBoundary"
            )


@dataclass(frozen=True, slots=True)
class ControlledCompositionSessionCycleInput:
    """Fresh caller facts for exactly one P0.6 composition cycle."""

    feasible_decision: FeasibleDecision
    metadata: EdgeCommandMetadata
    duration: timedelta
    tolerance_kw: float = 0.01

    def __post_init__(self) -> None:
        if not isinstance(self.feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(self.metadata, EdgeCommandMetadata):
            raise TypeError("metadata must be an EdgeCommandMetadata")
        object.__setattr__(
            self, "duration", require_positive_timedelta(self.duration, "duration")
        )
        object.__setattr__(
            self,
            "tolerance_kw",
            require_non_negative_number(self.tolerance_kw, "tolerance_kw"),
        )


@dataclass(frozen=True, slots=True)
class ControlledCompositionSessionContinuation:
    """One-shot, same-session capability for the next explicit cycle only."""

    session_id: str
    ordinal: int
    next_runtime: ControlledEdgeRuntime
    _token: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_id", require_non_empty_string(self.session_id, "session_id")
        )
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool):
            raise TypeError("ordinal must be an int")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        if not isinstance(self.next_runtime, ControlledEdgeRuntime):
            raise TypeError("next_runtime must be a ControlledEdgeRuntime")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


@dataclass(frozen=True, slots=True)
class ControlledCompositionSessionCycleReceipt:
    """Immutable audit record and the next one-shot continuation."""

    session_id: str
    ordinal: int
    evidence: ControlledEdgeCompositionEvidence
    continuation: ControlledCompositionSessionContinuation

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_id", require_non_empty_string(self.session_id, "session_id")
        )
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool):
            raise TypeError("ordinal must be an int")
        if self.ordinal <= 0:
            raise ValueError("ordinal must be positive")
        if not isinstance(self.evidence, ControlledEdgeCompositionEvidence):
            raise TypeError("evidence must be a ControlledEdgeCompositionEvidence")
        if not isinstance(self.continuation, ControlledCompositionSessionContinuation):
            raise TypeError(
                "continuation must be a ControlledCompositionSessionContinuation"
            )
        if self.continuation.session_id != self.session_id:
            raise ValueError("continuation must belong to the receipt session")
        if self.continuation.ordinal != self.ordinal:
            raise ValueError("continuation ordinal must match receipt ordinal")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


@dataclass(frozen=True, slots=True)
class ControlledCompositionSessionTerminationReceipt:
    """Non-executable evidence that one session was explicitly terminated."""

    session_id: str
    final_ordinal: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_id", require_non_empty_string(self.session_id, "session_id")
        )
        if not isinstance(self.final_ordinal, int) or isinstance(
            self.final_ordinal, bool
        ):
            raise TypeError("final_ordinal must be an int")
        if self.final_ordinal < 0:
            raise ValueError("final_ordinal must be non-negative")

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)


class ControlledCompositionSessionTerminatedError(RuntimeError):
    """Raised when a terminal session is asked to perform another action."""

    __slots__ = ("session_id",)

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"controlled composition session {session_id!r} is terminal")


class ControlledCompositionSessionFailureError(RuntimeError):
    """Non-executable fact that consumes the submitted continuation terminally."""

    __slots__ = ("failure_kind", "ordinal", "session_id")

    def __init__(self, session_id: str, ordinal: int, cause: Exception) -> None:
        self.session_id = session_id
        self.ordinal = ordinal
        self.failure_kind = type(cause).__name__
        super().__init__(
            f"controlled composition session {session_id!r} failed at ordinal "
            f"{ordinal}: {self.failure_kind}"
        )


class ControlledCompositionSession:
    """Caller-owned facade with no scheduler, retry loop, or transport behavior."""

    __slots__ = (
        "_active_continuation",
        "_adapter",
        "_composition_boundary",
        "_handoff_boundary",
        "_ordinal",
        "_runtime",
        "_session_id",
        "_terminal",
        "_used_decision_ids",
        "_used_metadata_ids",
    )

    def __init__(
        self, creation_input: ControlledCompositionSessionCreationInput
    ) -> None:
        self._session_id = creation_input.session_id
        self._runtime = creation_input.runtime
        self._adapter = creation_input.adapter
        self._handoff_boundary = creation_input.handoff_boundary
        self._composition_boundary = creation_input.composition_boundary
        self._ordinal = 0
        self._terminal = False
        self._active_continuation = ControlledCompositionSessionContinuation(
            self._session_id, 0, self._runtime, object()
        )
        self._used_decision_ids: set[int] = set()
        self._used_metadata_ids: set[int] = set()

    @classmethod
    def create(
        cls, creation_input: ControlledCompositionSessionCreationInput
    ) -> ControlledCompositionSession:
        if not isinstance(creation_input, ControlledCompositionSessionCreationInput):
            raise TypeError(
                "creation_input must be a ControlledCompositionSessionCreationInput"
            )
        return cls(creation_input)

    @property
    def initial_continuation(self) -> ControlledCompositionSessionContinuation:
        """Return the unconsumed initial capability without executing a cycle."""

        if self._terminal:
            raise ControlledCompositionSessionTerminatedError(self._session_id)
        return self._active_continuation

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_terminal(self) -> bool:
        return self._terminal

    def _consume_and_terminate(self) -> None:
        self._terminal = True
        self._active_continuation = None  # type: ignore[assignment]

    def _require_current_continuation(
        self, continuation: ControlledCompositionSessionContinuation
    ) -> None:
        if not isinstance(continuation, ControlledCompositionSessionContinuation):
            raise TypeError(
                "continuation must be a ControlledCompositionSessionContinuation"
            )
        if continuation is not self._active_continuation:
            raise ValueError(
                "continuation is not the exact active session continuation"
            )
        if continuation.session_id != self._session_id:
            raise ValueError("continuation belongs to another session")
        if continuation.ordinal != self._ordinal:
            raise ValueError("continuation ordinal is not current")
        if continuation.next_runtime is not self._runtime:
            raise ValueError("continuation runtime is not the current session runtime")

    def _require_fresh_cycle_input(
        self, cycle_input: ControlledCompositionSessionCycleInput
    ) -> None:
        if not isinstance(cycle_input, ControlledCompositionSessionCycleInput):
            raise TypeError(
                "cycle_input must be a ControlledCompositionSessionCycleInput"
            )
        identities = (
            (id(cycle_input.feasible_decision), self._used_decision_ids, "decision"),
            (id(cycle_input.metadata), self._used_metadata_ids, "metadata"),
        )
        for identity, seen, label in identities:
            if identity in seen:
                raise ValueError(f"{label} cannot be reused by a session cycle")

    @staticmethod
    def _validate_cycle_result(
        result: ControlledEdgeCompositionResult,
        cycle_input: ControlledCompositionSessionCycleInput,
    ) -> None:
        evidence = result.evidence
        handoff = evidence.handoff_result
        step = evidence.runtime_step
        if handoff.source_feasible_decision is not cycle_input.feasible_decision:
            raise ValueError("P0.5 handoff must retain exact feasible_decision")
        if handoff.metadata is not cycle_input.metadata:
            raise ValueError("P0.5 handoff must retain exact metadata")
        if step.caller_command is not handoff.command:
            raise ValueError("P0.3 caller must retain the exact P0.5 command")
        if step.admitted_command is None:
            raise ValueError("P0.3 non-admission is terminal for a session cycle")
        if step.admitted_command is not handoff.command:
            raise ValueError("P0.3 admission must retain the exact P0.5 command")
        if step.command_origin is not CommandOrigin.CURRENT_CALLER:
            raise ValueError("P0.3 admission must have current-caller origin")

        adapter_evidence = evidence.adapter_evidence
        if (
            adapter_evidence.observation.availability
            is not AdapterFactAvailability.AVAILABLE
            or adapter_evidence.acknowledgement.availability
            is not AdapterFactAvailability.AVAILABLE
            or adapter_evidence.actual_telemetry.availability
            is not AdapterFactAvailability.AVAILABLE
        ):
            raise ValueError("P0.4 unavailable facts are terminal for a session cycle")
        transmission = adapter_evidence.transmission
        if (
            transmission is None
            or transmission.status is not TransmissionStatus.TRANSMITTED
        ):
            raise ValueError("P0.4 transmission must succeed for an admitted cycle")
        if evidence.correlated_acknowledgement is None:
            raise ValueError(
                "P0.4 acknowledgement must correlate for an admitted cycle"
            )
        if evidence.adapter_actual_telemetry is None:
            raise ValueError(
                "P0.4 actual telemetry must be available for a session cycle"
            )

    def run_cycle(
        self,
        cycle_input: ControlledCompositionSessionCycleInput,
        continuation: ControlledCompositionSessionContinuation,
    ) -> ControlledCompositionSessionCycleReceipt:
        """Execute exactly one P0.6 composition; every failure is terminal."""

        if self._terminal:
            raise ControlledCompositionSessionTerminatedError(self._session_id)
        try:
            self._require_current_continuation(continuation)
            self._require_fresh_cycle_input(cycle_input)
            result = self._composition_boundary.compose(
                ControlledEdgeCompositionInput(
                    cycle_input.feasible_decision,
                    cycle_input.metadata,
                    self._handoff_boundary,
                    self._runtime,
                    self._adapter,
                    cycle_input.duration,
                    cycle_input.tolerance_kw,
                )
            )
            self._validate_cycle_result(result, cycle_input)
        except Exception as cause:
            self._consume_and_terminate()
            raise ControlledCompositionSessionFailureError(
                self._session_id, self._ordinal + 1, cause
            ) from cause

        self._used_decision_ids.add(id(cycle_input.feasible_decision))
        self._used_metadata_ids.add(id(cycle_input.metadata))
        self._ordinal += 1
        self._runtime = result.continuation.next_runtime
        next_continuation = ControlledCompositionSessionContinuation(
            self._session_id, self._ordinal, self._runtime, object()
        )
        self._active_continuation = next_continuation
        return ControlledCompositionSessionCycleReceipt(
            self._session_id, self._ordinal, result.evidence, next_continuation
        )

    def terminate(
        self,
        continuation: ControlledCompositionSessionContinuation,
    ) -> ControlledCompositionSessionTerminationReceipt:
        """Consume the exact continuation and permanently close the session."""

        if self._terminal:
            raise ControlledCompositionSessionTerminatedError(self._session_id)
        try:
            self._require_current_continuation(continuation)
        except Exception as cause:
            self._consume_and_terminate()
            raise ControlledCompositionSessionFailureError(
                self._session_id, self._ordinal, cause
            ) from cause
        self._consume_and_terminate()
        return ControlledCompositionSessionTerminationReceipt(
            self._session_id, self._ordinal
        )

    def __copy__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __deepcopy__(self, memo: object) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce__(self) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        _reject_copy_or_serialization(type(self).__name__)
