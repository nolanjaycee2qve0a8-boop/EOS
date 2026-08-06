"""Tests for Phase 6 aggregate simulation contracts."""

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
    SimulationScenario,
    SimulationState,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    TariffSimulationInput,
    TariffSimulationResult,
)
from simulator import aggregate as aggregate_module


def make_step(sequence: int = 0) -> SimulationStepIdentity:
    return SimulationStepIdentity(
        sequence,
        60.0,
        datetime(2026, 8, 6, 12, sequence, tzinfo=UTC),
    )


def make_step_input(step: SimulationStepIdentity | None = None) -> SimulationStepInput:
    exact_step = step if step is not None else make_step()
    feasible_decision = FeasibleDecisionIntent(DecisionIntent(1.0))
    actuation = BatterySimulationActuation(feasible_decision, 1.0)

    return SimulationStepInput(
        exact_step,
        PVSimulationInput(exact_step, 5.0),
        LoadSimulationInput(exact_step, 3.0),
        TariffSimulationInput(exact_step, 0.8, 0.3),
        BatterySimulationInput(
            exact_step,
            BatterySimulationState(0.5),
            actuation,
        ),
        GridSimulationInput(exact_step, 1.0),
    )


def make_state(simulation_input: SimulationStepInput) -> SimulationState:
    return SimulationState(
        simulation_input.step_identity,
        PVSimulationResult(simulation_input.pv_input, 4.0),
        LoadSimulationResult(simulation_input.load_input, 3.0),
        TariffSimulationResult(simulation_input.tariff_input, 0.8, 0.3),
        BatterySimulationResult(
            simulation_input.battery_input,
            BatterySimulationState(0.55),
            1.0,
        ),
        GridSimulationResult(simulation_input.grid_input, 1.0),
    )


def test_step_input_preserves_exact_component_identities() -> None:
    step = make_step()
    aggregate_input = make_step_input(step)

    assert aggregate_input.step_identity is step
    assert aggregate_input.pv_input.step_identity is step
    assert aggregate_input.load_input.step_identity is step
    assert aggregate_input.tariff_input.step_identity is step
    assert aggregate_input.battery_input.step_identity is step
    assert aggregate_input.grid_input.step_identity is step


def test_step_input_rejects_equal_but_distinct_component_step() -> None:
    step = make_step()
    other_step = make_step()
    valid = make_step_input(step)

    with pytest.raises(ValueError, match=r"pv_input\.step_identity"):
        SimulationStepInput(
            step,
            PVSimulationInput(other_step, 5.0),
            valid.load_input,
            valid.tariff_input,
            valid.battery_input,
            valid.grid_input,
        )


@pytest.mark.parametrize(
    ("field_name", "index"),
    [
        ("pv_input", 0),
        ("load_input", 1),
        ("tariff_input", 2),
        ("battery_input", 3),
        ("grid_input", 4),
    ],
)
def test_step_input_rejects_invalid_component_type(
    field_name: str,
    index: int,
) -> None:
    valid = make_step_input()
    components: list[object] = [
        valid.pv_input,
        valid.load_input,
        valid.tariff_input,
        valid.battery_input,
        valid.grid_input,
    ]
    components[index] = object()

    with pytest.raises(TypeError, match=field_name):
        SimulationStepInput(valid.step_identity, *cast(Any, components))


def test_step_input_rejects_invalid_step_type() -> None:
    valid = make_step_input()

    with pytest.raises(TypeError, match="step_identity"):
        SimulationStepInput(
            cast(Any, object()),
            valid.pv_input,
            valid.load_input,
            valid.tariff_input,
            valid.battery_input,
            valid.grid_input,
        )


def test_state_preserves_exact_component_result_identities() -> None:
    aggregate_input = make_step_input()
    state = make_state(aggregate_input)

    assert state.step_identity is aggregate_input.step_identity
    assert state.pv_result.simulation_input is aggregate_input.pv_input
    assert state.load_result.simulation_input is aggregate_input.load_input
    assert state.tariff_result.simulation_input is aggregate_input.tariff_input
    assert state.battery_result.simulation_input is aggregate_input.battery_input
    assert state.grid_result.simulation_input is aggregate_input.grid_input


def test_state_rejects_equal_but_distinct_result_step() -> None:
    aggregate_input = make_step_input()
    other_step_input = make_step_input(make_step())
    valid_state = make_state(aggregate_input)

    with pytest.raises(ValueError, match="pv_result step_identity"):
        SimulationState(
            aggregate_input.step_identity,
            PVSimulationResult(other_step_input.pv_input, 4.0),
            valid_state.load_result,
            valid_state.tariff_result,
            valid_state.battery_result,
            valid_state.grid_result,
        )


@pytest.mark.parametrize(
    ("field_name", "index"),
    [
        ("pv_result", 0),
        ("load_result", 1),
        ("tariff_result", 2),
        ("battery_result", 3),
        ("grid_result", 4),
    ],
)
def test_state_rejects_invalid_component_result_type(
    field_name: str,
    index: int,
) -> None:
    aggregate_input = make_step_input()
    valid = make_state(aggregate_input)
    components: list[object] = [
        valid.pv_result,
        valid.load_result,
        valid.tariff_result,
        valid.battery_result,
        valid.grid_result,
    ]
    components[index] = object()

    with pytest.raises(TypeError, match=field_name):
        SimulationState(aggregate_input.step_identity, *cast(Any, components))


