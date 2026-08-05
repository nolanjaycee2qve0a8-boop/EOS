# TASK-062 — Decision Formation Boundary

Status: IN REVIEW

## Objective

Establish the immutable and abstract boundary that relates existing decision
facts and Phase 4 Objective/Capability evidence to one Phase 5 semantic intent
candidate.

TASK-062 defines contracts only. It introduces no concrete formation algorithm.

## Architecture

```text
DecisionContext
        +
ObjectiveCapabilityActivationComposition
        +
explicit active CapabilityDescriptor
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

## DecisionFormationInput

A frozen, slotted dataclass containing exactly:

- `source_context: DecisionContext`;
- `composition: ObjectiveCapabilityActivationComposition`;
- `capability: CapabilityDescriptor`.

All three fields preserve exact caller-supplied object identity. `capability`
must be the exact object present in
`composition.active_capabilities.active_capabilities`. A descriptor that is
equal by value but reconstructed, inactive, or absent is rejected with
`ValueError`.

Invalid field types raise `TypeError` with the field name.

## DecisionIntentCandidate

A frozen, slotted dataclass containing exactly:

- `formation_input: DecisionFormationInput`;
- `intent: decision_formation.DecisionIntent`.

The candidate preserves both exact input references. It does not copy,
reconstruct, serialize, normalize, resolve, constrain, execute, or explain the
intent.

## DecisionFormationBoundary

An abstract, stateless boundary with empty slots:

```python
def form(
    self,
    formation_input: DecisionFormationInput,
) -> DecisionIntentCandidate: ...
```

No concrete production implementation is introduced. A future implementation
may form a candidate, but TASK-062 defines only the extension contract.

## Descriptor and implementation separation

`DecisionFormationInput.capability` is provenance only. A
`CapabilityDescriptor` is not a Capability implementation, factory, registry
key, policy, optimizer, or executable object. TASK-062 performs no descriptor
lookup and owns no implementation.

## Identity contract

```text
formation_input.source_context is original_context
formation_input.composition is original_composition
formation_input.capability is original_active_capability

candidate.formation_input is original_formation_input
candidate.intent is original_intent
```

The contract applies only to direct input/output relationships. It does not
claim an automatic Mapping, Discovery, Matching, Activation, or implementation
binding chain.

## Dependency direction

Allowed production dependencies are stable contracts only:

```text
decision_formation.input
    -> kernel.decision.context
    -> objective.activation_composition
    -> capability.descriptor

decision_formation.candidate
    -> decision_formation.input
    -> decision_formation.intent

decision_formation.boundary
    -> decision_formation.input
    -> decision_formation.candidate
```

Kernel, Objective, and Capability packages do not depend on Decision Formation.

## Non-goals

- Concrete formation algorithm or charge/discharge rule.
- Capability implementation access, creation, selection, or execution.
- Objective priority, ranking, scoring, weighting, or conflict resolution.
- Candidate collection or Intent resolution.
- Constraint evaluation or physical feasibility.
- Optimization, forecasting, or scheduling.
- Command generation, Runtime, Dispatch, Device, PCS, BMS, CAN, Modbus, MQTT,
  persistence, telemetry, cache, or history.

## Validation

Required checks cover:

- exact context, composition, capability, input, and intent identities;
- inactive/absent capability rejection;
- equal-but-reconstructed descriptor rejection;
- invalid type rejection;
- frozen/slotted field contracts;
- abstract signature and empty slots;
- no concrete production boundary implementation;
- contract-only dependencies;
- public exports and full regression suite.
