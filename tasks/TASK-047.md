# TASK-047 - EMS Capability Composition Boundary

## Status

IN REVIEW

## Objective

Introduce the abstract boundary for deterministic composition of multiple EMS
capabilities.

TASK-047 defines ordered, exactly-once capability evaluation without selecting,
scoring, optimizing, or resolving the resulting business intents.

It introduces no concrete production composition implementation.

## Architecture

~~~text
DecisionContext
        +
caller-supplied tuple[EMSCapabilityBoundary, ...]
        |
        v
CapabilityCompositionBoundary
        |
        v
tuple[DecisionIntent, ...]
~~~

The output tuple preserves one exact intent per input tuple position. TASK-047
does not collapse multiple intents into one final intent.

## Public Contract

~~~python
class CapabilityCompositionBoundary(ABC):
    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        context: DecisionContext,
        capabilities: tuple[EMSCapabilityBoundary, ...],
    ) -> tuple[DecisionIntent, ...]:
        raise NotImplementedError
~~~

Public import:

~~~python
from capability import CapabilityCompositionBoundary
~~~

## Ordering Contract

- The caller supplies an immutable capability tuple.
- Tuple position is the authoritative evaluation order.
- A conforming implementation does not sort or reorder capabilities.
- A conforming implementation does not deduplicate repeated capability
  positions.
- An empty tuple produces an empty intent tuple.

## Execution Contract

A conforming implementation:

1. receives the exact caller `DecisionContext`;
2. calls each capability tuple position exactly once;
3. supplies that exact context to each call;
4. preserves the exact returned `DecisionIntent`;
5. returns intents in the same tuple order; and
6. stops immediately and propagates the exact exception if a capability fails.

No capability is re-executed for comparison, explanation, selection, or
validation.

## No Resolution Semantics

The boundary returns an ordered intent tuple because TASK-047 has no authority
to decide which business objective wins.

It does not:

- choose one intent;
- merge intent values;
- sum or average battery power;
- assign priority or weight;
- score capabilities;
- resolve conflicts; or
- generate fallback business rules.

Any future intent resolution requires a separate explicit TASK and ADR.

## Statelessness

The abstract boundary:

- uses empty slots;
- owns no capability tuple;
- owns no mutable fields;
- owns no cache or history;
- owns no Policy, Constraint, Runtime, Dispatcher, or Device instance; and
- introduces no concrete production implementation.

A frozen dataclass is not applicable because the boundary is a fieldless
abstract behavior contract.

## Existing Contract Stability

TASK-047 does not modify:

- `EMSCapabilityBoundary`;
- `TOUEnergyCapability`;
- `DecisionContext`;
- `DecisionIntent`;
- Policy contracts;
- Constraint contracts or implementations;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationIntegration`;
- `DecisionEvaluationCycle`;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- Concrete production composition pipeline.
- Capability selection, priority, scoring, arbitration, or conflict resolution.
- TOU, self-consumption, peak shaving, zero-export, or pricing logic.
- SOC, battery power, grid, PCS, or BMS logic.
- Optimization, MPC, forecasting, or scheduling.
- Runtime, command generation, dispatch, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.

## Tests

Focused tests cover:

- abstract boundary and exact signature;
- caller tuple order;
- exactly-once evaluation per tuple position;
- repeated capability positions without deduplication;
- exact context and intent identities;
- empty composition;
- immediate exception propagation;
- empty slots and no instance state;
- dependency isolation;
- no concrete production composition; and
- public import.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
