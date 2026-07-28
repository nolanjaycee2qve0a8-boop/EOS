# TASK-031 ? Decision Intent Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionIntent` as the immutable semantic policy intention between
`DecisionContextResult` and future command generation.

TASK-031 defines policy meaning only. It does not implement an EMS algorithm,
generate a device command, or perform execution.

## Architecture

~~~text
EnergySystemState
        |
        v
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
        |
        v
Device Execution
~~~

`DecisionContextResult` holds the exact `DecisionIntent` object supplied by a
policy implementation. It does not copy, translate, execute, or dispatch the
intent.

## Physical Contract

`battery_power_intent_kw`:

- Unit: kilowatts (kW).
- Sign: positive means charging the battery.
- Sign: negative means discharging the battery.
- Zero: idle battery power intent.
- Valid range: any finite real number.
- Scaling: literal kW with no percentage, per-unit, integer-register, or hidden
  scaling.

The sign convention describes semantic battery intention, not a device
protocol or physical measurement. Future command generation owns any explicit
translation needed by a device-facing contract.

## Immutability

`DecisionIntent` is a frozen, slotted dataclass with one finite numeric field.
It owns no mutable collection, cache, history, or runtime state.

## Legacy Isolation

TASK-031 does not modify `EMSPolicy`, legacy `DecisionResult`, runtime,
execution, cycle, dispatch, or device layers. No compatibility adapter or
migration is introduced.

## Non-goals

- EMS algorithms or charge/discharge strategy selection.
- Optimization, scheduling, or forecasting.
- Device, PCS, CAN, Modbus, or protocol commands.
- Command generation or dispatch.
- Execution events or runtime integration.
- Persistence, telemetry, cache, history, or state retention.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
