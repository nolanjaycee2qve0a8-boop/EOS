"""Tests for the concrete deterministic simple Battery physics model."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from ems_simulator import BatteryParameters, SimpleBatteryPhysicsModel
from ems_simulator import battery as battery_module
from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
    SimulationModelBinding,
    SimulationStepIdentity,
)


def make_parameters(**overrides: float) -> BatteryParameters:
    values = {
        "capacity_kwh": 10.0,
        "max_charge_power_kw": 5.0,
        "max_discharge_power_kw": 5.0,
        "charge_efficiency": 1.0,
        "discharge_efficiency": 1.0,
        "reserve_soc": 0.2,
    }
    values.update(overrides)
    return BatteryParameters(**values)


def make_input(
    power_kw: float,
    *,
    soc: float = 0.5,
    duration_seconds: float = 3600.0,
) -> BatterySimulationInput:
    feasible = FeasibleDecisionIntent(DecisionIntent(power_kw))
    actuation = BatterySimulationActuation(feasible, power_kw)
    return BatterySimulationInput(
        SimulationStepIdentity(0, duration_seconds, None),
        BatterySimulationState(soc),
        actuation,
    )


def test_charging_increases_soc() -> None:
    simulation_input = make_input(2.0, soc=0.5)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == 2.0
    assert result.next_state.soc == pytest.approx(0.7)


def test_discharging_decreases_soc() -> None:
    simulation_input = make_input(-2.0, soc=0.7)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == -2.0
    assert result.next_state.soc == pytest.approx(0.5)


def test_idle_preserves_exact_source_state() -> None:
    simulation_input = make_input(0.0, soc=0.5)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == 0.0
    assert result.next_state is simulation_input.source_state


def test_charge_efficiency_reduces_stored_energy() -> None:
    simulation_input = make_input(2.0, soc=0.5)
    parameters = make_parameters(charge_efficiency=0.8)

    result = SimpleBatteryPhysicsModel(parameters).simulate(simulation_input)

    assert result.actual_power_kw == 2.0
    assert result.next_state.soc == pytest.approx(0.66)


def test_discharge_efficiency_increases_removed_stored_energy() -> None:
    simulation_input = make_input(-2.0, soc=0.7)
    parameters = make_parameters(discharge_efficiency=0.8)

    result = SimpleBatteryPhysicsModel(parameters).simulate(simulation_input)

    assert result.actual_power_kw == -2.0
    assert result.next_state.soc == pytest.approx(0.45)


@pytest.mark.parametrize(
    ("power_kw", "expected_power_kw", "expected_soc"),
    [(8.0, 3.0, 0.8), (-8.0, -2.0, 0.3)],
)
def test_charge_and_discharge_power_limits(
    power_kw: float,
    expected_power_kw: float,
    expected_soc: float,
) -> None:
    parameters = make_parameters(
        max_charge_power_kw=3.0,
        max_discharge_power_kw=2.0,
    )
    simulation_input = make_input(power_kw, soc=0.5)

    result = SimpleBatteryPhysicsModel(parameters).simulate(simulation_input)

    assert result.actual_power_kw == expected_power_kw
    assert result.next_state.soc == pytest.approx(expected_soc)


def test_soc_upper_limit_clips_actual_charge_power() -> None:
    simulation_input = make_input(5.0, soc=0.9)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == pytest.approx(1.0)
    assert result.next_state.soc == 1.0


def test_soc_lower_limit_clips_actual_discharge_power() -> None:
    simulation_input = make_input(-5.0, soc=0.3)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == pytest.approx(-1.0)
    assert result.next_state.soc == 0.2


@pytest.mark.parametrize(
    ("power_kw", "soc"),
    [(2.0, 1.0), (-2.0, 0.2), (-2.0, 0.1)],
)
def test_soc_boundary_blocks_power_without_normalizing_source_state(
    power_kw: float,
    soc: float,
) -> None:
    simulation_input = make_input(power_kw, soc=soc)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.actual_power_kw == 0.0
    assert result.next_state is simulation_input.source_state


def test_duration_controls_energy_transition() -> None:
    simulation_input = make_input(2.0, soc=0.5, duration_seconds=1800.0)

    result = SimpleBatteryPhysicsModel(make_parameters()).simulate(simulation_input)

    assert result.next_state.soc == pytest.approx(0.6)


def test_result_preserves_complete_exact_input_lineage() -> None:
    parameters = make_parameters()
    model = SimpleBatteryPhysicsModel(parameters)
    simulation_input = make_input(1.0)

    result = model.simulate(simulation_input)

    assert model.parameters is parameters
    assert result.simulation_input is simulation_input
    assert result.simulation_input.step_identity is simulation_input.step_identity
    assert result.simulation_input.source_state is simulation_input.source_state
    assert result.simulation_input.actuation is simulation_input.actuation
    assert (
        result.simulation_input.actuation.source_feasible_decision
        is simulation_input.actuation.source_feasible_decision
    )


def test_same_input_is_deterministic_without_result_or_state_retention() -> None:
    simulation_input = make_input(1.5)
    model = SimpleBatteryPhysicsModel(make_parameters())

    first = model.simulate(simulation_input)
    second = model.simulate(simulation_input)

    assert first == second
    assert first is not second
    assert first.next_state is not second.next_state


def test_model_rejects_invalid_references() -> None:
    with pytest.raises(TypeError, match="parameters"):
        SimpleBatteryPhysicsModel(cast(Any, object()))
    with pytest.raises(TypeError, match="BatterySimulationInput"):
        SimpleBatteryPhysicsModel(make_parameters()).simulate(cast(Any, object()))


def test_model_is_frozen_slotted_and_has_no_instance_dictionary() -> None:
    model = SimpleBatteryPhysicsModel(make_parameters())

    assert is_dataclass(SimpleBatteryPhysicsModel)
    assert cast(Any, SimpleBatteryPhysicsModel).__dataclass_params__.frozen
    assert SimpleBatteryPhysicsModel.__slots__ == ("parameters",)
    assert [field.name for field in fields(SimpleBatteryPhysicsModel)] == ["parameters"]
    assert not hasattr(model, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, model).parameters = make_parameters()


def test_model_is_accepted_as_exact_caller_supplied_battery_binding() -> None:
    model = SimpleBatteryPhysicsModel(make_parameters())

    binding = SimulationModelBinding(BatterySimulationModelBoundary, model)

    assert binding.model is model
    assert binding.component_contract is BatterySimulationModelBoundary


def test_model_signature_and_result_contract_are_explicit() -> None:
    signature = inspect.signature(SimpleBatteryPhysicsModel.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is BatterySimulationResult


def test_model_dependencies_are_application_input_and_simulator_contracts_only() -> (
    None
):
    tree = ast.parse(inspect.getsource(battery_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"dataclasses", "ems_simulator.input", "simulator"}
