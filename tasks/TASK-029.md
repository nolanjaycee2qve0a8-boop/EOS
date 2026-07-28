# TASK-029 ? DecisionContext Policy Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionContextPolicy` as a pure, stateless abstraction between the
immutable `DecisionContext` input and immutable `DecisionContextResult` output.

TASK-029 defines a contract only. It does not implement an EMS algorithm or
migrate existing execution and runtime boundaries.

## Architecture

### Legacy boundary

~~~text
EnergySystemContext
        |
        v
EMSPolicy
        |
        v
DecisionContextResult
~~~

### DecisionContext boundary

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
DecisionContextResult
~~~

## Contract

`DecisionContextPolicy` is an abstract class with one method:

~~~python
evaluate(context: DecisionContext) -> DecisionContextResult
~~~

The boundary:

- accepts exactly one `DecisionContext`;
- returns exactly one `DecisionContextResult`;
- has empty slots and owns no instance state;
- does not mutate its immutable input; and
- defines no algorithm or execution behavior.

## Coexistence

The existing `EMSPolicy` remains unchanged. It accepts
`EnergySystemContext` and is already consumed by legacy execution, cycle, and
runtime boundaries.

`DecisionContextPolicy` is independent: it does not inherit from, overload,
wrap, adapt, or replace `EMSPolicy`. No compatibility layer is introduced.
Migration or orchestration between the new boundary and runtime is outside
TASK-029.

## Non-goals

- EMS algorithms or rule-based policies.
- Optimization, scheduling, or forecasting.
- Runtime, `PolicyExecutor`, or `EMSCycle` migration.
- Dispatch, commands, or device control.
- Persistence, telemetry, caches, history, or mutable policy state.
- Compatibility adapters between policy boundaries.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
