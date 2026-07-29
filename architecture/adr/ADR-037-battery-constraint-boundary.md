# ADR-037 - Battery Constraint Boundary

## Status

Accepted

## Context

Phase 1 established `DecisionConstraintBoundary` as the substitutable seam
between semantic `DecisionIntent` and `FeasibleDecisionIntent`. TASK-037 then
introduced the first concrete EMS policy, which intentionally does not enforce
SOC or battery power limits.

Phase 2 now needs its first concrete constraint implementation without leaking
battery-specific facts into the generic boundary or the orchestrator.

## Decision

Introduce `BatteryConstraintImplementation` as a frozen, slotted subclass of
`DecisionConstraintBoundary`.

It keeps the existing general contract:

~~~python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
~~~

The caller supplies `soc`, `reserve_soc`, `max_charge_power_kw`, and
`max_discharge_power_kw` when constructing the implementation. These are
immutable facts for one evaluation context, not mutable runtime ownership.

The implementation blocks charging at full SOC, blocks discharging at or below
reserve SOC, and clips charging or discharging intent to the corresponding
power magnitude.

## Identity Decision

If an intent is already feasible, the returned `FeasibleDecisionIntent`
references the exact source `DecisionIntent`.

If an intent must be blocked or clipped, the implementation creates a new
immutable `DecisionIntent` containing the allowed raw kW value. The source
intent remains unchanged.

## Dependency Direction

~~~text
DecisionIntent
        |
        v
BatteryConstraintImplementation
        |
        v
FeasibleDecisionIntent
~~~

There is no dependency on policy implementations, runtime, execution,
dispatcher, device protocols, persistence, telemetry, optimization, or
forecasting.

## Consequences

- `DecisionConstraintBoundary` remains substitutable.
- `DecisionEvaluationOrchestrator` remains generic and unchanged.
- Battery-specific facts do not leak into the common evaluate signature.
- Policy remains responsible for intention; constraint remains responsible for
  physical permission.
- Original policy intent remains available for audit and explanation.
- Future grid, export-limit, and temperature constraints can use independent
  immutable implementations.

## Rejected Alternatives

- Add SOC and power arguments to `DecisionConstraintBoundary.evaluate`:
  rejected because it would leak battery-specific facts into a generic
  contract and break substitutability.
- Put SOC and power clipping into `SelfConsumptionPolicy`: rejected because
  policy expresses preference while constraints enforce feasibility.
- Modify `DecisionIntent` in place: rejected because domain objects are
  immutable and the original policy evidence must remain observable.
- Store mutable constraint history or runtime cache: rejected because
  constraint evaluation must remain deterministic and independently owned.

## Non-goals

- SOC calculation, prediction, or battery electrochemical modeling.
- Strategy selection, optimization, forecasting, pricing, or scheduling.
- Runtime, dispatch, command generation, persistence, or telemetry.
- PCS, BMS, CAN, Modbus, MQTT, or device control.
