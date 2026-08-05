# ADR-060 — Decision Formation Boundary

## Status

Accepted

## Context

TASK-061 introduced an independent Phase 5 semantic `DecisionIntent` with
`charge`, `discharge`, and `idle` actions. Phase 4 already provides immutable
Objective/Capability evidence, while the existing `DecisionContext` provides a
stable fact snapshot.

EOS now needs a formation seam that can associate those exact inputs with one
semantic intent candidate without adding an EMS algorithm, Capability
selection, physical feasibility, optimization, command generation, or runtime
ownership.

Using only a `CapabilityDescriptor` without Phase 4 activation evidence would
lose provenance. Allowing Formation to choose a descriptor from a collection
would turn the boundary into a hidden selection point. Reconstructing equal
descriptors would break identity lineage.

## Decision

Add three public contracts to the independent `decision_formation` package:

- frozen/slotted `DecisionFormationInput`;
- frozen/slotted `DecisionIntentCandidate`;
- abstract, empty-slotted `DecisionFormationBoundary`.

The accepted relationship is:

```text
DecisionContext + Objective/Active-Capability Composition
                + exact active CapabilityDescriptor
                              |
                              v
                 DecisionFormationInput
                              |
                              v
                 DecisionFormationBoundary
                              |
                              v
                 DecisionIntentCandidate
```

No concrete production Formation implementation is introduced.

## Input decision

`DecisionFormationInput` directly stores the supplied context, composition, and
capability descriptor. The descriptor must be the exact active descriptor in
the composition. Inactive, absent, or equal-but-reconstructed descriptors are
invalid.

The explicit descriptor identifies provenance only. It does not cause
selection, reflection, registry lookup, factory construction, or Capability
execution.

## Candidate decision

`DecisionIntentCandidate` stores exactly the supplied formation input and Phase
5 intent. It does not copy or reconstruct either object and carries no score,
priority, reason, feasible status, command, event, or execution result.

## Boundary decision

`DecisionFormationBoundary` defines only:

```python
form(formation_input: DecisionFormationInput) -> DecisionIntentCandidate
```

It is abstract, stateless, and empty-slotted. It owns no policy, Capability
implementation, context, composition, resolver, constraint, optimizer, runtime,
dispatcher, or device.

## Identity decision

- Context identity is preserved.
- Composition identity is preserved.
- Active capability descriptor identity is preserved.
- Candidate input identity is preserved.
- Candidate Intent identity is preserved.
- No copy, reconstruction, serialization, normalization, sorting, or
  deduplication occurs.

These are direct boundary contracts only. TASK-062 does not establish an
automatic Phase 4 evidence pipeline or descriptor-to-implementation binding.

## Dependency decision

Decision Formation depends on stable Kernel DecisionContext, Objective
composition, Capability descriptor, and Phase 5 Intent contracts. None of those
packages imports Decision Formation.

There is no dependency on Capability implementations, Constraint, Optimization,
Runtime, Execution, Dispatch, Device, PCS, BMS, protocols, persistence, or
telemetry.

## Consequences

- Phase 5 gains explicit immutable formation input and candidate provenance.
- A future concrete former can implement the boundary without modifying stable
  Objective, Capability, Context, or Intent contracts.
- Invalid active-capability lineage is rejected before a candidate can be
  represented.
- Resolution and physical feasibility remain separate future tasks.

## Rejected alternatives

### Let Formation select an active capability

Rejected because selection is not Formation provenance.

### Resolve a descriptor to an implementation automatically

Rejected because a descriptor is not an implementation or registry key.

### Return DecisionIntent directly

Rejected because the candidate must preserve its exact formation evidence.

### Add feasibility or command fields

Rejected because Constraint and Execution are later boundaries.

## Non-goals

- Concrete formation logic, charge/discharge rules, or policy evaluation.
- Capability selection, implementation binding, creation, or execution.
- Resolution, Constraint, Optimization, forecasting, or scheduling.
- Command, Runtime, Dispatch, Device, PCS, BMS, protocol, persistence, cache,
  or history.
