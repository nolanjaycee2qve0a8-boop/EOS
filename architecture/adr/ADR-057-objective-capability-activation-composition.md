# ADR-057 — Objective-Capability Activation Composition

## Status

Accepted

## Context

TASK-055 established descriptor-level Objective-to-Capability support mappings.
TASK-056 through TASK-058 then established discovery, matching, and activation
status boundaries for Capability descriptors. EOS now needs an immutable seam
that records which completed active capability collection is associated with an
objective without adding selection or execution behavior.

Copying active descriptors into a new independently supplied subset would make
the composition an implicit selection point and could omit active capabilities.
Storing Capability instances would reverse dependency direction and introduce
implementation or runtime ownership.

## Decision

Add the following public contracts to the Objective package:

- immutable `ObjectiveCapabilityActivationComposition`;
- abstract, stateless
  `ObjectiveCapabilityActivationCompositionBoundary`.

The accepted relationship is:

```text
ObjectiveDescriptor             ActiveCapabilityCollection
        |                                  |
        +----------------------------------+
                                           |
                                           v
          ObjectiveCapabilityActivationCompositionBoundary
                                           |
                                           v
             ObjectiveCapabilityActivationComposition
```

No concrete production composition implementation is introduced.

## Complete-reference decision

The composition stores exactly two references: the supplied objective and the
supplied complete active capability collection. It does not define a separate
capability tuple, subset, selected flag, score, rank, priority, reason, fallback,
command, event, or intent.

Because the exact active collection is retained, composition completeness does
not require copying descriptors. Repeated descriptor identities in the nested
active tuple are rejected. Descriptor source identity remains enforced by the
existing `ActiveCapabilityCollection` contract.

## Identity and immutability decision

- The composition model is frozen and slotted.
- Objective identity is preserved.
- Active capability collection identity is preserved.
- Nested tuple, order, and descriptor identities are preserved.
- Duplicate active descriptor identities are rejected.
- Equal-but-reconstructed capability descriptors cannot enter a valid source.
- No copying, reconstruction, sorting, deduplication, or normalization occurs.

## Dependency decision

The accepted dependencies are:

```text
objective.activation_composition -> objective.model
objective.activation_composition -> capability.activation
```

Dependency remains Objective-to-Capability-contract only. The Capability package
does not import Objective. No Constraint, Evaluation, Runtime, Execution,
Device, protocol, persistence, or telemetry dependency is introduced.

## Separation decision

Composition is distinct from:

- discovery, matching, and activation logic;
- selection, ranking, priority, scoring, and weighting;
- optimization, conflict resolution, and fallback;
- Capability execution and device control;
- intent generation and resolution.

TASK-059 establishes only an immutable relationship artifact and its abstract
construction seam.

## Consequences

- Objective-to-active-Capability relationships gain an explicit contract.
- Composition completeness is guaranteed without copying a capability subset.
- Identity lineage remains observable through the full active collection.
- Future providers can implement the boundary without modifying stable models.
- Decision, Constraint, Runtime, and Device layers remain isolated.

## Rejected alternatives

### Store a separate capability subset

Rejected because it would introduce omission and implicit selection semantics.

### Store concrete Capability instances

Rejected because the composition must remain at the descriptor contract layer.

### Add selected, priority, or score fields

Rejected because those fields introduce arbitration behavior.

### Generate DecisionIntent

Rejected because composition does not decide battery behavior.

## Non-goals

- Selection, ranking, priority, scoring, weighting, optimization, conflict
  resolution, or fallback.
- Capability activation logic, implementation creation, or execution.
- Intent generation or resolution.
- Constraint, Device, CAN, Modbus, Runtime, persistence, telemetry, cache, or
  history.
