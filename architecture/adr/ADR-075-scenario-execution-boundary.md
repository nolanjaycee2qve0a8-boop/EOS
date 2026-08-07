# ADR-075 — Execute Explicit Scenario Steps Without Progression

Status: Accepted

## Context

TASK-072 introduced `SimulationScenario` as an immutable caller-ordered tuple
of complete step inputs. TASK-076 can execute one explicit step, and TASK-077
can preserve its structurally completed evidence. EOS now needs a minimal
boundary that composes those contracts across an explicit scenario without
becoming a Runtime, Scheduler, progression engine, or scenario generator.

The boundary must preserve caller order and exact object provenance. It must
also make failure behavior explicit and avoid re-executing steps to construct
evidence.

## Decision

Introduce stateless, empty-slotted `ScenarioExecutionBoundary` and frozen,
slotted `ScenarioExecutionResult`.

`execute(scenario, bindings)` traverses the exact `scenario.steps` tuple. For
each step, it calls `SingleStepSimulationExecutor.execute(step, bindings)`
once, then passes the returned exact result to
`SimulationExecutionTrace.create(bindings, step_result)` once. It returns an
immutable tuple of traces in exact scenario order.

`ScenarioExecutionResult` stores exact scenario and binding collection
references. It validates that every scenario step has exactly one trace at the
same index, that every tuple occurrence has a distinct trace artifact, and
that every trace references the exact binding collection. Repeating the same
exact step reference remains a valid caller ordering fact and causes another
explicit execution.

Any exception stops execution and propagates unchanged. No partial result is
returned. An empty scenario returns an empty trace tuple.

## Consequences

- Explicit scenarios can be executed deterministically without hidden step
  generation or ordering.
- The existing single-step executor remains the only owner of component model
  coordination.
- The existing trace remains the only single-step evidence artifact.
- Successful scenario evidence preserves direct identity from scenario step
  to trace and from caller bindings to every trace.
- Failure can leave effects inside caller-owned model implementations for
  already attempted steps; TASK-078 adds no rollback or retry semantics.
- The boundary owns no model, scenario, state, trace history, or Runtime state.

## Rejected alternatives

### Reimplement component execution in the scenario boundary

Rejected because it would duplicate TASK-076 completeness, ordering, type,
and exception contracts.

### Generate each next step from the previous result

Rejected because progression is a separate future boundary. TASK-078 consumes
only explicit caller-supplied steps.

### Sort by sequence or timestamp

Rejected because `SimulationScenario` preserves caller order, including a
deliberately non-chronological order.

### Re-execute a step to build evidence

Rejected because each step must execute once and TASK-077 already constructs
evidence by observation.

### Return partial results after failure

Rejected because TASK-078 defines stop-first propagation, not recovery or
checkpoint semantics.

## Non-goals

- Scenario generation, state progression, scheduling, Runtime, or clock
  ownership.
- Retry, timeout, rollback, recovery, replay, persistence, cache, or history.
- Device, Command, Dispatch, PCS/BMS, protocol, or communication.
- Physics, power balance, SOC calculation, forecasting, optimization, policy,
  or EMS strategy.
