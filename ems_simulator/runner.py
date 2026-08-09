"""Deterministic 24-hour runner for the EOS EMS Simulator demo."""

from dataclasses import dataclass

from ems_simulator.battery import SimpleBatteryPhysicsModel
from ems_simulator.grid import GridEnergyBalanceSimulationModel
from ems_simulator.input import HOURS_PER_DAY, DailySimulationScenarioInput
from ems_simulator.load import LoadProfileSimulationModel
from ems_simulator.pv import PVProfileSimulationModel
from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    GridSimulationModelBoundary,
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationExecutionTrace,
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationScenario,
    SimulationStepInput,
    SimulationStepProgression,
    SingleStepSimulationExecutor,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)


@dataclass(frozen=True, slots=True)
class _ExactPVResultModel(PVSimulationModelBoundary):
    result: PVSimulationResult

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be the exact PV result input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactLoadResultModel(LoadSimulationModelBoundary):
    result: LoadSimulationResult

    def simulate(self, simulation_input: LoadSimulationInput) -> LoadSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be the exact Load result input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactTariffResultModel(TariffSimulationModelBoundary):
    result: TariffSimulationResult

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be the exact Tariff result input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactBatteryResultModel(BatterySimulationModelBoundary):
    result: BatterySimulationResult

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be the exact Battery result input")
        return self.result


@dataclass(frozen=True, slots=True)
class DailySimulationResult:
    """Preserve exact evidence for one completed 24-hour demo simulation."""

    source_input: DailySimulationScenarioInput
    scenario: SimulationScenario
    traces: tuple[SimulationExecutionTrace, ...]
    progressions: tuple[SimulationStepProgression, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, DailySimulationScenarioInput):
            raise TypeError("source_input must be a DailySimulationScenarioInput")
        if not isinstance(self.scenario, SimulationScenario):
            raise TypeError("scenario must be a SimulationScenario")
        if not isinstance(self.traces, tuple):
            raise TypeError("traces must be a tuple")
        if not isinstance(self.progressions, tuple):
            raise TypeError("progressions must be a tuple")
        if len(self.scenario.steps) != HOURS_PER_DAY:
            raise ValueError("scenario must contain exactly 24 steps")
        if len(self.traces) != HOURS_PER_DAY:
            raise ValueError("traces must contain exactly 24 values")
        if len(self.progressions) != HOURS_PER_DAY - 1:
            raise ValueError("progressions must contain exactly 23 values")

        for index, (step, trace) in enumerate(
            zip(self.scenario.steps, self.traces, strict=True)
        ):
            if not isinstance(trace, SimulationExecutionTrace):
                raise TypeError(
                    "traces must contain only SimulationExecutionTrace objects"
                )
            if step.step_identity is not self.source_input.step_identities[index]:
                raise ValueError(
                    "each step must preserve the exact source step identity"
                )
            if trace.simulation_input is not step:
                raise ValueError("each trace must preserve the exact scenario step")

        for index, progression in enumerate(self.progressions):
            if not isinstance(progression, SimulationStepProgression):
                raise TypeError(
                    "progressions must contain only SimulationStepProgression objects"
                )
            if progression.previous_trace is not self.traces[index]:
                raise ValueError(
                    "each progression must preserve the exact previous trace"
                )
            if progression.next_input is not self.scenario.steps[index + 1]:
                raise ValueError(
                    "each progression must preserve the exact next step input"
                )


