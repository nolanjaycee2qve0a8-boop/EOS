# TASK-141 - Rolling PV Opportunity Headroom Composition

## Objective

Compose TASK-140's first next/current PV-surplus opportunity selection with
TASK-132's existing PV headroom calculation.  The composition constructs a new
selected `ForecastHorizon` that holds only the exact `ForecastPoint` objects
selected by the opportunity window, then delegates all headroom mathematics to
TASK-132 exactly once.

## Public contracts

- `RollingPVHeadroomRequirementInput`
- `RollingPVHeadroomRequirement`
- `RollingPVHeadroomRequirementBoundary`
- `DeterministicRollingPVHeadroomRequirementCalculator`

The input retains exact references to the caller's full forecast horizon,
battery model, window configuration, and explicit control-step duration.  The
result retains the exact input, `PVOpportunityWindow`, newly constructed
selected `ForecastHorizon`, and `PVHeadroomRequirement` evidence.

## Composition semantics

1. TASK-140 selects one first next/current PV opportunity from the full caller
   horizon.
2. TASK-141 constructs a new `ForecastHorizon` from exactly the selected
   window steps, preserving every original `ForecastPoint` identity and order.
3. TASK-132 receives that selected horizon with the exact caller battery model
   and duration, and calculates its unchanged headroom formula once.

An inactive cloud-gap point retained by TASK-140 remains in the selected
horizon. TASK-132 consequently sees its zero surplus naturally; TASK-141 does
not reclassify, sort, deduplicate, fill, or remove points.

If no opportunity exists, TASK-141 passes `ForecastHorizon(())` into TASK-132.
The existing zero-headroom result and maximum recommended SOC behavior are
therefore reused without a special result type or duplicate formula.

## Provenance and execution guarantees

- `opportunity_window.source_input.forecast_horizon is source_input.forecast_horizon`
- `opportunity_window.source_input.configuration is source_input.window_configuration`
- each selected horizon point is the exact selected window-step point
- `headroom_requirement.source_input.forecast_horizon is selected_forecast_horizon`
- `headroom_requirement.source_input.battery_model is source_input.battery_model`
- the selector is called once and the headroom calculator is called once per
  composition invocation

## Architectural progression

- TASK-132: all caller-supplied horizon points become headroom evidence.
- TASK-139: a repeating 24-hour horizon demonstrated useful but conservative
  headroom behavior.
- TASK-140: selects only one rolling PV opportunity as ordered evidence.
- TASK-141: adapts that selected opportunity into the unchanged TASK-132
  headroom calculation.

## Non-goals

TASK-141 does not alter TASK-140 selection semantics or TASK-132's formula. It
does not modify the headroom-aware physical optimizer, reservation, candidate
planner, MPC cycle, daily demo, explanations, CSV, simulator, feasibility, or
actuation. In particular, TASK-139 behavior remains unchanged until a later
integration task explicitly consumes this composition.

## Validation

- focused composition tests including empty opportunity, cloud-gap retention,
  first-opportunity-only behavior, identity provenance, and exactly-once calls
- full `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
