"""End-to-end validation of the Phase 6 immutable simulation flow."""

from datetime import UTC, datetime

from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationScenario,
    SimulationState,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)


class RecordingPVModel(PVSimulationModelBoundary):
    __slots__ = ("actual_power_kw", "calls", "received")

    def __init__(self, actual_power_kw: float) -> None:
        self.actual_power_kw = actual_power_kw
        self.calls = 0
        self.received: PVSimulationInput | None = None

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        self.calls += 1
        self.received = simulation_input
        return PVSimulationResult(simulation_input, self.actual_power_kw)


class RecordingLoadModel(LoadSimulationModelBoundary):
    __slots__ = ("actual_power_kw", "calls", "received")

    def __init__(self, actual_power_kw: float) -> None:
        self.actual_power_kw = actual_power_kw
        self.calls = 0
        self.received: LoadSimulationInput | None = None

    def simulate(self, simulation_input: LoadSimulationInput) -> LoadSimulationResult:
        self.calls += 1
        self.received = simulation_input
        return LoadSimulationResult(simulation_input, self.actual_power_kw)


class RecordingTariffModel(TariffSimulationModelBoundary):
    __slots__ = ("calls", "export_price", "import_price", "received")

    def __init__(self, import_price: float, export_price: float) -> None:
        self.import_price = import_price
        self.export_price = export_price
        self.calls = 0
        self.received: TariffSimulationInput | None = None

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        self.calls += 1
        self.received = simulation_input
        return TariffSimulationResult(
            simulation_input,
            self.import_price,
            self.export_price,
        )


class RecordingBatteryModel(BatterySimulationModelBoundary):
    __slots__ = ("actual_power_kw", "calls", "next_state", "received")

    def __init__(
        self,
        next_state: BatterySimulationState,
        actual_power_kw: float,
    ) -> None:
        self.next_state = next_state
        self.actual_power_kw = actual_power_kw
        self.calls = 0
        self.received: BatterySimulationInput | None = None

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        self.calls += 1
        self.received = simulation_input
        return BatterySimulationResult(
            simulation_input,
            self.next_state,
            self.actual_power_kw,
        )


class RecordingGridModel(GridSimulationModelBoundary):
    __slots__ = ("actual_grid_power_kw", "calls", "received")

    def __init__(self, actual_grid_power_kw: float) -> None:
        self.actual_grid_power_kw = actual_grid_power_kw
        self.calls = 0
        self.received: GridSimulationInput | None = None

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        self.calls += 1
        self.received = simulation_input
        return GridSimulationResult(simulation_input, self.actual_grid_power_kw)


def make_step_input(
    sequence: int,
    battery_power_kw: float,
    grid_power_kw: float,
) -> tuple[
    SimulationStepInput,
    FeasibleDecisionIntent,
    BatterySimulationState,
]:
    step = SimulationStepIdentity(
        sequence,
        300.0,
        datetime(2026, 8, 6, 12, sequence, tzinfo=UTC),
    )
    feasible_decision = FeasibleDecisionIntent(
        DecisionIntent(battery_power_kw),
    )
    source_battery_state = BatterySimulationState(0.4)
    actuation = BatterySimulationActuation(
        feasible_decision,
        battery_power_kw,
    )
    simulation_input = SimulationStepInput(
        step,
        PVSimulationInput(step, 6.0),
        LoadSimulationInput(step, 4.0),
        TariffSimulationInput(step, 0.6, 0.2),
        BatterySimulationInput(step, source_battery_state, actuation),
        GridSimulationInput(step, grid_power_kw),
    )
    return simulation_input, feasible_decision, source_battery_state


