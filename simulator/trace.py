"""Immutable evidence for one structurally completed simulation step."""

from dataclasses import dataclass

from simulator.aggregate import (
    SimulationState,
    SimulationStepInput,
    SimulationStepResult,
)
from simulator.binding import SimulationModelBindingCollection


@dataclass(frozen=True, slots=True)
class SimulationExecutionTrace:
    """Preserve exact references across one completed single-step observation.

    The trace observes existing artifacts only. It does not execute a model,
    call the executor, copy evidence, or prove behavior beyond the structural
    identity relationships represented by its inputs.
    """

    simulation_input: SimulationStepInput
    bindings: SimulationModelBindingCollection
    state: SimulationState
    step_result: SimulationStepResult

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, SimulationStepInput):
            raise TypeError("simulation_input must be a SimulationStepInput")
        if not isinstance(self.bindings, SimulationModelBindingCollection):
            raise TypeError("bindings must be a SimulationModelBindingCollection")
        if not isinstance(self.state, SimulationState):
            raise TypeError("state must be a SimulationState")
        if not isinstance(self.step_result, SimulationStepResult):
            raise TypeError("step_result must be a SimulationStepResult")
        if self.step_result.simulation_input is not self.simulation_input:
            raise ValueError(
                "step_result.simulation_input must be the exact simulation_input"
            )
        if self.step_result.state is not self.state:
            raise ValueError("step_result.state must be the exact state")

    @classmethod
    def create(
        cls,
        bindings: SimulationModelBindingCollection,
        step_result: SimulationStepResult,
    ) -> "SimulationExecutionTrace":
        """Observe exact artifacts from one structurally completed step."""
        if not isinstance(bindings, SimulationModelBindingCollection):
            raise TypeError("bindings must be a SimulationModelBindingCollection")
        if not isinstance(step_result, SimulationStepResult):
            raise TypeError("step_result must be a SimulationStepResult")
        return cls(
            simulation_input=step_result.simulation_input,
            bindings=bindings,
            state=step_result.state,
            step_result=step_result,
        )
