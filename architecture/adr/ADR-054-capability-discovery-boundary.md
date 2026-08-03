# ADR-054 — Capability Discovery Boundary

## Status

Accepted

## Context

TASK-055 introduced `CapabilityDescriptor` so Objective-Capability mappings can
refer to capability semantics without depending on executable implementations.
EOS now needs a stable seam for reporting which descriptors are available,
while keeping discovery separate from hardware access, matching, selection,
activation, execution, and intent generation.

Treating discovery as device scanning or Capability construction would bind a
descriptor observation contract to infrastructure and behavior. That would
reverse stable dependency directions and introduce mutable runtime ownership.

## Decision

Add two public contracts to the Capability package:

- immutable `AvailableCapabilityCollection`;
- abstract, stateless `CapabilityDiscoveryBoundary`.

The accepted relationship is:

```text
CapabilityDiscoveryBoundary
        |
        v
AvailableCapabilityCollection
        |
        v
tuple[CapabilityDescriptor, ...]
```

`CapabilityDiscoveryBoundary.discover()` returns an immutable collection of
descriptor references. No concrete production discovery implementation is
introduced.

## Descriptor-only decision

Discovery output contains `CapabilityDescriptor` objects only. It cannot
contain Capability instances, implementation classes, factories, execution
handles, device clients, protocol frames, or `DecisionIntent` objects.

## Identity and immutability decision

- `AvailableCapabilityCollection` is frozen and slotted.
- Its only collection is a tuple.
- The exact descriptor tuple is retained.
- Caller/provider order is retained.
- Every descriptor identity is retained.
- Empty availability is valid.
- No copying, reconstruction, sorting, deduplication, or normalization occurs.

## Dependency decision

The accepted dependency is:

```text
capability.discovery -> capability.descriptor
```

The discovery module imports only the narrow descriptor contract and Python
standard-library abstractions. It has no dependency on concrete Capability
implementations, Objective, Kernel, Constraint, Evaluation, Runtime, Execution,
Device, persistence, or telemetry.

## Boundary decision

Discovery reports availability. It does not perform:

- hardware or protocol discovery;
- Objective-Capability matching;
- selection, ranking, priority, scoring, or weighting;
- activation or execution;
- intent generation or resolution.

Those responsibilities remain outside TASK-056.

## Consequences

- Available capability semantics have a stable immutable observation contract.
- Future providers can evolve behind an abstract boundary.
- Descriptor identity can be preserved across future observation layers.
- No device, runtime, or behavior dependency enters the discovery contract.
- Mapping, selection, activation, and execution remain separate future concerns.

## Rejected alternatives

### Return concrete Capability instances

Rejected because discovery must not construct or own executable behavior.

### Scan CAN or Modbus devices

Rejected because protocol and device discovery are infrastructure concerns.

### Match descriptors to objectives

Rejected because mapping and matching are separate from availability reporting.

### Select or activate capabilities

Rejected because discovery is not arbitration or lifecycle execution.

### Return DecisionIntent

Rejected because availability does not decide battery behavior.

## Non-goals

- Concrete discovery providers.
- Capability registries or persistence.
- Device, protocol, Runtime, or Execution integration.
- Matching, selection, activation, optimization, or intent generation.
- Cache, history, timestamps, UUIDs, telemetry, or mutable state.