def test_state_rejects_invalid_step_type() -> None:
    aggregate_input = make_step_input()
    valid = make_state(aggregate_input)

    with pytest.raises(TypeError, match="step_identity"):
        SimulationState(
            cast(Any, object()),
            valid.pv_result,
            valid.load_result,
            valid.tariff_result,
            valid.battery_result,
            valid.grid_result,
        )


def test_step_result_preserves_exact_input_state_and_component_lineage() -> None:
    aggregate_input = make_step_input()
    state = make_state(aggregate_input)

    result = SimulationStepResult(aggregate_input, state)

    assert result.simulation_input is aggregate_input
    assert result.state is state
    assert result.state.pv_result.simulation_input is aggregate_input.pv_input
    assert result.state.load_result.simulation_input is aggregate_input.load_input
    assert result.state.tariff_result.simulation_input is aggregate_input.tariff_input
    assert result.state.battery_result.simulation_input is aggregate_input.battery_input
    assert result.state.grid_result.simulation_input is aggregate_input.grid_input


def test_step_result_rejects_equal_but_distinct_component_input() -> None:
    aggregate_input = make_step_input()
    reconstructed_pv_input = PVSimulationInput(
        aggregate_input.step_identity,
        aggregate_input.pv_input.available_power_kw,
    )
    state = make_state(aggregate_input)
    mismatched_state = SimulationState(
        aggregate_input.step_identity,
        PVSimulationResult(reconstructed_pv_input, 4.0),
        state.load_result,
        state.tariff_result,
        state.battery_result,
        state.grid_result,
    )

    with pytest.raises(ValueError, match=r"pv_result\.simulation_input"):
        SimulationStepResult(aggregate_input, mismatched_state)


def test_step_result_rejects_invalid_references() -> None:
    aggregate_input = make_step_input()
    state = make_state(aggregate_input)

    with pytest.raises(TypeError, match="simulation_input"):
        SimulationStepResult(cast(Any, object()), state)
    with pytest.raises(TypeError, match="state"):
        SimulationStepResult(aggregate_input, cast(Any, object()))


def test_step_result_rejects_distinct_state_step_identity() -> None:
    aggregate_input = make_step_input()
    other_input = make_step_input(make_step())
    other_state = make_state(other_input)

    with pytest.raises(ValueError, match=r"state\.step_identity"):
        SimulationStepResult(aggregate_input, other_state)


def test_scenario_preserves_exact_tuple_identity_and_caller_order() -> None:
    first = make_step_input(make_step(0))
    second = make_step_input(make_step(1))
    steps = (second, first)

    scenario = SimulationScenario(steps)

    assert scenario.steps is steps
    assert scenario.steps[0] is second
    assert scenario.steps[1] is first


def test_scenario_accepts_empty_tuple() -> None:
    steps: tuple[SimulationStepInput, ...] = ()

    scenario = SimulationScenario(steps)

    assert scenario.steps is steps


def test_scenario_rejects_mutable_collection() -> None:
    with pytest.raises(TypeError, match="steps"):
        SimulationScenario(cast(Any, [make_step_input()]))


def test_scenario_rejects_invalid_step_member() -> None:
    with pytest.raises(TypeError, match="SimulationStepInput"):
        SimulationScenario(cast(Any, (object(),)))


@pytest.mark.parametrize(
    ("model_type", "expected_slots", "expected_fields"),
    [
        (
            SimulationStepInput,
            (
                "step_identity",
                "pv_input",
                "load_input",
                "tariff_input",
                "battery_input",
                "grid_input",
            ),
            [
                "step_identity",
                "pv_input",
                "load_input",
                "tariff_input",
                "battery_input",
                "grid_input",
            ],
        ),
        (
            SimulationState,
            (
                "step_identity",
                "pv_result",
                "load_result",
                "tariff_result",
                "battery_result",
                "grid_result",
            ),
            [
                "step_identity",
                "pv_result",
                "load_result",
                "tariff_result",
                "battery_result",
                "grid_result",
            ],
        ),
        (
            SimulationStepResult,
            ("simulation_input", "state"),
            ["simulation_input", "state"],
        ),
        (SimulationScenario, ("steps",), ["steps"]),
    ],
)
def test_aggregate_artifacts_are_frozen_slotted_and_field_complete(
    model_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(model_type)
    assert cast(Any, model_type).__dataclass_params__.frozen
    assert cast(Any, model_type).__slots__ == expected_slots
    assert [field.name for field in fields(model_type)] == expected_fields


def test_aggregate_artifacts_have_no_instance_dictionary() -> None:
    aggregate_input = make_step_input()
    state = make_state(aggregate_input)
    result = SimulationStepResult(aggregate_input, state)
    scenario = SimulationScenario((aggregate_input,))

    for artifact in (aggregate_input, state, result, scenario):
        assert not hasattr(artifact, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).state = state


def test_aggregate_contract_does_not_execute_models_or_advance_steps() -> None:
    aggregate_input = make_step_input()
    state = make_state(aggregate_input)
    result = SimulationStepResult(aggregate_input, state)

    for artifact in (aggregate_input, state, result):
        for forbidden in (
            "simulate",
            "execute",
            "advance",
            "next_step",
            "runtime",
            "scheduler",
            "command",
            "device",
            "balance",
            "cache",
            "history",
        ):
            assert not hasattr(artifact, forbidden)


def test_aggregate_module_depends_only_on_component_contracts() -> None:
    tree = ast.parse(inspect.getsource(aggregate_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "simulator.battery",
        "simulator.core",
        "simulator.grid",
        "simulator.load",
        "simulator.pv",
        "simulator.tariff",
    }
