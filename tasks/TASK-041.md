# TASK-041 - Grid Power Limit Constraint Implementation

## Status

IN REVIEW

## Objective

Implement the first concrete `GridConstraintBoundary` using immutable grid
power limit facts.

The implementation converts one battery power intention into an allowed
battery power intention whose projected grid exchange is within the configured
import and export range.

## Architecture

~~~text
source DecisionIntent
        |
        v
GridPowerLimitConstraintImplementation
        |
        v
FeasibleDecisionIntent
~~~

The existing contract remains:

~~~python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
~~~

`DecisionIntent` continues to contain only
`battery_power_intent_kw`. No grid field is added to the intent.

## Immutable Constraint Facts

Construction requires:

~~~python
GridPowerLimitConstraintImplementation(
    grid_power_baseline_kw=...,
    max_import_power_kw=...,
    max_export_power_kw=...,
)
~~~

All values are literal, unscaled kW.

`grid_power_baseline_kw` is the grid power before applying the supplied battery
intent:

- positive means importing from the grid;
- negative means exporting to the grid;
- zero means balanced exchange; and
- any finite real value is valid.

`max_import_power_kw` and `max_export_power_kw` are non-negative finite power
magnitudes. They define the allowed grid interval:

~~~text
[-max_export_power_kw, max_import_power_kw]
~~~

The facts are frozen, slotted, and owned only for the evaluation represented by
the instance. They are not history, cache, policy, runtime, or device state.

## Deterministic Projection

The existing battery intent sign convention remains:

- positive means battery charging;
- negative means battery discharging; and
- zero means idle.

Projected grid power is:

~~~python
projected_grid_power_kw = grid_power_baseline_kw + intent.battery_power_intent_kw
~~~

Positive charging increases projected grid import. Negative discharging
reduces import or increases export.

The constraint clamps only the projected grid exchange:

~~~python
allowed_grid_power_kw = clamp(
    projected_grid_power_kw,
    -max_export_power_kw,
    max_import_power_kw,
)

allowed_battery_intent_kw = allowed_grid_power_kw - grid_power_baseline_kw
~~~

No scaling, unit conversion, forecasting, pricing, optimization, or hidden
power model is applied.

## Identity and Immutability

When no adjustment is required:

~~~python
result.intent is source_intent
~~~

When the projected grid exchange is outside the allowed interval:

- the source intent remains unchanged;
- a new immutable `DecisionIntent` contains the allowed battery power; and
- `FeasibleDecisionIntent` references that exact new object.

TASK-039 source/feasible lineage remains unchanged.

## Boundary Preservation

TASK-041 does not modify:

- `DecisionConstraintBoundary`;
- `GridConstraintBoundary`;
- `DecisionIntent`;
- `FeasibleDecisionIntent`;
- policy or orchestration contracts;
- source/feasible lineage;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- A dedicated Zero Export strategy or controller.
- TOU or electricity-price behavior.
- Optimization, forecasting, or scheduling.
- SOC, battery capability, or degradation constraints.
- PCS/BMS control, commands, protocols, or dispatch.
- Runtime, persistence, telemetry, cache, or history.

## Tests

Focused tests cover:

- import-limit adjustment;
- export-limit adjustment;
- exact identity when no adjustment is required;
- immutable source preservation after adjustment;
- deterministic baseline correction;
- validation of units, ranges, types, and finite values;
- frozen and slotted facts;
- dependency isolation; and
- public import.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
