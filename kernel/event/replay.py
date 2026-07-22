"""Deterministic iteration boundary for immutable event journals."""

from kernel.event.journal import EventJournal
from kernel.event.sequence import EventRecord
from kernel.event.validation import require_instance


def replay(journal: EventJournal) -> tuple[EventRecord, ...]:
    """Return existing records in their validated sequence order."""
    validated = require_instance(journal, EventJournal, "journal")
    return validated.events()
