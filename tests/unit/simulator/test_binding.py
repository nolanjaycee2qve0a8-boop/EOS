"""Tests for immutable caller-supplied simulation model bindings."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from simulator import (
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationModelBinding,
    SimulationModelBindingCollection,
)
from simulator import binding as binding_module


class TestPVModel(PVSimulationModelBoundary):
    __test__ = False
    __slots__ = ()

    def simulate(
        self,
        simulation_input: PVSimulationInput,
    ) -> PVSimulationResult:
        raise AssertionError("TASK-075 bindings must not execute models")


class TestLoadModel(LoadSimulationModelBoundary):
    __test__ = False
    __slots__ = ()

    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        raise AssertionError("TASK-075 bindings must not execute models")


def test_binding_preserves_exact_model_identity() -> None:
    model = TestPVModel()

    binding = SimulationModelBinding(PVSimulationModelBoundary, model)

    assert binding.component_contract is PVSimulationModelBoundary
    assert binding.model is model


def test_binding_rejects_invalid_component_contract() -> None:
    with pytest.raises(TypeError, match="component_contract"):
        SimulationModelBinding(cast(Any, object()), TestPVModel())


def test_binding_rejects_model_for_different_contract() -> None:
    with pytest.raises(TypeError, match="model"):
        SimulationModelBinding(PVSimulationModelBoundary, TestLoadModel())


def test_collection_preserves_exact_tuple_bindings_and_order() -> None:
    pv_binding = SimulationModelBinding(PVSimulationModelBoundary, TestPVModel())
    load_binding = SimulationModelBinding(
        LoadSimulationModelBoundary,
        TestLoadModel(),
    )
    caller_bindings = (load_binding, pv_binding)

    collection = SimulationModelBindingCollection(caller_bindings)

    assert collection.bindings is caller_bindings
    assert collection.bindings[0] is load_binding
    assert collection.bindings[1] is pv_binding


def test_empty_binding_collection_is_valid() -> None:
    caller_bindings: tuple[SimulationModelBinding, ...] = ()

    collection = SimulationModelBindingCollection(caller_bindings)

    assert collection.bindings is caller_bindings


def test_collection_preserves_repeated_exact_binding_references() -> None:
    binding = SimulationModelBinding(PVSimulationModelBoundary, TestPVModel())
    caller_bindings = (binding, binding)

    collection = SimulationModelBindingCollection(caller_bindings)

    assert collection.bindings is caller_bindings
    assert collection.bindings[0] is binding
    assert collection.bindings[1] is binding


def test_collection_rejects_mutable_or_invalid_contents() -> None:
    binding = SimulationModelBinding(PVSimulationModelBoundary, TestPVModel())

    with pytest.raises(TypeError, match="tuple"):
        SimulationModelBindingCollection(cast(Any, [binding]))
    with pytest.raises(TypeError, match="SimulationModelBinding"):
        SimulationModelBindingCollection((cast(Any, object()),))


def test_reconstructed_binding_is_not_identity_membership() -> None:
    model = TestPVModel()
    original = SimulationModelBinding(PVSimulationModelBoundary, model)
    collection = SimulationModelBindingCollection((original,))
    reconstructed = SimulationModelBinding(PVSimulationModelBoundary, model)

    assert reconstructed is not original
    assert reconstructed != original
    assert reconstructed not in collection.bindings


@pytest.mark.parametrize(
    ("artifact_type", "expected_slots", "expected_fields"),
    [
        (
            SimulationModelBinding,
            ("component_contract", "model"),
            ["component_contract", "model"],
        ),
        (
            SimulationModelBindingCollection,
            ("bindings",),
            ["bindings"],
        ),
    ],
)
def test_binding_artifacts_are_identity_based_frozen_and_slotted(
    artifact_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(artifact_type)
    parameters = cast(Any, artifact_type).__dataclass_params__
    assert parameters.frozen
    assert not parameters.eq
    assert cast(Any, artifact_type).__slots__ == expected_slots
    assert [field.name for field in fields(artifact_type)] == expected_fields


def test_binding_artifacts_have_no_instance_dictionary_and_are_frozen() -> None:
    binding = SimulationModelBinding(PVSimulationModelBoundary, TestPVModel())
    collection = SimulationModelBindingCollection((binding,))

    assert not hasattr(binding, "__dict__")
    assert not hasattr(collection, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, binding).model = TestPVModel()
    with pytest.raises(FrozenInstanceError):
        cast(Any, collection).bindings = ()


def test_binding_creation_does_not_execute_model() -> None:
    model = TestPVModel()
    binding = SimulationModelBinding(PVSimulationModelBoundary, model)

    collection = SimulationModelBindingCollection((binding,))

    assert collection.bindings[0].model is model


def test_binding_module_has_no_registry_factory_or_forbidden_dependencies() -> None:
    source = inspect.getsource(binding_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "simulator.battery",
        "simulator.grid",
        "simulator.load",
        "simulator.pv",
        "simulator.tariff",
    }
    for forbidden in (
        "registry",
        "factory",
        "runtime",
        "scheduler",
        "device",
        "command",
        "dispatcher",
        "optimization",
        "executor",
        "execute(",
        "simulate(",
    ):
        assert forbidden not in source.lower()
