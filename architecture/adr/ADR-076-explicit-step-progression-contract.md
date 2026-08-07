# ADR-076 — Keep Simulation Step Progression Caller-Owned and Explicit

Status: Accepted

## Context

TASK-078 can execute a caller-defined `SimulationScenario`, but scenario order
does not explain how a future caller constructed the next step or connected
state provenance between steps. Embedding this work in simulation execution
would make Simulation own time, future inputs, and lifecycle progression,
turning it into a Runtime.

EOS needs a minimal immutable relationship that can prove which completed
result precedes which caller-supplied next input without generating or
executing that input.

## Decision

Introduce identity-based frozen/slotted `SimulationStepProgression` containing
the exact previous trace, its exact step result, and the exact caller-supplied
next input.

Validate:

```text
previous_result is previous_trace.step_result
next_input.battery_input.source_state
    is previous_result.state.battery_result.next_state
```

The first rule rejects a reconstructed value-equal previous result. The second
preserves the Battery state transition already exposed by the model result and
rejects reconstructed value-equal state. The relation does not calculate or
mutate either state.

Introduce abstract, stateless, empty-slotted
`SimulationStepProgressionBoundary.relate(previous_trace, next_input)`. No
concrete implementation is added in TASK-079.

The caller owns the next input and its time facts. The contract does not read a
clock, increment time or sequence, compare chronology, or invoke simulation.

## Consequences

- Previous evidence and caller next input provenance are explicit.
- Battery state transition identity can be audited without hidden mutation.
- A caller may choose any explicit next step identity and other component
  facts; TASK-079 adds no ordering or scheduling policy.
- Simulation remains separate from Runtime and lifecycle ownership.
- Future concrete progression validation can implement the abstract contract
  without changing existing execution or scenario contracts.

## Rejected alternatives

### Add `source_result` to `SimulationStepInput`

Rejected because it would modify the frozen Phase 6 aggregate contract and
force every standalone input to participate in progression.

### Generate the next input from the previous result

Rejected because Simulation must not decide future facts or own progression.

### Advance sequence or timestamp automatically

Rejected because time and step identity remain caller-owned immutable facts.

### Accept a value-equal reconstructed result or state

Rejected because value equality does not preserve provenance.

### Put progression inside scenario execution

Rejected because scenario ordering and step generation are separate concerns.

## Non-goals

- Runtime, Scheduler, clock, loop, thread, queue, retry, timeout, or lifecycle
  ownership.
- Scenario execution, automatic progression, step generation, model execution,
  or replay.
- History, persistence, telemetry, cache, recovery, or rollback.
- Forecasting, optimization, EMS strategy, decision making, or constraint
  evaluation.
- Device, Command, Dispatch, PCS/BMS, CAN, Modbus, MQTT, or communication.
