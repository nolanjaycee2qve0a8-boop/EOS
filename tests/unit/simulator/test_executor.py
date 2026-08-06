"""Tests for deterministic execution of one explicit simulation step."""

import ast
import inspect
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
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    SingleStepSimulationExecutor,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import executor as executor_module


class RecordingPVModel(PVSimulationModelBoundary):
    __slots__ = ("calls", "order", "received")

    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self.order = order
        self.received: PVSimulationInput | None = None

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        self.calls += 1
        self.order.append("pv")
        self.received = simulation_input
        return PVSimulationResult(simulation_input, 4.0)


class RecordingLoadModel(LoadSimulationModelBoundary):
    __slots__ = ("calls", "order", "received")

    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self.order = order
        self.received: LoadSimulationInput | None = None

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        self.calls += 1
        self.order.append("load")
        self.received = simulation_input
        return LoadSimulationResult(simulation_input, 3.0)


class RecordingTariffModel(TariffSimulationModelBoundary):
    __slots__ = ("calls", "order", "received")

    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self.order = order
        self.received: TariffSimulationInput | None = None

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        self.calls += 1
        self.order.append("tariff")
        self.received = simulation_input
        return TariffSimulationResult(simulation_input, 0.8, 0.2)


class RecordingBatteryModel(BatterySimulationModelBoundary):
    __slots__ = ("calls", "next_state", "order", "received")

    def __init__(
        self,
        order: list[str],
        next_state: BatterySimulationState,
    ) -> None:
        self.calls = 0
        self.order = order
        self.next_state = next_state
        self.received: BatterySimulationInput | None = None

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        self.calls += 1
        self.order.append("battery")
        self.received = simulation_input
        return BatterySimulationResult(simulation_input, self.next_state, 1.0)


class RecordingGridModel(GridSimulationModelBoundary):
    __slots__ = ("calls", "order", "received")

    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self.order = order
        self.received: GridSimulationInput | None = None

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        self.calls += 1
        self.order.append("grid")
        self.received = simulation_input
        return GridSimulationResult(simulation_input, 1.0)


class FailingLoadModel(LoadSimulationModelBoundary):
    __slots__ = ("error", "order")

    def __init__(self, order: list[str], error: RuntimeError) -> None:
        self.order = order
        self.error = error

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        self.order.append("load")
        raise self.error


class InvalidPVResultModel(PVSimulationModelBoundary):
    __slots__ = ("order",)

    def __init__(self, order: list[str]) -> None:
        self.order = order

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        self.order.append("pv")
        return cast(PVSimulationResult, object())


def make_input() -> SimulationStepInput:
    step = SimulationStepIdentity(
        0,
        60.0,
        datetime(2026, 8, 6, 14, 0, tzinfo=UTC),
    )
    feasible = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible, 1.0)
    return SimulationStepInput(
        step,
        PVSimulationInput(step, 5.0),
        LoadSimulationInput(step, 4.0),
        TariffSimulationInput(step, 0.8, 0.2),
        BatterySimulationInput(step, BatterySimulationState(0.5), actuation),
        GridSimulationInput(step, 1.0),
    )


def make_models(
    order: list[str],
) -> tuple[
    RecordingPVModel,
    RecordingLoadModel,
    RecordingTariffModel,
    RecordingBatteryModel,
    RecordingGridModel,
]:
    return (
        RecordingPVModel(order),
        RecordingLoadModel(order),
        RecordingTariffModel(order),
        RecordingBatteryModel(order, BatterySimulationState(0.55)),
        RecordingGridModel(order),
    )


def make_bindings(
    models: tuple[
        RecordingPVModel,
        RecordingLoadModel,
        RecordingTariffModel,
        RecordingBatteryModel,
        RecordingGridModel,
    ],
) -> tuple[SimulationModelBinding, ...]:
    pv, load, tariff, battery, grid = models
    return (
        SimulationModelBinding(PVSimulationModelBoundary, pv),
        SimulationModelBinding(LoadSimulationModelBoundary, load),
        SimulationModelBinding(TariffSimulationModelBoundary, tariff),
        SimulationModelBinding(BatterySimulationModelBoundary, battery),
        SimulationModelBinding(GridSimulationModelBoundary, grid),
    )


