# TASK-025 — Decision Explanation Boundary

## Status

IN REVIEW

## Objective

Add an immutable explanation observation above `ExecutionAudit`.

The boundary exposes the exact source decision context and result already
represented by a completed execution audit. It does not produce inferred
reasons, execute runtime behavior, or recompute policy output.

## Architecture

~~~text
RuntimeExecutionTrace
        |
        v
ExecutionAudit
        |
        v
DecisionExplanation
        |
        v
immutable explanation observation
~~~

`DecisionExplanation.create(audit)` returns a frozen, slotted object containing
the exact audit, trace, source context, and source `DecisionResult` references.

## Identity Contract

The explanation preserves:

- `explanation.audit is audit`;
- `explanation.trace is audit.trace`;
- `explanation.context is audit.source_tick.execution.cycle.context`; and
- `explanation.decision_result is
  audit.source_tick.execution.cycle.result`.

Commands, events, journals, and `EventRecord` objects remain the same objects
already present in the lifecycle. No object is copied, serialized, normalized,
or reconstructed.

## Explanation Is Separate from Execution

Execution decides and performs lifecycle transitions. Explanation only exposes
the provenance of an existing completed source decision. This prevents
inspection from becoming a hidden policy or runtime invocation.

## No Recalculation

Re-evaluating a policy could produce a different result or introduce side
effects. The explanation therefore reads the existing `DecisionResult` and
context by identity. It does not call runtime, policy evaluation, dispatch,
`CommandExecutor`, `RuntimeReplay`, `ExecutionAudit.create()`, or journal
append.

## Statelessness

The boundary owns no policy, cache, history, global state, persistence,
telemetry, timestamp, UUID, or runtime service. Repeated calls create
independent immutable wrappers around the same original references.

## Non-goals

- Intelligent diagnosis or automatic recommendations.
- Machine learning or optimization analysis.
- Electricity price calculations or forecasting.
- Battery optimization.
- Cloud analytics, persistence, telemetry, or UI dashboards.
- Future natural-language or optimization-specific explanation layers.

## Validation

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
