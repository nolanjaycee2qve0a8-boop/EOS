# ADR-013 — Journaled EMS Execution Service

## Status

Accepted

## Context

EOS has separate immutable boundaries for policy execution and event
journaling: EMSCycle executes one policy through PolicyExecutor, while
JournaledEMSCycle records a completed cycle's events through EventJournal.
Callers need one synchronous entry point that composes these boundaries without
duplicating or bypassing them.

A stateful service, direct policy invocation, or direct journal manipulation
would weaken ownership boundaries and create another source of execution or
sequencing behavior.

## Decision

Introduce JournaledEMSExecutionService as a stateless class with an empty slots
declaration and one static method:

`execute(policy, context, journal) -> JournaledEMSCycle`

Validate all three inputs before execution. Call EMSCycle.execute exactly once,
then pass its exact result and the exact source journal to
JournaledEMSCycle.record exactly once. Return the exact object produced by
recording.

Do not call EMSPolicy, PolicyExecutor, EventRecord, or EventJournal.append
directly. Do not catch or translate downstream exceptions. Retain no objects or
runtime state.

## Consequences

- Callers gain one explicit synchronous journaled-execution entry point.
- Existing execution and journaling boundaries remain authoritative.
- Input, intermediate, output, and nested object identities are preserved.
- Invalid journals cannot trigger policy evaluation.
- Policy, cycle, journal, and event exceptions propagate unchanged.
- Runtime scheduling and repeated execution remain separate concerns.

## Alternatives Considered

- Call policy.evaluate directly: rejected because it bypasses EMSCycle and PolicyExecutor.
- Call PolicyExecutor directly: rejected because EMSCycle is the completed-execution boundary.
- Append EventRecords in the service: rejected because JournaledEMSCycle owns recording.
- Store policy or journal on the service: rejected because the service must be stateless.
- Catch and wrap exceptions: rejected because no error translation contract exists.
- Add retries or asynchronous execution: rejected because those require runtime
  scheduling semantics outside this task.
