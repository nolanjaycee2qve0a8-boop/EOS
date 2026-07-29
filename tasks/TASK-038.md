# TASK-038 - Battery Constraint Boundary

## Status

IN REVIEW

## Objective

Introduce `BatteryConstraintImplementation` as the first concrete Phase 2
implementation of `DecisionConstraintBoundary`.

The implementation decides which battery power intention is physically
allowed by one immutable set of battery constraint facts. It does not change
policy output, execute commands, or control devices.

## Architecture

~~~text
DecisionContextPolicy
        |
        v
DecisionContextResult
        |
        v
DecisionIntent
        |
        v
BatteryConstraintImplementation
        |
        v
FeasibleDecisionIntent
~~~

Policy decides what the system wants to do. The constraint implementation
decides what the supplied battery facts allow.

## Boundary Contract

`BatteryConstraintImplementation` inherits `DecisionConstraintBoundary` and
preserves its substitutable method contract:

~~~python
evaluate(
    intent: DecisionIntent,
) -> FeasibleDecisionIntent
~~~

The implementation receives battery-specific facts during construction rather
than adding them to the general `evaluate` method:

~~~python
BatteryConstraintImplementation(
    soc=...,
    reserve_soc=...,
    max_charge_power_kw=...,
    max_discharge_power_kw=...,
)
~~~

## Constraint Facts

- `soc`: unitless fraction in the inclusive range `[0, 1]`.
- `reserve_soc`: unitless fraction in the inclusive range `[0, 1]`.
- `max_charge_power_kw`: non-negative raw power magnitude in kW.
- `max_discharge_power_kw`: non-negative raw power magnitude in kW.

The frozen, slotted implementation may retain these immutable facts for one
evaluation context. It must not retain history, cache, runtime state, policy,
dispatcher, commands, events, or device state.

## Deterministic Rules

`DecisionIntent.battery_power_intent_kw` retains its existing sign convention:

- greater than zero means charging intent;
- less than zero means discharging intent;
- zero means idle.

The implementation applies only these rules:

1. At `soc == 1`, positive charging intent becomes zero.
2. At `soc <= reserve_soc`, negative discharging intent becomes zero.
3. Positive power above `max_charge_power_kw` is clipped to that maximum.
4. Negative power whose magnitude exceeds `max_discharge_power_kw` is clipped
   to the negative maximum.
5. Zero and already feasible intentions remain unchanged.

There is no SOC calculation, prediction, saturation outside these explicit
rules, optimization, forecasting, or strategy selection.

## Identity and Immutability

The source `DecisionIntent` is never mutated.

- If the requested power is already feasible, the exact source intent
  identity is preserved in `FeasibleDecisionIntent`.
- If the requested power is blocked or clipped, a new immutable
  `DecisionIntent` is created for the allowed power.

The implementation itself is `@dataclass(frozen=True, slots=True)` and contains
only four scalar constraint facts.

## Non-goals

- EMS policy or strategy changes.
- SOC estimation or battery modeling.
- PCS, BMS, CAN, Modbus, MQTT, or device control.
- Commands, dispatch, runtime, persistence, telemetry, cache, or history.
- Optimization, forecasting, TOU pricing, or scheduling.
- Modification of `DecisionConstraintBoundary` or
  `DecisionEvaluationOrchestrator`.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
