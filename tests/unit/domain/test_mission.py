"""Tests for Mission."""

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from kernel.domain import Mission
from kernel.ids import MissionId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
MISSION_ID = MissionId("mission-1")


def make_mission(
    *,
    mission_id: MissionId = MISSION_ID,
    created_at: datetime = FIXED_TIME,
    valid_from: datetime = FIXED_TIME,
    valid_until: datetime | None = None,
    objective: str = "minimize grid import",
    priority: int = 0,
    parameters: Mapping[str, object] | None = None,
) -> Mission:
    return Mission(
        mission_id=mission_id,
        created_at=created_at,
        valid_from=valid_from,
        valid_until=valid_until,
        objective=objective,
        priority=priority,
        parameters={} if parameters is None else parameters,
    )


def test_mission_creation() -> None:
    mission = make_mission(valid_until=FIXED_TIME + timedelta(hours=1))
    assert mission.priority == 0


def test_mission_fields_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, make_mission()).priority = 1


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        (
            "created_at",
            lambda: make_mission(created_at=datetime(2026, 1, 1, 12, 0)),
        ),
        (
            "valid_from",
            lambda: make_mission(valid_from=datetime(2026, 1, 1, 12, 0)),
        ),
    ],
)
def test_mission_rejects_naive_required_times(
    field_name: str, factory: Callable[[], Mission]
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()


def test_mission_rejects_naive_valid_until() -> None:
    with pytest.raises(ValueError, match="valid_until"):
        make_mission(valid_until=datetime(2026, 1, 1, 13, 0))


def test_mission_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="mission_id"):
        make_mission(mission_id=MissionId(" "))


@pytest.mark.parametrize("objective", ["", "  "])
def test_mission_rejects_empty_objective(objective: str) -> None:
    with pytest.raises(ValueError, match="objective"):
        make_mission(objective=objective)


def test_mission_rejects_negative_priority() -> None:
    with pytest.raises(ValueError, match="priority"):
        make_mission(priority=-1)


def test_mission_rejects_bool_priority() -> None:
    with pytest.raises(ValueError, match="priority"):
        make_mission(priority=True)


@pytest.mark.parametrize(
    "valid_until", [FIXED_TIME, FIXED_TIME - timedelta(microseconds=1)]
)
def test_mission_requires_valid_until_after_valid_from(
    valid_until: datetime,
) -> None:
    with pytest.raises(ValueError, match="valid_until"):
        make_mission(valid_until=valid_until)


def test_mission_defensively_copies_parameters() -> None:
    parameters: dict[str, object] = {"limit_kw": 5}
    mission = make_mission(parameters=parameters)
    parameters["limit_kw"] = 10
    assert mission.parameters["limit_kw"] == 5


def test_mission_parameters_are_read_only() -> None:
    parameters = cast(MutableMapping[str, object], make_mission().parameters)
    with pytest.raises(TypeError):
        parameters["limit_kw"] = 5


def test_mission_value_equality() -> None:
    assert make_mission(parameters={"limit_kw": 5}) == make_mission(
        parameters={"limit_kw": 5}
    )
