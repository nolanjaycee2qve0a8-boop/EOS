# TASK-012 — EMS Decision Cycle

## Status

IN REVIEW

## Objective

Introduce one immutable deterministic EMS execution unit. EMSCycle records the
exact EnergySystemContext supplied to one policy execution and the exact
DecisionResult returned through PolicyExecutor.

This task creates a single cycle object. It does not create repetition,
scheduling, or runtime ownership.

## Scope

- A frozen slotted EMSCycle containing context and result.
- One `EMSCycle.execute(policy, context)` class factory.
- Mandatory delegation through PolicyExecutor.
- Exact context and result identity preservation.
- Boundary validation, public import, and focused unit tests.

## Non-goals

- Runtime loops, schedulers, timers, threads, or retries.
- Device, PCS, battery, or SOC control.
- EMS algorithms, optimization, forecasting, or policy selection.
- Persistence, communication, telemetry, or journaling.
- Changes to DecisionPipeline or runtime.

## Execution Contract

`EMSCycle.execute` accepts one EMSPolicy and one EnergySystemContext. It calls
`PolicyExecutor.execute(policy, context)` exactly once, then constructs an
EMSCycle from the original context object and exact returned DecisionResult.

EMSCycle never calls `policy.evaluate` directly and does not store the policy.
PolicyExecutor owns boundary validation and exception behavior.

## Immutability

- EMSCycle is a frozen slotted dataclass.
- Its only fields are context and result.
- Neither input is copied, normalized, modified, or replaced.
- The immutable context, assets, states, PowerFlow, and result remain unchanged.

## Acceptance Criteria

- Valid factory execution returns an EMSCycle.
- Context and result object identities are preserved.
- The policy is evaluated exactly once through PolicyExecutor.
- The cycle is frozen, slotted, and contains no policy field.
- Policy exceptions propagate unchanged.
- Public imports support `from kernel.cycle import EMSCycle`.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
