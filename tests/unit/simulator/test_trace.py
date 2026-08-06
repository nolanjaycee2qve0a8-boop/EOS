"""Tests for immutable single-step simulation execution evidence."""

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
    SimulationExecutionTrace,
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationState,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import trace as trace_module


class NeverPVModel(PVSimulationModelBoundary):
    __slots__ = ()

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        raise AssertionError("trace must not execute PV model")


class NeverLoadModel(LoadSimulationModelBoundary):
    __slots__ = ()

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        raise AssertionError("trace must not execute Load model")


class NeverTariffModel(TariffSimulationModelBoundary):
    __slots__ = ()

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        raise AssertionError("trace must not execute Tariff model")


class NeverBatteryModel(BatterySimulationModelBoundary):
    __slots__ = ()

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        raise AssertionError("trace must not execute Battery model")


class NeverGridModel(GridSimulationModelBoundary):
    __slots__ = ()

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        raise AssertionError("trace must not execute Grid model")


def make_bindings() -> SimulationModelBindingCollection:
    caller_bindings = (
        SimulationModelBinding(PVSimulationModelBoundary, NeverPVModel()),
        SimulationModelBinding(LoadSimulationModelBoundary, NeverLoadModel()),
        SimulationModelBinding(
            TariffSimulationModelBoundary,
            NeverTariffModel(),
        ),
        SimulationModelBinding(
            BatterySimulationModelBoundary,
            NeverBatteryModel(),
        ),
        SimulationModelBinding(GridSimulationModelBoundary, NeverGridModel()),
    )
    return SimulationModelBindingCollection(caller_bindings)


def make_step_result(sequence: int = 0) -> SimulationStepResult:
    step = SimulationStepIdentity(
        sequence,
        60.0,
        datetime(2026, 8, 6, 15, sequence, tzinfo=UTC),
    )
    feasible = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible, 1.0)
    simulation_input = SimulationStepInput(
        step,
        PVSimulationInput(step, 5.0),
        LoadSimulationInput(step, 4.0),
        TariffSimulationInput(step, 0.8, 0.2),
        BatterySimulationInput(step, BatterySimulationState(0.5), actuation),
        GridSimulationInput(step, 1.0),
    )
    state = SimulationState(
        step,
        PVSimulationResult(simulation_input.pv_input, 4.0),
        LoadSimulationResult(simulation_input.load_input, 3.0),
        TariffSimulationResult(simulation_input.tariff_input, 0.8, 0.2),
        BatterySimulationResult(
            simulation_input.battery_input,
            BatterySimulationState(0.55),
            1.0,
        ),
        GridSimulationResult(simulation_input.grid_input, 1.0),
    )
    return SimulationStepResult(simulation_input, state)


def test_trace_preserves_exact_completed_step_artifacts() -> None:
    bindings = make_bindings()
    step_result = make_step_result()

    trace = SimulationExecutionTrace.create(bindings, step_result)

    assert trace.bindings is bindings
    assert trace.simulation_input is step_result.simulation_input
    assert trace.state is step_result.state
    assert trace.step_result is step_result
    assert trace.state.pv_result is step_result.state.pv_result
    assert trace.state.load_result is step_result.state.load_result
    assert trace.state.tariff_result is step_result.state.tariff_result
    assert trace.state.battery_result is step_result.state.battery_result
    assert trace.state.grid_result is step_result.state.grid_result


def test_trace_creation_is_observation_only_and_does_not_execute_models() -> None:
    bindings = make_bindings()
    step_result = make_step_result()

    trace = SimulationExecutionTrace.create(bindings, step_result)

    assert trace.bindings.bindings is bindings.bindings
    assert trace.step_result is step_result


def test_trace_rejects_mismatched_input_identity() -> None:
    bindings = make_bindings()
    first = make_step_result(0)
    second = make_step_result(1)

    with pytest.raises(ValueError, match="exact simulation_input"):
        SimulationExecutionTrace(
            first.simulation_input,
            bindings,
            first.state,
            second,
        )


def test_trace_rejects_mismatched_state_identity() -> None:
    bindings = make_bindings()
    first = make_step_result(0)
    second = make_step_result(1)

    with pytest.raises(ValueError, match="exact state"):
        SimulationExecutionTrace(
            first.simulation_input,
            bindings,
            second.state,
            first,
        )


@pytest.mark.parametrize(
    ("bindings", "step_result", "field_name"),
    [
        (cast(Any, object()), make_step_result(), "bindings"),
        (make_bindings(), cast(Any, object()), "step_result"),
    ],
)
def test_trace_create_rejects_invalid_inputs(
    bindings: SimulationModelBindingCollection,
    step_result: SimulationStepResult,
    field_name: str,
) -> None:
    with pytest.raises(TypeError, match=field_name):
        SimulationExecutionTrace.create(bindings, step_result)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("simulation_input", object()),
        ("bindings", object()),
        ("state", object()),
        ("step_result", object()),
    ],
)
def test_trace_constructor_rejects_invalid_field_types(
    field_name: str,
    replacement: object,
) -> None:
    bindings = make_bindings()
    step_result = make_step_result()
    values: dict[str, object] = {
        "simulation_input": step_result.simulation_input,
        "bindings": bindings,
        "state": step_result.state,
        "step_result": step_result,
    }
    values[field_name] = replacement

    with pytest.raises(TypeError, match=field_name):
        SimulationExecutionTrace(**cast(Any, values))


def test_trace_is_frozen_slotted_and_field_complete() -> None:
    trace = SimulationExecutionTrace.create(make_bindings(), make_step_result())

    assert is_dataclass(SimulationExecutionTrace)
    assert cast(Any, SimulationExecutionTrace).__dataclass_params__.frozen
    assert SimulationExecutionTrace.__slots__ == (
        "simulation_input",
        "bindings",
        "state",
        "step_result",
    )
    assert tuple(field.name for field in fields(SimulationExecutionTrace)) == (
        "simulation_input",
        "bindings",
        "state",
        "step_result",
    )
    assert not hasattr(trace, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, trace).state = trace.state


def test_different_completed_steps_do_not_share_trace_state() -> None:
    first_result = make_step_result(0)
    second_result = make_step_result(1)

    first = SimulationExecutionTrace.create(make_bindings(), first_result)
    second = SimulationExecutionTrace.create(make_bindings(), second_result)

    assert first is not second
    assert first.simulation_input is first_result.simulation_input
    assert second.simulation_input is second_result.simulation_input
    assert first.simulation_input is not second.simulation_input
    assert first.state is not second.state


def test_trace_module_is_observation_only_and_dependency_isolated() -> None:
    tree = ast.parse(inspect.getsource(trace_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "simulator.aggregate",
        "simulator.binding",
    }
    source = inspect.getsource(trace_module).lower()
    for forbidden in (
        "simulator.executor",
        ".execute(",
        ".simulate(",
        ".append(",
        "runtime",
        "scheduler",
        "device",
        "command",
        "dispatcher",
        "optimization",
        "timestamp(",
        "uuid",
        "cache",
        "history",
    ):
        assert forbidden not in source
