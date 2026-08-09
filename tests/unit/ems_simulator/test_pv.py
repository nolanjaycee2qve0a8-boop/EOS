"""Tests for the concrete deterministic PV profile model."""

import ast
import inspect
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from ems_simulator import PVProfileSimulationModel
from ems_simulator import pv as pv_module
from simulator import (
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
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
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.2,
        1.0,
        2.5,
        4.0,
        5.0,
        5.8,
        6.0,
        5.5,
        4.6,
        3.5,
        2.0,
        0.8,
        0.1,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    inputs = tuple(
        PVSimulationInput(make_step(hour), profile[hour]) for hour in range(24)
    )
    model = PVProfileSimulationModel()

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


def test_zero_pv_produces_zero_generation() -> None:
    simulation_input = PVSimulationInput(make_step(), 0.0)

    result = PVProfileSimulationModel().simulate(simulation_input)

    assert result.actual_power_kw == 0.0
    assert result.simulation_input is simulation_input


@pytest.mark.parametrize("value", [-0.1, float("nan"), float("inf")])
def test_invalid_profile_power_is_rejected_before_model_execution(value: float) -> None:
    with pytest.raises(ValueError, match="available_power_kw"):
        PVSimulationInput(make_step(), value)


def test_model_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="PVSimulationInput"):
        PVProfileSimulationModel().simulate(cast(Any, object()))


def test_same_input_produces_same_value_without_result_retention() -> None:
    simulation_input = PVSimulationInput(make_step(), 4.25)
    model = PVProfileSimulationModel()

    first = model.simulate(simulation_input)
    second = model.simulate(simulation_input)

    assert first == second
    assert first is not second
    assert first.simulation_input is simulation_input
    assert second.simulation_input is simulation_input


def test_model_is_stateless_empty_slotted_and_has_no_instance_dictionary() -> None:
    model = PVProfileSimulationModel()

    assert PVProfileSimulationModel.__slots__ == ()
    assert not hasattr(model, "__dict__")
    assert isinstance(model, PVSimulationModelBoundary)


def test_model_is_accepted_as_exact_caller_supplied_pv_binding() -> None:
    model = PVProfileSimulationModel()

    binding = SimulationModelBinding(PVSimulationModelBoundary, model)

    assert binding.model is model
    assert binding.component_contract is PVSimulationModelBoundary


def test_model_signature_and_result_contract_are_explicit() -> None:
    signature = inspect.signature(PVProfileSimulationModel.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is PVSimulationResult


def test_model_dependencies_do_not_include_runtime_device_or_strategy() -> None:
    tree = ast.parse(inspect.getsource(pv_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"simulator"}
