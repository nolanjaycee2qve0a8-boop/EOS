# ADR-063 — Simulation Core Identity and Time Contracts

## Status

Accepted

## Context

Phase 6 needs deterministic simulation inputs before any PV, Load, Tariff,
Battery, Grid, aggregate state, or step composition contract can be introduced.
Simulation must not read the current time, generate an identifier, own a clock,
or become Runtime.

Defining aggregate contracts first would require component types that do not
yet exist. TASK-065 therefore establishes only the common identity and time
facts required by later component boundaries.

## Decision

Add a public frozen/slotted `SimulationStepIdentity` in the existing top-level
`simulator` package.

It stores exactly:

- a non-negative integer `sequence`;
- a positive finite raw `duration_seconds`;
- an explicit timezone-aware `timestamp` or explicit `None`.

No default timestamp is provided. Every caller must explicitly supply a
timezone-aware value or explicitly state that absolute time is absent.

## Identity decision

Validation returns the exact timezone-aware datetime supplied by the caller:

```text
step.timestamp is original_timestamp
```

There is no copy, timezone conversion, serialization, timestamp generation, or
normalization of datetime identity.

## Time decision

Duration uses seconds as a raw unit and is normalized to a finite `float` only.
No milliseconds, minutes, interval inference, or hidden scaling is supported.

Sequence is zero-based and non-negative. It is explicit caller evidence, not a
counter owned by Simulator.

## Isolation decision

TASK-065 adds no component model, aggregate state, scenario, model execution,
loop, Runtime, Device, Command, Optimization, persistence, cache, or history.

The simulation core depends only on the Python standard library and focused
local validation. No existing package depends on Simulator.

## Consequences

- Later component contracts share one explicit step identity and time language.
- Tests can construct deterministic steps without patching a clock.
- Timezone meaning and duration units are unambiguous.
- Component and aggregate contracts remain free to evolve in their scheduled
  TASKs without changing TASK-065.

## Rejected alternatives

### Read the current time during construction

Rejected because construction would become nondeterministic and clock-owning.

### Generate a UUID for every step

Rejected because identity must be caller supplied and replayable.

### Store duration in an ambiguous generic field

Rejected because numeric fields require explicit units and scaling.

### Add component or aggregate state now

Rejected because TASK-066 through TASK-072 own those contracts.

## Non-goals

- PV, Load, Tariff, Battery, or Grid modeling.
- Aggregate simulation state, scenario, input, result, or composition.
- Runtime, Device execution, Command, Dispatch, or protocols.
- Optimization, forecasting, persistence, telemetry, cache, or history.
