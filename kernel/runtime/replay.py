"""Deterministic observation of an already completed runtime lifecycle."""

from dataclasses import dataclass

from kernel.runtime.journaled import (
    DispatchedJournaledEMSTick,
    JournaledEMSTick,
)
from kernel.runtime.trace import RuntimeExecutionTrace


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Preserve exact lifecycle identities observed during replay."""

    source_tick: JournaledEMSTick
    dispatched_tick: DispatchedJournaledEMSTick
    progressed_tick: JournaledEMSTick

    def __post_init__(self) -> None:
        if not isinstance(self.source_tick, JournaledEMSTick):
            raise TypeError("source_tick must be a JournaledEMSTick")
        if not isinstance(self.dispatched_tick, DispatchedJournaledEMSTick):
            raise TypeError("dispatched_tick must be a DispatchedJournaledEMSTick")
        if not isinstance(self.progressed_tick, JournaledEMSTick):
            raise TypeError("progressed_tick must be a JournaledEMSTick")

        if self.dispatched_tick.tick is not self.source_tick:
            raise ValueError("dispatched_tick.tick must be the exact source_tick")

        source_records = self.source_tick.execution.journal.events()
        progressed_records = self.progressed_tick.execution.journal.events()
        if len(progressed_records) < len(source_records) or any(
            progressed is not source
            for progressed, source in zip(
                progressed_records,
                source_records,
                strict=False,
            )
        ):
            raise ValueError(
                "progressed_tick journal must preserve source EventRecord identities"
            )


class RuntimeReplay:
    """Replay immutable lifecycle observations without executing runtime logic."""

    __slots__ = ()

    @staticmethod
    def replay(trace: RuntimeExecutionTrace) -> ReplayResult:
        """Return an immutable observation containing the trace's exact objects."""
        if not isinstance(trace, RuntimeExecutionTrace):
            raise TypeError("trace must be a RuntimeExecutionTrace")

        return ReplayResult(
            source_tick=trace.source_tick,
            dispatched_tick=trace.dispatched_tick,
            progressed_tick=trace.progressed_tick,
        )
