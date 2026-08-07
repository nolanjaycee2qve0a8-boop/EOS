# TASK-078 — Scenario Execution Boundary

Status: IN REVIEW

## Objective

Introduce a stateless deterministic boundary that executes every explicit
`SimulationStepInput` in an existing `SimulationScenario` through the existing
single-step executor and returns immutable scenario evidence.

TASK-078 coordinates existing steps only. It does not generate, advance,
derive, normalize, or mutate a simulation step.

## Architecture

```text
SimulationScenario
        +
SimulationModelBindingCollection
        |
        v
ScenarioExecutionBoundary
        |
        v
SingleStepSimulationExecutor (once per explicit step)
        |
        v
SimulationExecutionTrace (one per completed step)
        |
        v
ScenarioExecutionResult
```

## Public contracts

```python
ScenarioExecutionBoundary.execute(
    scenario: SimulationScenario,
    bindings: SimulationModelBindingCollection,
) -> ScenarioExecutionResult
```

```python
@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    scenario: SimulationScenario
    bindings: SimulationModelBindingCollection
    traces: tuple[SimulationExecutionTrace, ...]
```

The boundary is empty-slotted and stateless. The result is frozen, slotted,
and tuple-only.

## Execution semantics

- Validate `scenario` and `bindings` before iteration.
- Iterate `scenario.steps` in exact caller order.
- Do not sort, deduplicate, normalize, or infer dependencies.
- Invoke `SingleStepSimulationExecutor.execute()` exactly once per explicit
  step on the successful path.
- Create exactly one `SimulationExecutionTrace` from each completed exact step
  result.
- Stop at the first exception and propagate the same exception unchanged.
- Return no partial `ScenarioExecutionResult` after failure.
- An empty scenario returns an empty trace tuple without model execution.

The boundary does not perform step progression. Every step, including its
source state and actuation, is already an explicit caller-owned input.

## Identity and provenance

```text
result.scenario is original_scenario
result.bindings is original_bindings
result.traces[index].simulation_input is original_scenario.steps[index]
result.traces[index].bindings is original_bindings
```

`ScenarioExecutionResult` validates complete, ordered, exactly-once coverage:
its trace count must equal its scenario step count, and each trace must refer
to the exact step at the same caller-owned index. Every tuple occurrence has a
distinct trace artifact, even when the caller repeats the same exact step
reference. Reordered, missing, extra, duplicate-trace, or differently bound
evidence is rejected.

The trace tuple is newly assembled output evidence. The scenario, binding
collection, steps, bindings, inputs, states, component results, and step
results are not copied, reconstructed, serialized, or normalized.

## Dependency direction

```text
simulator.scenario_execution
        -> simulator.executor
        -> simulator.trace
        -> simulator.aggregate + simulator.binding
```

Existing component, aggregate, binding, executor, and trace contracts do not
depend on scenario execution.

## Non-goals

- No scenario generation, next-step generation, state progression, or
  automatic propagation of one result into another input.
- No Runtime, Scheduler, clock ownership, timer, loop ownership, thread,
  queue, async, retry, timeout, cache, or history.
- No Device, Command, Dispatch, PCS/BMS, CAN, Modbus, MQTT, or protocol.
- No persistence, telemetry, replay engine, recovery, or rollback.
- No production physics, power balance, SOC calculation, forecasting,
  optimization, EMS policy, or business strategy.

## Tests

Focused tests cover:

- caller step order and caller binding order;
- exactly-once component execution per successful step;
- exact scenario, bindings, step, component input/result, state, and trace
  provenance;
- empty scenario behavior;
- stop-first exact exception propagation;
- complete ordered trace coverage validation;
- repeated step occurrences with distinct trace artifacts;
- frozen/slotted tuple-only result and stateless boundary;
- invalid type rejection, public imports, and dependency isolation.

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

- focused tests: 26 passed;
- full pytest: 1349 passed;
- Ruff check: passed;
- Ruff format check: passed;
- mypy: passed;
- pre-commit: passed.
