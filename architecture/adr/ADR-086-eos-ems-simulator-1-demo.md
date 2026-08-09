# ADR-086 — EOS EMS Simulator 1.0 Demo

## Status

Accepted for TASK-089.

## Context

TASK-082～088 provide all component facts, deterministic physical models, daily execution,
trace evidence, CSV export, SVG visualization, and summary calculations. A single runnable
application entry point is needed to prove the pieces form a usable Simulator 1.0 Demo.

## Decision

Add `ems_simulator.demo` as an application composition module. It owns only explicit Demo
facts and orchestration:

1. create fixed caller-supplied hourly identities and profiles;
2. create immutable Battery parameters and initial SOC;
3. call the existing `DailySimulationRunner` once;
4. call the existing `SimulationResultExporter` once;
5. write existing export artifacts plus a deterministic text summary.

The public CLI is:

```text
python -m ems_simulator.demo --output-dir <directory>
```

`DemoExecutionResult` is frozen and slotted. It validates exact provenance:

- `simulation_result.source_input is source_input`;
- `export.source_result is simulation_result`.

The output directory is explicit caller input. The Demo may create that directory for ease of
use, but it does not retain the path globally or introduce Runtime persistence.

## Strategy boundary

The Demo reuses the existing simple self-consumption rule solely to validate the simulator.
Battery physical limits and SOC protection remain in `SimpleBatteryPhysicsModel`; Grid balance
remains `Load + Battery - PV`. No new strategy, optimizer, forecast, or constraint contract is
introduced.

## Consequences

- A user can produce all Simulator 1.0 outputs with one command.
- The example is deterministic and covered by end-to-end integration tests.
- Phase 5～8 contracts and implementations remain unchanged.
- The Demo is educational/application evidence, not Runtime or production device control.

## Rejected alternatives

- Adding an interactive dashboard or Web API.
- Reading profiles from cloud services or device telemetry.
- Introducing Runtime, Scheduler, background loops, or clock ownership.
- Adding MPC, Optimization, AI, Forecast, PCS/BMS, Device, or Command behavior.
