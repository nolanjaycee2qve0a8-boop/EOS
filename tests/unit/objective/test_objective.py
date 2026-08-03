"""Tests for immutable objective description contracts."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from objective import ObjectiveCollection, ObjectiveDescriptor


def test_descriptor_creation() -> None:
    descriptor = ObjectiveDescriptor(
        name="test concern",
        description="A test-only concern without decision behavior.",
    )

    assert descriptor.name == "test concern"
    assert descriptor.description == "A test-only concern without decision behavior."


@pytest.mark.parametrize("field_name", ["name", "description"])
def test_descriptor_requires_string_fields(field_name: str) -> None:
    values: dict[str, object] = {
        "name": "test concern",
        "description": "test description",
    }
    values[field_name] = 1

    with pytest.raises(TypeError, match=field_name):
        ObjectiveDescriptor(**cast(Any, values))


@pytest.mark.parametrize("field_name", ["name", "description"])
@pytest.mark.parametrize("value", ["", "   "])
def test_descriptor_rejects_empty_fields(field_name: str, value: str) -> None:
    values = {
        "name": "test concern",
        "description": "test description",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        ObjectiveDescriptor(**values)


def test_collection_preserves_exact_descriptor_identity_and_order() -> None:
    first = ObjectiveDescriptor("first", "First test concern.")
    second = ObjectiveDescriptor("second", "Second test concern.")
    supplied = (first, second)

    collection = ObjectiveCollection(supplied)

    assert collection.objectives is supplied
    assert collection.objectives[0] is first
    assert collection.objectives[1] is second


def test_collection_accepts_empty_tuple() -> None:
    supplied: tuple[ObjectiveDescriptor, ...] = ()

    collection = ObjectiveCollection(supplied)

    assert collection.objectives is supplied


def test_collection_rejects_mutable_or_invalid_contents() -> None:
    descriptor = ObjectiveDescriptor("test", "Test concern.")

    with pytest.raises(TypeError, match="objectives"):
        ObjectiveCollection(cast(Any, [descriptor]))
    with pytest.raises(TypeError, match="ObjectiveDescriptor"):
        ObjectiveCollection(cast(Any, ("not a descriptor",)))


def test_models_are_frozen_slotted_and_have_no_mutable_containers() -> None:
    descriptor = ObjectiveDescriptor("test", "Test concern.")
    collection = ObjectiveCollection((descriptor,))

    assert [field.name for field in fields(ObjectiveDescriptor)] == [
        "name",
        "description",
    ]
    assert [field.name for field in fields(ObjectiveCollection)] == ["objectives"]
    assert ObjectiveDescriptor.__slots__ == ("name", "description")
    assert ObjectiveCollection.__slots__ == ("objectives",)
    assert not hasattr(descriptor, "__dict__")
    assert not hasattr(collection, "__dict__")
    assert isinstance(collection.objectives, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, descriptor).name = "changed"
    with pytest.raises(FrozenInstanceError):
        cast(Any, collection).objectives = ()
