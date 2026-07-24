# ADR-012 — Deterministic EMS Cycle Event Journaling

## Status

Accepted

## Context

An EMSCycle records one immutable EnergySystemContext and its DecisionResult.
DecisionResult may contain ordered domain events that need deterministic
association with the existing immutable EventJournal. That association must
not modify the cycle, journal, events, or legacy RuntimeKernel journaling.

Commands and events have different responsibilities. Treating commands as
journal events, or generating new event metadata during recording, would cross
the established decision and event boundaries.

## Decision

Introduce JournaledEMSCycle as a frozen slotted dataclass containing exactly:

- the original EMSCycle; and
- the EventJournal resulting from appending the cycle's events.

For an empty source journal, assign sequence zero to the first new event.
Otherwise continue from the last EventRecord sequence plus one. Append one new
EventRecord per event through EventJournal.append, preserving event order and
exact Event identities.

If the cycle has no events, return the exact source journal. Ignore commands
entirely. Do not store policy or introduce clocks, identifiers, timestamps,
scheduling, retries, persistence, communications, or runtime behavior.

## Consequences

- Completed cycles can be associated with deterministic immutable event history.
- Event sequence allocation is explicit and reproducible.
- Source journals, cycles, results, and domain events remain unchanged.
- Empty event results allocate no new journal object.
- Commands remain outside the event-journaling boundary.
- Legacy RuntimeKernel journaling remains unchanged.

## Alternatives Considered

- Mutate EventJournal in place: rejected because the journal is immutable.
- Journal commands: rejected because commands request actions and are not domain events.
- Generate timestamps or UUIDs: rejected because events already contain caller-owned metadata.
- Call runtime journaling logic: rejected because TASK-013 must not refactor or
  couple to RuntimeKernel.
- Renumber existing records: rejected because existing journal history and
  identities must remain unchanged.
- Store policy on JournaledEMSCycle: rejected because the association records
  only a completed cycle and its progressed journal.
