"""Tests for Command."""

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.domain import Command
from kernel.ids import AssetId, CommandId, MissionId, SnapshotId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
COMMAND_ID = CommandId("command-1")
MISSION_ID = MissionId("mission-1")
SNAPSHOT_ID = SnapshotId("snapshot-1")
ASSET_ID = AssetId("asset-1")


def make_command(
    *,
    command_id: CommandId = COMMAND_ID,
    mission_id: MissionId = MISSION_ID,
    snapshot_id: SnapshotId = SNAPSHOT_ID,
    asset_id: AssetId = ASSET_ID,
    issued_at: datetime = FIXED_TIME,
    action: str = "set_power",
    parameters: Mapping[str, object] | None = None,
) -> Command:
    return Command(
        command_id=command_id,
        mission_id=mission_id,
        snapshot_id=snapshot_id,
        asset_id=asset_id,
        issued_at=issued_at,
        action=action,
        parameters={} if parameters is None else parameters,
    )


def test_command_creation() -> None:
    command = make_command(parameters={"power_kw": 5})
    assert command.action == "set_power"


def test_command_fields_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, make_command()).action = "stop"


def test_command_rejects_naive_issued_at() -> None:
    with pytest.raises(ValueError, match="issued_at"):
        make_command(issued_at=datetime(2026, 1, 1, 12, 0))


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        ("command_id", lambda: make_command(command_id=CommandId(""))),
        ("mission_id", lambda: make_command(mission_id=MissionId(" "))),
        ("snapshot_id", lambda: make_command(snapshot_id=SnapshotId(""))),
        ("asset_id", lambda: make_command(asset_id=AssetId(" "))),
    ],
)
def test_command_rejects_empty_ids(
    field_name: str, factory: Callable[[], Command]
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()


@pytest.mark.parametrize("action", ["", "  "])
def test_command_rejects_empty_action(action: str) -> None:
    with pytest.raises(ValueError, match="action"):
        make_command(action=action)


def test_command_defensively_copies_parameters() -> None:
    parameters: dict[str, object] = {"power_kw": 5}
    command = make_command(parameters=parameters)
    parameters["power_kw"] = 10
    assert command.parameters["power_kw"] == 5


def test_command_parameters_are_read_only() -> None:
    parameters = cast(MutableMapping[str, object], make_command().parameters)
    with pytest.raises(TypeError):
        parameters["power_kw"] = 5


def test_command_value_equality() -> None:
    assert make_command(parameters={"power_kw": 5}) == make_command(
        parameters={"power_kw": 5}
    )