class DailySimulationRunner:
    """Run one explicit 24-hour scenario without retaining runtime state."""

    __slots__ = ()

    @staticmethod
    def run(source_input: DailySimulationScenarioInput) -> DailySimulationResult:
        """Execute 24 explicit steps in caller order through the Phase 7 executor."""
        if not isinstance(source_input, DailySimulationScenarioInput):
            raise TypeError("source_input must be a DailySimulationScenarioInput")

        pv_model = PVProfileSimulationModel()
        load_model = LoadProfileSimulationModel()
        battery_model = SimpleBatteryPhysicsModel(source_input.battery_parameters)
        battery_state = BatterySimulationState(source_input.initial_soc)
        steps: list[SimulationStepInput] = []
        traces: list[SimulationExecutionTrace] = []
        progressions: list[SimulationStepProgression] = []

        for index, step_identity in enumerate(source_input.step_identities):
            pv_input = PVSimulationInput(
                step_identity,
                source_input.pv_power_curve_kw[index],
            )
            load_input = LoadSimulationInput(
                step_identity,
                source_input.load_power_curve_kw[index],
            )
            tariff_input = TariffSimulationInput(
                step_identity,
                source_input.tariff_curve_cny_per_kwh[index],
                0.0,
            )
            requested_battery_power_kw = DailySimulationRunner._battery_request(
                pv_input.available_power_kw,
                load_input.demand_power_kw,
                battery_state.soc,
                source_input.battery_parameters.reserve_soc,
            )
            source_intent = DecisionIntent(requested_battery_power_kw)
            feasible_decision = FeasibleDecisionIntent(source_intent)
            actuation = BatterySimulationActuation(
                feasible_decision,
                requested_battery_power_kw,
            )
            battery_input = BatterySimulationInput(
                step_identity,
                battery_state,
                actuation,
            )
            grid_input = GridSimulationInput(
                step_identity,
                load_input.demand_power_kw
                + requested_battery_power_kw
                - pv_input.available_power_kw,
            )
            step = SimulationStepInput(
                step_identity,
                pv_input,
                load_input,
                tariff_input,
                battery_input,
                grid_input,
            )
            if traces:
                progressions.append(
                    SimulationStepProgression(
                        traces[-1],
                        traces[-1].step_result,
                        step,
                    )
                )

            trace = DailySimulationRunner._execute_step(
                step,
                pv_model,
                load_model,
                battery_model,
            )
            steps.append(step)
            traces.append(trace)
            battery_state = trace.state.battery_result.next_state

        scenario = SimulationScenario(tuple(steps))
        return DailySimulationResult(
            source_input,
            scenario,
            tuple(traces),
            tuple(progressions),
        )

    @staticmethod
    def _battery_request(
        pv_power_kw: float,
        load_power_kw: float,
        soc: float,
        reserve_soc: float,
    ) -> float:
        imbalance_kw = pv_power_kw - load_power_kw
        if imbalance_kw >= 0:
            return imbalance_kw
        if soc > reserve_soc:
            return imbalance_kw
        return 0.0

    @staticmethod
    def _execute_step(
        step: SimulationStepInput,
        pv_model: PVProfileSimulationModel,
        load_model: LoadProfileSimulationModel,
        battery_model: SimpleBatteryPhysicsModel,
    ) -> SimulationExecutionTrace:
        pv_result = pv_model.simulate(step.pv_input)
        load_result = load_model.simulate(step.load_input)
        tariff_result = TariffSimulationResult(
            step.tariff_input,
            step.tariff_input.import_price_cny_per_kwh,
            step.tariff_input.export_price_cny_per_kwh,
        )
        battery_result = battery_model.simulate(step.battery_input)
        grid_model = GridEnergyBalanceSimulationModel(
            pv_result,
            load_result,
            battery_result,
        )
        bindings = SimulationModelBindingCollection(
            (
                SimulationModelBinding(
                    PVSimulationModelBoundary,
                    _ExactPVResultModel(pv_result),
                ),
                SimulationModelBinding(
                    LoadSimulationModelBoundary,
                    _ExactLoadResultModel(load_result),
                ),
                SimulationModelBinding(
                    TariffSimulationModelBoundary,
                    _ExactTariffResultModel(tariff_result),
                ),
                SimulationModelBinding(
                    BatterySimulationModelBoundary,
                    _ExactBatteryResultModel(battery_result),
                ),
                SimulationModelBinding(GridSimulationModelBoundary, grid_model),
            )
        )
        step_result = SingleStepSimulationExecutor.execute(step, bindings)
        return SimulationExecutionTrace.create(bindings, step_result)
