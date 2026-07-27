# ADR-023 — Execution Audit Boundary

## Status

Accepted

## Context

`RuntimeExecutionTrace` preserves one completed decision, journal, dispatch,
and progression lifecycle. Operators and future audit consumers need a stable
observation above that trace without coupling audit inspection to runtime
execution.

If audit replays or recomputes the lifecycle, it can duplicate external
effects, produce new decisions, or change journal history. If it copies
lifecycle objects, exact provenance and identity relationships are lost.

## Decision

Introduce the frozen, slotted `ExecutionAudit` model.

`ExecutionAudit.create(trace)` validates an existing `RuntimeExecutionTrace`
and retains exact references to:

- the trace;
- its source tick;
- its dispatched tick; and
- its progressed tick.

Validation is identity-based. The dispatched tick must contain the exact source
tick, and the progressed journal must preserve every source `EventRecord` as
the same object in its prefix.

Audit construction only observes existing immutable relationships. It does not
call runtime, dispatch, `CommandExecutor`, `RuntimeReplay`, policy evaluation,
or `EventJournal.append()`.

## Why Audit Is Separate from Execution

Execution owns lifecycle transitions and external effects. Audit only describes
the relationships that already resulted from a completed lifecycle. Keeping
these boundaries separate prevents observation from becoming a hidden runtime
operation.

## Why Audit Does Not Replay or Recompute

Replay and audit have different responsibilities. Runtime replay exposes the
existing lifecycle as a replay observation. Audit independently validates and
exposes provenance from the trace; it does not invoke replay or recreate the
execution that produced the trace.

## Why Identity Preservation Is Required

Exact identity demonstrates that the audit refers to the original decision,
journals, commands, events, and records. Value-equal replacements could conceal
reconstruction and would weaken deterministic provenance.

## Consequences

- Completed execution traces have a deterministic audit observation.
- Lifecycle and journal object identities remain intact.
- Audit creation has no execution or journal side effects.
- No audit state is retained between calls.
- Persistence, reporting, diagnosis, recovery, and UI concerns remain future,
  intentionally excluded extensions.

## Rejected Alternatives

- Re-execute or replay during audit: rejected because audit is observation.
- Copy lifecycle objects: rejected because copies lose exact provenance.
- Append audit records: rejected because audit must not change journal history.
- Store audit history: rejected because persistence ownership is out of scope.
