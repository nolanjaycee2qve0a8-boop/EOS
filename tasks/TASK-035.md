# TASK-035 ? Decision Evaluation Orchestration Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionEvaluationOrchestrator` as a stateless composition boundary
for one complete decision evaluation. It coordinates existing contracts and
returns an immutable `DecisionEvaluationCycle`.

No EMS strategy or executable device behavior is introduced.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult / DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent / ConstraintExplanation
        |
        v
DecisionEvaluationCycle
~~~

## Contract

`DecisionEvaluationOrchestrator.evaluate()` accepts the state, policy, and
constraint boundary per call. All external decision facts remain required
keyword-only inputs:

- `timestamp`;
- `battery_power_limit_kw`;
- `battery_energy_capacity_kwh`;
- `load_power_kw`;
- `electricity_price_cny_per_kwh`;
- `reserve_soc`; and
- `export_limit_kw`.

It performs this fixed composition:

1. assemble `DecisionContext` with `DecisionContextAssembler`;
2. evaluate the supplied `DecisionContextPolicy` once;
3. evaluate the supplied `DecisionConstraintBoundary` once;
4. create `ConstraintExplanation` from the exact feasible intent;
5. create and return `DecisionEvaluationCycle`.

## Identity Preservation

The orchestration path passes exact objects between boundaries. The returned
cycle guarantees:

~~~python
cycle.intent is cycle.result.intent
cycle.feasible_intent.intent is cycle.intent
cycle.explanation.feasible_intent is cycle.feasible_intent
cycle.explanation.source_intent is cycle.intent
~~~

There is no copy, reconstruction, serialization, normalization, or mutation
of decision artifacts.

## Ownership

The orchestrator has empty slots and no instance state. Policy and constraint
objects are supplied for one call and are not retained.

## Non-goals

- EMS strategy or algorithms.
- Optimization, scheduling, or forecasting.
- Runtime or runtime state.
- Commands, dispatch, or device control.
- PCS, BMS, CAN, Modbus, MQTT, or other adapters.
- Persistence, telemetry, cache, or history.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
