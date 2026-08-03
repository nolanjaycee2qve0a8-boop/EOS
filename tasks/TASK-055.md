# TASK-055 — Objective-Capability Mapping Boundary

Status: IN REVIEW

## Objective

Add the immutable relationship boundary that describes which capability
descriptors can support an objective descriptor.

Mapping expresses relationships only. It does not select or execute a
capability and does not generate a decision intent.

## Architecture

```text
ObjectiveCollection / ActiveObjectiveCollection
        |
        v
ObjectiveCapabilityMappingBoundary
        |
        v
ObjectiveCapabilityMappingCollection
        |
        v
ObjectiveCapabilityMapping
        |
        +--> exact ObjectiveDescriptor
        |
        +--> tuple[CapabilityDescriptor, ...]
```

## Public contracts

### CapabilityDescriptor

An immutable capability contract containing exactly:

- `name: str`;
- `description: str`.

It contains no Capability implementation instance, execution method, score,
priority, weight, intent, or runtime state.

### ObjectiveCapabilityMapping

An immutable relationship containing:

- `objective: ObjectiveDescriptor`;
- `capabilities: tuple[CapabilityDescriptor, ...]`.

The exact objective descriptor, capability tuple, order, and descriptor
identities are preserved. An empty capability tuple is valid and does not
invent support.

### ObjectiveCapabilityMappingCollection

An immutable artifact containing:

- exact `ObjectiveCollection` or `ActiveObjectiveCollection` source;
- caller-produced tuple of exact mapping objects.

Every mapping objective must be an exact descriptor from the supplied source.
Equal-but-reconstructed descriptors are rejected.

### ObjectiveCapabilityMappingBoundary

An abstract, stateless boundary:

```python
def map_objectives(
    self,
    objectives: ObjectiveCollection | ActiveObjectiveCollection,
) -> ObjectiveCapabilityMappingCollection: ...
```

No concrete production mapping implementation is introduced.

## Dependency direction

```text
objective.mapping -> capability.descriptor
```

The mapping module imports the narrow descriptor contract directly. It does
not import or instantiate TOU, Self Consumption, composition, resolution, or
any other Capability implementation.

The reverse dependency is forbidden:

```text
capability -X-> objective
```

## Public API

```python
from capability import CapabilityDescriptor
from objective import (
    ObjectiveCapabilityMapping,
    ObjectiveCapabilityMappingBoundary,
    ObjectiveCapabilityMappingCollection,
)
```

## Scope protection

TASK-055 does not modify Kernel, `DecisionIntent`, `DecisionContext`,
Constraint, Evaluation, Runtime, Execution, or legacy EMS Policy.

## Non-goals

- Capability selection, ranking, or priority.
- Capability scoring or weighting.
- Capability optimization or execution.
- Intent resolution or generation.
- Concrete mapping rules.
- Runtime, Device, persistence, cache, or history.

## Validation

```text
pytest: 971 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
```
