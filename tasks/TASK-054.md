# TASK-054 — Objective Activation Boundary

Status: IN REVIEW

## Objective

Add the minimal immutable boundary for representing which already-described
EMS objectives are active.

Activation does not decide priority, resolve conflicts, optimize objectives,
or generate an energy intent.

## Architecture

```text
ObjectiveCollection
        |
        v
ObjectiveActivationBoundary
        |
        v
ActiveObjectiveCollection
```

## Public contracts

### ObjectiveActivationBoundary

An abstract, stateless boundary:

```python
def activate(
    self,
    objectives: ObjectiveCollection,
) -> ActiveObjectiveCollection: ...
```

Each invocation receives the exact immutable source collection once and
returns one immutable activation artifact. The boundary owns no state, cache,
history, runtime, resolver, or decision logic.

### ActiveObjectiveCollection

An immutable result containing exactly:

- `source_collection: ObjectiveCollection`;
- `active_objectives: tuple[ObjectiveDescriptor, ...]`.

The result preserves:

- exact source collection identity;
- exact caller-supplied active tuple identity;
- exact descriptor identities from the source collection;
- caller-supplied active order, including an empty result.

An equal but reconstructed descriptor is rejected because value equality is
not identity lineage.

## Exactly-once semantics

The boundary accepts one source collection for one activation invocation and
returns one result. It does not call `EMSObjectiveBoundary.describe()`, repeat
activation, or re-evaluate source descriptors. Tests use a test-only recording
implementation to verify one call produces one result.

## Public API

```python
from objective import ActiveObjectiveCollection, ObjectiveActivationBoundary
```

No concrete production activation implementation is introduced.

## Scope protection

TASK-054 does not modify:

- Kernel or `DecisionContext`;
- Capability;
- Constraint;
- Evaluation;
- Runtime;
- legacy EMS contracts or execution.

## Non-goals

- Objective priority or ranking.
- Objective conflict resolution.
- Objective weighting or scoring.
- Optimization.
- Resolver behavior.
- Intent generation.
- Policy, Capability, Constraint, or Evaluation behavior.
- Runtime, Dispatch, Device control, persistence, cache, or history.

## Validation

```text
pytest: 948 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
```
