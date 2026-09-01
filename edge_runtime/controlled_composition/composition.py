"""One caller-driven P0.5 -> P0.3 -> P0.4 composition without new authority."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn, SupportsIndex

from edge_runtime import CommandAcknowledgement, PowerCommand, TelemetrySnapshot
from edge_runtime.controlled_runtime import (
    CommandOrigin,
    ControlledEdgeRuntime,
    RuntimeLoopStep,
)
from edge_runtime.device_adapter import (
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterStepEvidence,
    DeviceObservation,
    DeviceTransmissionEvidence,
    P03DeviceAdapterIntegration,
    ResidentialDeviceAdapterBoundary,
)
from edge_runtime.validation import (
    require_non_negative_number,
    require_positive_timedelta,
)
from ems_strategy.edge_command_handoff import (
    EdgeCommandHandoffBoundary,
    EdgeCommandHandoffResult,
    EdgeCommandMetadata,
)
from ems_strategy.feasibility import FeasibleDecision


@dataclass(frozen=True, slots=True)
class ControlledEdgeCompositionInput:
    """All caller-owned sources for one P0.6 composition cycle."""

    feasible_decision: FeasibleDecision
    metadata: EdgeCommandMetadata
    handoff_boundary: EdgeCommandHandoffBoundary
    runtime: ControlledEdgeRuntime
    adapter: ResidentialDeviceAdapterBoundary
    duration: timedelta
    tolerance_kw: float = 0.01

    def __post_init__(self) -> None:
        if not isinstance(self.feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(self.metadata, EdgeCommandMetadata):
            raise TypeError("metadata must be an EdgeCommandMetadata")
        if not isinstance(self.handoff_boundary, EdgeCommandHandoffBoundary):
            raise TypeError("handoff_boundary must be an EdgeCommandHandoffBoundary")
        if not isinstance(self.runtime, ControlledEdgeRuntime):
            raise TypeError("runtime must be a ControlledEdgeRuntime")
        if not isinstance(self.adapter, ResidentialDeviceAdapterBoundary):
            raise TypeError("adapter must be a ResidentialDeviceAdapterBoundary")
        object.__setattr__(
            self, "duration", require_positive_timedelta(self.duration, "duration")
        )
        object.__setattr__(
            self,
            "tolerance_kw",
            require_non_negative_number(self.tolerance_kw, "tolerance_kw"),
        )


@dataclass(frozen=True, slots=True)
class ControlledEdgeCompositionEvidence:
    """Audit-only P0.5/P0.3/P0.4 facts, with no execution authority.

    The evidence deliberately has no source input, adapter, handoff boundary,
    transmission request, or next runtime.  It records what one completed
    logical P0.3 tick and its later P0.4 audit observed; it cannot resume or
    recreate that cycle.
    """

    handoff_result: EdgeCommandHandoffResult
    runtime_step: RuntimeLoopStep
    adapter_evidence: DeviceAdapterStepEvidence
    correlated_acknowledgement: CommandAcknowledgement | None
    adapter_actual_telemetry: TelemetrySnapshot | None

    def __post_init__(self) -> None:
        if not isinstance(self.handoff_result, EdgeCommandHandoffResult):
            raise TypeError("handoff_result must be an EdgeCommandHandoffResult")
        if not isinstance(self.runtime_step, RuntimeLoopStep):
            raise TypeError("runtime_step must be a RuntimeLoopStep")
        if not isinstance(self.adapter_evidence, DeviceAdapterStepEvidence):
            raise TypeError("adapter_evidence must be a DeviceAdapterStepEvidence")
        if self.correlated_acknowledgement is not None and not isinstance(
            self.correlated_acknowledgement, CommandAcknowledgement
        ):
            raise TypeError(
                "correlated_acknowledgement must be a CommandAcknowledgement or None"
            )
        if self.adapter_actual_telemetry is not None and not isinstance(
            self.adapter_actual_telemetry, TelemetrySnapshot
        ):
            raise TypeError(
                "adapter_actual_telemetry must be a TelemetrySnapshot or None"
            )

        if self.runtime_step.caller_command is not self.handoff_result.command:
            raise ValueError("P0.3 caller command must be the exact P0.5 command")

        transmission = self.adapter_evidence.transmission
        if self.runtime_step.admitted_command is None:
            if self.runtime_step.command_origin is not CommandOrigin.NONE:
                raise ValueError("non-admitted P0.3 command requires none origin")
            if transmission is not None or self.correlated_acknowledgement is not None:
                raise ValueError(
                    "non-admitted P0.3 command cannot produce transmission"
                )
            return

        if self.runtime_step.command_origin is not CommandOrigin.CURRENT_CALLER:
            raise ValueError("admitted P0.3 command must originate from current caller")
        if self.runtime_step.admitted_command is not self.handoff_result.command:
            raise ValueError("P0.3 admitted command must preserve exact P0.5 command")
        if transmission is None:
            raise ValueError(
                "admitted P0.3 command requires P0.4 transmission evidence"
            )
        safety = self.runtime_step.device_step.safety_decision
        if safety is None:
            raise ValueError("admitted P0.3 command requires retained safety decision")
        command = self.handoff_result.command
        for field_name in (
            "command_id",
            "sequence",
            "provenance_id",
            "correlation_id",
            "issued_at",
            "not_before",
            "expires_at",
        ):
            if getattr(transmission, field_name) != getattr(command, field_name):
                raise ValueError(f"P0.4 transmission must preserve {field_name}")
        if (
            transmission.safety_final_power_kw
            != safety.final_requested_battery_power_kw
        ):
            raise ValueError("P0.4 transmission must preserve P0.3 safety-final power")
        if transmission.operating_mode is not safety.final_operating_mode:
            raise ValueError("P0.4 transmission must preserve P0.3 safety-final mode")

    def __copy__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionEvidence cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionEvidence cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionEvidence cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionEvidence cannot be serialized")


@dataclass(frozen=True, slots=True)
class ControlledEdgeCompositionContinuation:
    """Current-caller continuation containing only P0.3's exact next runtime.

    This is not historical evidence and is intentionally non-copyable and
    non-serializable.  It carries neither adapter nor handoff authority and
    cannot manufacture a new command or replay an old one.
    """

    next_runtime: ControlledEdgeRuntime

    def __post_init__(self) -> None:
        if not isinstance(self.next_runtime, ControlledEdgeRuntime):
            raise TypeError("next_runtime must be a ControlledEdgeRuntime")

    def __copy__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionContinuation cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionContinuation cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionContinuation cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionContinuation cannot be serialized")


@dataclass(frozen=True, slots=True)
class ControlledEdgeCompositionResult:
    """One immutable P0.6 result separating audit evidence from continuation."""

    evidence: ControlledEdgeCompositionEvidence
    continuation: ControlledEdgeCompositionContinuation

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, ControlledEdgeCompositionEvidence):
            raise TypeError("evidence must be ControlledEdgeCompositionEvidence")
        if not isinstance(self.continuation, ControlledEdgeCompositionContinuation):
            raise TypeError(
                "continuation must be ControlledEdgeCompositionContinuation"
            )
        if not self.continuation.next_runtime.trace.steps or (
            self.continuation.next_runtime.trace.steps[-1]
            is not self.evidence.runtime_step
        ):
            raise ValueError("continuation must retain the exact P0.3 runtime step")

    def __copy__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionResult cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionResult cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionResult cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ControlledEdgeCompositionResult cannot be serialized")


class ControlledEdgeCompositionBoundary(ABC):
    """Define one stateless P0.6 cycle over existing public P0.3/P0.4 contracts."""

    __slots__ = ()

    def compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        if not isinstance(composition_input, ControlledEdgeCompositionInput):
            raise TypeError(
                "composition_input must be a ControlledEdgeCompositionInput"
            )
        result = self._compose(composition_input)
        if not isinstance(result, ControlledEdgeCompositionResult):
            raise TypeError("compose must return a ControlledEdgeCompositionResult")
        evidence = result.evidence
        self._validate_handoff_identity(evidence.handoff_result, composition_input)
        if result.continuation.next_runtime is composition_input.runtime:
            raise ValueError("P0.3 tick must return a distinct next_runtime")
        return result

    @staticmethod
    def _validate_handoff_identity(
        handoff_result: EdgeCommandHandoffResult,
        composition_input: ControlledEdgeCompositionInput,
    ) -> None:
        """Reject substituted P0.5 sources before P0.3 logical execution."""
        if not isinstance(handoff_result, EdgeCommandHandoffResult):
            raise TypeError("handoff must return an EdgeCommandHandoffResult")
        if (
            handoff_result.source_feasible_decision
            is not composition_input.feasible_decision
        ):
            raise ValueError(
                "handoff_result must retain exact feasible_decision identity"
            )
        if handoff_result.metadata is not composition_input.metadata:
            raise ValueError("handoff_result must retain exact metadata identity")

    @abstractmethod
    def _compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        raise NotImplementedError


class DeterministicControlledEdgeComposition(ControlledEdgeCompositionBoundary):
    """Compose P0.5 handoff, P0.3 tick and P0.4 audit facts exactly once each."""

    __slots__ = ()

    def _compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        handoff_result = composition_input.handoff_boundary.handoff(
            composition_input.feasible_decision,
            metadata=composition_input.metadata,
        )
        self._validate_handoff_identity(handoff_result, composition_input)
        next_runtime = composition_input.runtime.tick(
            handoff_result.command,
            duration=composition_input.duration,
            tolerance_kw=composition_input.tolerance_kw,
        )
        runtime_step = next_runtime.trace.steps[-1]

        observation = composition_input.adapter.acquire_observation()
        if not isinstance(observation, DeviceObservation):
            raise TypeError("adapter must return a DeviceObservation")
        transmission: DeviceTransmissionEvidence | None = None
        correlated_acknowledgement: CommandAcknowledgement | None = None
        if runtime_step.admitted_command is not None:
            safety = runtime_step.device_step.safety_decision
            if safety is None:
                raise ValueError("admitted P0.3 command has no safety decision")
            caller_command = runtime_step.caller_command
            if not isinstance(caller_command, PowerCommand):
                raise ValueError("admitted P0.3 command requires caller command")
            request = P03DeviceAdapterIntegration.transmission_request(
                caller_command,
                runtime_step.admitted_command,
                safety,
            )
            transmission = composition_input.adapter.transmit(request)
            if not isinstance(transmission, DeviceTransmissionEvidence):
                raise TypeError("adapter must return DeviceTransmissionEvidence")
            acknowledgement = composition_input.adapter.observe_acknowledgement()
            if not isinstance(acknowledgement, DeviceAckObservation):
                raise TypeError("adapter must return a DeviceAckObservation")
            correlated_acknowledgement = (
                P03DeviceAdapterIntegration.correlated_acknowledgement(
                    request, acknowledgement
                )
            )
        else:
            acknowledgement = composition_input.adapter.observe_acknowledgement()
            if not isinstance(acknowledgement, DeviceAckObservation):
                raise TypeError("adapter must return a DeviceAckObservation")
        actual_observation = composition_input.adapter.observe_actual_telemetry()
        if not isinstance(actual_observation, DeviceActualTelemetryObservation):
            raise TypeError("adapter must return a DeviceActualTelemetryObservation")
        adapter_actual_telemetry = P03DeviceAdapterIntegration.actual_telemetry(
            actual_observation
        )
        adapter_evidence = DeviceAdapterStepEvidence(
            observation,
            transmission,
            acknowledgement,
            actual_observation,
        )
        return ControlledEdgeCompositionResult(
            ControlledEdgeCompositionEvidence(
                handoff_result,
                runtime_step,
                adapter_evidence,
                correlated_acknowledgement,
                adapter_actual_telemetry,
            ),
            ControlledEdgeCompositionContinuation(next_runtime),
        )
