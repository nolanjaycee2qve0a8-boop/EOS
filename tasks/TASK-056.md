# TASK-056 — Capability Discovery Boundary

Status: IN REVIEW

## Objective

Add the minimal immutable boundary for reporting which capability descriptors
are available to a caller.

Discovery reports descriptor availability only. It does not discover hardware,
instantiate or execute capabilities, match objectives, select capabilities,
activate behavior, or generate a decision intent.

## Architecture

```text
CapabilityDiscoveryBoundary
        |
        v
AvailableCapabilityCollection
        |
        v
tuple[CapabilityDescriptor, ...]
```

## Public contracts

### AvailableCapabilityCollection

An immutable result containing exactly:

- `capabilities: tuple[CapabilityDescriptor, ...]`.

The result preserves the exact caller/provider-produced tuple, its order, and
the exact identity of every descriptor. Empty availability is valid. The model
does not copy, reconstruct, sort, deduplicate, normalize, or instantiate any
capability.

### CapabilityDiscoveryBoundary

An abstract, stateless boundary:

```python
def discover(self) -> AvailableCapabilityCollection: ...
```

No concrete production discovery implementation is introduced. The abstract
contract owns no state, cache, history, runtime, device connection, protocol
client, registry, or capability implementation.

## Discovery meaning

Discovery answers:

> Which immutable capability descriptors does a future provider report as
> available?

It does not answer:

- Which device is connected?
- Which capability matches an objective?
- Which capability should be selected or activated?
- What should the battery do?

## Dependency direction

```text
capability.discovery -> capability.descriptor
```

The discovery contract depends only on the existing descriptor contract. It
does not depend on concrete Capability implementations, Objective mapping,
Kernel, Constraint, Evaluation, Runtime, Execution, or Device layers.

## Public API

```python
from capability import AvailableCapabilityCollection, CapabilityDiscoveryBoundary
```

## Scope protection

TASK-056 does not modify `CapabilityDescriptor`, `EMSCapabilityBoundary`,
Capability Composition, Intent Resolution, Objective mapping, `DecisionIntent`,
Constraint, Evaluation, Runtime, Execution, or legacy EMS paths.

## Non-goals

- Device discovery or connection.
- CAN, Modbus, MQTT, HTTP, serial, PCS, or BMS access.
- Capability implementation instances, classes, factories, or execution.
- Objective-Capability matching.
- Capability selection, ranking, priority, scoring, or weighting.
- Capability activation.
- Optimization, intent generation, or intent resolution.
- Persistence, telemetry, registry state, cache, or history.

## Validation

```text
pytest: 981 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
pre-commit run --all-files: passed
```
