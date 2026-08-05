"""Tests for Phase 6 simulation core identity and time contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from simulator import SimulationStepIdentity
from simulator import core as core_module


def test_simulation_step_identity_accepts_explicit_time_facts() -> None:
    timestamp = datetime(2026, 8, 5, 12, 0, tzinfo=timezone(timedelta(hours=8)))

    step = SimulationStepIdentity(
        sequence=0,
        duration_seconds=60,
        timestamp=timestamp,
    )

    assert step.sequence == 0
    assert step.duration_seconds == 60.0
    assert step.timestamp is timestamp


def test_simulation_step_identity_accepts_explicit_absent_timestamp() -> None:
    step = SimulationStepIdentity(sequence=3, duration_seconds=0.5, timestamp=None)

    assert step.timestamp is None


@pytest.mark.parametrize("sequence", [True, 1.0, "1", None, object()])
def test_simulation_step_identity_rejects_invalid_sequence_type(
    sequence: object,
) -> None:
    with pytest.raises(TypeError, match="sequence"):
        SimulationStepIdentity(
            sequence=cast(Any, sequence),
            duration_seconds=1.0,
            timestamp=None,
        )


def test_simulation_step_identity_rejects_negative_sequence() -> None:
    with pytest.raises(ValueError, match="sequence"):
        SimulationStepIdentity(sequence=-1, duration_seconds=1.0, timestamp=None)


@pytest.mark.parametrize("duration", [True, "1", None, object()])
def test_simulation_step_identity_rejects_invalid_duration_type(
    duration: object,
) -> None:
    with pytest.raises(TypeError, match="duration_seconds"):
        SimulationStepIdentity(
            sequence=0,
            duration_seconds=cast(Any, duration),
            timestamp=None,
        )


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
def test_simulation_step_identity_rejects_invalid_duration_value(
    duration: float,
) -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        SimulationStepIdentity(sequence=0, duration_seconds=duration, timestamp=None)


def test_simulation_step_identity_rejects_invalid_timestamp_type() -> None:
    with pytest.raises(TypeError, match="timestamp"):
        SimulationStepIdentity(
            sequence=0,
            duration_seconds=1.0,
            timestamp=cast(Any, "2026-08-05T12:00:00+08:00"),
        )


def test_simulation_step_identity_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        SimulationStepIdentity(
            sequence=0,
            duration_seconds=1.0,
            timestamp=datetime(2026, 8, 5, 12, 0),
        )


def test_simulation_step_identity_accepts_utc_timestamp_identity() -> None:
    timestamp = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)

    step = SimulationStepIdentity(0, 1.0, timestamp)

    assert step.timestamp is timestamp


def test_simulation_step_identity_is_frozen_slotted_and_field_complete() -> None:
    step = SimulationStepIdentity(0, 1.0, None)

    assert is_dataclass(step)
    assert cast(Any, SimulationStepIdentity).__dataclass_params__.frozen
    assert SimulationStepIdentity.__slots__ == (
        "sequence",
        "duration_seconds",
        "timestamp",
    )
    assert [field.name for field in fields(SimulationStepIdentity)] == [
        "sequence",
        "duration_seconds",
        "timestamp",
    ]
    assert not hasattr(step, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, step).sequence = 1


def test_simulation_step_identity_has_no_runtime_or_component_state() -> None:
    step = SimulationStepIdentity(0, 1.0, None)

    for forbidden in (
        "runtime",
        "scheduler",
        "command",
        "device",
        "pv",
        "load",
        "battery",
        "grid",
        "tariff",
        "cache",
        "history",
    ):
        assert not hasattr(step, forbidden)


def test_core_module_dependencies_are_standard_library_and_local_validation() -> None:
    tree = ast.parse(inspect.getsource(core_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "datetime",
        "simulator.validation",
    }
