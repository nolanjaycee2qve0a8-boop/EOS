# ADR-052 — Objective Activation Boundary

## Status

Accepted

## Context

TASK-053 introduced immutable descriptions of what the EMS cares about. A
description alone does not distinguish between the full known objective set
and the objectives active for a particular future use case.

EOS needs a minimal activation seam while preserving the separation between
objective description and all decision-producing behavior.

## Decision

Add two public contracts to the independent `objective` package:

- abstract, stateless `ObjectiveActivationBoundary`;
- immutable `ActiveObjectiveCollection`.

The accepted relationship is:

```text
ObjectiveCollection
        |
        v
ObjectiveActivationBoundary
        |
        v
ActiveObjectiveCollection
```

`ObjectiveActivationBoundary.activate()` accepts one exact
`ObjectiveCollection` and returns one `ActiveObjectiveCollection`.

The result stores the exact source collection and a caller-produced tuple of
exact descriptors from that source. Identity membership is validated with
`is`, not value equality alone.

## Activation meaning

Activation answers:

> Which of the described objectives are active?

It does not answer:

- Which active objective has priority?
- How should conflicts be resolved?
- What score or weight should an objective receive?
- What should the battery do?

Those semantics are intentionally absent.

## Immutability and lineage decision

- `ActiveObjectiveCollection` is frozen and slotted.
- Collections use tuples only.
- Source collection identity is preserved.
- Active tuple identity and order are preserved.
- Every active descriptor must be an exact source descriptor object.
- Empty activation is valid.
- No copying, reconstruction, sorting, deduplication, or normalization occurs.

## Exactly-once decision

One `activate()` invocation consumes one exact source reference and returns one
result. The boundary does not call objective description, recursively invoke
activation, or run any other EOS layer.

## Dependency decision

The activation module depends only on Python standard-library abstractions and
the existing immutable objective models. It has no dependency on Kernel,
`DecisionContext`, Capability, Constraint, Evaluation, Runtime, Dispatch,
Device, optimization, or legacy execution.

No existing EOS package depends on activation.

## Consequences

- Objective activation has a stable immutable seam.
- Activation evidence retains exact source lineage.
- Future implementations can define activation facts behind the boundary.
- No priority, conflict, optimization, or decision semantics are implied.
- Existing EOS architecture and legacy execution remain unchanged.

## Rejected alternatives

### Add active state to ObjectiveDescriptor

Rejected because it would mutate or overload the stable description contract.

### Add priority, ranking, weight, or score

Rejected because activation is not arbitration or optimization.

### Return DecisionIntent

Rejected because activation must not decide battery behavior.

### Implement a concrete activation rule

Rejected because TASK-054 establishes the boundary only.

## Non-goals

- Concrete activation rules.
- Priority, ranking, weighting, scoring, or conflict resolution.
- Optimization, resolver behavior, or intent generation.
- Kernel, Capability, Constraint, Evaluation, Runtime, or legacy changes.
- Dispatch, Device control, persistence, telemetry, cache, or history.
