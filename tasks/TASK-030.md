# TASK-030 ? DecisionContext Result Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionContextResult` as the immutable output contract returned by
`DecisionContextPolicy`.

TASK-030 introduces a boundary only. It does not define an EMS algorithm,
optimization result, device command, execution event, or runtime integration.

## Architecture

### Legacy path

~~~text
EnergySystemContext
        |
        v
EMSPolicy
        |
        v
DecisionResult
        |
        v
Execution
~~~

### DecisionContext path

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
Future command generation layer
~~~

## Contract

`DecisionContextResult` was introduced by TASK-030 as a frozen, slotted
dataclass. TASK-031 subsequently adds its semantic `DecisionIntent` reference.
It contains no mutable collection, device command, or execution event.

`DecisionContextPolicy.evaluate()` returns `DecisionContextResult`. It remains
a stateless abstract contract and provides no implementation.

## Coexistence

The legacy `kernel.decision.DecisionResult` remains unchanged. It continues to
carry immutable command and event tuples for existing `EMSPolicy`, execution,
cycle, dispatch, and runtime consumers.

`DecisionContextResult` is independent. TASK-030 does not migrate, adapt, or
overload legacy consumers. A future architecture task may define policy output
fields or command generation without changing the ownership of the legacy
execution path.

## Non-goals

- Charging or discharging strategies.
- EMS algorithms, optimization, or forecasting.
- Device commands or execution events.
- Command generation, dispatch, or device control.
- Runtime or legacy execution migration.
- Persistence, telemetry, caches, or history.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
