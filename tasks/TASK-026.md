# TASK-026 — Decision Context Boundary

## Status

IN REVIEW

## Objective

Introduce `DecisionContext` as an immutable snapshot of the facts visible at
one future EMS decision boundary.

It defines decision input only. It does not evaluate policy, optimize energy
use, forecast conditions, issue commands, or produce a `DecisionResult`.

## Architecture

~~~text
Runtime evidence layer
        |
        v
DecisionContext
        |
        v
Future EMS policy layer
        |
        v
DecisionResult
~~~

`DecisionContext` describes the world observed at a decision instant. Runtime
evidence-to-context assembly and policy integration remain future boundaries.

## Initial Facts

- timezone-aware `timestamp`;
- battery SOC;
- battery power limit and energy capacity;
- PV, load, and grid power observations;
- electricity price;
- reserve SOC; and
- export limit.

Every field is an immutable scalar. The first version contains no collection,
derived result, command, recommendation, forecast, or optimization output.

## Identity

Consumers receive the exact `DecisionContext` supplied by their caller. The
context is not copied, serialized, normalized into another model, or
reconstructed at an observation boundary.

TASK-025's `DecisionExplanation.source_context` continues to preserve the exact
context used by its existing completed decision. This task intentionally does
not change `DecisionExplanation`, `RuntimeExecutionTrace`, or `ExecutionAudit`.
Connecting `DecisionContext` to a future policy and explanation lifecycle is
outside TASK-026.

## Validation

Validation establishes factual input integrity only:

- timestamp must be timezone-aware;
- SOC and reserve SOC must be between zero and one;
- capacity must be positive;
- physical limits and non-negative measurements must not be negative; and
- all numeric facts must be finite and non-boolean.

Grid power and electricity price remain signed observations. No balance,
strategy, recommendation, or control calculation occurs.

## Non-goals

- EMS policy or optimization.
- Forecasting or recommendations.
- Commands or decision results.
- Runtime integration or lifecycle modification.
- Caches, history, persistence, telemetry, or mutable state.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
