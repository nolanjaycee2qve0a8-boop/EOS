# TASK-057 — Capability Matching Boundary

Status: IN REVIEW

## Objective

Add the immutable boundary that represents matching facts between required and
available capability descriptors.

Matching expresses relationships only. It does not rank, score, prioritize,
select, optimize, fall back, activate, execute, or generate an intent.

## Architecture

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

## Public contracts

### RequiredCapabilityCollection

An immutable collection containing exactly:

- `capabilities: tuple[CapabilityDescriptor, ...]`.

It preserves the exact caller tuple, caller order, and each descriptor identity.
Empty requirements are valid.

### CapabilityMatch

An immutable relationship containing exactly:

- `required: CapabilityDescriptor`;
- `available: CapabilityDescriptor`.

The model preserves both exact references. It does not explain how the
relationship was determined and contains no score, rank, priority, or fallback.

### CapabilityMatchCollection

An immutable artifact containing exactly:

- `required_collection: RequiredCapabilityCollection`;
- `available_collection: AvailableCapabilityCollection`;
- `matches: tuple[CapabilityMatch, ...]`.

Every match must reference exact descriptors from its respective source
collection. Equal-but-reconstructed descriptors are rejected. The exact source
collections, match tuple, order, match objects, and descriptor identities are
preserved. Empty matches are valid.

### CapabilityMatchingBoundary

An abstract, stateless boundary:

```python
def match_capabilities(
    self,
    required: RequiredCapabilityCollection,
    available: AvailableCapabilityCollection,
) -> CapabilityMatchCollection: ...
```

No concrete production matching implementation is introduced.

## Matching meaning

The output records caller/provider-produced facts of the form:

> This exact required descriptor is related to this exact available descriptor.

The boundary does not define comparison rules, name equality, compatibility,
selection, conflict handling, or behavior.

## Dependency direction

```text
capability.matching -> capability.descriptor
capability.matching -> capability.discovery
```

The matching contract depends only on immutable Capability descriptor and
availability contracts. It has no Objective, Kernel, Constraint, Evaluation,
Runtime, Execution, Device, protocol, persistence, or telemetry dependency.

## Public API

```python
from capability import (
    CapabilityMatch,
    CapabilityMatchCollection,
    CapabilityMatchingBoundary,
    RequiredCapabilityCollection,
)
```

## Non-goals

- Concrete matching algorithms or name comparison.
- Ranking, scoring, priority, weighting, or selection.
- Optimization, conflict resolution, or fallback.
- Activation, Capability execution, or instance creation.
- `DecisionIntent` generation or resolution.
- Device access, CAN, Modbus, PCS, BMS, or Runtime integration.
- Persistence, telemetry, cache, or history.

## Validation

```text
pytest: 995 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
pre-commit run --all-files: passed
```
