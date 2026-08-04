# TASK-059 — Objective-Capability Activation Composition

Status: IN REVIEW

## Objective

Add an immutable boundary that relates one exact objective descriptor to one
complete `ActiveCapabilityCollection`.

The composition expresses which already-active capabilities an objective uses.
It does not select, rank, prioritize, score, optimize, resolve conflicts,
execute capabilities, or generate an intent.

## Architecture

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

## Public contracts

### ObjectiveCapabilityActivationComposition

An immutable artifact containing exactly:

- `objective: ObjectiveDescriptor`;
- `active_capabilities: ActiveCapabilityCollection`.

Both exact input object references are preserved. The composition stores the
entire active collection rather than accepting a second capability subset, so
all active capability descriptors remain present without hidden selection or
omission.

The active collection already guarantees that its descriptors originate from
the exact matching result. The composition additionally rejects repeated
descriptor identities in its active tuple. Equal-but-reconstructed capability
descriptors cannot enter through a valid `ActiveCapabilityCollection`.

### ObjectiveCapabilityActivationCompositionBoundary

An abstract, stateless boundary:

```python
def compose(
    self,
    objective: ObjectiveDescriptor,
    active_capabilities: ActiveCapabilityCollection,
) -> ObjectiveCapabilityActivationComposition: ...
```

No concrete production composition implementation is introduced.

## Completeness and identity

- The exact objective object is preserved.
- The exact `ActiveCapabilityCollection` object is preserved.
- The exact nested active tuple, order, and descriptor identities are preserved.
- No capability subset is copied or reconstructed in the composition.
- Duplicate active descriptor identities are rejected.
- Empty active capability collections are valid and remain complete.

## Dependency direction

```text
objective.activation_composition -> objective.model
objective.activation_composition -> capability.activation
```

The Objective package may depend on stable Capability contracts. The Capability
package does not depend on Objective. There is no Constraint, Evaluation,
Runtime, Execution, Device, protocol, persistence, or telemetry dependency.

## Public API

```python
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveCapabilityActivationCompositionBoundary,
)
```

## Non-goals

- Capability selection, ranking, priority, scoring, or weighting.
- Optimization, conflict resolution, or fallback.
- Capability activation logic, implementation creation, or execution.
- `DecisionIntent` generation or resolution.
- Constraint, Runtime, Execution, Device, CAN, or Modbus integration.
- Persistence, telemetry, cache, or history.

## Validation

```text
pytest: 1027 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
pre-commit run --all-files: passed
```
