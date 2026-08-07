"""Deterministic execution boundary for an explicit simulation scenario."""

from dataclasses import dataclass

from simulator.aggregate import SimulationScenario
from simulator.binding import SimulationModelBindingCollection
from simulator.executor import SingleStepSimulationExecutor
from simulator.trace import SimulationExecutionTrace


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """Preserve exact evidence for one explicitly supplied scenario."""

    scenario: SimulationScenario
    bindings: SimulationModelBindingCollection
    traces: tuple[SimulationExecutionTrace, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, SimulationScenario):
            raise TypeError("scenario must be a SimulationScenario")
        if not isinstance(self.bindings, SimulationModelBindingCollection):
            raise TypeError("bindings must be a SimulationModelBindingCollection")
        if not isinstance(self.traces, tuple):
            raise TypeError("traces must be a tuple")
        if len(self.traces) != len(self.scenario.steps):
            raise ValueError("traces must cover every scenario step exactly once")
        for index, trace in enumerate(self.traces):
            if not isinstance(trace, SimulationExecutionTrace):
                raise TypeError(
                    "traces must contain only SimulationExecutionTrace objects"
                )
            if any(previous is trace for previous in self.traces[:index]):
                raise ValueError(
                    "each scenario step occurrence must have a distinct trace"
                )
            if trace.bindings is not self.bindings:
                raise ValueError("each trace must reference the exact bindings")
            if trace.simulation_input is not self.scenario.steps[index]:
                raise ValueError(
                    "each trace input must be the exact caller-ordered scenario step"
                )


class ScenarioExecutionBoundary:
    """Execute each explicit scenario step once without retaining state."""

    __slots__ = ()

    @staticmethod
    def execute(
        scenario: SimulationScenario,
        bindings: SimulationModelBindingCollection,
    ) -> ScenarioExecutionResult:
        """Execute caller-ordered steps through the single-step boundary."""
        if not isinstance(scenario, SimulationScenario):
            raise TypeError("scenario must be a SimulationScenario")
        if not isinstance(bindings, SimulationModelBindingCollection):
            raise TypeError("bindings must be a SimulationModelBindingCollection")

        traces = tuple(
            SimulationExecutionTrace.create(
                bindings,
                SingleStepSimulationExecutor.execute(simulation_input, bindings),
            )
            for simulation_input in scenario.steps
        )
        return ScenarioExecutionResult(scenario, bindings, traces)
