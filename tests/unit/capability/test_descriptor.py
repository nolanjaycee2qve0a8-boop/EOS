"""Tests for the immutable capability descriptor contract."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from capability import CapabilityDescriptor


def test_descriptor_creation() -> None:
    descriptor = CapabilityDescriptor(
        name="test capability",
        description="A test-only capability description.",
    )

    assert descriptor.name == "test capability"
    assert descriptor.description == "A test-only capability description."


@pytest.mark.parametrize("field_name", ["name", "description"])
def test_descriptor_requires_string_fields(field_name: str) -> None:
    values: dict[str, object] = {
        "name": "test capability",
        "description": "test description",
    }
    values[field_name] = 1

    with pytest.raises(TypeError, match=field_name):
        CapabilityDescriptor(**cast(Any, values))


@pytest.mark.parametrize("field_name", ["name", "description"])
@pytest.mark.parametrize("value", ["", "   "])
def test_descriptor_rejects_empty_fields(field_name: str, value: str) -> None:
    values = {
        "name": "test capability",
        "description": "test description",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        CapabilityDescriptor(**values)


def test_descriptor_is_frozen_slotted_and_has_no_mutable_state() -> None:
    descriptor = CapabilityDescriptor("test", "Test capability description.")

    assert [field.name for field in fields(CapabilityDescriptor)] == [
        "name",
        "description",
    ]
    assert CapabilityDescriptor.__slots__ == ("name", "description")
    assert not hasattr(descriptor, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, descriptor).name = "changed"


def test_public_import() -> None:
    from capability import __all__ as public_names

    assert "CapabilityDescriptor" in public_names
