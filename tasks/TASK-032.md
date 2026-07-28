# TASK-032 ? Decision Constraint Boundary

## Status

IN REVIEW

## Objective

Introduce a pure architectural seam for evaluating immutable
`DecisionIntent` values before future executable decision generation.

TASK-032 defines the boundary and its immutable successful result only. It does
not implement a constraint algorithm, EMS strategy, device command, or runtime
integration.

## Architecture

~~~text
DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
Future Executable Decision Generation
~~~

## Contracts

`DecisionConstraintBoundary` is an abstract, stateless interface:

~~~python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
~~~

It owns no state and defines no constraint calculation.

`FeasibleDecisionIntent` is a frozen, slotted dataclass containing exactly one
field:

~~~python
intent: DecisionIntent
~~~

The wrapper preserves the exact original intent identity. It does not copy,
reconstruct, serialize, normalize, clip, or mutate the intent.

No new numeric field is introduced. The existing
`DecisionIntent.battery_power_intent_kw` contract remains literal, unscaled kW:
positive means charging, negative means discharging, and zero means idle.

## Deliberately Undefined Semantics

TASK-032 does not specify the constraints an implementation evaluates, the
source of those constraints, or how infeasibility is reported. Those contracts
require a later architecture decision.

In particular, the boundary performs no SOC logic, power limit enforcement,
clipping, saturation, optimization, forecasting, or strategy selection.

## Identity and Immutability

- Input `DecisionIntent` is never modified.
- A successful result references the exact supplied intent object.
- The result has no mutable container, cache, history, or runtime state.
- The abstract boundary has empty slots and retains no evaluated values.

## Non-goals

- Constraint algorithms or physical limit calculations.
- EMS charge/discharge strategy.
- SOC control or battery model behavior.
- Power clipping, saturation, or hidden correction.
- Optimization objectives or forecasting.
- Device, PCS, CAN, Modbus, or protocol commands.
- Dispatch, execution events, or runtime integration.
- Persistence, telemetry, cache, or history.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
