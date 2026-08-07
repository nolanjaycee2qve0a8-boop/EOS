# ADR-077 — Validate Phase 7 Without Adding a Simulation Runtime

Status: Accepted

## Context

TASK-075 through TASK-079 introduced model binding, one-step execution,
single-step evidence, explicit scenario execution, and caller-owned step
progression contracts. Each contract has focused unit coverage, but Phase 7
also needs evidence that their composition preserves deterministic execution,
identity lineage, failure semantics, and architectural isolation.

Adding a production orchestration layer solely for validation would expand
scope and risk turning deterministic simulation execution into Runtime.

## Decision

Validate the complete Phase 7 chain using integration tests and test-only
component model implementations. Do not add or modify production Python code.

The success path executes an explicit two-step scenario and verifies:

- exact caller scenario, binding, step, trace, result, and progression
  relationships;
- caller-defined ordering;
- exactly-once component execution per successful step;
- deterministic observed values across independent executions;
- explicit Battery next-state to next-input source-state provenance.

The failure path raises one exact component exception during a later step and
verifies stop-first propagation, no retry, no implicit continuation, no later
step execution, and no successful scenario result.

## Consequences

- Phase 7 contracts have end-to-end evidence without another production
  abstraction.
- Determinism is demonstrated as equal observations for equal explicit facts,
  not as shared result identity across independent executions.
- Identity lineage remains direct and local to the contracts that own it.
- Caller-owned model side effects before failure are observable and are not
  rolled back.
- Simulation remains separate from Runtime, scheduling, and Device execution.

## Rejected alternatives

### Add a Phase 7 production integration service

Rejected because scenario execution already composes the production path and
TASK-080 only needs validation.

### Add automatic progression between scenario steps

Rejected because TASK-079 freezes next-step input as caller-owned.

### Retry the failed component or continue later steps

Rejected because existing execution contracts are stop-first and propagate
the exact exception.

### Persist traces for validation

Rejected because persistence and history are outside Phase 7.

## Non-goals

- Production code, API, or contract changes.
- Runtime, real-time execution, scheduling, clocks, loops, threads, or queues.
- Device control, Command, Dispatch, PCS/BMS, CAN, Modbus, MQTT, or protocols.
- Optimization, forecasting, EMS algorithms, decisions, or constraints.
- Persistence, history, telemetry, replay, recovery, retry, or rollback.
