"""Tests for deterministic execution of an explicit simulation scenario."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

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
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationScenario,
    SimulationStepIdentity,
    SimulationStepInput,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import scenario_execution as scenario_execution_module


class RecordingPVModel(PVSimulationModelBoundary):
    __slots__ = ("order", "received")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.order = order
        self.received: list[PVSimulationInput] = []

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        self.order.append(("pv", simulation_input.step_identity.sequence))
        self.received.append(simulation_input)
        return PVSimulationResult(simulation_input, simulation_input.available_power_kw)


class RecordingLoadModel(LoadSimulationModelBoundary):
    __slots__ = ("error_sequence", "order", "received")

    def __init__(
        self,
        order: list[tuple[str, int]],
        error_sequence: int | None = None,
    ) -> None:
        self.order = order
        self.error_sequence = error_sequence
        self.received: list[LoadSimulationInput] = []

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        sequence = simulation_input.step_identity.sequence
        self.order.append(("load", sequence))
        self.received.append(simulation_input)
        if sequence == self.error_sequence:
            raise SCENARIO_ERROR
        return LoadSimulationResult(simulation_input, simulation_input.demand_power_kw)


class RecordingTariffModel(TariffSimulationModelBoundary):
    __slots__ = ("order", "received")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.order = order
        self.received: list[TariffSimulationInput] = []

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        self.order.append(("tariff", simulation_input.step_identity.sequence))
        self.received.append(simulation_input)
        return TariffSimulationResult(
            simulation_input,
            simulation_input.import_price_cny_per_kwh,
            simulation_input.export_price_cny_per_kwh,
        )


class RecordingBatteryModel(BatterySimulationModelBoundary):
    __slots__ = ("order", "received")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.order = order
        self.received: list[BatterySimulationInput] = []

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        self.order.append(("battery", simulation_input.step_identity.sequence))
        self.received.append(simulation_input)
        return BatterySimulationResult(
            simulation_input,
            simulation_input.source_state,
            simulation_input.actuation.battery_power_kw,
        )


class RecordingGridModel(GridSimulationModelBoundary):
    __slots__ = ("order", "received")

    def __init__(self, order: list[tuple[str, int]]) -> None:
        self.order = order
        self.received: list[GridSimulationInput] = []

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        self.order.append(("grid", simulation_input.step_identity.sequence))
        self.received.append(simulation_input)
        return GridSimulationResult(
            simulation_input,
            simulation_input.requested_grid_power_kw,
        )


SCENARIO_ERROR = RuntimeError("scenario step failed")


def make_step(sequence: int) -> SimulationStepInput:
    identity = SimulationStepIdentity(
        sequence,
        60.0,
        datetime(2026, 8, 7, 10, sequence, tzinfo=UTC),
    )
    feasible = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible, 1.0)
    return SimulationStepInput(
        identity,
        PVSimulationInput(identity, 5.0),
        LoadSimulationInput(identity, 4.0),
        TariffSimulationInput(identity, 0.8, 0.2),
        BatterySimulationInput(identity, BatterySimulationState(0.5), actuation),
        GridSimulationInput(identity, 1.0),
    )


def make_bindings(
    order: list[tuple[str, int]],
    *,
    error_sequence: int | None = None,
) -> tuple[
    SimulationModelBindingCollection,
    RecordingPVModel,
    RecordingLoadModel,
    RecordingTariffModel,
    RecordingBatteryModel,
    RecordingGridModel,
]:
    pv = RecordingPVModel(order)
    load = RecordingLoadModel(order, error_sequence)
    tariff = RecordingTariffModel(order)
    battery = RecordingBatteryModel(order)
    grid = RecordingGridModel(order)
    bindings = SimulationModelBindingCollection(
        (
            SimulationModelBinding(LoadSimulationModelBoundary, load),
            SimulationModelBinding(PVSimulationModelBoundary, pv),
            SimulationModelBinding(GridSimulationModelBoundary, grid),
            SimulationModelBinding(TariffSimulationModelBoundary, tariff),
            SimulationModelBinding(BatterySimulationModelBoundary, battery),
        )
    )
    return bindings, pv, load, tariff, battery, grid


def test_scenario_executes_steps_and_models_once_in_exact_caller_order() -> None:
    first = make_step(2)
    second = make_step(0)
    caller_steps = (first, second)
    scenario = SimulationScenario(caller_steps)
    order: list[tuple[str, int]] = []
    bindings, pv, load, tariff, battery, grid = make_bindings(order)

    result = ScenarioExecutionBoundary.execute(scenario, bindings)

    assert result.scenario is scenario
    assert result.scenario.steps is caller_steps
    assert result.bindings is bindings
    assert tuple(trace.simulation_input for trace in result.traces) == caller_steps
    assert result.traces[0].simulation_input is first
    assert result.traces[1].simulation_input is second
    assert all(trace.bindings is bindings for trace in result.traces)
    assert order == [
        ("load", 2),
        ("pv", 2),
        ("grid", 2),
        ("tariff", 2),
        ("battery", 2),
        ("load", 0),
        ("pv", 0),
        ("grid", 0),
        ("tariff", 0),
        ("battery", 0),
    ]
    assert pv.received == [first.pv_input, second.pv_input]
    assert load.received == [first.load_input, second.load_input]
    assert tariff.received == [first.tariff_input, second.tariff_input]
    assert battery.received == [first.battery_input, second.battery_input]
    assert grid.received == [first.grid_input, second.grid_input]


def test_scenario_result_preserves_exact_step_evidence_chain() -> None:
    step = make_step(0)
    scenario = SimulationScenario((step,))
    bindings, *_ = make_bindings([])

    result = ScenarioExecutionBoundary.execute(scenario, bindings)
    trace = result.traces[0]

    assert trace.step_result.simulation_input is step
    assert trace.simulation_input is step
    assert trace.state is trace.step_result.state
    assert trace.state.pv_result.simulation_input is step.pv_input
    assert trace.state.load_result.simulation_input is step.load_input
    assert trace.state.tariff_result.simulation_input is step.tariff_input
    assert trace.state.battery_result.simulation_input is step.battery_input
    assert trace.state.grid_result.simulation_input is step.grid_input


def test_empty_scenario_preserves_identity_without_model_execution() -> None:
    scenario = SimulationScenario(())
    order: list[tuple[str, int]] = []
    bindings, *_ = make_bindings(order)

    result = ScenarioExecutionBoundary.execute(scenario, bindings)

    assert result.scenario is scenario
    assert result.bindings is bindings
    assert result.traces == ()
    assert order == []


def test_exception_stops_scenario_and_propagates_exact_object() -> None:
    first = make_step(2)
    failing = make_step(0)
    later = make_step(1)
    scenario = SimulationScenario((first, failing, later))
    order: list[tuple[str, int]] = []
    bindings, *_ = make_bindings(order, error_sequence=0)

    with pytest.raises(RuntimeError) as caught:
        ScenarioExecutionBoundary.execute(scenario, bindings)

    assert caught.value is SCENARIO_ERROR
    assert order == [
        ("load", 2),
        ("pv", 2),
        ("grid", 2),
        ("tariff", 2),
        ("battery", 2),
        ("load", 0),
    ]


@pytest.mark.parametrize(
    ("scenario", "bindings", "field_name"),
    [
        (cast(Any, object()), make_bindings([])[0], "scenario"),
        (SimulationScenario(()), cast(Any, object()), "bindings"),
    ],
)
def test_execution_rejects_invalid_inputs_before_model_execution(
    scenario: SimulationScenario,
    bindings: SimulationModelBindingCollection,
    field_name: str,
) -> None:
    with pytest.raises(TypeError, match=field_name):
        ScenarioExecutionBoundary.execute(scenario, bindings)


def test_result_requires_exact_complete_ordered_trace_coverage() -> None:
    first = make_step(0)
    second = make_step(1)
    scenario = SimulationScenario((first, second))
    bindings, *_ = make_bindings([])
    completed = ScenarioExecutionBoundary.execute(scenario, bindings)

    with pytest.raises(ValueError, match="every scenario step exactly once"):
        ScenarioExecutionResult(scenario, bindings, completed.traces[:1])
    with pytest.raises(ValueError, match="caller-ordered scenario step"):
        ScenarioExecutionResult(scenario, bindings, tuple(reversed(completed.traces)))
    with pytest.raises(ValueError, match="exact bindings"):
        ScenarioExecutionResult(
            scenario,
            make_bindings([])[0],
            completed.traces,
        )


def test_repeated_step_occurrences_execute_once_each_with_distinct_traces() -> None:
    repeated_step = make_step(0)
    scenario = SimulationScenario((repeated_step, repeated_step))
    order: list[tuple[str, int]] = []
    bindings, *_ = make_bindings(order)

    result = ScenarioExecutionBoundary.execute(scenario, bindings)

    assert result.traces[0] is not result.traces[1]
    assert result.traces[0].simulation_input is repeated_step
    assert result.traces[1].simulation_input is repeated_step
    assert len(order) == 10

    with pytest.raises(ValueError, match="distinct trace"):
        ScenarioExecutionResult(
            scenario,
            bindings,
            (result.traces[0], result.traces[0]),
        )


def test_result_rejects_mutable_or_invalid_trace_collection() -> None:
    scenario = SimulationScenario(())
    bindings, *_ = make_bindings([])

    with pytest.raises(TypeError, match="traces"):
        ScenarioExecutionResult(scenario, bindings, cast(Any, []))
    with pytest.raises(TypeError, match="SimulationExecutionTrace"):
        ScenarioExecutionResult(
            SimulationScenario((make_step(0),)),
            bindings,
            cast(Any, (object(),)),
        )


@pytest.mark.parametrize(
    ("scenario", "bindings", "field_name"),
    [
        (cast(Any, object()), make_bindings([])[0], "scenario"),
        (SimulationScenario(()), cast(Any, object()), "bindings"),
    ],
)
def test_result_rejects_invalid_source_types(
    scenario: SimulationScenario,
    bindings: SimulationModelBindingCollection,
    field_name: str,
) -> None:
    with pytest.raises(TypeError, match=field_name):
        ScenarioExecutionResult(scenario, bindings, ())


def test_result_is_frozen_slotted_and_has_exact_fields() -> None:
    result = ScenarioExecutionBoundary.execute(
        SimulationScenario(()),
        make_bindings([])[0],
    )

    assert is_dataclass(ScenarioExecutionResult)
    assert cast(Any, ScenarioExecutionResult).__dataclass_params__.frozen
    assert ScenarioExecutionResult.__slots__ == ("scenario", "bindings", "traces")
    assert tuple(field.name for field in fields(ScenarioExecutionResult)) == (
        "scenario",
        "bindings",
        "traces",
    )
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).traces = ()


def test_boundary_is_stateless_empty_slotted_and_has_exact_signature() -> None:
    boundary = ScenarioExecutionBoundary()
    signature = inspect.signature(ScenarioExecutionBoundary.execute)

    assert ScenarioExecutionBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")
    assert tuple(signature.parameters) == ("scenario", "bindings")
    assert signature.return_annotation is ScenarioExecutionResult


def test_module_only_coordinates_existing_simulation_boundaries() -> None:
    tree = ast.parse(inspect.getsource(scenario_execution_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "simulator.aggregate",
        "simulator.binding",
        "simulator.executor",
        "simulator.trace",
    }
    source = inspect.getsource(scenario_execution_module).lower()
    for forbidden in (
        "runtime",
        "scheduler",
        "device",
        "command",
        "dispatcher",
        "optimization",
        "forecast",
        "registry",
        "factory",
        "cache",
        "history",
        "retry",
        "timeout",
        "next_step",
    ):
        assert forbidden not in source
