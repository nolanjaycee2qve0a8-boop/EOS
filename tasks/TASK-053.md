# TASK-053 — EMS Objective Boundary

Status: IN REVIEW

## Objective

Introduce the EOS objective description layer without implementing any
objective, decision rule, scoring model, or intent generation.

An objective states what the EMS cares about. It does not decide what the
battery should do.

## Architecture

```text
EMSObjectiveBoundary
        |
        v
ObjectiveCollection
        |
        v
tuple[ObjectiveDescriptor, ...]
```

This boundary is independent from Capability, Intent Resolution, Constraint,
Evaluation, Runtime, and legacy execution.

## Public contracts

### ObjectiveDescriptor

An immutable semantic description with exactly:

- `name: str`;
- `description: str`.

Both fields must be non-empty strings. The descriptor contains no score,
priority, weight, decision, intent, command, or execution state.

### ObjectiveCollection

An immutable tuple of `ObjectiveDescriptor` instances. It preserves the exact
caller-supplied tuple and descriptor identities and does not sort, deduplicate,
rank, or normalize them.

An empty collection is valid because the contract must not invent an objective.

### EMSObjectiveBoundary

An abstract, stateless boundary:

```python
def describe(self) -> ObjectiveCollection: ...
```

It has empty slots and owns no mutable state, cache, history, runtime, resolver,
or intent.

## Public API

```python
from objective import (
    EMSObjectiveBoundary,
    ObjectiveCollection,
    ObjectiveDescriptor,
)
```

No concrete production objective is exported.

## Scope protection

TASK-053 does not modify:

- Kernel;
- Capability;
- Constraint;
- Evaluation;
- Runtime;
- legacy contracts or execution.

The package configuration is updated only so the new independent `objective`
package is included in distributions and coverage scope.

## Non-goals

- Concrete objectives.
- Optimization or objective functions.
- Scoring, priority, weighting, or ranking.
- Intent resolution.
- Intent generation.
- Policy, Capability, or Constraint behavior.
- Runtime, Dispatch, Device control, persistence, cache, or history.

## Validation

```text
pytest: 936 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
```
