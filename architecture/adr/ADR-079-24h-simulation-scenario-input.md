# ADR-079: 24-Hour Simulation Scenario Input

## Status

Accepted

## Context

Phase 7 froze deterministic execution contracts, but EOS did not yet provide an
application input that a user can populate with one day of PV, load, tariff,
and battery facts. The first runnable EMS demo ultimately needs those facts
before concrete models, strategy, state progression, reporting, and plotting can
be introduced.

The existing Phase 6 `SimulationScenario` is intentionally an aggregate of
complete `SimulationStepInput` objects. Constructing it at data-ingestion time
would require inventing future Battery actuation, Battery source-state
progression, and Grid request facts. That would hide decision and physics logic
inside an input contract.

## Decision

Add a separate application package, `ems_simulator`, with:

- immutable `BatteryParameters`;
- immutable `DailySimulationScenarioInput`.

The daily input preserves exact caller-supplied 24-value tuples and explicit
hourly `SimulationStepIdentity` objects. It validates units, ranges, duration,
sequence, and timestamp continuity without copying, sorting, normalizing, or
generating any value.

The input remains distinct from the executable Phase 6 `SimulationScenario`.
A later application runner may assemble complete Phase 6 step inputs as each
explicit step becomes executable, while reusing the frozen Phase 5–7 contracts.

## Consequences

- The demo has one deterministic, unit-explicit source of 24-hour facts.
- Caller order, time ownership, and referenced object identities remain visible.
- Strategy, battery physics, grid balance, and execution cannot leak into data
  ingestion.
- The application layer can evolve without changing frozen simulator contracts.
- A later runner must explicitly bridge daily facts to complete Phase 6 inputs;
  TASK-082 does not provide that bridge.

## Rejected alternatives

### Preconstruct 24 complete SimulationStepInput objects

Rejected because future battery actuation and state progression do not yet
exist and must not be fabricated by an input boundary.

### Store mutable lists or dictionaries

Rejected because mutation would make a simulation input nondeterministic and
would weaken provenance.

### Generate timestamps or infer default battery facts

Rejected because time and physical parameters are caller-owned facts. Hidden
defaults would make units and scenario meaning ambiguous.

### Implement the runner, strategy, or physics in this task

Rejected because TASK-082 is data input only and the requested development
sequence introduces those capabilities separately.
