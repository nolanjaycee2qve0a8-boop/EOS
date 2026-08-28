"""Pure Feasibility-to-Edge command handoff without execution authority."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from edge_runtime import OperatingMode, PowerCommand
from edge_runtime.validation import (
    require_aware_datetime,
    require_non_empty_string,
    require_non_negative_int,
)
from ems_strategy.feasibility import FeasibleDecision


@dataclass(frozen=True, slots=True)
class EdgeCommandMetadata:
    """Caller-owned command identity and time facts, with no power authority."""

    command_id: str
    sequence: int
    provenance_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    reason_code: str
    source: str
    correlation_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "command_id",
            "provenance_id",
            "reason_code",
            "source",
            "correlation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_non_empty_string(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self, "sequence", require_non_negative_int(self.sequence, "sequence")
        )
        for field_name in ("issued_at", "not_before", "expires_at"):
            object.__setattr__(
                self,
                field_name,
                require_aware_datetime(getattr(self, field_name), field_name),
            )
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        if self.not_before > self.expires_at:
            raise ValueError("not_before must not be later than expires_at")


def _approved_signed_power(feasible_decision: FeasibleDecision) -> float:
    action = feasible_decision.approved_intent.action
    magnitude = feasible_decision.approved_power_kw
    if action == "charge":
        return magnitude
    if action == "discharge":
        return -magnitude
    return 0.0


@dataclass(frozen=True, slots=True)
class EdgeCommandHandoffResult:
    """Relate exact Feasibility evidence to one caller-owned Edge command."""

    source_feasible_decision: FeasibleDecision
    metadata: EdgeCommandMetadata
    command: PowerCommand

    def __post_init__(self) -> None:
        if not isinstance(self.source_feasible_decision, FeasibleDecision):
            raise TypeError("source_feasible_decision must be a FeasibleDecision")
        if not isinstance(self.metadata, EdgeCommandMetadata):
            raise TypeError("metadata must be an EdgeCommandMetadata")
        if not isinstance(self.command, PowerCommand):
            raise TypeError("command must be a PowerCommand")

        approved_action = self.source_feasible_decision.approved_intent.action
        approved_power_kw = self.source_feasible_decision.approved_power_kw
        if approved_action == "charge":
            if self.command.requested_battery_power_kw != approved_power_kw:
                raise ValueError("command power must match approved charge mapping")
            if self.command.operating_mode is not OperatingMode.NORMAL:
                raise ValueError("command mode must match approved charge mapping")
        elif approved_action == "discharge":
            if self.command.requested_battery_power_kw != -approved_power_kw:
                raise ValueError("command power must match approved discharge mapping")
            if self.command.operating_mode is not OperatingMode.NORMAL:
                raise ValueError("command mode must match approved discharge mapping")
        else:
            if self.command.requested_battery_power_kw != 0.0:
                raise ValueError("command power must match approved idle mapping")
            if self.command.operating_mode is not OperatingMode.SAFE_IDLE:
                raise ValueError("command mode must match approved idle mapping")
        if self.command.schema_version != "edge-power-command/v1":
            raise ValueError("command must use edge-power-command/v1")
        for field_name in (
            "command_id",
            "sequence",
            "provenance_id",
            "issued_at",
            "not_before",
            "expires_at",
            "reason_code",
            "source",
            "correlation_id",
        ):
            if getattr(self.command, field_name) != getattr(self.metadata, field_name):
                raise ValueError(f"command {field_name} must preserve metadata")


class EdgeCommandHandoffBoundary(ABC):
    """Define one stateless handoff from Feasibility to an unexecuted command."""

    __slots__ = ()

    def handoff(
        self,
        feasible_decision: FeasibleDecision,
        *,
        metadata: EdgeCommandMetadata,
    ) -> EdgeCommandHandoffResult:
        """Create one command without admission, execution, or retained state."""
        if not isinstance(feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(metadata, EdgeCommandMetadata):
            raise TypeError("metadata must be an EdgeCommandMetadata")
        result = self._handoff(feasible_decision, metadata=metadata)
        if not isinstance(result, EdgeCommandHandoffResult):
            raise TypeError("handoff must return an EdgeCommandHandoffResult")
        if result.source_feasible_decision is not feasible_decision:
            raise ValueError(
                "handoff must preserve exact source_feasible_decision identity"
            )
        if result.metadata is not metadata:
            raise ValueError("handoff must preserve exact metadata identity")
        return result

    @abstractmethod
    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
        *,
        metadata: EdgeCommandMetadata,
    ) -> EdgeCommandHandoffResult:
        """Create one unexecuted command without accessing runtime authority."""
        raise NotImplementedError


class DeterministicEdgeCommandHandoff(EdgeCommandHandoffBoundary):
    """Perform exactly one caller-metadata and approved-power conversion."""

    __slots__ = ()

    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
        *,
        metadata: EdgeCommandMetadata,
    ) -> EdgeCommandHandoffResult:
        requested_power_kw = _approved_signed_power(feasible_decision)
        command = PowerCommand(
            "edge-power-command/v1",
            metadata.command_id,
            metadata.sequence,
            metadata.provenance_id,
            metadata.issued_at,
            metadata.not_before,
            metadata.expires_at,
            requested_power_kw,
            (
                OperatingMode.SAFE_IDLE
                if requested_power_kw == 0
                else OperatingMode.NORMAL
            ),
            metadata.reason_code,
            metadata.source,
            metadata.correlation_id,
        )
        return EdgeCommandHandoffResult(feasible_decision, metadata, command)
