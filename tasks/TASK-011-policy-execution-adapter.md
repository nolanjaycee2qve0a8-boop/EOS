# TASK-011 — Policy Execution Adapter

## Status

IN REVIEW

## Objective

Introduce a stateless adapter that executes one supplied EMSPolicy against one
immutable EnergySystemContext and returns the exact DecisionResult.

The adapter establishes a narrow invocation boundary. It does not implement an
EMS algorithm or own runtime behavior.

## Scope

- A stateless PolicyExecutor.
- One `execute(policy, context) -> DecisionResult` method.
- Explicit validation of policy, context, and result boundary types.
- Exact exception propagation and immutable context preservation.
- Stable public import and focused unit tests.

## Non-goals

- EMS algorithms, optimization, or scheduling.
- Runtime loops, timers, threads, or background execution.
- Device or battery control.
- Persistence, communication, telemetry, or infrastructure ownership.
- Policy selection, registration, caching, or lifecycle management.
- Changes to DecisionPipeline or runtime.

## Execution Contract

PolicyExecutor accepts the policy for each call rather than storing it. Its
static execute method:

1. validates the supplied EMSPolicy and EnergySystemContext;
2. calls `policy.evaluate(context)` exactly once;
3. validates that the result is a DecisionResult; and
4. returns that exact result object.

Policy exceptions propagate unchanged. PolicyExecutor does not catch,
translate, retry, schedule, or persist an evaluation.

## Immutability and Ownership

- PolicyExecutor has no instance state.
- It does not own or retain a policy.
- It does not mutate context, assets, states, or PowerFlow.
- It does not own clocks, loops, threads, devices, or storage.

## Acceptance Criteria

- Normal policy execution returns the exact DecisionResult.
- A caller can replace the policy on every call.
- Context and nested object identity remain unchanged.
- Policy exceptions propagate unchanged.
- Invalid boundary types raise TypeError.
- Public imports support `from kernel.execution import PolicyExecutor`.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
