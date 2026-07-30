# ADR-040 - Grid Power Limit Constraint

## Status

Accepted

## Context

TASK-040 established `GridConstraintBoundary` without choosing an algorithm.
EOS now needs its first concrete grid-side physical constraint while preserving
the existing generic `evaluate(intent)` contract and the source/feasible intent
lineage introduced by TASK-039.

`DecisionIntent` describes battery charging power as positive and battery
discharging power as negative. It deliberately contains no grid target.
Therefore import and export feasibility cannot be evaluated from the intent and
limit magnitudes alone. An explicit grid baseline fact is required.

## Decision

Introduce the frozen, slotted:

~~~python
GridPowerLimitConstraintImplementation(
    grid_power_baseline_kw,
    max_import_power_kw,
    max_export_power_kw,
)
~~~

It inherits `GridConstraintBoundary` and preserves:

~~~python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
~~~

All facts are literal, unscaled kW.

`grid_power_baseline_kw` is the grid exchange before applying the supplied
battery intent. Positive means import, negative means export, and zero means
balanced exchange.

The import and export limits are non-negative magnitudes. The allowed grid
interval is:

~~~text
[-max_export_power_kw, max_import_power_kw]
~~~

Project and clamp deterministically:

~~~python
projected_grid_power_kw = grid_power_baseline_kw + intent.battery_power_intent_kw

allowed_grid_power_kw = clamp(
    projected_grid_power_kw,
    -max_export_power_kw,
    max_import_power_kw,
)

allowed_battery_intent_kw = allowed_grid_power_kw - grid_power_baseline_kw
~~~

If the allowed battery power equals the requested battery power, preserve the
exact source intent identity. Otherwise create a new immutable
`DecisionIntent`; never mutate the source object.

## Architecture

~~~text
DecisionContextResult.intent
        |
        v
source DecisionIntent
        |
        v
GridPowerLimitConstraintImplementation
        |
        v
FeasibleDecisionIntent
~~~

## Consequences

- Grid import and export limits become enforceable through the existing
  constraint seam.
- The grid baseline has an explicit unit, sign, and lifecycle meaning.
- `DecisionIntent` remains battery-specific and immutable.
- Generic and grid-specific boundary signatures remain stable.
- Source intent evidence remains observable after adjustment.
- A baseline already outside the allowed range can produce a corrective
  battery intent that projects exactly to the nearest limit.
- Runtime, policy, device, and persistence layers remain isolated.

## Rejected Alternatives

- Treat battery intent as grid power: rejected because the two contracts have
  different meanings.
- Omit the baseline: rejected because identical battery intents can be feasible
  or infeasible under different grid conditions.
- Add grid fields to `DecisionIntent`: rejected because intent remains the
  semantic battery power request.
- Add grid arguments to `evaluate`: rejected because it would break the stable
  generic and grid constraint boundaries.
- Put limits in Policy: rejected because policy expresses intention and
  constraints enforce physical feasibility.
- Read runtime or device state: rejected because immutable facts must be
  supplied explicitly.
- Add a dedicated Zero Export branch: rejected because TASK-041 implements one
  generic numeric interval, not a strategy or controller.

## Non-goals

- TOU, pricing, optimization, forecasting, or scheduling.
- Zero Export strategy or anti-backflow controller.
- PCS/BMS control, commands, protocols, dispatch, or runtime execution.
- Persistence, telemetry, cache, history, or mutable state.
- Changes to battery constraints, policy, intent lineage, or legacy contracts.
