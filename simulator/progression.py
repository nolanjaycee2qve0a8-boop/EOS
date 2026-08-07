"""Explicit caller-owned simulation step progression contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from simulator.aggregate import SimulationStepInput, SimulationStepResult
from simulator.trace import SimulationExecutionTrace


@dataclass(frozen=True, slots=True, eq=False)
class SimulationStepProgression:
    """Relate completed evidence to an exact caller-supplied next input."""

    previous_trace: SimulationExecutionTrace
    previous_result: SimulationStepResult
    next_input: SimulationStepInput

    def __post_init__(self) -> None:
        if not isinstance(self.previous_trace, SimulationExecutionTrace):
            raise TypeError("previous_trace must be a SimulationExecutionTrace")
        if not isinstance(self.previous_result, SimulationStepResult):
            raise TypeError("previous_result must be a SimulationStepResult")
        if not isinstance(self.next_input, SimulationStepInput):
            raise TypeError("next_input must be a SimulationStepInput")
        if self.previous_result is not self.previous_trace.step_result:
            raise ValueError(
                "previous_result must be the exact previous_trace.step_result"
            )
        previous_next_state = self.previous_result.state.battery_result.next_state
        if self.next_input.battery_input.source_state is not previous_next_state:
            raise ValueError(
                "next_input battery source_state must be the exact previous "
                "battery next_state"
            )


class SimulationStepProgressionBoundary(ABC):
    """Define stateless validation of a caller-supplied next step relation."""

    __slots__ = ()

    @abstractmethod
    def relate(
        self,
        previous_trace: SimulationExecutionTrace,
        next_input: SimulationStepInput,
    ) -> SimulationStepProgression:
        """Return a relation without generating or executing the next step."""
        raise NotImplementedError
