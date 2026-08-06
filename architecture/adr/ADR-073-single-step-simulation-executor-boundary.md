# ADR-073 — Execute One Explicit Simulation Step in Caller Binding Order

Status: Accepted

## Context

Phase 6 froze immutable component and aggregate simulation contracts. TASK-075
then introduced explicit caller-owned model bindings without execution
semantics. EOS now needs one minimal coordination boundary that can invoke the
five bound component models once and assemble existing evidence without
becoming a scenario runner or operational Runtime.

Execution requires a complete component set, deterministic ordering, explicit
failure behavior, and preservation of the Phase 6 identity chain.

## Decision

Introduce the stateless, empty-slotted `SingleStepSimulationExecutor` with one
static method:

```python
execute(
    simulation_input: SimulationStepInput,
    bindings: SimulationModelBindingCollection,
) -> SimulationStepResult
```

Before model execution, require exactly one binding for each exact PV, Load,
Tariff, Battery, and Grid model boundary. Matching uses class identity. Missing
or duplicate bindings fail before any model call.

After validation, iterate `bindings.bindings` in exact caller order. Each model
receives its corresponding exact component input and is invoked once. Returned
result types are checked immediately. Any exception stops execution and
propagates unchanged.

The executor constructs existing `SimulationState` and `SimulationStepResult`
artifacts from exact inputs and returned results. It does not introduce another
execution-result model or duplicate existing aggregate validation.

## Consequences

- One explicit step has deterministic, caller-controlled execution order.
- Every required component executes exactly once on success.
- Invalid completeness fails before side effects in caller model objects.
- Failure is simple and observable: stop immediately and preserve the exact
  exception.
- Phase 6 input/result identity checks remain the source of aggregate
  provenance validation.
- The executor stores no models or Runtime state.

## Rejected alternatives

### Fixed internal PV/Load/Tariff/Battery/Grid order

Rejected because TASK-075 explicitly preserves caller order. TASK-076 should
execute that explicit order rather than hide an automatic reorder.

### Execute while validating completeness

Rejected because a missing later binding could otherwise cause partial model
execution before an invalid input set is discovered.

### Registry or model lookup

Rejected because caller-supplied exact bindings already express ownership and
component relationships.

### Scenario loop in the same executor

Rejected because one-step coordination and scenario progression have different
lifecycle and failure semantics.

### Automatic retry or result correction

Rejected because both would introduce hidden policy and duplicate execution.

## Non-goals

- Component physics, state calculation, power balance, forecasting, or
  optimization.
- Scenario runner, loop, step progression, or next-input generation.
- Runtime, Scheduler, clock ownership, retry, timeout, queue, thread, or async.
- Device, Command, Dispatch, PCS/BMS, protocols, persistence, cache, or history.

