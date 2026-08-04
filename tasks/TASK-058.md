# TASK-058 — Capability Activation Boundary

Status: IN REVIEW

## Objective

Add an immutable boundary that represents active and inactive states for exact
capability descriptors from an already completed `CapabilityMatchCollection`.

Activation records status only. It does not rank, score, prioritize, select,
optimize, resolve conflicts, fall back, execute capabilities, or generate an
intent.

## Architecture

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

## Public contracts

### ActiveCapabilityCollection

An immutable artifact containing exactly:

- `source_collection: CapabilityMatchCollection`;
- `active_capabilities: tuple[CapabilityDescriptor, ...]`;
- `inactive_capabilities: tuple[CapabilityDescriptor, ...]`.

The source collection and both status tuples are preserved exactly. Every
descriptor in either status tuple must be the exact available descriptor from
a match in the source collection. Equal-but-reconstructed and unrelated
descriptors are rejected.

Every matched available descriptor must belong to exactly one status category:
active or inactive. Omission and overlap are invalid. An empty matched result
therefore has two empty status tuples.

### CapabilityActivationBoundary

An abstract, stateless boundary:

```python
def activate(
    self,
    matches: CapabilityMatchCollection,
) -> ActiveCapabilityCollection: ...
```

No concrete production activation implementation is introduced.

## Identity and immutability

- All production models are frozen and slotted.
- All collections are tuples.
- The exact source `CapabilityMatchCollection` reference is preserved.
- Active and inactive tuples, order, and descriptor identities are preserved.
- Membership and complete-status validation use identity comparisons.
- No copy, reconstruction, sorting, deduplication, or normalization occurs.

## Execution semantics

The abstract operation accepts one completed match collection per call and
returns one activation-status artifact. A test-only implementation verifies one
call produces one result. The boundary stores no cache, history, runtime state,
or implementation instance.

## Dependency direction

```text
capability.activation -> capability.matching
capability.activation -> capability.descriptor
```

There is no dependency on Objective, Kernel, Constraint, Evaluation, Runtime,
Execution, Device, CAN, Modbus, persistence, or telemetry.

## Public API

```python
from capability import ActiveCapabilityCollection, CapabilityActivationBoundary
```

## Non-goals

- Concrete activation rules or providers.
- Priority, ranking, scoring, weighting, or selection.
- Optimization, conflict resolution, or fallback.
- Capability implementation creation or execution.
- `DecisionIntent` generation or resolution.
- Constraint, Runtime, Execution, Device, CAN, or Modbus integration.
- Persistence, telemetry, cache, or history.

## Validation

```text
pytest: 1012 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
pre-commit run --all-files: passed
```
