# ADR-047 - Intent Resolution Boundary

## Status

Accepted

## Context

TASK-047 established an abstract composition seam that can produce an ordered
tuple containing one exact `DecisionIntent` per capability position. It
deliberately does not decide which intent should continue into physical
feasibility evaluation.

The Constraint layer accepts one source intent. EOS therefore needs an explicit
architectural seam between independent capability candidates and a future
single resolved intent.

Putting resolution inside composition would erase the accepted separation
between deterministic capability evaluation and business conflict policy.
Putting it inside Constraint would make physical feasibility responsible for
choosing business objectives.

## Decision

Introduce an independent abstract contract:

~~~python
class IntentResolutionBoundary(ABC):
    __slots__ = ()

    @abstractmethod
    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent:
        raise NotImplementedError
~~~

TASK-048 defines only the boundary. No production implementation is added.

## Architecture

~~~text
CapabilityCompositionBoundary
        |
        v
ordered tuple[DecisionIntent, ...]
        |
        v
IntentResolutionBoundary
        |
        v
one DecisionIntent
        |
        v
Constraint Layer
~~~

## Contract Scope

The boundary fixes only:

- immutable tuple input;
- one `DecisionIntent` return value;
- a stateless abstract extension point; and
- dependency on the stable `DecisionIntent` contract.

It does not fix a concrete decision rule.

In particular, TASK-048 does not define behavior for empty, single, conflicting,
or equivalent candidate tuples. It does not require the resolved intent to be
an existing candidate and does not authorize construction of a new intent.
Those identity and failure semantics must be defined by the future concrete
resolution task.

## No Arbitration Semantics

The boundary contains no:

- priority or precedence table;
- weight;
- score;
- ranking;
- winner selection;
- averaging, summation, clipping, or normalization;
- optimization objective or solver;
- fallback;
- schedule;
- AI selection; or
- domain-specific business rule.

The method name `resolve` identifies the seam, not an implemented algorithm.

## Layer Ownership

~~~text
Capability Composition -> evaluate capabilities and preserve candidates
Intent Resolution       -> future business-resolution implementation seam
Constraint              -> enforce physical feasibility
Evaluation              -> preserve completed decision evidence
Runtime / Device        -> later lifecycle and external execution
~~~

TASK-048 changes none of the surrounding owners.

## Statelessness

`IntentResolutionBoundary` is abstract and empty-slotted. It stores no
candidate tuple, resolved intent, capability, constraint, cache, history,
runtime state, or external service.

No frozen dataclass is needed because this ADR introduces no data carrier.

## Dependency Direction

Allowed:

~~~text
capability.resolution -> kernel.decision.DecisionIntent
~~~

Forbidden:

~~~text
kernel -> capability.resolution
capability.resolution -> concrete capability
capability.resolution -> constraint / evaluation
capability.resolution -> runtime / execution / dispatch
capability.resolution -> device / persistence / telemetry
~~~

## Existing Contract Stability

The following remain unchanged:

- `DecisionIntent`;
- `EMSCapabilityBoundary`;
- `CapabilityCompositionBoundary`;
- concrete capability implementations;
- Policy contracts;
- Constraint contracts and implementations;
- Evaluation Integration and Cycle;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- EOS has an explicit seam between multi-capability candidates and one future
  source intent.
- Capability composition remains free of hidden arbitration.
- Constraint remains free of business-objective selection.
- Future resolution behavior requires an explicit implementation task and ADR.
- No current execution path changes.

## Rejected Alternatives

- Resolve inside `CapabilityCompositionBoundary`: rejected because composition
  only evaluates and preserves independent outputs.
- Resolve inside Constraint: rejected because physical feasibility must not
  choose business objectives.
- Return the first candidate: rejected because tuple position is not yet
  declared as priority.
- Sum or average candidates: rejected because this invents an EMS strategy.
- Add priority, weights, or scores now: rejected because TASK-048 is
  boundary-only.
- Add a concrete resolver now: rejected because no arbitration contract has
  been reviewed.

## Non-goals

- Concrete resolver or arbitration algorithm.
- Priority, scoring, ranking, weighting, scheduling, or optimization.
- TOU, SOC, battery, grid, PCS, BMS, or device logic.
- Constraint execution, evaluation integration, runtime, or dispatch.
- Forecasting, AI, persistence, telemetry, cache, or history.
