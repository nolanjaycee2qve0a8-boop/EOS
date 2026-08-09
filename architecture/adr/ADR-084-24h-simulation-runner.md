# ADR-084 — 24h Simulation Runner

## Status

Accepted for TASK-087.

## Context

TASK-082 supplies an explicit immutable 24-hour input. TASK-083 through TASK-086
provide deterministic PV, Load, Battery, and Grid application models. Phase 7
already freezes binding, single-step execution, trace, scenario, and progression
contracts. The application now needs a first end-to-end runner without turning
simulation into Runtime ownership.

The Grid model depends on realized same-step PV, Load, and Battery results, while
the frozen Phase 7 executor receives all model bindings before execution. The
runner must bridge this dependency without changing the executor or recomputing
component physics.

## Decision

Add an empty-slotted `DailySimulationRunner` and frozen/slotted
`DailySimulationResult` in the application-level `ems_simulator` package.

For each exact caller step, the runner:

1. creates component inputs using the exact step identity;
2. creates a simple self-consumption Battery request;
3. evaluates PV, Load, Tariff, and Battery once;
4. constructs the TASK-086 Grid model from those exact realized results;
5. binds frozen exact-result adapters plus the Grid model;
6. calls `SingleStepSimulationExecutor.execute()` exactly once;
7. creates one exact `SimulationExecutionTrace`;
8. passes the exact Battery next state into the next step source state.

The exact-result adapters are immutable coordination artifacts. They do not copy,
rebuild, normalize, or recalculate component evidence. This keeps the existing
executor completeness and trace contracts intact while allowing Grid to consume
realized component evidence.

The runner constructs `SimulationStepProgression` artifacts between adjacent
steps. It does not generate timestamps or step identities; all time facts remain
caller supplied through `DailySimulationScenarioInput`.

## Physical conventions

- Battery power greater than zero means charging.
- Battery power less than zero means discharging.
- Grid power greater than zero means import.
- Grid power less than zero means export.
- Grid balance is `Load + Battery - PV`.

## Consequences

- EOS can execute a deterministic 24-hour application demo and retain complete
  step evidence.
- Battery state continuity is identity-based, not value-only.
- Phase 5–7 contracts remain unchanged.
- The demo rule is intentionally simple and is not an optimization architecture.
- CSV export, plotting, and daily energy summaries remain future application work.

## Rejected alternatives

- Modifying the Phase 7 executor to understand Grid dependencies.
- Computing Grid from requested rather than realized Battery power.
- Storing current SOC or traces on the runner.
- Introducing Runtime, Scheduler, clock reads, retries, persistence, or devices.
