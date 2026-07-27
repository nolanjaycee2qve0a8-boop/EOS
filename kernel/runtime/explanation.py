"""Immutable explanation observation for one completed EMS decision."""

from dataclasses import dataclass

from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult
from kernel.runtime.audit import ExecutionAudit
from kernel.runtime.trace import RuntimeExecutionTrace


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    """Expose exact decision artifacts without recomputing their meaning."""

    audit: ExecutionAudit
    trace: RuntimeExecutionTrace
    source_context: EnergySystemContext
    decision_result: DecisionResult

    def __post_init__(self) -> None:
        if not isinstance(self.audit, ExecutionAudit):
            raise TypeError("audit must be an ExecutionAudit")
        if not isinstance(self.trace, RuntimeExecutionTrace):
            raise TypeError("trace must be a RuntimeExecutionTrace")
        if not isinstance(self.source_context, EnergySystemContext):
            raise TypeError("source_context must be an EnergySystemContext")
        if not isinstance(self.decision_result, DecisionResult):
            raise TypeError("decision_result must be a DecisionResult")

        if self.trace is not self.audit.trace:
            raise ValueError("trace must be the exact audit trace")
        if self.audit.source_tick is not self.trace.source_tick:
            raise ValueError("audit source_tick must be the exact trace source_tick")
        if self.audit.dispatched_tick is not self.trace.dispatched_tick:
            raise ValueError(
                "audit dispatched_tick must be the exact trace dispatched_tick"
            )
        if self.audit.progressed_tick is not self.trace.progressed_tick:
            raise ValueError(
                "audit progressed_tick must be the exact trace progressed_tick"
            )
        if self.audit.dispatched_tick.tick is not self.audit.source_tick:
            raise ValueError(
                "audit dispatched_tick.tick must be the exact audit source_tick"
            )

        source_cycle = self.audit.source_tick.execution.cycle
        if self.source_context is not source_cycle.context:
            raise ValueError("source_context must be the exact source decision context")
        if self.decision_result is not source_cycle.result:
            raise ValueError("decision_result must be the exact source decision result")

        source_records = self.audit.source_tick.execution.journal.events()
        progressed_records = self.audit.progressed_tick.execution.journal.events()
        if len(progressed_records) < len(source_records) or any(
            progressed is not source
            for progressed, source in zip(
                progressed_records,
                source_records,
                strict=False,
            )
        ):
            raise ValueError(
                "progressed journal must preserve source EventRecord identities"
            )

    @classmethod
    def create(cls, audit: ExecutionAudit) -> "DecisionExplanation":
        """Observe the exact source decision represented by an execution audit."""
        if not isinstance(audit, ExecutionAudit):
            raise TypeError("audit must be an ExecutionAudit")

        source_cycle = audit.source_tick.execution.cycle
        return cls(
            audit=audit,
            trace=audit.trace,
            source_context=source_cycle.context,
            decision_result=source_cycle.result,
        )
