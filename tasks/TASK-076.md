# TASK-076 — Single-Step Simulation Executor Boundary

Status: IN REVIEW

## Objective

Introduce the first deterministic Phase 7 execution boundary for one explicit
`SimulationStepInput` using caller-supplied `SimulationModelBinding` artifacts.

TASK-076 coordinates existing contracts only. It does not implement component
physics, generate a step, advance a scenario, own Runtime state, or interact
with a Device.

## Architecture

```text
SimulationStepInput
        +
SimulationModelBindingCollection
        |
        v
SingleStepSimulationExecutor
        |
        v
exact component results
        |
        v
SimulationState
        |
        v
SimulationStepResult
```

## Public contract

```python
SingleStepSimulationExecutor.execute(
    simulation_input: SimulationStepInput,
    bindings: SimulationModelBindingCollection,
) -> SimulationStepResult
```

The executor is stateless and empty-slotted. The method is static; it stores no
model, binding, input, state, result, cache, or history.

## Binding completeness

Before executing any model, the executor validates that the collection
contains exactly one binding for each exact component boundary:

- `PVSimulationModelBoundary`;
- `LoadSimulationModelBoundary`;
- `TariffSimulationModelBoundary`;
- `BatterySimulationModelBoundary`;
- `GridSimulationModelBoundary`.

Missing or duplicate component bindings raise `ValueError` before any model is
called. Contract matching uses identity (`is`), not string lookup or equality.

TASK-075 remains unchanged: its collection may represent empty, partial, or
duplicate binding facts. TASK-076 defines the stricter completeness required
only for executable one-step input.

## Execution semantics

- Iterate the exact caller tuple without sorting or reordering.
- Call each bound model exactly once with its corresponding exact component
  input.
- Validate the returned component result type immediately.
- Stop on the first exception and propagate the exact exception unchanged.
- Do not execute later models after a failure.
- Construct `SimulationState` from the exact returned results.
- Return `SimulationStepResult` containing the exact original aggregate input.

Caller order is execution order. The executor does not infer dependencies,
priority, or an alternative order.

## Identity and provenance

The executor preserves the existing Phase 6 chain:

```text
result.simulation_input is original_step_input
result.state.step_identity is original_step_input.step_identity
result.state.<component>_result.simulation_input
    is original_step_input.<component>_input
```

Each exact bound model receives the exact matching component input. There is no
copy, reconstruction, serialization, normalization, or input conversion.

## Dependency direction

```text
simulator.executor
        -> simulator.binding
        -> simulator.aggregate
        -> existing simulator component contracts
```

Existing component, binding, and aggregate contracts do not depend on the
executor. The executor has no dependency on Runtime, Scheduler, Device,
Command, Dispatcher, Optimization, Policy, Capability, persistence, telemetry,
cache, or history.

## Non-goals

- No production PV, Load, Tariff, Battery, or Grid physics.
- No model creation, registry, discovery, selection, or lifecycle ownership.
- No scenario runner, loop, batch, automatic step progression, or next-input
  generation.
- No power-balance, SOC-transition, pricing, forecasting, or optimization.
- No Runtime, Scheduler, clock ownership, thread, queue, async, retry, or
  timeout.
- No Device, Command, Dispatch, PCS, BMS, CAN, Modbus, or MQTT.

## Tests

Focused tests cover:

- exactly-once execution for all five component models;
- exact caller binding order;
- exact component input/result and aggregate provenance;
- missing and duplicate binding rejection before execution;
- invalid input and binding types;
- invalid model result rejection;
- exact exception propagation and stop-on-first-failure behavior;
- empty slots, no instance dictionary, exact method signature, public import,
  and dependency isolation.

## Validation

```text
focused tests: 24 passed
pytest: 1320 passed
ruff check .: passed
ruff format --check .: passed (386 files)
mypy .: passed (237 source files)
pre-commit run --all-files: passed
```
