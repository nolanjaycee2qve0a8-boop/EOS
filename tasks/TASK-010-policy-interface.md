# TASK-010 — EMS Policy Interface Boundary

## Status

IN REVIEW

## Objective

Introduce the first EMS-specific policy abstraction boundary. EMSPolicy defines
where future energy-management algorithms may consume an immutable
EnergySystemContext and return an immutable DecisionResult.

This task defines only the interface contract. It does not implement an EMS
algorithm or connect the new boundary to runtime orchestration.

## Scope

- An abstract EMSPolicy interface.
- One `evaluate(context) -> DecisionResult` method contract.
- Explicit deterministic, stateless, and side-effect-free obligations.
- Stable public import and focused interface tests.

## Non-goals

- Energy optimization, scheduling, TOU, peak shaving, or self-consumption logic.
- MPC, MILP, AI policies, forecasting, or pricing.
- SOC, PCS, battery, or device control.
- Clocks, schedulers, threads, storage, communication, or device access.
- DecisionPipeline or runtime integration changes.
- Concrete or example EMS policy implementations.

## Contract

`EMSPolicy.evaluate` accepts one EnergySystemContext and returns one
DecisionResult. Implementations must:

- return the same result for the same context;
- remain stateless across evaluations;
- perform no externally visible side effects;
- never mutate the context, its assets, states, or PowerFlow; and
- avoid ownership of runtime services and infrastructure.

The interface uses `evaluate` to distinguish the EMS-specific context contract
from the existing `DecisionPolicy.decide(snapshot, mission)` boundary. TASK-010
does not change or adapt that existing interface.

## Acceptance Criteria

- EMSPolicy is abstract and cannot be instantiated directly.
- The evaluate signature accepts EnergySystemContext.
- The return annotation and documentation specify DecisionResult.
- The interface defines no instance state.
- Tests demonstrate context preservation and deterministic evaluation.
- Public imports support `from kernel.policy import EMSPolicy`.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~

## Implementation Notes

The tests use a minimal local subclass solely to exercise the abstract contract.
It is not an EOS EMS algorithm and is not exported by the kernel package.
