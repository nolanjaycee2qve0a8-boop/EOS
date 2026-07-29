# TASK-036 ? EMS Policy Implementation Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionContextPolicyImplementation` as the abstract extension seam
through which future concrete EMS decision policies plug into
`DecisionContextPolicy`.

This task defines implementation structure only. It does not provide a real
EMS strategy.

## Architecture

~~~text
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextPolicyImplementation
        |
        v
Future Concrete Policy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
~~~

The implementation boundary inherits the existing contract:

~~~python
evaluate(
    context: DecisionContext,
) -> DecisionContextResult
~~~

Concrete subclasses must implement that method. The boundary itself contains
no evaluation behavior.

## Identity Preservation

A concrete implementation returns its exact `DecisionContextResult`; the
boundary does not copy, wrap, reconstruct, serialize, or normalize the result
or its `DecisionIntent`.

The downstream identity contract remains:

~~~python
returned_result is concrete_policy_result
returned_result.intent is original_intent
~~~

## Ownership and Isolation

`DecisionContextPolicyImplementation` has empty slots and no instance state. It
owns no runtime, dispatcher, device, command executor, storage, cache, or
history.

The legacy `EMSPolicy` remains a separate, unchanged contract.

## Non-goals

- Real EMS algorithms or strategy selection.
- SOC calculation or SOC control.
- TOU, PV, battery, charging, or discharging strategies.
- Optimization or forecasting.
- Commands, dispatch, runtime, or device control.
- PCS, BMS, CAN, Modbus, MQTT, or other adapters.
- Persistence, telemetry, cache, or history.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
