# TASK-048 - Intent Resolution Boundary

## Status

IN REVIEW

## Objective

Introduce the abstract extension boundary through which an immutable tuple of
candidate `DecisionIntent` objects may later produce one resolved
`DecisionIntent`.

TASK-048 defines the seam only. It introduces no resolution implementation or
business arbitration behavior.

## Architecture

~~~text
tuple[DecisionIntent, ...]
        |
        v
IntentResolutionBoundary
        |
        v
DecisionIntent
        |
        v
Constraint Layer
~~~

Capability composition remains responsible for producing independent candidate
intents. A future resolution implementation may consume those candidates.
Physical feasibility remains owned by the Constraint layer.

## Public Contract

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

Public import:

~~~python
from capability import IntentResolutionBoundary
~~~

## Input Contract

`candidates` is an immutable tuple of existing `DecisionIntent` candidate
artifacts.

The boundary declaration:

- does not reorder candidates;
- does not deduplicate candidates;
- does not mutate candidates or their intent objects;
- does not execute capabilities to regenerate candidates; and
- does not store the tuple after the call.

TASK-048 does not define empty-, single-, or multi-candidate resolution
behavior. Those semantics belong to a future concrete implementation and its
own reviewed contract.

## Output Contract

The abstract return type is one immutable `DecisionIntent`.

TASK-048 does not decide:

- whether the returned object is one exact candidate;
- whether a future implementation may construct a new immutable intent;
- how conflicts are detected;
- what happens when no candidate exists; or
- what failure type a concrete strategy uses.

These are resolution-policy decisions and are intentionally absent from this
boundary-only task.

## No Resolution Algorithm

No production implementation is introduced.

The boundary does not define:

- priority or precedence;
- weight;
- score;
- ranking;
- winner selection;
- averaging or summation;
- conflict arbitration;
- fallback;
- optimization; or
- AI-based selection.

## Statelessness

The boundary:

- is abstract;
- uses empty slots;
- owns no fields or mutable containers;
- owns no candidates, cache, history, or runtime state;
- owns no Capability, Constraint, Evaluation, Runtime, Dispatcher, or Device
  instance; and
- introduces no concrete production resolver.

A frozen dataclass is not applicable because the boundary is a fieldless
abstract behavior contract.

## Existing Contract Stability

TASK-048 does not modify:

- `DecisionIntent`;
- `EMSCapabilityBoundary`;
- `CapabilityCompositionBoundary`;
- `TOUEnergyCapability`;
- Policy contracts;
- Constraint contracts or implementations;
- `ConstraintEvaluationPipeline`;
- `DecisionEvaluationIntegration`;
- `DecisionEvaluationCycle`;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Dependency Direction

Allowed:

~~~text
IntentResolutionBoundary -> DecisionIntent
~~~

Forbidden:

~~~text
Kernel -> IntentResolutionBoundary
IntentResolutionBoundary -> concrete Capability
IntentResolutionBoundary -> Constraint
IntentResolutionBoundary -> Evaluation
IntentResolutionBoundary -> Runtime / Execution / Dispatch
IntentResolutionBoundary -> Device / Persistence / Telemetry
~~~

## Non-goals

- Concrete intent resolver.
- Capability priority, weight, scoring, ranking, or scheduling.
- Arbitration, conflict resolution, or intent merging.
- Optimization, MPC, forecasting, or AI selection.
- TOU, self-consumption, SOC, battery, grid, PCS, or BMS logic.
- Constraint execution or feasibility enforcement.
- Evaluation integration or lifecycle recording.
- Runtime, command generation, dispatch, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.

## Tests

Focused tests cover:

- abstract boundary and exact signature;
- immutable tuple input and `DecisionIntent` return annotations;
- exact single-candidate identity through a test-only implementation;
- empty slots and absence of instance state;
- stable dependency direction;
- absence of a concrete production resolver; and
- public import.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
