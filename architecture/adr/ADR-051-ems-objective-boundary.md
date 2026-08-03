# ADR-051 — EMS Objective Boundary

## Status

Accepted

## Context

Phase 3 established stable Capability, intent resolution, physical Constraint,
and evaluation evidence contracts. EOS now needs a separate vocabulary for
describing what the EMS cares about before any future objective-specific
behavior is considered.

Without a dedicated boundary, an objective description could be confused with
a Capability that generates intent, a resolver that selects intent, or an
optimization function that scores alternatives.

## Decision

Create an independent top-level `objective` package exposing only:

- `EMSObjectiveBoundary`;
- `ObjectiveDescriptor`;
- `ObjectiveCollection`.

The accepted relationship is:

```text
EMSObjectiveBoundary
        |
        v
immutable ObjectiveCollection
        |
        v
immutable ObjectiveDescriptor references
```

`ObjectiveDescriptor` contains only a non-empty name and description.
`ObjectiveCollection` contains only a tuple of descriptors in exact caller
order. `EMSObjectiveBoundary` is abstract and stateless and returns an
`ObjectiveCollection` through `describe()`.

No concrete production objective is introduced.

## Boundary meaning

Objective answers:

> What does the EMS care about?

It does not answer:

> What should the battery do?

The latter would require separate future behavior and must not be inferred,
generated, scored, or resolved by this boundary.

## Immutability decision

- Data models are frozen and slotted.
- Collections use tuples only.
- The supplied tuple and descriptor identities are preserved.
- No list, dictionary, set, mutable default, cache, or history exists.
- The abstract boundary uses empty slots and owns no instance state.

## Dependency decision

The objective package depends only on Python standard-library abstractions and
its own models. It has no dependency on Kernel, Capability, Constraint,
Evaluation, Runtime, Dispatch, Device, optimization, or legacy execution.

Existing packages do not depend on the new objective package.

## Consequences

- EOS gains explicit objective vocabulary without decision behavior.
- Future objective definitions can be reviewed independently from Capability
  and physical feasibility.
- Descriptions remain deterministic and immutable.
- No existing architecture contract changes.
- Any future concrete objective or objective-to-behavior connection requires a
  separate TASK and ADR.

## Rejected alternatives

### Put objectives in Capability

Rejected because Capability produces intent, while Objective only describes a
concern.

### Add priority, weight, or score fields

Rejected because those fields would introduce resolution or optimization
semantics.

### Return DecisionIntent from the objective boundary

Rejected because that would make Objective decide battery behavior.

### Add concrete objectives in TASK-053

Rejected because this task establishes the boundary only.

## Non-goals

- Concrete objectives.
- Optimization, scoring, priority, weighting, ranking, or arbitration.
- Resolver or intent generation.
- Policy, Capability, Constraint, or Evaluation changes.
- Runtime, Dispatch, Device control, persistence, telemetry, cache, or history.
