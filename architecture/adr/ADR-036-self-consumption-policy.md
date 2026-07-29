# ADR-036 ? Self Consumption Policy

## Status

Accepted

## Context

EOS now has an abstract policy implementation boundary and immutable decision
input, result, and intent contracts. The first concrete strategy should
demonstrate that a policy can express a useful semantic intention while
remaining independent from constraints, execution, and devices.

## Decision

Introduce `SelfConsumptionPolicy` as a stateless concrete subclass of
`DecisionContextPolicyImplementation`.

For one immutable `DecisionContext`, it compares instantaneous PV generation
and load consumption:

~~~text
PV surplus: battery charging intent = PV power - load power
Load deficit: battery discharging intent = -(load power - PV power)
Balanced: battery intent = 0 kW
~~~

The output uses the existing `DecisionIntent.battery_power_intent_kw` contract:
positive is charging, negative is discharging, and zero is idle.

## Architecture

~~~text
DecisionContext
        |
        v
SelfConsumptionPolicy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
        |
        v
Future Constraint Evaluation
~~~

## Constraint Separation

The policy does not enforce SOC, reserve SOC, battery power limits, export
limits, or device capability. It performs no clipping or saturation. Constraint
evaluation remains the responsibility of `DecisionConstraintBoundary`.

The policy also ignores electricity price and grid exchange because TOU and
grid-control strategies are outside this basic self-consumption decision.

## Identity and Ownership

The policy constructs one `DecisionIntent` and passes that exact reference to
`DecisionContextResult`. It does not copy, reconstruct, or serialize the
intent.

`SelfConsumptionPolicy` has empty slots and owns no runtime, dispatcher,
device, storage, cache, or history.

## Consequences

- EOS gains its first concrete but narrowly scoped EMS strategy.
- PV surplus produces charging intent.
- Load deficit produces discharging intent.
- Physical feasibility remains separate from policy semantics.
- Runtime and device execution remain independent.

## Rejected Alternatives

- Enforce SOC or battery power limits: rejected because constraints own
  feasibility.
- Include electricity price or TOU behavior: rejected because this policy is
  limited to physical self-consumption.
- Generate commands or control PCS/BMS: rejected because policies produce
  semantic intent only.
- Forecast PV or load: rejected because the policy uses the current immutable
  context only.

## Non-goals

- Optimization, forecasting, scheduling, or degradation modeling.
- SOC prediction or battery modeling.
- Runtime, dispatch, command generation, or persistence.
- PCS, BMS, CAN, Modbus, MQTT, or device control.
