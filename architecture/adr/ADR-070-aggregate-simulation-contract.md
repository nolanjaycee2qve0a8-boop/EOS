# ADR-070 — Aggregate Simulation Contract

## Status

Accepted

## Context

TASK-065～071 established independent immutable contracts for deterministic
step identity/time, PV, Load, Tariff, Battery actuation/state/model, and Grid.
EOS now needs a stable way to relate these exact component artifacts without
embedding execution or creating a Runtime loop.

Value-only aggregation would allow reconstructed component inputs or results
to appear related even when they did not participate in the same lifecycle.
Automatic ordering or execution would turn an evidence contract into a
Simulator runtime.

## Decision

Add four frozen/slotted contracts in `simulator.aggregate`:

- `SimulationStepInput`;
- `SimulationState`;
- `SimulationStepResult`;
- `SimulationScenario`.

No execution boundary or concrete simulation model is introduced.

## Step input decision

`SimulationStepInput` stores one exact `SimulationStepIdentity` and the exact
PV, Load, Tariff, Battery, and Grid input objects for that step.

Each component input must reference the aggregate step with `is`. Equal but
distinct step objects are rejected.

## State decision

`SimulationState` stores one exact step and the exact five component result
objects associated with that step. It is an immutable aggregate observation,
not mutable Runtime state and not a state-transition engine.

## Result lineage decision

`SimulationStepResult` directly stores the exact aggregate input and state.
In addition to sharing the exact step, every state result must reference the
corresponding exact component input from the aggregate input.

This validation is observation-only. It does not call a component model,
rebuild an artifact, append evidence, or change state.

## Scenario decision

`SimulationScenario` stores a caller-supplied
`tuple[SimulationStepInput, ...]`. It preserves the exact tuple, element
identities, and caller order. Empty tuples are allowed.

The contract deliberately does not sort, deduplicate, infer chronology,
generate steps, or execute them. Scenario is immutable input description, not
Runtime or Scheduler ownership.

## Identity decision

Identity validation uses `is` for every direct lifecycle relationship:

```text
aggregate input -> exact component inputs
aggregate state -> exact component results
step result -> exact aggregate input and state
component result -> corresponding exact component input
scenario -> exact caller tuple and step inputs
```

No copy, reconstruction, serialization, normalization, or hidden lookup is
performed.

## Consequences

- Component contracts can now form consistent one-step evidence.
- Cross-component provenance is explicit and deterministic.
- Scenario ordering remains caller-owned.
- TASK-073 can validate integration without changing component contracts.
- Runtime and Device execution remain outside Simulation.

## Rejected alternatives

### Execute component models while constructing aggregate artifacts

Rejected because constructors validate evidence and must not execute behavior.

### Accept value-equal reconstructed steps or inputs

Rejected because equality does not prove lifecycle provenance.

### Sort or deduplicate scenario steps

Rejected because caller ordering is an explicit input fact.

### Calculate Grid power balance in the aggregate

Rejected because TASK-072 only composes existing observations.

### Store lists or mutable runtime history

Rejected because deterministic scenarios and evidence require immutable tuples.

## Non-goals

- Simulation engine, orchestration, Runtime, loop, scheduler, or progression.
- Power/energy calculation, interpolation, optimization, or forecasting.
- Device, Command, Dispatch, protocol, persistence, telemetry, cache, or history.
