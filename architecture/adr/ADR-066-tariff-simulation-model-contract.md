# ADR-066 — Tariff Simulation Model Contract

## Status

Accepted

## Context

Phase 6 has explicit step identity/time plus PV and Load component contracts.
It next needs an independent Tariff component seam before aggregate simulation
contracts are introduced.

Tariff observation is not TOU decision logic. Reading a system clock, choosing
a pricing window, querying a cloud service, forecasting a price, or deciding
whether to charge would mix time, Capability, strategy, and infrastructure
responsibilities into the simulation boundary.

## Decision

Add three public contracts in `simulator.tariff`:

- frozen/slotted `TariffSimulationInput`;
- frozen/slotted `TariffSimulationResult`;
- abstract, stateless, empty-slotted `TariffSimulationModelBoundary`.

No concrete production model is introduced.

## Time decision

Tariff input requires a `SimulationStepIdentity` with an explicit
timezone-aware timestamp. The boundary preserves the exact step object and does
not read a clock, generate time, or convert timezone.

## Price decision

Import and export prices use signed finite raw CNY per kWh values. Negative
prices are valid. Boolean and non-finite values are invalid.

Input prices are explicit caller facts. Result prices are explicit simulated
observations. The abstract contract does not define how a future implementation
relates them and contains no lookup, TOU selection, prediction, scaling, or
currency conversion.

## Identity decision

```text
input.step_identity is original_step_identity
result.simulation_input is original_input
```

There is no copy, reconstruction, serialization, or hidden source lookup.

## Boundary decision

The model boundary defines only:

```text
simulate(TariffSimulationInput) -> TariffSimulationResult
```

It owns no clock, schedule, price service, Capability, policy, Runtime,
Device, Command, cache, or history.

## Consequences

- Phase 6 gains explicit tariff units, time semantics, and provenance.
- Future tariff implementations can remain replaceable.
- Negative-price scenarios can be represented without contract migration.
- TOU strategy, prediction, Runtime, and external services remain outside the
  component boundary.

## Rejected alternatives

### Read the current time in the model boundary

Rejected because Simulation time is caller evidence.

### Encode TOU windows now

Rejected because TASK-068 is contract-only and TOU selection is separate logic.

### Fetch prices from an API

Rejected because Simulation does not own infrastructure or external services.

### Reject negative prices

Rejected because signed energy prices are valid domain facts.

### Return unlabelled numeric values

Rejected because units, direction, and provenance would be ambiguous.

## Non-goals

- TOU, scheduling, arbitrage, billing, forecast, or optimization.
- Runtime, Device, Command, Dispatch, APIs, telemetry, or persistence.
- Aggregate simulation contracts, cache, or history.
