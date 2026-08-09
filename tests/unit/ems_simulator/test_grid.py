"""Tests for the deterministic Grid energy balance model."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from ems_simulator import GridEnergyBalanceSimulationModel
from ems_simulator import grid as grid_module
from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    LoadSimulationInput,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationResult,
    SimulationModelBinding,
    SimulationStepIdentity,
)


def make_component_results(
    *,
    pv_power_kw: float,
    load_power_kw: float,
    battery_power_kw: float,
    step: SimulationStepIdentity | None = None,
) -> tuple[PVSimulationResult, LoadSimulationResult, BatterySimulationResult]:
    step = step or SimulationStepIdentity(0, 3600.0, None)
    pv_input = PVSimulationInput(step, pv_power_kw)
    load_input = LoadSimulationInput(step, load_power_kw)
    feasible = FeasibleDecisionIntent(DecisionIntent(battery_power_kw))
    battery_input = BatterySimulationInput(
        step,
        BatterySimulationState(0.5),
        BatterySimulationActuation(feasible, battery_power_kw),
    )
    return (
        PVSimulationResult(pv_input, pv_power_kw),
        LoadSimulationResult(load_input, load_power_kw),
        BatterySimulationResult(
            battery_input,
            battery_input.source_state,
            battery_power_kw,
        ),
    )


def evaluate_balance(
    *,
    pv_power_kw: float,
    load_power_kw: float,
    battery_power_kw: float,
) -> GridSimulationResult:
    results = make_component_results(
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        battery_power_kw=battery_power_kw,
    )
    model = GridEnergyBalanceSimulationModel(*results)
    grid_input = GridSimulationInput(results[0].simulation_input.step_identity, 0.0)
    return model.simulate(grid_input)


def test_pv_surplus_exports_to_grid() -> None:
    result = evaluate_balance(pv_power_kw=5.0, load_power_kw=2.0, battery_power_kw=0.0)

    assert result.actual_grid_power_kw == -3.0


def test_battery_charging_increases_grid_import() -> None:
    without_charging = evaluate_balance(
        pv_power_kw=1.0,
        load_power_kw=2.0,
        battery_power_kw=0.0,
    )
    charging = evaluate_balance(
        pv_power_kw=1.0,
        load_power_kw=2.0,
        battery_power_kw=2.0,
    )

    assert without_charging.actual_grid_power_kw == 1.0
    assert charging.actual_grid_power_kw == 3.0


def test_battery_discharging_decreases_grid_import() -> None:
    without_discharging = evaluate_balance(
        pv_power_kw=1.0,
        load_power_kw=4.0,
        battery_power_kw=0.0,
    )
    discharging = evaluate_balance(
        pv_power_kw=1.0,
        load_power_kw=4.0,
        battery_power_kw=-2.0,
    )

    assert without_discharging.actual_grid_power_kw == 3.0
    assert discharging.actual_grid_power_kw == 1.0


@pytest.mark.parametrize(
    ("pv_power_kw", "load_power_kw", "battery_power_kw", "expected_grid_kw"),
    [
        (2.0, 5.0, 0.0, 3.0),
        (5.0, 2.0, 0.0, -3.0),
        (4.0, 3.0, 1.0, 0.0),
    ],
)
def test_grid_import_export_and_zero_balance(
    pv_power_kw: float,
    load_power_kw: float,
    battery_power_kw: float,
    expected_grid_kw: float,
) -> None:
    result = evaluate_balance(
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        battery_power_kw=battery_power_kw,
    )

    assert result.actual_grid_power_kw == expected_grid_kw


def test_model_preserves_exact_component_and_grid_input_identities() -> None:
    step = SimulationStepIdentity(3, 3600.0, None)
    pv_result, load_result, battery_result = make_component_results(
        pv_power_kw=4.0,
        load_power_kw=3.0,
        battery_power_kw=1.0,
        step=step,
    )
    model = GridEnergyBalanceSimulationModel(
        pv_result,
        load_result,
        battery_result,
    )
    grid_input = GridSimulationInput(step, 99.0)

    result = model.simulate(grid_input)

    assert model.pv_result is pv_result
    assert model.load_result is load_result
    assert model.battery_result is battery_result
    assert result.simulation_input is grid_input
    assert result.simulation_input.step_identity is step
    assert result.actual_grid_power_kw == 0.0
    assert grid_input.requested_grid_power_kw == 99.0


def test_reconstructed_equal_step_identity_is_rejected() -> None:
    step = SimulationStepIdentity(0, 3600.0, None)
    reconstructed = SimulationStepIdentity(0, 3600.0, None)
    pv_result, load_result, battery_result = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
        step=step,
    )

    model = GridEnergyBalanceSimulationModel(
        pv_result,
        load_result,
        battery_result,
    )

    assert reconstructed == step
    assert reconstructed is not step
    with pytest.raises(ValueError, match="exact shared step identity"):
        model.simulate(GridSimulationInput(reconstructed, 0.0))


def test_mismatched_component_step_identity_is_rejected() -> None:
    step = SimulationStepIdentity(0, 3600.0, None)
    pv_result, _, battery_result = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
        step=step,
    )
    _, mismatched_load, _ = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
        step=SimulationStepIdentity(0, 3600.0, None),
    )

    with pytest.raises(ValueError, match="load_result"):
        GridEnergyBalanceSimulationModel(
            pv_result,
            mismatched_load,
            battery_result,
        )


@pytest.mark.parametrize("field_name", ["pv_result", "load_result", "battery_result"])
def test_model_rejects_invalid_component_result_types(field_name: str) -> None:
    pv_result, load_result, battery_result = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
    )
    values: dict[str, object] = {
        "pv_result": pv_result,
        "load_result": load_result,
        "battery_result": battery_result,
    }
    values[field_name] = object()

    with pytest.raises(TypeError, match=field_name):
        GridEnergyBalanceSimulationModel(**cast(Any, values))


def test_model_rejects_invalid_grid_input_type() -> None:
    results = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
    )

    with pytest.raises(TypeError, match="GridSimulationInput"):
        GridEnergyBalanceSimulationModel(*results).simulate(cast(Any, object()))


def test_same_facts_are_deterministic_without_result_retention() -> None:
    results = make_component_results(
        pv_power_kw=2.0,
        load_power_kw=4.0,
        battery_power_kw=-1.0,
    )
    model = GridEnergyBalanceSimulationModel(*results)
    grid_input = GridSimulationInput(results[0].simulation_input.step_identity, 0.0)

    first = model.simulate(grid_input)
    second = model.simulate(grid_input)

    assert first == second
    assert first is not second
    assert first.simulation_input is grid_input
    assert second.simulation_input is grid_input


def test_model_is_frozen_slotted_and_has_no_instance_dictionary() -> None:
    results = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
    )
    model = GridEnergyBalanceSimulationModel(*results)

    assert is_dataclass(GridEnergyBalanceSimulationModel)
    assert cast(Any, GridEnergyBalanceSimulationModel).__dataclass_params__.frozen
    assert GridEnergyBalanceSimulationModel.__slots__ == (
        "pv_result",
        "load_result",
        "battery_result",
    )
    assert [field.name for field in fields(GridEnergyBalanceSimulationModel)] == [
        "pv_result",
        "load_result",
        "battery_result",
    ]
    assert not hasattr(model, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, model).pv_result = results[0]


def test_model_is_accepted_as_exact_caller_supplied_grid_binding() -> None:
    results = make_component_results(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
    )
    model = GridEnergyBalanceSimulationModel(*results)

    binding = SimulationModelBinding(GridSimulationModelBoundary, model)

    assert binding.model is model
    assert binding.component_contract is GridSimulationModelBoundary


def test_model_signature_and_result_contract_are_explicit() -> None:
    signature = inspect.signature(GridEnergyBalanceSimulationModel.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is GridSimulationResult


def test_model_dependencies_are_simulator_contracts_only() -> None:
    tree = ast.parse(inspect.getsource(grid_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"dataclasses", "simulator"}
