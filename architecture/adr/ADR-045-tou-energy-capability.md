# ADR-045 - TOU Energy Capability

## Status

Accepted

## Context

TASK-045 introduced `EMSCapabilityBoundary` as the Phase 3 extension point from
immutable `DecisionContext` facts to semantic `DecisionIntent`.

EOS now needs its first concrete capability to prove that a business objective
can evolve in the top-level capability package without modifying Kernel,
Constraint, Evaluation, Runtime, or Device architecture.

Time-of-use energy behavior is suitable for this proof because
`DecisionContext` already contains a timezone-aware timestamp and an explicit
electricity price in CNY per kWh. The rule must remain explicit and
deterministic rather than becoming a scheduler, forecast, or optimization
engine.

## Decision

Introduce immutable caller facts:

~~~python
@dataclass(frozen=True, slots=True)
class TOUCapabilityParameters:
    charge_hours: tuple[int, ...]
    discharge_hours: tuple[int, ...]
    charge_price_ceiling_cny_per_kwh: float
    discharge_price_floor_cny_per_kwh: float
    charge_power_intent_kw: float
    discharge_power_intent_kw: float
~~~

Introduce the concrete capability:

~~~python
@dataclass(frozen=True, slots=True)
class TOUEnergyCapability(EMSCapabilityBoundary):
    parameters: TOUCapabilityParameters

    def evaluate(
        self,
        context: DecisionContext,
    ) -> DecisionIntent: ...
~~~

## Architecture

~~~text
DecisionContext
        |
        v
TOUEnergyCapability
        |
        v
DecisionIntent
        |
        v
existing physical Constraint boundaries
~~~

Capability expresses intent. Constraint remains the owner of feasibility.
Evaluation remains the owner of decision-flow coordination.

## Deterministic Rule

The capability reads:

- `context.timestamp.hour`;
- `context.electricity_price_cny_per_kwh`; and
- its exact immutable `TOUCapabilityParameters`.

It returns:

- positive charge intent when the hour is in `charge_hours` and price is at or
  below the charge ceiling;
- negative discharge intent when the hour is in `discharge_hours` and price is
  at or above the discharge floor; or
- zero intent otherwise.

Threshold comparisons are inclusive.

## Physical Contracts

Hours:

- integers from 0 through 23;
- interpreted in the timezone carried by `DecisionContext.timestamp`;
- stored in caller-supplied tuples;
- unique within each tuple; and
- disjoint between charge and discharge tuples.

Prices:

- literal, unscaled CNY per kWh;
- finite and signed;
- supplied by caller without lookup or conversion.

Intent powers:

- literal, unscaled non-negative kW magnitudes;
- positive output for charging;
- negative output for discharging;
- zero output for idle;
- semantic targets rather than battery or PCS capability.

## Ownership and Immutability

Parameters and capability are frozen and slotted. The capability preserves the
exact parameter identity and stores no other object.

Evaluation owns no:

- cache or history;
- mutable runtime state;
- clock or scheduler;
- tariff database;
- forecast or optimizer;
- Constraint, Integration, Runtime, Dispatcher, or Device instance.

The context is read only and is neither copied nor retained.

## Dependency Direction

Allowed:

~~~text
TOUEnergyCapability -> EMSCapabilityBoundary
TOUEnergyCapability -> DecisionContext
TOUEnergyCapability -> DecisionIntent
~~~

Forbidden:

~~~text
TOUEnergyCapability -> Constraint implementation
TOUEnergyCapability -> Evaluation Integration
TOUEnergyCapability -> Runtime / Execution / Dispatch
TOUEnergyCapability -> PCS / BMS / Device protocol
Kernel -> TOUEnergyCapability
~~~

## Existing Contract Stability

The following remain unchanged:

- `EMSCapabilityBoundary`;
- `DecisionIntent`;
- Policy contracts;
- Constraint contracts and implementations;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationIntegration`;
- `DecisionEvaluationCycle`;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- EOS has its first concrete Phase 3 capability.
- Time, price, and intent facts have explicit units and validation.
- TOU intent remains independently testable without devices or Runtime.
- All TOU outputs still require physical Constraint evaluation.
- Richer tariffs, minute-level periods, forecasts, and optimization remain
  future explicit architecture decisions.

## Rejected Alternatives

- Put TOU logic in Policy: rejected because Phase 3 capabilities must evolve
  through the dedicated boundary without changing Policy contracts.
- Put TOU logic in Constraint: rejected because price preference is a business
  objective, not physical feasibility.
- Pass tariff facts to `evaluate()`: rejected because it would change the
  stable `EMSCapabilityBoundary.evaluate(context)` signature.
- Read a tariff database or system clock: rejected because inputs must be
  explicit and deterministic.
- Enforce SOC or power limits in TOU: rejected because Constraint owns physical
  feasibility.
- Use an optimizer: rejected because TASK-046 defines one explicit rule only.

## Non-goals

- Tariff service, calendar, timezone conversion, or scheduling.
- Optimization, MPC, forecast, or dynamic pricing.
- SOC, battery, grid, PCS, or BMS constraints.
- Runtime, dispatch, commands, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.
