"""Tests for the concrete deterministic Load profile model."""

import ast
import inspect
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from ems_simulator import LoadProfileSimulationModel
from ems_simulator import load as load_module
from simulator import (
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    SimulationModelBinding,
    SimulationStepIdentity,
)


def make_step(hour: int = 0) -> SimulationStepIdentity:
    return SimulationStepIdentity(
        sequence=hour,
        duration_seconds=3600,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
    )


def test_normal_24_hour_profile_produces_exact_profile_values() -> None:
    profile = (
        1.8,
        1.6,
        1.5,
        1.5,
        1.6,
        1.9,
        2.4,
        3.1,
        3.6,
        3.2,
        2.8,
        2.6,
        2.7,
        2.9,
        3.0,
        3.2,
        3.8,
        4.6,
        5.2,
        4.8,
        4.0,
        3.2,
        2.6,
        2.1,
    )
    inputs = tuple(
        LoadSimulationInput(make_step(hour), profile[hour]) for hour in range(24)
    )
    model = LoadProfileSimulationModel()

    results = tuple(model.simulate(simulation_input) for simulation_input in inputs)

    assert tuple(result.actual_power_kw for result in results) == profile
    assert all(
        result.simulation_input is simulation_input
        for result, simulation_input in zip(results, inputs, strict=True)
    )
    assert all(
        result.simulation_input.step_identity is simulation_input.step_identity
        for result, simulation_input in zip(results, inputs, strict=True)
    )


def test_zero_load_produces_zero_consumption() -> None:
    simulation_input = LoadSimulationInput(make_step(), 0.0)

    result = LoadProfileSimulationModel().simulate(simulation_input)

    assert result.actual_power_kw == 0.0
    assert result.simulation_input is simulation_input


@pytest.mark.parametrize("value", [-0.1, float("nan"), float("inf")])
def test_invalid_profile_power_is_rejected_before_model_execution(value: float) -> None:
    with pytest.raises(ValueError, match="demand_power_kw"):
        LoadSimulationInput(make_step(), value)


def test_model_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="LoadSimulationInput"):
        LoadProfileSimulationModel().simulate(cast(Any, object()))


def test_same_input_produces_same_value_without_result_retention() -> None:
    simulation_input = LoadSimulationInput(make_step(), 4.25)
    model = LoadProfileSimulationModel()

    first = model.simulate(simulation_input)
    second = model.simulate(simulation_input)

    assert first == second
    assert first is not second
    assert first.simulation_input is simulation_input
    assert second.simulation_input is simulation_input


def test_model_is_stateless_empty_slotted_and_has_no_instance_dictionary() -> None:
    model = LoadProfileSimulationModel()

    assert LoadProfileSimulationModel.__slots__ == ()
    assert not hasattr(model, "__dict__")
    assert isinstance(model, LoadSimulationModelBoundary)


def test_model_is_accepted_as_exact_caller_supplied_load_binding() -> None:
    model = LoadProfileSimulationModel()

    binding = SimulationModelBinding(LoadSimulationModelBoundary, model)

    assert binding.model is model
    assert binding.component_contract is LoadSimulationModelBoundary


def test_model_signature_and_result_contract_are_explicit() -> None:
    signature = inspect.signature(LoadProfileSimulationModel.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is LoadSimulationResult


def test_model_dependencies_do_not_include_runtime_device_or_strategy() -> None:
    tree = ast.parse(inspect.getsource(load_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"simulator"}
