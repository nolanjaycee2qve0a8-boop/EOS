# ADR-026 — Energy System State Boundary

## Status

Accepted

## Context

Future EMS decisions require one physical system observation containing battery,
PCS, photovoltaic, and grid facts. These facts must be explicit before
`DecisionContext` assembly or policy evaluation.

TASK-007 already defines asset-scoped observations in `kernel.state`. Replacing
those models would break their established asset identity contract.

## Decision

Introduce `kernel.system_state` as a separate physical system snapshot package.
It exposes frozen, slotted `BatteryState`, `PCSState`, `PVState`, `GridState`,
and `EnergySystemState` models.

Component models contain only finite factual scalar values with explicit units,
ranges, and sign conventions. PCS operating and fault states are non-empty
string observations; no enum or state machine is introduced.

`EnergySystemState` exposes the fields `battery`, `pcs`, `pv`, and `grid`, and
stores the exact four component objects received from its caller. Construction
performs type validation but no copy, reconstruction, serialization,
calculation, or state transition. No compatibility aliases are provided.

## Architecture Position

~~~text
Physical system
        |
        v
EnergySystemState
        |
        v
DecisionContext
        |
        v
Future EMS Policy
        |
        v
DecisionResult
~~~

TASK-027 defines the physical state layer only. State-to-context assembly
remains a future boundary.

## Consequences

- Physical system facts have a stable immutable contract.
- Exact component object identity is preserved by the aggregate.
- Units, ranges, and power sign conventions are explicit.
- Existing TASK-007 state models remain unchanged.
- Runtime, policy, optimization, dispatch, persistence, and telemetry remain
  outside this package.

## Rejected Alternatives

- Rewrite `kernel.state`: rejected because it would break TASK-007 contracts.
- Add control methods: rejected because state records facts only.
- Add enums or state machines: rejected because device semantics are outside
  this boundary.
- Assemble `DecisionContext` now: rejected because integration is outside
  TASK-027.
