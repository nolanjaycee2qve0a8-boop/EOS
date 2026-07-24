"""Stateless synchronous orchestration for one journaled EMS execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kernel.context import EnergySystemContext
from kernel.event import EventJournal
from kernel.policy import EMSPolicy

if TYPE_CHECKING:
    from kernel.cycle import JournaledEMSCycle


class JournaledEMSExecutionService:
    """Execute and journal one EMS decision without retaining runtime state."""

    __slots__ = ()

    @staticmethod
    def execute(
        policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSCycle:
        """Return the exact journaled cycle produced by the existing boundaries."""
        from kernel.cycle import EMSCycle, JournaledEMSCycle

        if not isinstance(policy, EMSPolicy):
            raise TypeError("policy must be an EMSPolicy instance")
        if not isinstance(context, EnergySystemContext):
            raise TypeError("context must be an EnergySystemContext")
        if not isinstance(journal, EventJournal):
            raise TypeError("journal must be an EventJournal")

        cycle = EMSCycle.execute(policy, context)
        return JournaledEMSCycle.record(cycle, journal)
