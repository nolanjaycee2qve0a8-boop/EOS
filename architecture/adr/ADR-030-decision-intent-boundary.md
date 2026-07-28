# ADR-030 ? Decision Intent Boundary

## Status

Accepted

## Context

TASK-030 separated the new `DecisionContextPolicy` output from the legacy
command-and-event `DecisionResult`. The new path now needs a semantic policy
intention without coupling policy output to device commands or execution.

## Decision

Introduce `DecisionIntent` as a frozen, slotted domain value containing:

~~~python
battery_power_intent_kw: float
~~~

The value is literal, unscaled kW. Positive values mean charging, negative
values mean discharging, and zero means idle. Any finite real value is valid.
Physical limit enforcement is intentionally deferred to a future explicit
boundary.

`DecisionContextResult` contains the exact `DecisionIntent` reference. It does
not transform or execute that intent.

## Architecture

~~~text
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
        |
        v
Future Command Generation
~~~

## Consequences

- Policy intention has an explicit unit, sign, range, and scaling contract.
- Charge, discharge, and idle meaning are represented by one consistent
  numeric value without redundant mode state.
- Policy output remains separate from commands, protocols, dispatch, and
  execution events.
- Future command generation must explicitly translate semantic intent into a
  device-facing contract.

## Rejected Alternatives

- Store device commands in the intent: rejected because commands belong to a
  later generation and execution layer.
- Add a separate charge/discharge enum: rejected because it duplicates the
  sign encoded by battery power and permits inconsistent states.
- Enforce asset power limits: rejected because TASK-031 defines semantics, not
  validation against a particular physical system.
- Add optimization or forecast outputs: rejected because policy algorithms and
  external analytical engines are outside this boundary.

## Non-goals

- Runtime, dispatch, or device integration.
- EMS algorithms, optimization, or forecasting.
- Persistence, telemetry, cache, or history.
- Changes to legacy `EMSPolicy`, `DecisionResult`, or execution flow.
