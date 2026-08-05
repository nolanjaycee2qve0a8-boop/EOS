"""Tests for Phase 6 electrical load simulation contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from simulator import (
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    SimulationStepIdentity,
)
from simulator import load as load_module


class RecordingLoadModel(LoadSimulationModelBoundary):
    """Test-only model returning caller-configured output."""

    __slots__ = ("actual_power_kw", "received")

    def __init__(self, actual_power_kw: float) -> None:
        self.actual_power_kw = actual_power_kw
        self.received: LoadSimulationInput | None = None

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        self.received = simulation_input
        return LoadSimulationResult(simulation_input, self.actual_power_kw)


def make_step() -> SimulationStepIdentity:
    return SimulationStepIdentity(
        sequence=0,
        duration_seconds=60.0,
        timestamp=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )


def test_load_input_preserves_exact_step_identity() -> None:
    step = make_step()

    simulation_input = LoadSimulationInput(step, demand_power_kw=5.0)

    assert simulation_input.step_identity is step
    assert simulation_input.demand_power_kw == 5.0


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_load_input_rejects_invalid_demand_power_type(value: object) -> None:
    with pytest.raises(TypeError, match="demand_power_kw"):
        LoadSimulationInput(make_step(), cast(Any, value))


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_load_input_rejects_invalid_demand_power_value(value: float) -> None:
    with pytest.raises(ValueError, match="demand_power_kw"):
        LoadSimulationInput(make_step(), value)


def test_load_input_rejects_invalid_step_identity() -> None:
    with pytest.raises(TypeError, match="step_identity"):
        LoadSimulationInput(cast(Any, object()), 1.0)


def test_load_result_preserves_exact_input_identity() -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)

    result = LoadSimulationResult(simulation_input, actual_power_kw=3.0)

    assert result.simulation_input is simulation_input
    assert result.actual_power_kw == 3.0


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_load_result_rejects_invalid_actual_power_type(value: object) -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)

    with pytest.raises(TypeError, match="actual_power_kw"):
        LoadSimulationResult(simulation_input, cast(Any, value))


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_load_result_rejects_invalid_actual_power_value(value: float) -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)

    with pytest.raises(ValueError, match="actual_power_kw"):
        LoadSimulationResult(simulation_input, value)


def test_load_result_rejects_power_above_demand() -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)

    with pytest.raises(ValueError, match="demand_power_kw"):
        LoadSimulationResult(simulation_input, 5.1)


def test_load_result_rejects_invalid_input() -> None:
    with pytest.raises(TypeError, match="simulation_input"):
        LoadSimulationResult(cast(Any, object()), 0.0)


@pytest.mark.parametrize(
    ("model_type", "expected_slots", "expected_fields"),
    [
        (
            LoadSimulationInput,
            ("step_identity", "demand_power_kw"),
            ["step_identity", "demand_power_kw"],
        ),
        (
            LoadSimulationResult,
            ("simulation_input", "actual_power_kw"),
            ["simulation_input", "actual_power_kw"],
        ),
    ],
)
def test_load_artifacts_are_frozen_slotted_and_field_complete(
    model_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(model_type)
    assert cast(Any, model_type).__dataclass_params__.frozen
    assert cast(Any, model_type).__slots__ == expected_slots
    assert [field.name for field in fields(model_type)] == expected_fields


def test_load_artifacts_have_no_instance_dictionary() -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)
    result = LoadSimulationResult(simulation_input, 3.0)

    assert not hasattr(simulation_input, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).actual_power_kw = 4.0


def test_load_model_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert inspect.isabstract(LoadSimulationModelBoundary)
    assert LoadSimulationModelBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, LoadSimulationModelBoundary)()


def test_test_only_model_receives_exact_input_and_result_preserves_it() -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)
    model = RecordingLoadModel(4.0)

    result = model.simulate(simulation_input)

    assert model.received is simulation_input
    assert result.simulation_input is simulation_input


def test_load_model_boundary_signature_is_contract_only() -> None:
    signature = inspect.signature(LoadSimulationModelBoundary.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is LoadSimulationResult
    assert getattr(LoadSimulationModelBoundary.simulate, "__isabstractmethod__", False)


def test_load_contract_has_no_prediction_behavior_or_execution_state() -> None:
    simulation_input = LoadSimulationInput(make_step(), 5.0)
    result = LoadSimulationResult(simulation_input, 3.0)

    for artifact in (simulation_input, result):
        for forbidden in (
            "forecast",
            "user_behavior",
            "demand_response",
            "device",
            "runtime",
            "command",
            "schedule",
            "cache",
            "history",
        ):
            assert not hasattr(artifact, forbidden)


def test_load_module_dependencies_are_core_and_standard_library_only() -> None:
    tree = ast.parse(inspect.getsource(load_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "simulator.core",
        "simulator.validation",
    }


def test_no_concrete_load_model_is_exported() -> None:
    concrete_models = [
        member
        for _, member in inspect.getmembers(load_module, inspect.isclass)
        if issubclass(member, LoadSimulationModelBoundary)
        and member is not LoadSimulationModelBoundary
    ]

    assert concrete_models == []
