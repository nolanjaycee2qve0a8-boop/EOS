# ADR-055 — Capability Matching Boundary

## Status

Accepted

## Context

TASK-056 established an immutable observation of available capability
descriptors. EOS also needs a way to represent required descriptors and facts
that relate requirements to availability without embedding a matching
algorithm, selection policy, or executable Capability behavior.

Using concrete Capability instances or device data would couple relationship
evidence to runtime and infrastructure. Adding scores or priorities would turn
matching into arbitration rather than fact representation.

## Decision

Add the following public contracts to the Capability package:

- immutable `RequiredCapabilityCollection`;
- immutable `CapabilityMatch`;
- immutable `CapabilityMatchCollection`;
- abstract, stateless `CapabilityMatchingBoundary`.

The accepted relationship is:

```text
RequiredCapabilityCollection
        |                         AvailableCapabilityCollection
        +-------------------------+
                                  |
                                  v
                    CapabilityMatchingBoundary
                                  |
                                  v
                    CapabilityMatchCollection
```

No concrete production matching implementation is introduced.

## Fact-only decision

`CapabilityMatch` stores one exact required descriptor reference and one exact
available descriptor reference. It does not store a score, rank, priority,
weight, reason, fallback, selected flag, activation state, executable object,
or intent.

`CapabilityMatchCollection` validates that each relationship points into the
exact supplied source collections using identity comparisons.

## Identity and immutability decision

- All models are frozen and slotted.
- All collections are tuples.
- Required and available source collection identities are preserved.
- Required and available descriptor identities are preserved.
- Match tuple, order, and match object identities are preserved.
- Empty required, available, and match collections are valid.
- Equal-but-reconstructed source descriptors are rejected.
- No copying, reconstruction, sorting, deduplication, or normalization occurs.

## Dependency decision

The accepted dependencies are:

```text
capability.matching -> capability.descriptor
capability.matching -> capability.discovery
```

The module imports no concrete Capability implementation and has no dependency
on Objective, Kernel, Constraint, Evaluation, Runtime, Execution, Device,
protocol, persistence, or telemetry layers.

## Separation decision

Matching is distinct from:

- ranking and scoring;
- priority and weighting;
- selection and conflict resolution;
- optimization and fallback;
- activation and execution;
- intent generation and resolution.

TASK-057 establishes only the seam and immutable relationship artifacts.

## Consequences

- Required-to-available relationships gain a stable identity-based contract.
- Future matching implementations can evolve behind an abstract boundary.
- Selection and activation remain separate future responsibilities.
- Capability implementations, devices, and runtime state remain isolated.

## Rejected alternatives

### Match concrete Capability instances

Rejected because matching output must remain at the descriptor layer.

### Match by name inside the model

Rejected because the boundary task does not define a matching algorithm.

### Store a score, priority, or selected flag

Rejected because those fields introduce ranking or selection semantics.

### Add fallback behavior

Rejected because fallback is decision behavior, not a matching fact.

### Return DecisionIntent

Rejected because matching does not decide battery behavior.

## Non-goals

- Concrete matching rules.
- Selection, ranking, priority, scoring, weighting, optimization, or fallback.
- Activation, execution, Capability instances, or intent generation.
- Device, CAN, Modbus, Runtime, persistence, telemetry, cache, or history.
