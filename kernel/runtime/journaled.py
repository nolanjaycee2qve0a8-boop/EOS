"""Stateless runtime boundary for one journaled EMS tick."""

from dataclasses import dataclass

from kernel.context import EnergySystemContext
from kernel.cycle import JournaledEMSCycle
from kernel.event import EventJournal
from kernel.execution import JournaledEMSExecutionService
from kernel.policy import EMSPolicy


@dataclass(frozen=True, slots=True)
class JournaledEMSTick:
    """Carry the exact journaled execution produced by one runtime tick."""

    execution: JournaledEMSCycle

    def __post_init__(self) -> None:
        if not isinstance(self.execution, JournaledEMSCycle):
            raise TypeError("execution must be a JournaledEMSCycle")


class JournaledEMSRuntime:
    """Execute one journaled EMS tick without retaining runtime state."""

    __slots__ = ()

    @staticmethod
    def tick(
        policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSTick:
        """Return one tick containing the exact service execution."""
        if not isinstance(policy, EMSPolicy):
            raise TypeError("policy must be an EMSPolicy instance")
        if not isinstance(context, EnergySystemContext):
            raise TypeError("context must be an EnergySystemContext")
        if not isinstance(journal, EventJournal):
            raise TypeError("journal must be an EventJournal")

        execution = JournaledEMSExecutionService.execute(
            policy,
            context,
            journal,
        )
        return JournaledEMSTick(execution=execution)
