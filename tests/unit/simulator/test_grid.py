"""Tests for the Phase 6 grid simulation model contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from simulator import (
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    SimulationStepIdentity,
)
from simulator import grid as grid_module


class RecordingGridModel(GridSimulationModelBoundary):
    """Test-only model returning a caller-configured exchange observation."""

    __slots__ = ("actual_grid_power_kw", "received")

    def __init__(self, actual_grid_power_kw: float) -> None:
        self.actual_grid_power_kw = actual_grid_power_kw
        self.received: GridSimulationInput | None = None

    def simulate(
        self,
        simulation_input: GridSimulationInput,
    ) -> GridSimulationResult:
        self.received = simulation_input
        return GridSimulationResult(simulation_input, self.actual_grid_power_kw)


def make_step() -> SimulationStepIdentity:
    return SimulationStepIdentity(0, 60.0, None)


@pytest.mark.parametrize(
    ("power_kw", "meaning"),
    [(3.0, "import"), (-3.0, "export"), (0.0, "balanced")],
)
def test_grid_input_uses_explicit_power_sign_contract(
    power_kw: float,
    meaning: str,
) -> None:
    step = make_step()

    simulation_input = GridSimulationInput(step, power_kw)

    assert simulation_input.step_identity is step
    assert simulation_input.requested_grid_power_kw == power_kw
    assert meaning in (GridSimulationInput.__doc__ or "")


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_grid_input_rejects_invalid_power_type(value: object) -> None:
    with pytest.raises(TypeError, match="requested_grid_power_kw"):
        GridSimulationInput(make_step(), cast(Any, value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_grid_input_rejects_non_finite_power(value: float) -> None:
    with pytest.raises(ValueError, match="requested_grid_power_kw"):
        GridSimulationInput(make_step(), value)


def test_grid_input_rejects_invalid_step_type() -> None:
    with pytest.raises(TypeError, match="step_identity"):
        GridSimulationInput(cast(Any, object()), 1.0)


@pytest.mark.parametrize(
    ("power_kw", "meaning"),
    [(2.0, "import"), (-2.0, "export"), (0.0, "balanced")],
)
def test_grid_result_preserves_input_and_sign_contract(
    power_kw: float,
    meaning: str,
) -> None:
    simulation_input = GridSimulationInput(make_step(), 1.0)

    result = GridSimulationResult(simulation_input, power_kw)

    assert result.simulation_input is simulation_input
    assert result.actual_grid_power_kw == power_kw
    assert meaning in (GridSimulationResult.__doc__ or "")


def test_grid_result_does_not_force_requested_and_actual_equality() -> None:
    simulation_input = GridSimulationInput(make_step(), 4.0)

    result = GridSimulationResult(simulation_input, 2.5)

    assert result.simulation_input is simulation_input
    assert result.actual_grid_power_kw == 2.5
    assert simulation_input.requested_grid_power_kw == 4.0


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_grid_result_rejects_invalid_power_type(value: object) -> None:
    with pytest.raises(TypeError, match="actual_grid_power_kw"):
        GridSimulationResult(
            GridSimulationInput(make_step(), 1.0),
            cast(Any, value),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_grid_result_rejects_non_finite_power(value: float) -> None:
    with pytest.raises(ValueError, match="actual_grid_power_kw"):
        GridSimulationResult(GridSimulationInput(make_step(), 1.0), value)


def test_grid_result_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="simulation_input"):
        GridSimulationResult(cast(Any, object()), 1.0)


@pytest.mark.parametrize(
    ("model_type", "expected_slots", "expected_fields"),
    [
        (
            GridSimulationInput,
            ("step_identity", "requested_grid_power_kw"),
            ["step_identity", "requested_grid_power_kw"],
        ),
        (
            GridSimulationResult,
            ("simulation_input", "actual_grid_power_kw"),
            ["simulation_input", "actual_grid_power_kw"],
        ),
    ],
)
def test_grid_artifacts_are_frozen_slotted_and_field_complete(
    model_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(model_type)
    assert cast(Any, model_type).__dataclass_params__.frozen
    assert cast(Any, model_type).__slots__ == expected_slots
    assert [field.name for field in fields(model_type)] == expected_fields


def test_grid_artifacts_have_no_instance_dictionary() -> None:
    simulation_input = GridSimulationInput(make_step(), 1.0)
    result = GridSimulationResult(simulation_input, 1.0)

    assert not hasattr(simulation_input, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).actual_grid_power_kw = 0.0


def test_grid_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert inspect.isabstract(GridSimulationModelBoundary)
    assert GridSimulationModelBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, GridSimulationModelBoundary)()


def test_test_only_grid_model_receives_exact_input_once() -> None:
    simulation_input = GridSimulationInput(make_step(), 2.0)
    model = RecordingGridModel(1.5)

    result = model.simulate(simulation_input)

    assert model.received is simulation_input
    assert result.simulation_input is simulation_input
    assert result.actual_grid_power_kw == 1.5


def test_grid_boundary_signature_is_contract_only() -> None:
    signature = inspect.signature(GridSimulationModelBoundary.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is GridSimulationResult
    assert getattr(
        GridSimulationModelBoundary.simulate,
        "__isabstractmethod__",
        False,
    )


def test_grid_contract_has_no_balance_constraint_or_execution_ownership() -> None:
    simulation_input = GridSimulationInput(make_step(), 1.0)
    result = GridSimulationResult(simulation_input, 1.0)

    for artifact in (simulation_input, result):
        for forbidden in (
            "balance",
            "import_limit",
            "export_limit",
            "constraint",
            "runtime",
            "command",
            "device",
            "dispatch",
            "cache",
            "history",
        ):
            assert not hasattr(artifact, forbidden)


def test_grid_module_dependencies_are_core_and_standard_library_only() -> None:
    tree = ast.parse(inspect.getsource(grid_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "simulator.core",
        "simulator.validation",
    }


def test_no_concrete_grid_model_is_exported() -> None:
    concrete_models = [
        member
        for _, member in inspect.getmembers(grid_module, inspect.isclass)
        if issubclass(member, GridSimulationModelBoundary)
        and member is not GridSimulationModelBoundary
    ]

    assert concrete_models == []
