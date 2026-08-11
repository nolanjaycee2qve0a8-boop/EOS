"""Application-level composition of EMS decisions and deterministic simulation."""

from dataclasses import dataclass

from capability import CapabilityDescriptor
from ems_simulator.battery import SimpleBatteryPhysicsModel
from ems_simulator.grid import GridEnergyBalanceSimulationModel
from ems_simulator.input import HOURS_PER_DAY, DailySimulationScenarioInput
from ems_simulator.load import LoadProfileSimulationModel
from ems_simulator.pv import PVProfileSimulationModel
from ems_simulator.runner import DailySimulationResult
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
    EMSDecision,
    FeasibilityBoundary,
    FeasibleDecision,
    StrategyCoordinator,
)
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition
from simulator import (
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
from simulator.validation import require_non_negative_number, require_number


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
class EMSIntegrationScenarioInput:
    """Preserve caller-supplied daily facts and EMS context evidence.

    This input only relates existing immutable daily data, active capability
    evidence, and explicit context facts. It neither selects a strategy nor
    performs feasibility or simulation work.
    """

    daily_input: DailySimulationScenarioInput
    objective_composition: ObjectiveCapabilityActivationComposition
    capability: CapabilityDescriptor
    battery_power_limit_kw: float
    export_limit_kw: float
    initial_grid_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.daily_input, DailySimulationScenarioInput):
            raise TypeError("daily_input must be a DailySimulationScenarioInput")
        if not isinstance(
            self.objective_composition,
            ObjectiveCapabilityActivationComposition,
        ):
            raise TypeError(
                "objective_composition must be an "
                "ObjectiveCapabilityActivationComposition"
            )
        if not isinstance(self.capability, CapabilityDescriptor):
            raise TypeError("capability must be a CapabilityDescriptor")
        if not any(
            self.capability is active_capability
            for active_capability in (
                self.objective_composition.active_capabilities.active_capabilities
            )
        ):
            raise ValueError(
                "capability must preserve exact active descriptor identity"
            )
        object.__setattr__(
            self,
            "battery_power_limit_kw",
            require_non_negative_number(
                self.battery_power_limit_kw,
                "battery_power_limit_kw",
            ),
        )
        object.__setattr__(
            self,
            "export_limit_kw",
            require_non_negative_number(self.export_limit_kw, "export_limit_kw"),
        )
        object.__setattr__(
            self,
            "initial_grid_power_kw",
            require_number(self.initial_grid_power_kw, "initial_grid_power_kw"),
        )