def test_executor_executes_each_model_once_and_preserves_exact_evidence() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    bindings = SimulationModelBindingCollection(make_bindings(models))

    result = SingleStepSimulationExecutor.execute(simulation_input, bindings)

    assert [model.calls for model in models] == [1, 1, 1, 1, 1]
    assert result.simulation_input is simulation_input
    assert result.state.step_identity is simulation_input.step_identity
    assert result.state.pv_result.simulation_input is simulation_input.pv_input
    assert result.state.load_result.simulation_input is simulation_input.load_input
    assert result.state.tariff_result.simulation_input is simulation_input.tariff_input
    assert (
        result.state.battery_result.simulation_input is simulation_input.battery_input
    )
    assert result.state.grid_result.simulation_input is simulation_input.grid_input
    assert models[0].received is simulation_input.pv_input
    assert models[1].received is simulation_input.load_input
    assert models[2].received is simulation_input.tariff_input
    assert models[3].received is simulation_input.battery_input
    assert models[4].received is simulation_input.grid_input


def test_executor_uses_exact_caller_binding_order() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    pv, load, tariff, battery, grid = make_bindings(models)
    caller_bindings = (grid, pv, battery, tariff, load)

    SingleStepSimulationExecutor.execute(
        simulation_input,
        SimulationModelBindingCollection(caller_bindings),
    )

    assert order == ["grid", "pv", "battery", "tariff", "load"]


def test_executor_rejects_missing_binding_before_execution() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    bindings = SimulationModelBindingCollection(make_bindings(models)[:-1])

    with pytest.raises(ValueError, match="GridSimulationModelBoundary"):
        SingleStepSimulationExecutor.execute(simulation_input, bindings)

    assert order == []


def test_executor_rejects_duplicate_binding_before_execution() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    bindings = make_bindings(models)
    duplicate = SimulationModelBindingCollection((*bindings, bindings[0]))

    with pytest.raises(ValueError, match="PVSimulationModelBoundary"):
        SingleStepSimulationExecutor.execute(simulation_input, duplicate)

    assert order == []


def test_executor_stops_and_propagates_exact_model_exception() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    pv, _, tariff, battery, grid = make_bindings(models)
    error = RuntimeError("load failed")
    failing_load = SimulationModelBinding(
        LoadSimulationModelBoundary,
        FailingLoadModel(order, error),
    )
    bindings = SimulationModelBindingCollection(
        (pv, failing_load, tariff, battery, grid),
    )

    with pytest.raises(RuntimeError) as raised:
        SingleStepSimulationExecutor.execute(simulation_input, bindings)

    assert raised.value is error
    assert order == ["pv", "load"]
    assert models[0].calls == 1
    assert models[2].calls == 0
    assert models[3].calls == 0
    assert models[4].calls == 0


def test_executor_rejects_invalid_model_result_without_continuing() -> None:
    simulation_input = make_input()
    order: list[str] = []
    models = make_models(order)
    _, load, tariff, battery, grid = make_bindings(models)
    invalid_pv = SimulationModelBinding(
        PVSimulationModelBoundary,
        InvalidPVResultModel(order),
    )
    bindings = SimulationModelBindingCollection(
        (invalid_pv, load, tariff, battery, grid),
    )

    with pytest.raises(TypeError, match="PVSimulationResult"):
        SingleStepSimulationExecutor.execute(simulation_input, bindings)

    assert order == ["pv"]


@pytest.mark.parametrize("value", [None, object(), "step"])
def test_executor_rejects_invalid_step_input(value: object) -> None:
    with pytest.raises(TypeError, match="simulation_input"):
        SingleStepSimulationExecutor.execute(
            cast(Any, value),
            SimulationModelBindingCollection(()),
        )


@pytest.mark.parametrize("value", [None, object(), ()])
def test_executor_rejects_invalid_bindings(value: object) -> None:
    with pytest.raises(TypeError, match="bindings"):
        SingleStepSimulationExecutor.execute(make_input(), cast(Any, value))


def test_executor_is_stateless_empty_slotted_and_has_exact_signature() -> None:
    executor = SingleStepSimulationExecutor()
    signature = inspect.signature(SingleStepSimulationExecutor.execute)

    assert SingleStepSimulationExecutor.__slots__ == ()
    assert not hasattr(executor, "__dict__")
    assert list(signature.parameters) == ["simulation_input", "bindings"]
    assert signature.return_annotation is SimulationStepResult


def test_executor_has_no_scenario_runtime_device_or_command_dependency() -> None:
    tree = ast.parse(inspect.getsource(executor_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "simulator.aggregate",
        "simulator.battery",
        "simulator.binding",
        "simulator.grid",
        "simulator.load",
        "simulator.pv",
        "simulator.tariff",
        "typing",
    }
    source = inspect.getsource(executor_module).lower()
    for forbidden in (
        "simulationscenario",
        "runtime",
        "scheduler",
        "device",
        "command",
        "dispatcher",
        "optimization",
        "while ",
        "retry",
        "cache",
        "history",
    ):
        assert forbidden not in source
