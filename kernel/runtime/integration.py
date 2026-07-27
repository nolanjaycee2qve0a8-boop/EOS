"""Stateless integration of tick, dispatch, and progression boundaries."""

from kernel.context import EnergySystemContext
from kernel.dispatch import CommandDispatcher
from kernel.event import EventJournal
from kernel.policy import EMSPolicy
from kernel.runtime.journaled import JournaledEMSRuntime, JournaledEMSTick


class DispatchProgressionRuntime:
    """Compose one complete dispatch-before-progression lifecycle."""

    __slots__ = ()

    @staticmethod
    def execute(
        policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
        dispatcher: CommandDispatcher,
        next_policy: EMSPolicy,
        next_context: EnergySystemContext,
    ) -> JournaledEMSTick:
        """Return the exact next tick after one validated lifecycle."""
        if not isinstance(policy, EMSPolicy):
            raise TypeError("policy must be an EMSPolicy instance")
        if not isinstance(context, EnergySystemContext):
            raise TypeError("context must be an EnergySystemContext")
        if not isinstance(journal, EventJournal):
            raise TypeError("journal must be an EventJournal")
        if not isinstance(dispatcher, CommandDispatcher):
            raise TypeError("dispatcher must be a CommandDispatcher")
        if not isinstance(next_policy, EMSPolicy):
            raise TypeError("next_policy must be an EMSPolicy instance")
        if not isinstance(next_context, EnergySystemContext):
            raise TypeError("next_context must be an EnergySystemContext")

        tick = JournaledEMSRuntime.tick(policy, context, journal)
        dispatched = JournaledEMSRuntime.dispatch(tick, dispatcher)
        return JournaledEMSRuntime.progress_after_dispatch(
            dispatched,
            next_policy,
            next_context,
        )
