"""Stateless deterministic orchestration of command dispatch."""

from kernel.decision import DecisionResult
from kernel.dispatch.dispatcher import CommandDispatcher


class CommandExecutor:
    """Dispatch one DecisionResult's commands sequentially in tuple order."""

    __slots__ = ()

    @staticmethod
    def execute(
        dispatcher: CommandDispatcher,
        decision_result: DecisionResult,
    ) -> None:
        """Dispatch each exact command once, stopping on the first exception."""
        if not isinstance(dispatcher, CommandDispatcher):
            raise TypeError("dispatcher must be a CommandDispatcher")
        if not isinstance(decision_result, DecisionResult):
            raise TypeError("decision_result must be a DecisionResult")

        for command in decision_result.commands:
            dispatcher.dispatch(command)
