# ADR-056 — Capability Activation Boundary

## Status

Accepted

## Context

TASK-057 established immutable facts describing which required capability
descriptors are matched or missing. EOS now needs a separate seam for recording
whether matched capability descriptors are active or inactive without turning
matching into activation and without introducing executable Capability objects.

Embedding activation status in `CapabilityMatch` would mix relationship facts
with a later lifecycle state. Returning concrete Capability instances would
couple the descriptor layer to implementations, devices, and runtime ownership.

## Decision

Add the following public contracts to the Capability package:

- immutable `ActiveCapabilityCollection`;
- abstract, stateless `CapabilityActivationBoundary`.

The accepted relationship is:

```text
CapabilityMatchCollection
        |
        v
CapabilityActivationBoundary
        |
        v
ActiveCapabilityCollection
        |-- active_capabilities
        `-- inactive_capabilities
```

No concrete production activation implementation is introduced.

## Status-only decision

`ActiveCapabilityCollection` references the exact source match collection and
stores exact matched available descriptor references in caller-supplied active
and inactive tuples. It stores no priority, rank, score, selected flag, reason,
fallback, executable object, command, event, or intent.

Every matched available descriptor belongs to exactly one of the active or
inactive categories. Omission and overlap are rejected using identity-based
membership checks.

## Identity and immutability decision

- The result model is frozen and slotted.
- All collections are tuples.
- Source match collection identity is preserved.
- Active and inactive tuple and descriptor identities are preserved.
- Equal-but-reconstructed and unrelated descriptors are rejected.
- No copying, reconstruction, sorting, deduplication, or normalization occurs.

## Dependency decision

The accepted dependencies are:

```text
capability.activation -> capability.matching
capability.activation -> capability.descriptor
```

The module imports no concrete Capability implementation and has no dependency
on Objective, Kernel, Constraint, Evaluation, Runtime, Execution, Device,
protocol, persistence, or telemetry layers.

## Separation decision

Activation status is distinct from:

- matching and discovery;
- ranking, scoring, priority, weighting, and selection;
- optimization, conflict resolution, and fallback;
- Capability execution and device control;
- intent generation and resolution.

TASK-058 establishes only the abstract seam and immutable status artifact.

## Consequences

- Matched capability activation status gains an explicit immutable contract.
- Matching remains a relationship-fact boundary.
- Future activation implementations can evolve behind an abstract interface.
- Capability implementations, decision intents, devices, and runtime remain
  isolated.

## Rejected alternatives

### Add active state to CapabilityMatch

Rejected because matching and activation are separate lifecycle concerns.

### Return concrete Capability instances

Rejected because activation output must remain at the descriptor layer.

### Store only active descriptors and infer inactive descriptors

Rejected because the activation result must explicitly express both states and
provide complete, mutually exclusive coverage.

### Add priority or selection rules

Rejected because TASK-058 defines no activation algorithm or arbitration.

### Return DecisionIntent

Rejected because activation status does not decide battery behavior.

## Non-goals

- Concrete activation algorithms or providers.
- Selection, ranking, priority, scoring, weighting, optimization, conflict
  resolution, or fallback.
- Capability execution, instances, or intent generation.
- Constraint, Device, CAN, Modbus, Runtime, persistence, telemetry, cache, or
  history.
