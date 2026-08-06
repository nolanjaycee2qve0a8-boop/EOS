# TASK-077 — Simulation Execution Trace / Evidence Contract

Status: IN REVIEW

## Objective

Introduce an immutable observation boundary for one structurally completed
single-step simulation execution.

TASK-077 records exact existing artifacts only. It does not execute a model,
call `SingleStepSimulationExecutor`, reconstruct evidence, or claim behavior
that cannot be proven from the supplied object relationships.

## Architecture

```text
SimulationModelBindingCollection
        +
completed SimulationStepResult
        |
        v
SimulationExecutionTrace
        |- exact SimulationStepInput
        |- exact binding collection
        |- exact SimulationState
        |- exact SimulationStepResult
```

## Contract

`SimulationExecutionTrace` is a frozen, slotted dataclass containing exactly:

- `simulation_input: SimulationStepInput`;
- `bindings: SimulationModelBindingCollection`;
- `state: SimulationState`;
- `step_result: SimulationStepResult`.

It validates:

```text
trace.step_result.simulation_input is trace.simulation_input
trace.step_result.state is trace.state
```

All four fields preserve the exact caller references. There is no copy,
deepcopy, reconstruction, serialization, normalization, or new component
result creation.

## Creation boundary

```python
SimulationExecutionTrace.create(
    bindings: SimulationModelBindingCollection,
    step_result: SimulationStepResult,
) -> SimulationExecutionTrace
```

`create()` derives only direct references already held by the completed step
result:

```text
trace.bindings is original_bindings
trace.step_result is original_step_result
trace.simulation_input is original_step_result.simulation_input
trace.state is original_step_result.state
```

It does not call the executor or a model and does not validate by re-execution.

## Evidence semantics

The trace proves a structurally consistent association among the supplied
binding collection and a completed step result. The existing aggregate
contracts prove exact input/result/state lineage inside the step result.

The current artifacts do not embed model identities in component results.
Therefore TASK-077 does not overclaim that it can independently prove which
model instance produced a result. It preserves the exact caller-supplied
binding collection as associated evidence; behavioral proof remains with the
execution boundary and tests.

## Immutability and ownership

- The trace is frozen and slotted.
- It contains no list, dict, set, cache, history, or mutable default.
- It stores references only and never mutates a binding or model.
- Caller-supplied model instances remain caller owned; trace creation does not
  inspect, execute, copy, or manage their internal state.
- Different completed steps produce independent trace artifacts.

## Dependency direction

```text
simulator.trace
        -> simulator.aggregate
        -> simulator.binding
```

The trace does not depend on `simulator.executor`. Executor, aggregate,
binding, and component packages do not depend on the trace.

There is no dependency on Runtime, Scheduler, Device, Command, Dispatcher,
Optimization, Policy, Capability, persistence, telemetry, cache, or history.

## Non-goals

- No model or executor invocation.
- No binding completeness validation or execution reconstruction.
- No scenario runner, loop, step progression, recovery, replay, or retry.
- No timestamps, UUID generation, logging framework, database, persistence,
  cache, or history.
- No Runtime, Scheduler, Device, Command, Dispatch, PCS/BMS, or protocol.
- No physics, power balance, SOC transition, forecasting, optimization, or EMS
  strategy.

## Tests

Focused tests cover:

- exact binding/input/state/result identities;
- exact component result identities through the existing state;
- mismatched input and state identity rejection;
- invalid type rejection;
- frozen/slotted field completeness and absence of `__dict__`;
- independent trace artifacts;
- observation-only creation with model implementations that fail if called;
- dependency isolation and public import.

## Validation

Run:

```text
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
```

Results:

- focused tests: 24 passed;
- full pytest: 1334 passed;
- Ruff check: passed;
- Ruff format check: passed;
- mypy: passed;
- pre-commit: passed.
