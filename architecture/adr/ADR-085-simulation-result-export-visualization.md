# ADR-085 — Simulation Result Export and Visualization

## Status

Accepted for TASK-088.

## Context

TASK-087 produces a complete immutable 24-hour evidence graph, but engineers need
a stable tabular export, readable curves, and daily energy totals. Export must not
turn observation into another execution path or add infrastructure dependencies.

## Decision

Add an application-level, empty-slotted `SimulationResultExporter`. Its pure
`export()` operation reads one exact `DailySimulationResult` and creates frozen,
slotted output artifacts:

- `DailySimulationExport`;
- `DailyEnergySummary`;
- `SimulationVisualization`.

Each artifact preserves the exact source result reference. CSV rows are emitted in
trace order with a frozen header and ISO 8601 timestamps. Power and SOC use realized
trace values only.

Visualization uses deterministic SVG text rather than a stateful or third-party
plotting dependency. The power graph contains PV, Load, Battery, and Grid series;
the SOC graph contains Battery next-state SOC. Identical result evidence therefore
produces byte-identical SVG content.

Daily energy is integrated from explicit step duration. Battery throughput uses the
absolute realized Battery power. Grid positive power contributes to import; Grid
negative power contributes its magnitude to export.

An explicit `write_files()` operation writes the already-rendered immutable export
to an existing caller-supplied directory using fixed names. It does not create
directories, retain paths globally, or persist runtime history.

## Consequences

- Simulator 1.0 produces `simulation_result.csv`, `power_curve.svg`, and
  `soc_curve.svg` without changing simulation contracts.
- Export is deterministic and independently testable.
- The source result, traces, states, events, and model evidence remain untouched.
- SVG output avoids adding matplotlib or browser dependencies.
- Database, dashboard, cloud, Web API, and monitoring remain outside this boundary.

## Dependency direction

```text
ems_simulator.output
        |
        v
DailySimulationResult and immutable trace evidence
```

Phase 5–7 contracts do not depend on the export layer, and the export layer does not
depend on Runtime, Device, Command, database, network, or external plotting systems.
