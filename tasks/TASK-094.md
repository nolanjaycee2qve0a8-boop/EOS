# TASK-094 — EMS Feasible Decision to Simulator Actuation Handoff Contract

## Objective

Create the explicit adapter boundary between an approved Phase 9 EMS decision and the
existing Phase 6 Simulator actuation contract. No physical behavior is implemented.

## Architecture

```text
EMSDecision
      |
      v
FeasibilityBoundary
      |
      v
FeasibleDecision
      |
      v
ActuationHandoffBoundary
      |
      v
ActuationHandoffResult
      |
      +-- exact Phase 9 FeasibleDecision
      |
      +-- exact existing BatterySimulationActuation
      |
      v
Existing Simulator
```

## Adapter result

`ActuationHandoffResult` is frozen and slotted. It preserves:

- `source_feasible_decision is original_feasible_decision`;
- `actuation is original_actuation`.

The wrapper is necessary because the frozen Phase 6
`BatterySimulationActuation.source_feasible_decision` contract references the earlier
`kernel.decision.FeasibleDecisionIntent` type. TASK-094 does not modify or reinterpret
that contract. Cross-layer Phase 9 provenance is explicit in the adapter result.

## Direction mapping contract

The adapter validates raw signed Simulator Battery power:

- `charge` maps approved magnitude to positive kW;
- `discharge` maps approved magnitude to negative kW;
- `idle` maps to zero kW.

This is a semantic handoff only. It performs no Battery physics, SOC transition,
constraint calculation, clipping, Simulator execution, PCS control, or Command
generation.

## Boundary behavior

`ActuationHandoffBoundary` is abstract, stateless, and empty-slotted. Its public
`handoff(feasible_decision)` method validates the exact result lineage using `is`.
Implementations provide `_handoff()` and cannot substitute a reconstructed value-equal
source artifact.

## Non-goals

- no modification to `BatterySimulationActuation`;
- no modification to Phase 5–8 contracts or Simulator models;
- no Battery physics, SOC calculation, or Constraint algorithm;
- no Simulator execution, Runtime, Device, PCS, or Command integration;
- no EMS Strategy, TOU, Zero Export, MPC, or Optimization logic.

## Validation

- abstract/stateless boundary contract;
- frozen/slotted adapter result;
- exact feasible-decision and actuation identities;
- reconstructed source rejection by identity;
- charge/discharge/idle signed-power mapping;
- dependency isolation, full pytest, Ruff, mypy, and diff validation.
