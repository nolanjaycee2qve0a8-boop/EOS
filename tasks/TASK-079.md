# TASK-079 — Explicit Step Progression Contract

Status: IN REVIEW

## Objective

Define how a caller relates completed simulation evidence to the exact next
`SimulationStepInput` that the caller has already constructed.

Simulation does not own progression. It does not decide the next step,
generate future input, advance time, execute the next step, or manage a
lifecycle.

## Architecture

```text
completed SimulationExecutionTrace
        +
exact previous SimulationStepResult
        +
caller-supplied next SimulationStepInput
        |
        v
SimulationStepProgression
```

The abstract `SimulationStepProgressionBoundary` defines how a future caller
may validate and return this relationship. TASK-079 provides no concrete
progression implementation.

## Immutable relation

```python
@dataclass(frozen=True, slots=True, eq=False)
class SimulationStepProgression:
    previous_trace: SimulationExecutionTrace
    previous_result: SimulationStepResult
    next_input: SimulationStepInput
```

The artifact contains only exact references. Identity-based equality prevents
a reconstructed equal-field progression artifact from substituting for the
original relationship.

## Evidence identity

```text
progression.previous_trace is original_previous_trace
progression.previous_result is original_previous_result
progression.previous_result is progression.previous_trace.step_result
progression.next_input is caller_supplied_next_input
```

A reconstructed value-equal `SimulationStepResult` is rejected because it is
not the exact result stored by the previous trace.

## State transition provenance

The current aggregate contracts expose a state transition for Battery. The
relationship is explicit and identity-based:

```text
previous source state
    = previous_result.simulation_input.battery_input.source_state

previous produced next state
    = previous_result.state.battery_result.next_state

caller next input source state
    = next_input.battery_input.source_state

next_input.battery_input.source_state
    is previous_result.state.battery_result.next_state
```

TASK-079 validates this relationship but does not calculate, copy, mutate, or
advance Battery state. A reconstructed value-equal state is rejected. Other
component inputs remain explicit caller facts because their current contracts
do not define state transitions.

## Time ownership

The next input already contains its exact caller-supplied
`SimulationStepIdentity`, including timestamp and duration. TASK-079 does not:

- call `datetime.now()`, `time.time()`, or a clock;
- increment sequence or timestamp;
- infer duration;
- compare chronological order;
- schedule execution.

Step progression is a provenance relationship, not time scheduling.

## Abstract boundary

```python
class SimulationStepProgressionBoundary(ABC):
    __slots__ = ()

    @abstractmethod
    def relate(
        self,
        previous_trace: SimulationExecutionTrace,
        next_input: SimulationStepInput,
    ) -> SimulationStepProgression: ...
```

The boundary is abstract, stateless, and empty-slotted. It stores no current
step, history, clock, model, execution result, or Runtime state.

## Dependency direction

```text
simulator.progression
        -> simulator.trace
        -> simulator.aggregate
```

Trace, aggregate, executor, scenario, component, Kernel, Runtime, and Device
packages do not depend on the progression contract.

## Non-goals

- No Runtime, Scheduler, clock, loop, thread, queue, timer, async, retry, or
  timeout.
- No scenario runner, scenario execution, automatic progression, future input
  generation, or lifecycle ownership.
- No model execution, replay engine, history storage, persistence, telemetry,
  cache, recovery, or rollback.
- No forecast, optimization, EMS strategy, decision making, or constraint
  evaluation.
- No Command, Device, Dispatch, PCS, BMS, CAN, Modbus, MQTT, or protocol.

## Tests

Focused tests cover:

- exact trace, previous result, next input, previous state, and produced next
  state identities;
- reconstructed previous result and reconstructed state rejection;
- invalid type rejection;
- frozen/slotted identity-based artifact with no `__dict__`;
- abstract, stateless, empty-slotted boundary contract;
- absence of clock, Runtime, execution, Device, Command, persistence, cache,
  and history dependencies;
- public imports.

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

- focused tests: 23 passed;
- full pytest: 1360 passed;
- Ruff check: passed;
- Ruff format check: passed;
- mypy: passed;
- pre-commit: passed.
