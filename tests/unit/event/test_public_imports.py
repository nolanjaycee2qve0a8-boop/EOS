"""Tests for the public event journal imports."""

from kernel.event import EventJournal, EventRecord, replay


def test_event_journal_interfaces_are_publicly_importable() -> None:
    assert EventJournal.__name__ == "EventJournal"
    assert EventRecord.__name__ == "EventRecord"
    assert replay.__name__ == "replay"
