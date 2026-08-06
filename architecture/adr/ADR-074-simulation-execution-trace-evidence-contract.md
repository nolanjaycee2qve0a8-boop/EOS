# ADR-074 — Preserve Single-Step Simulation Execution as Immutable Evidence

Status: Accepted

## Context

TASK-076 can execute one explicit simulation step through caller-supplied model
bindings and return an immutable `SimulationStepResult`. Architecture review,
debugging, and future replay-oriented work need a stable observation artifact
that keeps the exact completed relationships visible without invoking the
executor or models again.

The trace must not turn evidence construction into execution, duplicate the
aggregate contracts, or overstate model provenance that current result
artifacts do not encode.

## Decision

Introduce frozen, slotted `SimulationExecutionTrace` with four exact
references:

- `simulation_input`;
- `bindings`;
- `state`;
- `step_result`.

Require identity consistency:

```text
step_result.simulation_input is simulation_input
step_result.state is state
```

Provide `SimulationExecutionTrace.create(bindings, step_result)`, which reads
the exact existing input and state references from the completed result and
constructs the trace. Creation performs no execution, mutation, copy,
serialization, or reconstruction.

The trace is described as structurally completed evidence. It preserves the
exact binding collection associated by the caller but does not independently
prove that those model instances produced the results, because current
component results retain inputs rather than model identities.

## Consequences

- Completed one-step relationships can be observed through one immutable
  artifact.
- Exact aggregate input, state, result, component results, and binding
  collection references remain accessible.
- Trace construction cannot cause duplicate model execution.
- The evidence contract remains honest about what object identity proves.
- Future replay, persistence, or audit behavior requires separate contracts.

## Rejected alternatives

### Call the executor from `create()`

Rejected because evidence creation must observe a completed result, not create
a new execution.

### Rebuild input, state, or component results

Rejected because reconstruction breaks exact provenance.

### Claim the bindings are cryptographic proof of model execution

Rejected because component result contracts do not reference model instances.
TASK-077 records caller-associated binding evidence without inventing a stronger
contract.

### Store only values or serialized snapshots

Rejected because value-only evidence loses identity relationships.

### Add timestamps, UUIDs, logs, or persistence

Rejected because external trace storage and indexing are separate concerns.

## Non-goals

- Executor or model invocation, replay, recovery, retry, or progression.
- Scenario runner, Runtime, Scheduler, Device, Command, Dispatch, or protocol.
- Persistence, telemetry, logging, timestamps, UUIDs, cache, or history.
- Physics, power balance, SOC transition, optimization, forecasting, or EMS
  strategy.
