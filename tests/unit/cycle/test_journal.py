"""Tests for deterministic event journaling of completed EMS cycles."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.domain import Command, Event
from kernel.event import EventJournal, EventRecord
from kernel.ids import (
    AssetId,
    CommandId,
    EventId,
    MissionId,
    SnapshotId,
)
from kernel.power import PowerFlow

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


def make_command(number: int) -> Command:
    return Command(
        command_id=CommandId(f"command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_context() -> EnergySystemContext:
    return EnergySystemContext(
        assets=(),
        states=(),
        power_flow=PowerFlow(
            pv_power_kw=0.0,
            load_power_kw=0.0,
            battery_power_kw=0.0,
            grid_power_kw=0.0,
        ),
    )


def make_cycle(
    *,
    events: tuple[Event, ...] = (),
    commands: tuple[Command, ...] = (),
) -> EMSCycle:
    return EMSCycle(
        context=make_context(),
        result=DecisionResult(commands=commands, events=events),
    )


def test_first_event_in_empty_journal_receives_sequence_zero() -> None:
    event = make_event(1)

    recorded = JournaledEMSCycle.record(
        make_cycle(events=(event,)),
        EventJournal(),
    )

    assert recorded.journal.events()[0].sequence == 0


def test_multiple_events_receive_contiguous_sequences() -> None:
    events = (make_event(1), make_event(2), make_event(3))

    recorded = JournaledEMSCycle.record(
        make_cycle(events=events),
        EventJournal(),
    )

    assert tuple(record.sequence for record in recorded.journal.events()) == (
        0,
        1,
        2,
    )


def test_populated_journal_continues_from_last_sequence() -> None:
    existing = EventRecord(sequence=4, event=make_event(0))
    journal = EventJournal().append(existing)

    recorded = JournaledEMSCycle.record(
        make_cycle(events=(make_event(1), make_event(2))),
        journal,
    )

    assert tuple(record.sequence for record in recorded.journal.events()) == (
        4,
        5,
        6,
    )


def test_event_order_is_preserved() -> None:
    first, second, third = make_event(1), make_event(2), make_event(3)

    recorded = JournaledEMSCycle.record(
        make_cycle(events=(third, first, second)),
        EventJournal(),
    )

    assert tuple(record.event for record in recorded.journal.events()) == (
        third,
        first,
        second,
    )


def test_exact_event_identities_are_preserved() -> None:
    first, second = make_event(1), make_event(2)

    recorded = JournaledEMSCycle.record(
        make_cycle(events=(first, second)),
        EventJournal(),
    )
    records = recorded.journal.events()

    assert records[0].event is first
    assert records[1].event is second


def test_exact_cycle_identity_is_preserved() -> None:
    cycle = make_cycle(events=(make_event(1),))

    recorded = JournaledEMSCycle.record(cycle, EventJournal())

    assert recorded.cycle is cycle


def test_original_journal_remains_unchanged() -> None:
    existing = EventRecord(sequence=7, event=make_event(0))
    journal = EventJournal().append(existing)

    recorded = JournaledEMSCycle.record(
        make_cycle(events=(make_event(1),)),
        journal,
    )

    assert journal.events() == (existing,)
    assert recorded.journal is not journal
    assert recorded.journal.events()[0] is existing


def test_empty_event_result_preserves_exact_journal_identity() -> None:
    journal = EventJournal().append(EventRecord(sequence=2, event=make_event(0)))

    recorded = JournaledEMSCycle.record(make_cycle(), journal)

    assert recorded.journal is journal


def test_commands_are_not_journaled() -> None:
    command = make_command(1)
    journal = EventJournal()

    recorded = JournaledEMSCycle.record(
        make_cycle(commands=(command,)),
        journal,
    )

    assert recorded.journal is journal
    assert recorded.journal.events() == ()
    assert recorded.cycle.result.commands == (command,)


def test_commands_do_not_change_event_recording() -> None:
    command = make_command(1)
    event = make_event(1)

    recorded = JournaledEMSCycle.record(
        make_cycle(commands=(command,), events=(event,)),
        EventJournal(),
    )

    assert len(recorded.journal.events()) == 1
    assert recorded.journal.events()[0].event is event


def test_journaled_cycle_is_frozen_and_slotted() -> None:
    recorded = JournaledEMSCycle.record(make_cycle(), EventJournal())

    assert not hasattr(recorded, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, recorded).journal = EventJournal()


def test_contains_exactly_cycle_and_journal_fields() -> None:
    assert [field.name for field in fields(JournaledEMSCycle)] == [
        "cycle",
        "journal",
    ]


def test_invalid_cycle_raises_type_error() -> None:
    with pytest.raises(TypeError, match="cycle"):
        JournaledEMSCycle.record(
            cast(EMSCycle, object()),
            EventJournal(),
        )


def test_invalid_journal_raises_type_error() -> None:
    with pytest.raises(TypeError, match="journal"):
        JournaledEMSCycle.record(
            make_cycle(),
            cast(EventJournal, object()),
        )
