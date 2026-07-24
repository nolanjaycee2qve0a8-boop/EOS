# ADR-016 — Command Dispatch Interface Boundary

## Status

Accepted

## Context

EOS policies produce immutable domain Command objects, but the kernel has no
stable boundary for handing one command to future external infrastructure.
Embedding protocol conversion or device communication into policies, decision
results, or runtime ticks would couple the deterministic kernel to mutable
external systems.

The boundary must exist before adapters are introduced, while leaving execution
semantics deliberately unspecified.

## Decision

Introduce CommandDispatcher as an abstract class with empty slots and one
abstract operation:

`dispatch(command: Command) -> None`

The operation accepts exactly one exact Command. A concrete implementation
returns None on normal completion and raises an exception on failure. The
interface itself performs no conversion, mutation, execution, persistence, or
journaling.

Export only CommandDispatcher from the new `kernel.dispatch` package. Do not
introduce a concrete production dispatcher in this decision.

## Consequences

- Future external adapters gain a stable Command submission boundary.
- Domain Command identity remains intact at the kernel boundary.
- Policy, decision, cycle, runtime, and journal types remain independent of
  device protocols.
- Failure is represented only by implementation exceptions for now.
- Retry, timeout, batching, ordering, receipts, and partial failure remain
  intentionally undefined.

## Alternatives Considered

- Dispatch directly from DecisionResult: rejected because it mixes immutable
  decision output with external side effects.
- Convert Commands to dictionaries in the boundary: rejected because protocol
  representation belongs to concrete adapters.
- Add a default in-memory or no-op dispatcher: rejected because this task
  defines no concrete production behavior.
- Define batch dispatch: rejected because ordering and partial-failure semantics
  have not been decided.
- Add receipts or status enums: rejected because execution-result semantics are
  outside this interface-only task.
