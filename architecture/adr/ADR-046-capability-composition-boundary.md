# ADR-046 - EMS Capability Composition Boundary

## Status

Accepted

## Context

TASK-045 established the abstract EMS capability extension point. TASK-046
proved that a concrete TOU capability can produce semantic
`DecisionIntent` without owning physical feasibility or execution.

Future EOS systems may evaluate more than one business capability for the same
immutable `DecisionContext`. EOS needs a stable composition seam before any
priority, arbitration, or conflict-resolution design is considered.

Combining multiple returned battery power values now would invent business
rules. Automatically choosing a capability would also couple composition to
specific EMS strategies.

## Decision

Introduce an independent abstract contract:

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

The result is an ordered tuple rather than a single resolved intent.

TASK-047 defines the contract only. No concrete production composition
implementation is added.

## Architecture

~~~text
exact DecisionContext
        +
caller-ordered capability tuple
        |
        v
CapabilityCompositionBoundary
        |
        v
ordered exact intent tuple
~~~

## Deterministic Contract

A conforming implementation must:

- treat caller tuple position as authoritative order;
- evaluate every tuple position exactly once;
- pass the exact same context object to every capability;
- preserve each exact returned intent object;
- return one intent per input tuple position;
- preserve duplicate capability positions rather than deduplicating; and
- stop and propagate the original exception on failure.

The empty capability tuple maps to the empty intent tuple.

## No Business Resolution

Composition is observation of ordered capability outputs, not resolution.

The boundary has no authority to:

- select a winner;
- sort by capability type;
- assign priority or score;
- merge, add, average, clip, or normalize power values;
- infer fallback intent;
- invoke Constraint for feasibility; or
- generate explanation reasons.

A future resolution layer requires explicit units, ownership, conflict
semantics, identity rules, failure behavior, TASK documentation, and an ADR.

## Statelessness

The boundary is abstract and empty-slotted. It stores no capability, context,
intent, cache, history, runtime state, or external dependency.

No frozen dataclass is introduced because the boundary adds no data carrier.
The capability tuple and returned tuple are immutable call artifacts supplied
or produced by future conforming implementations.

## Dependency Direction

Allowed:

~~~text
CapabilityCompositionBoundary -> EMSCapabilityBoundary
CapabilityCompositionBoundary -> DecisionContext
CapabilityCompositionBoundary -> DecisionIntent
~~~

Forbidden:

~~~text
CapabilityCompositionBoundary -> TOU implementation
CapabilityCompositionBoundary -> Constraint
CapabilityCompositionBoundary -> Evaluation Integration
CapabilityCompositionBoundary -> Runtime / Execution / Dispatch
CapabilityCompositionBoundary -> Device / Persistence / Telemetry
Kernel -> CapabilityCompositionBoundary
~~~

## Existing Contract Stability

The following remain unchanged:

- `EMSCapabilityBoundary`;
- `TOUEnergyCapability`;
- `DecisionIntent`;
- Policy contracts;
- Constraint contracts and implementations;
- Evaluation Integration and Cycle;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- EOS has an explicit multi-capability composition seam.
- Caller order and exactly-once semantics are reviewable before resolution
  behavior exists.
- Ordered intent identities remain available to a future resolution boundary.
- Capability, Constraint, Evaluation, Runtime, and Device ownership remain
  separate.
- No business conflict policy is silently introduced.

## Rejected Alternatives

- Return one intent: rejected because selecting or merging requires business
  semantics not authorized by TASK-047.
- Sum intent powers: rejected because capability goals may conflict and power
  addition is an invented strategy.
- Sort by capability class: rejected because the caller owns order.
- Deduplicate repeated instances: rejected because tuple position is the
  contract.
- Re-run capabilities for comparison: rejected because each position executes
  exactly once.
- Put composition in Constraint: rejected because physical feasibility does not
  own business capability ordering.
- Add a concrete implementation now: rejected because this task is
  boundary-only.

## Non-goals

- Capability arbitration, priority, scoring, or conflict resolution.
- TOU, SOC, battery, grid, PCS, or BMS logic.
- Optimization, MPC, forecast, or scheduling.
- Runtime, dispatch, commands, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.
