"""Tests for explicit caller-owned simulation step progression contracts."""

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
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    GridSimulationResult,
    LoadSimulationInput,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationResult,
    SimulationExecutionTrace,
    SimulationModelBindingCollection,
    SimulationState,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepProgression,
    SimulationStepProgressionBoundary,
    SimulationStepResult,
    TariffSimulationInput,
    TariffSimulationResult,
)
from simulator import progression as progression_module


class DirectProgressionBoundary(SimulationStepProgressionBoundary):
    __slots__ = ()

    def relate(
        self,
        previous_trace: SimulationExecutionTrace,
        next_input: SimulationStepInput,
    ) -> SimulationStepProgression:
        return SimulationStepProgression(
            previous_trace,
            previous_trace.step_result,
            next_input,
        )


def make_input(
    sequence: int,
    battery_state: BatterySimulationState,
) -> SimulationStepInput:
    identity = SimulationStepIdentity(
        sequence,
        60.0,
        datetime(2026, 8, 7, 12, sequence, tzinfo=UTC),
    )
    feasible = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible, 1.0)
    return SimulationStepInput(
        identity,
        PVSimulationInput(identity, 5.0),
        LoadSimulationInput(identity, 4.0),
        TariffSimulationInput(identity, 0.8, 0.2),
        BatterySimulationInput(identity, battery_state, actuation),
        GridSimulationInput(identity, 1.0),
    )


def make_previous_evidence() -> tuple[
    SimulationExecutionTrace,
    SimulationStepResult,
    BatterySimulationState,
    BatterySimulationState,
]:
    previous_source_state = BatterySimulationState(0.4)
    produced_next_state = BatterySimulationState(0.5)
    simulation_input = make_input(0, previous_source_state)
    state = SimulationState(
        simulation_input.step_identity,
        PVSimulationResult(simulation_input.pv_input, 5.0),
        LoadSimulationResult(simulation_input.load_input, 4.0),
        TariffSimulationResult(simulation_input.tariff_input, 0.8, 0.2),
        BatterySimulationResult(
            simulation_input.battery_input,
            produced_next_state,
            1.0,
        ),
        GridSimulationResult(simulation_input.grid_input, 1.0),
    )
    result = SimulationStepResult(simulation_input, state)
    trace = SimulationExecutionTrace.create(
        SimulationModelBindingCollection(()),
        result,
    )
    return trace, result, previous_source_state, produced_next_state


def test_progression_preserves_exact_evidence_and_caller_next_input() -> None:
    trace, result, previous_state, produced_next_state = make_previous_evidence()
    next_input = make_input(1, produced_next_state)

    progression = SimulationStepProgression(trace, result, next_input)

    assert progression.previous_trace is trace
    assert progression.previous_result is result
    assert progression.next_input is next_input
    assert (
        progression.previous_result.simulation_input.battery_input.source_state
        is previous_state
    )
    assert (
        progression.previous_result.state.battery_result.next_state
        is produced_next_state
    )
    assert progression.next_input.battery_input.source_state is produced_next_state


def test_abstract_boundary_preserves_caller_owned_relationship() -> None:
    trace, result, _, produced_next_state = make_previous_evidence()
    next_input = make_input(1, produced_next_state)

    progression = DirectProgressionBoundary().relate(trace, next_input)

    assert progression.previous_trace is trace
    assert progression.previous_result is result
    assert progression.next_input is next_input


def test_reconstructed_equal_previous_result_is_rejected() -> None:
    trace, result, _, produced_next_state = make_previous_evidence()
    reconstructed = SimulationStepResult(result.simulation_input, result.state)
    assert reconstructed == result
    assert reconstructed is not result

    with pytest.raises(ValueError, match=r"exact previous_trace\.step_result"):
        SimulationStepProgression(
            trace,
            reconstructed,
            make_input(1, produced_next_state),
        )


def test_reconstructed_equal_next_source_state_is_rejected() -> None:
    trace, result, _, produced_next_state = make_previous_evidence()
    reconstructed_state = BatterySimulationState(produced_next_state.soc)
    assert reconstructed_state == produced_next_state
    assert reconstructed_state is not produced_next_state

    with pytest.raises(ValueError, match="exact previous battery next_state"):
        SimulationStepProgression(
            trace,
            result,
            make_input(1, reconstructed_state),
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("previous_trace", object()),
        ("previous_result", object()),
        ("next_input", object()),
    ],
)
def test_progression_rejects_invalid_types(
    field_name: str,
    replacement: object,
) -> None:
    trace, result, _, produced_next_state = make_previous_evidence()
    values: dict[str, object] = {
        "previous_trace": trace,
        "previous_result": result,
        "next_input": make_input(1, produced_next_state),
    }
    values[field_name] = replacement

    with pytest.raises(TypeError, match=field_name):
        SimulationStepProgression(**cast(Any, values))


def test_progression_is_frozen_slotted_identity_based_and_field_complete() -> None:
    trace, result, _, produced_next_state = make_previous_evidence()
    next_input = make_input(1, produced_next_state)
    progression = SimulationStepProgression(trace, result, next_input)
    reconstructed = SimulationStepProgression(trace, result, next_input)

    assert is_dataclass(SimulationStepProgression)
    assert cast(Any, SimulationStepProgression).__dataclass_params__.frozen
    assert SimulationStepProgression.__slots__ == (
        "previous_trace",
        "previous_result",
        "next_input",
    )
    assert tuple(field.name for field in fields(SimulationStepProgression)) == (
        "previous_trace",
        "previous_result",
        "next_input",
    )
    assert not hasattr(progression, "__dict__")
    assert reconstructed is not progression
    assert reconstructed != progression
    with pytest.raises(FrozenInstanceError):
        cast(Any, progression).next_input = next_input


def test_progression_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert inspect.isabstract(SimulationStepProgressionBoundary)
    with pytest.raises(TypeError):
        cast(Any, SimulationStepProgressionBoundary)()
    assert SimulationStepProgressionBoundary.__slots__ == ()
    assert not hasattr(DirectProgressionBoundary(), "__dict__")
    assert cast(Any, SimulationStepProgressionBoundary.relate).__isabstractmethod__
    signature = inspect.signature(SimulationStepProgressionBoundary.relate)
    assert tuple(signature.parameters) == ("self", "previous_trace", "next_input")
    assert signature.return_annotation is SimulationStepProgression


def test_progression_module_has_no_clock_runtime_or_execution_dependency() -> None:
    tree = ast.parse(inspect.getsource(progression_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "simulator.aggregate",
        "simulator.trace",
    }
    source = inspect.getsource(progression_module).lower()
    for forbidden in (
        "datetime",
        "time.time",
        "now(",
        "clock",
        "runtime",
        "scheduler",
        "thread",
        "queue",
        "scenarioexecution",
        "singlestepsimulationexecutor",
        ".execute(",
        ".simulate(",
        "device",
        "command",
        "dispatcher",
        "optimization",
        "forecast",
        "cache",
        "history",
        "persistence",
    ):
        assert forbidden not in source
