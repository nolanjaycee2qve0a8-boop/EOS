"""Phase 7 deterministic simulation execution integration validation."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

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
    ScenarioExecutionBoundary,
    ScenarioExecutionResult,
    SimulationExecutionTrace,
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationScenario,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepProgression,
    SimulationStepResult,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)


class Phase7PVModel(PVSimulationModelBoundary):
    __slots__ = ("calls", "order")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.calls: list[PVSimulationInput] = []
        self.order = order

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        self.calls.append(simulation_input)
        self.order.append(("pv", simulation_input.step_identity.sequence))
        return PVSimulationResult(simulation_input, simulation_input.available_power_kw)


class Phase7LoadModel(LoadSimulationModelBoundary):
    __slots__ = ("calls", "fail_sequence", "order")

    def __init__(
        self,
        order: list[tuple[str, int]],
        fail_sequence: int | None = None,
    ) -> None:
        self.calls: list[LoadSimulationInput] = []
        self.fail_sequence = fail_sequence
        self.order = order

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        self.calls.append(simulation_input)
        sequence = simulation_input.step_identity.sequence
        self.order.append(("load", sequence))
        if sequence == self.fail_sequence:
            raise PHASE7_FAILURE
        return LoadSimulationResult(simulation_input, simulation_input.demand_power_kw)


class Phase7TariffModel(TariffSimulationModelBoundary):
    __slots__ = ("calls", "order")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.calls: list[TariffSimulationInput] = []
        self.order = order

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        self.calls.append(simulation_input)
        self.order.append(("tariff", simulation_input.step_identity.sequence))
        return TariffSimulationResult(
            simulation_input,
            simulation_input.import_price_cny_per_kwh,
            simulation_input.export_price_cny_per_kwh,
        )


class Phase7BatteryModel(BatterySimulationModelBoundary):
    __slots__ = ("calls", "next_states", "order")

    def __init__(
        self,
        order: list[tuple[str, int]],
        next_states: dict[int, BatterySimulationState],
    ) -> None:
        self.calls: list[BatterySimulationInput] = []
        self.next_states = next_states
        self.order = order

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        self.calls.append(simulation_input)
        sequence = simulation_input.step_identity.sequence
        self.order.append(("battery", sequence))
        return BatterySimulationResult(
            simulation_input,
            self.next_states[sequence],
            simulation_input.actuation.battery_power_kw,
        )


class Phase7GridModel(GridSimulationModelBoundary):
    __slots__ = ("calls", "order")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.calls: list[GridSimulationInput] = []
        self.order = order

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        self.calls.append(simulation_input)
        self.order.append(("grid", simulation_input.step_identity.sequence))
        return GridSimulationResult(
            simulation_input,
            simulation_input.requested_grid_power_kw,
        )


PHASE7_FAILURE = RuntimeError("phase 7 component failure")

type Phase7Models = tuple[
    Phase7PVModel,
    Phase7LoadModel,
    Phase7TariffModel,
    Phase7BatteryModel,
    Phase7GridModel,
]


def make_step(
    sequence: int, battery_state: BatterySimulationState
) -> SimulationStepInput:
    identity = SimulationStepIdentity(
        sequence,
        60.0,
        datetime(2026, 8, 7, 14, sequence, tzinfo=UTC),
    )
    feasible = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible, 1.0)
    return SimulationStepInput(
        identity,
        PVSimulationInput(identity, 5.0 + sequence),
        LoadSimulationInput(identity, 4.0 + sequence),
        TariffSimulationInput(identity, 0.8, 0.2),
        BatterySimulationInput(identity, battery_state, actuation),
        GridSimulationInput(identity, 1.0),
    )


def make_bindings(
    order: list[tuple[str, int]],
    next_states: dict[int, BatterySimulationState],
    *,
    fail_sequence: int | None = None,
) -> tuple[SimulationModelBindingCollection, Phase7Models]:
    models: Phase7Models = (
        Phase7PVModel(order),
        Phase7LoadModel(order, fail_sequence),
        Phase7TariffModel(order),
        Phase7BatteryModel(order, next_states),
        Phase7GridModel(order),
    )
    pv, load, tariff, battery, grid = models
    bindings = SimulationModelBindingCollection(
        (
            SimulationModelBinding(PVSimulationModelBoundary, pv),
            SimulationModelBinding(LoadSimulationModelBoundary, load),
            SimulationModelBinding(BatterySimulationModelBoundary, battery),
            SimulationModelBinding(GridSimulationModelBoundary, grid),
            SimulationModelBinding(TariffSimulationModelBoundary, tariff),
        )
    )
    return bindings, models


def result_values(result: ScenarioExecutionResult) -> tuple[tuple[float, ...], ...]:
    return tuple(
        (
            trace.state.pv_result.actual_power_kw,
            trace.state.load_result.actual_power_kw,
            trace.state.tariff_result.import_price_cny_per_kwh,
            trace.state.tariff_result.export_price_cny_per_kwh,
            trace.state.battery_result.actual_power_kw,
            trace.state.battery_result.next_state.soc,
            trace.state.grid_result.actual_grid_power_kw,
        )
        for trace in result.traces
    )


def test_phase7_end_to_end_identity_order_and_progression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_state = BatterySimulationState(0.4)
    first_next_state = BatterySimulationState(0.5)
    second_next_state = BatterySimulationState(0.6)
    first_step = make_step(0, initial_state)
    second_step = make_step(1, first_next_state)
    caller_steps = (first_step, second_step)
    scenario = SimulationScenario(caller_steps)
    order: list[tuple[str, int]] = []
    bindings, models = make_bindings(
        order,
        {0: first_next_state, 1: second_next_state},
    )
    generated_traces: list[SimulationExecutionTrace] = []
    original_create: Callable[
        [SimulationModelBindingCollection, SimulationStepResult],
        SimulationExecutionTrace,
    ] = SimulationExecutionTrace.create

    def recording_create(
        source_bindings: SimulationModelBindingCollection,
        step_result: SimulationStepResult,
    ) -> SimulationExecutionTrace:
        trace = original_create(source_bindings, step_result)
        generated_traces.append(trace)
        return trace

    monkeypatch.setattr(
        SimulationExecutionTrace,
        "create",
        staticmethod(recording_create),
    )

    result = ScenarioExecutionBoundary.execute(scenario, bindings)

    assert result.scenario is scenario
    assert result.scenario.steps is caller_steps
    assert result.bindings is bindings
    assert len(result.traces) == 2
    assert result.traces[0] is generated_traces[0]
    assert result.traces[1] is generated_traces[1]
    assert result.traces[0].simulation_input is first_step
    assert result.traces[1].simulation_input is second_step
    assert all(trace.bindings is bindings for trace in result.traces)
    assert [len(model.calls) for model in models] == [2, 2, 2, 2, 2]
    assert order == [
        ("pv", 0),
        ("load", 0),
        ("battery", 0),
        ("grid", 0),
        ("tariff", 0),
        ("pv", 1),
        ("load", 1),
        ("battery", 1),
        ("grid", 1),
        ("tariff", 1),
    ]

    first_trace = result.traces[0]
    progression = SimulationStepProgression(
        first_trace,
        first_trace.step_result,
        second_step,
    )
    assert progression.previous_trace is first_trace
    assert progression.previous_result is first_trace.step_result
    assert progression.next_input is second_step
    assert (
        progression.previous_result.state.battery_result.next_state is first_next_state
    )
    assert progression.next_input.battery_input.source_state is first_next_state


def test_phase7_same_inputs_produce_same_observed_values() -> None:
    initial_state = BatterySimulationState(0.4)
    first_next_state = BatterySimulationState(0.5)
    second_next_state = BatterySimulationState(0.6)
    scenario = SimulationScenario(
        (
            make_step(0, initial_state),
            make_step(1, first_next_state),
        )
    )
    first_bindings, first_models = make_bindings(
        [],
        {0: first_next_state, 1: second_next_state},
    )
    second_bindings, second_models = make_bindings(
        [],
        {0: first_next_state, 1: second_next_state},
    )

    first_result = ScenarioExecutionBoundary.execute(scenario, first_bindings)
    second_result = ScenarioExecutionBoundary.execute(scenario, second_bindings)

    assert result_values(first_result) == result_values(second_result)
    assert [len(model.calls) for model in first_models] == [2, 2, 2, 2, 2]
    assert [len(model.calls) for model in second_models] == [2, 2, 2, 2, 2]
    assert first_result.scenario is scenario
    assert second_result.scenario is scenario


def test_phase7_component_failure_stops_without_retry_skip_or_success_result() -> None:
    initial_state = BatterySimulationState(0.4)
    first_next_state = BatterySimulationState(0.5)
    second_next_state = BatterySimulationState(0.6)
    third_next_state = BatterySimulationState(0.7)
    scenario = SimulationScenario(
        (
            make_step(0, initial_state),
            make_step(1, first_next_state),
            make_step(2, second_next_state),
        )
    )
    order: list[tuple[str, int]] = []
    bindings, models = make_bindings(
        order,
        {0: first_next_state, 1: second_next_state, 2: third_next_state},
        fail_sequence=1,
    )
    completed_result: ScenarioExecutionResult | None = None

    with pytest.raises(RuntimeError) as caught:
        completed_result = ScenarioExecutionBoundary.execute(scenario, bindings)

    assert caught.value is PHASE7_FAILURE
    assert completed_result is None
    assert order == [
        ("pv", 0),
        ("load", 0),
        ("battery", 0),
        ("grid", 0),
        ("tariff", 0),
        ("pv", 1),
        ("load", 1),
    ]
    pv, load, tariff, battery, grid = models
    assert len(pv.calls) == 2
    assert len(load.calls) == 2
    assert len(tariff.calls) == 1
    assert len(battery.calls) == 1
    assert len(grid.calls) == 1
    assert all(
        call.step_identity.sequence != 2 for model in models for call in model.calls
    )