def test_phase6_complete_step_preserves_identity_and_executes_models_once() -> None:
    simulation_input, feasible_decision, source_battery_state = make_step_input(
        sequence=0,
        battery_power_kw=2.0,
        grid_power_kw=1.0,
    )
    next_battery_state = BatterySimulationState(0.45)
    pv_model = RecordingPVModel(5.0)
    load_model = RecordingLoadModel(3.5)
    tariff_model = RecordingTariffModel(0.6, 0.2)
    battery_model = RecordingBatteryModel(next_battery_state, 2.0)
    grid_model = RecordingGridModel(1.0)

    pv_result = pv_model.simulate(simulation_input.pv_input)
    load_result = load_model.simulate(simulation_input.load_input)
    tariff_result = tariff_model.simulate(simulation_input.tariff_input)
    battery_result = battery_model.simulate(simulation_input.battery_input)
    grid_result = grid_model.simulate(simulation_input.grid_input)
    state = SimulationState(
        simulation_input.step_identity,
        pv_result,
        load_result,
        tariff_result,
        battery_result,
        grid_result,
    )
    step_result = SimulationStepResult(simulation_input, state)

    assert pv_model.received is simulation_input.pv_input
    assert load_model.received is simulation_input.load_input
    assert tariff_model.received is simulation_input.tariff_input
    assert battery_model.received is simulation_input.battery_input
    assert grid_model.received is simulation_input.grid_input
    assert (
        simulation_input.battery_input.actuation.source_feasible_decision
        is feasible_decision
    )
    assert simulation_input.battery_input.source_state is source_battery_state
    assert battery_result.next_state is next_battery_state
    assert step_result.simulation_input is simulation_input
    assert step_result.state is state
    assert state.pv_result is pv_result
    assert state.load_result is load_result
    assert state.tariff_result is tariff_result
    assert state.battery_result is battery_result
    assert state.grid_result is grid_result
    assert source_battery_state.soc == 0.4
    assert next_battery_state.soc == 0.45
    assert [
        pv_model.calls,
        load_model.calls,
        tariff_model.calls,
        battery_model.calls,
        grid_model.calls,
    ] == [1, 1, 1, 1, 1]


def test_phase6_aggregation_does_not_reexecute_component_models() -> None:
    simulation_input, _, _ = make_step_input(0, -1.5, -0.5)
    models = (
        RecordingPVModel(4.0),
        RecordingLoadModel(4.0),
        RecordingTariffModel(0.6, 0.2),
        RecordingBatteryModel(BatterySimulationState(0.35), -1.5),
        RecordingGridModel(-0.5),
    )

    results = (
        models[0].simulate(simulation_input.pv_input),
        models[1].simulate(simulation_input.load_input),
        models[2].simulate(simulation_input.tariff_input),
        models[3].simulate(simulation_input.battery_input),
        models[4].simulate(simulation_input.grid_input),
    )
    state = SimulationState(simulation_input.step_identity, *results)
    step_result = SimulationStepResult(simulation_input, state)

    assert step_result.state.battery_result.actual_power_kw == -1.5
    assert step_result.state.grid_result.actual_grid_power_kw == -0.5
    assert [model.calls for model in models] == [1, 1, 1, 1, 1]


def test_phase6_scenario_preserves_exact_steps_and_caller_order() -> None:
    first, _, _ = make_step_input(0, 0.0, 0.0)
    second, _, _ = make_step_input(1, -1.0, 1.0)
    caller_steps = (second, first)

    scenario = SimulationScenario(caller_steps)

    assert scenario.steps is caller_steps
    assert scenario.steps[0] is second
    assert scenario.steps[1] is first
    assert scenario.steps[0].step_identity.sequence == 1
    assert scenario.steps[1].step_identity.sequence == 0


def test_phase6_flow_keeps_simulation_separate_from_runtime_and_commands() -> None:
    simulation_input, _, _ = make_step_input(0, 0.0, 0.0)
    state = SimulationState(
        simulation_input.step_identity,
        PVSimulationResult(simulation_input.pv_input, 5.0),
        LoadSimulationResult(simulation_input.load_input, 4.0),
        TariffSimulationResult(simulation_input.tariff_input, 0.6, 0.2),
        BatterySimulationResult(
            simulation_input.battery_input,
            simulation_input.battery_input.source_state,
            0.0,
        ),
        GridSimulationResult(simulation_input.grid_input, 0.0),
    )
    result = SimulationStepResult(simulation_input, state)

    for artifact in (simulation_input, state, result):
        assert not hasattr(artifact, "runtime")
        assert not hasattr(artifact, "command")
        assert not hasattr(artifact, "device")
        assert not hasattr(artifact, "advance")
