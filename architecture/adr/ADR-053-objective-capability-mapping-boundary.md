# ADR-053 — Objective-Capability Mapping Boundary

## Status

Accepted

## Context

TASK-053 describes what the EMS cares about. TASK-054 represents which of
those descriptions are active. EOS now needs a stable way to express that an
objective can be supported by one or more capability contracts without
selecting, ranking, executing, or instantiating those capabilities.

Referencing concrete Capability implementations from Objective would bind the
descriptive layer to business behavior and could introduce Runtime or Kernel
dependencies transitively.

## Decision

Add a narrow immutable `CapabilityDescriptor` contract to the Capability
package and add the following contracts to the Objective package:

- `ObjectiveCapabilityMapping`;
- `ObjectiveCapabilityMappingCollection`;
- abstract `ObjectiveCapabilityMappingBoundary`.

The accepted relationship is:

```text
ObjectiveDescriptor
        |
        v
ObjectiveCapabilityMapping
        |
        v
tuple[CapabilityDescriptor, ...]
```

The mapping boundary accepts an exact immutable `ObjectiveCollection` or
`ActiveObjectiveCollection` and returns an immutable mapping collection.

No concrete production mapping implementation is introduced.

## Descriptor decision

`CapabilityDescriptor` contains only a non-empty name and description. It is
not a Capability implementation, factory, class reference, execution handle,
or configuration object.

Mapping output therefore remains at the descriptor layer.

## Identity decision

- Mapping preserves the exact objective descriptor.
- Capability descriptor tuples and each descriptor identity are preserved.
- Mapping collection preserves the exact source and mapping tuple.
- Mapping objectives must be exact members of the source, validated with `is`.
- Equal-but-reconstructed objectives are rejected.
- Empty mapping collections and empty capability tuples are valid.
- No sorting, deduplication, normalization, copying, or reconstruction occurs.

## Dependency decision

The accepted direction is:

```text
objective.mapping -> capability.descriptor
```

`objective.mapping` imports only the narrow descriptor contract, not the
Capability package facade or implementations. Capability has no dependency on
Objective.

Kernel, Decision, Constraint, Evaluation, Runtime, Execution, and legacy paths
remain unchanged.

## Consequences

- EOS can describe objective support without instantiating capabilities.
- Objective and Capability remain separately reviewable.
- Future mapping implementations can evolve behind a stable stateless seam.
- Mapping cannot be mistaken for selection, arbitration, or execution.
- Reverse dependency from Capability to Objective remains prohibited.

## Rejected alternatives

### Store concrete Capability instances

Rejected because Objective must not depend on Capability implementations or
execution state.

### Store Capability classes or factories

Rejected because those are executable implementation references rather than
descriptors.

### Add priority, ranking, score, or weight

Rejected because mapping is not selection, arbitration, or optimization.

### Generate DecisionIntent from a mapping

Rejected because a relationship does not decide battery behavior.

## Non-goals

- Concrete mapping rules.
- Capability selection, ranking, priority, score, or weighting.
- Capability optimization, execution, composition, or resolution.
- Intent generation.
- Kernel, Constraint, Evaluation, Runtime, Execution, or legacy changes.
- Device control, persistence, telemetry, cache, or history.