@dataclass(frozen=True, slots=True)
class EMSIntegrationStepTrace:
    """Preserve exact EMS-to-simulation evidence for one completed step."""

    context: EMSContext
    decision: EMSDecision
    provenance: DecisionProvenance
    feasible_decision: FeasibleDecision
    handoff: ActuationHandoffResult
    simulation_trace: SimulationExecutionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.context, EMSContext):
            raise TypeError("context must be an EMSContext")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(self.provenance, DecisionProvenance):
            raise TypeError("provenance must be a DecisionProvenance")
        if not isinstance(self.feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(self.handoff, ActuationHandoffResult):
            raise TypeError("handoff must be an ActuationHandoffResult")
        if not isinstance(self.simulation_trace, SimulationExecutionTrace):
            raise TypeError("simulation_trace must be a SimulationExecutionTrace")
        if self.decision.source_context is not self.context:
            raise ValueError("decision must preserve exact context identity")
        if self.provenance.decision is not self.decision:
            raise ValueError("provenance must preserve exact decision identity")
        if self.feasible_decision.source_decision is not self.decision:
            raise ValueError("feasible_decision must preserve exact decision identity")
        if self.feasible_decision.source_provenance is not self.provenance:
            raise ValueError(
                "feasible_decision must preserve exact provenance identity"
            )
        if self.handoff.source_feasible_decision is not self.feasible_decision:
            raise ValueError("handoff must preserve exact feasible_decision identity")
        if (
            self.simulation_trace.simulation_input.battery_input.actuation
            is not self.handoff.actuation
        ):
            raise ValueError("simulation trace must preserve exact handoff actuation")


@dataclass(frozen=True, slots=True)
class EMSIntegrationResult:
    """Relate one exact scenario input to full EMS and simulation evidence."""

    source_input: EMSIntegrationScenarioInput
    simulation_result: DailySimulationResult
    traces: tuple[EMSIntegrationStepTrace, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EMSIntegrationScenarioInput):
            raise TypeError("source_input must be an EMSIntegrationScenarioInput")
        if not isinstance(self.simulation_result, DailySimulationResult):
            raise TypeError("simulation_result must be a DailySimulationResult")
        if not isinstance(self.traces, tuple):
            raise TypeError("traces must be a tuple")
        if self.simulation_result.source_input is not self.source_input.daily_input:
            raise ValueError("simulation_result must preserve exact daily_input")
        if len(self.traces) != HOURS_PER_DAY:
            raise ValueError("traces must contain exactly 24 values")
        for index, trace in enumerate(self.traces):
            if not isinstance(trace, EMSIntegrationStepTrace):
                raise TypeError(
                    "traces must contain only EMSIntegrationStepTrace objects"
                )
            if trace.simulation_trace is not self.simulation_result.traces[index]:
                raise ValueError(
                    "each trace must preserve exact simulation trace identity"
                )


class EMSIntegrationRunner:
    """Compose caller-owned EMS boundaries with existing deterministic models."""

    __slots__ = ()

    @staticmethod
    def run(
        source_input: EMSIntegrationScenarioInput,
        *,
        coordinator: StrategyCoordinator,
        feasibility: FeasibilityBoundary,
        handoff: ActuationHandoffBoundary,
    ) -> EMSIntegrationResult:
        """Run explicit daily inputs while retaining every decision artifact."""
        if not isinstance(source_input, EMSIntegrationScenarioInput):
            raise TypeError("source_input must be an EMSIntegrationScenarioInput")
        if not isinstance(coordinator, StrategyCoordinator):
            raise TypeError("coordinator must be a StrategyCoordinator")
        if not isinstance(feasibility, FeasibilityBoundary):
            raise TypeError("feasibility must be a FeasibilityBoundary")
        if not isinstance(handoff, ActuationHandoffBoundary):
            raise TypeError("handoff must be an ActuationHandoffBoundary")

        daily_input = source_input.daily_input
        pv_model = PVProfileSimulationModel()
        load_model = LoadProfileSimulationModel()
        battery_model = SimpleBatteryPhysicsModel(daily_input.battery_parameters)
        battery_state = BatterySimulationState(daily_input.initial_soc)
        previous_grid_power_kw = source_input.initial_grid_power_kw
        steps: list[SimulationStepInput] = []
        simulation_traces: list[SimulationExecutionTrace] = []
        integration_traces: list[EMSIntegrationStepTrace] = []
        progressions: list[SimulationStepProgression] = []

        for index, _step_identity in enumerate(daily_input.step_identities):
            context = EMSIntegrationRunner._create_context(
                source_input,
                index,
                battery_state,
                previous_grid_power_kw,
            )
            decision = coordinator.evaluate(context)
            provenance = DecisionProvenance(
                context,
                decision.source_strategy,
                decision,
            )
            feasible_decision = feasibility.evaluate(decision, provenance=provenance)
            handoff_result = handoff.handoff(feasible_decision)

            step = EMSIntegrationRunner._create_step(
                daily_input,
                index,
                battery_state,
                handoff_result,
            )
            if simulation_traces:
                progressions.append(
                    SimulationStepProgression(
                        simulation_traces[-1],
                        simulation_traces[-1].step_result,
                        step,
                    )
                )
            simulation_trace = EMSIntegrationRunner._execute_step(
                step,
                pv_model,
                load_model,
                battery_model,
            )
            integration_trace = EMSIntegrationStepTrace(
                context,
                decision,
                provenance,
                feasible_decision,
                handoff_result,
                simulation_trace,
            )
            steps.append(step)
            simulation_traces.append(simulation_trace)
            integration_traces.append(integration_trace)
            battery_state = simulation_trace.state.battery_result.next_state
            previous_grid_power_kw = (
                simulation_trace.state.grid_result.actual_grid_power_kw
            )

        scenario = SimulationScenario(tuple(steps))
        simulation_result = DailySimulationResult(
            daily_input,
            scenario,
            tuple(simulation_traces),
            tuple(progressions),
        )
        return EMSIntegrationResult(
            source_input,
            simulation_result,
            tuple(integration_traces),
        )

    @staticmethod
    def _create_context(
        source_input: EMSIntegrationScenarioInput,
        index: int,
        battery_state: BatterySimulationState,
        grid_power_kw: float,
    ) -> EMSContext:
        daily_input = source_input.daily_input
        timestamp = daily_input.step_identities[index].timestamp
        if timestamp is None:
            raise ValueError("daily_input step timestamp must be present")
        source_context = DecisionContext(
            timestamp=timestamp,
            soc=battery_state.soc,
            battery_power_limit_kw=source_input.battery_power_limit_kw,
            battery_energy_capacity_kwh=daily_input.battery_parameters.capacity_kwh,
            pv_power_kw=daily_input.pv_power_curve_kw[index],
            load_power_kw=daily_input.load_power_curve_kw[index],
            grid_power_kw=grid_power_kw,
            electricity_price_cny_per_kwh=daily_input.tariff_curve_cny_per_kwh[index],
            reserve_soc=daily_input.battery_parameters.reserve_soc,
            export_limit_kw=source_input.export_limit_kw,
        )
        return EMSContext(
            source_context,
            source_input.objective_composition,
            source_input.capability,
        )

    @staticmethod
    def _create_step(
        daily_input: DailySimulationScenarioInput,
        index: int,
        battery_state: BatterySimulationState,
        handoff: ActuationHandoffResult,
    ) -> SimulationStepInput:
        step_identity = daily_input.step_identities[index]
        pv_input = PVSimulationInput(
            step_identity,
            daily_input.pv_power_curve_kw[index],
        )
        load_input = LoadSimulationInput(
            step_identity,
            daily_input.load_power_curve_kw[index],
        )
        tariff_input = TariffSimulationInput(
            step_identity,
            daily_input.tariff_curve_cny_per_kwh[index],
            0.0,
        )
        battery_input = BatterySimulationInput(
            step_identity,
            battery_state,
            handoff.actuation,
        )
        grid_input = GridSimulationInput(
            step_identity,
            load_input.demand_power_kw
            + handoff.actuation.battery_power_kw
            - pv_input.available_power_kw,
        )
        return SimulationStepInput(
            step_identity,
            pv_input,
            load_input,
            tariff_input,
            battery_input,
            grid_input,
        )

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
