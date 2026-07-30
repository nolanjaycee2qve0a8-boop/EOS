# TASK-050 - Deterministic Intent Resolution Implementation

## Status

IN REVIEW

## Objective

Introduce the first concrete, replaceable implementation of
`IntentResolutionBoundary`.

The implementation resolves an immutable caller-supplied candidate tuple by
using one explicit, immutable zero-based candidate index. It returns the exact
selected `DecisionIntent` object.

## Architecture

~~~text
tuple[DecisionIntent, ...]
        +
immutable selected_candidate_index
        |
        v
DeterministicIntentResolutionImplementation
        |
        v
exact selected DecisionIntent
        |
        v
Constraint Layer
~~~

TASK-050 creates the resolver only. It does not connect Capability Composition,
Constraint, Evaluation, Runtime, or Device execution.

## Public Contracts

~~~python
@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionParameters:
    selected_candidate_index: int


@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionImplementation(IntentResolutionBoundary):
    parameters: DeterministicIntentResolutionParameters

    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent: ...
~~~

Public imports:

~~~python
from capability import (
    DeterministicIntentResolutionImplementation,
    DeterministicIntentResolutionParameters,
)
~~~

## Explicit Resolution Rule

`selected_candidate_index` is:

- a unitless integer;
- zero-based;
- greater than or equal to zero;
- supplied explicitly by the caller;
- required, with no default; and
- required to identify an existing tuple position when `resolve()` is called.

Resolution is:

~~~text
resolved_intent = candidates[selected_candidate_index]
~~~

The tuple order and index configuration are both caller-owned.

This is explicit positional selection, not an inferred capability priority.
The implementation does not inspect candidate values or capability origins.

## Candidate Contract

`candidates` must:

- be a tuple;
- contain only `DecisionIntent` objects; and
- contain the configured tuple position.

Wrong container or element types raise `TypeError`. Invalid parameter values or
an unavailable selected position raise `ValueError`. Error messages identify
`candidates` or `selected_candidate_index`.

## Identity Contract

The resolver returns the exact selected object:

~~~python
resolved is candidates[selected_candidate_index]
~~~

It does not:

- copy or reconstruct an intent;
- serialize or deserialize candidates;
- normalize, clip, sum, or average intent power; or
- mutate the candidate tuple or any intent.

Repeated references remain separate tuple positions.

## No Hidden Priority

The implementation contains no:

- capability name;
- capability type inspection;
- hard-coded TOU behavior;
- hard-coded Self Consumption behavior;
- implicit first/last candidate rule;
- priority table;
- weight;
- score;
- ranking;
- optimization objective; or
- arbitration based on intent values.

Changing the selected position requires a different immutable parameter object.

## Immutability and Statelessness

Both the parameters and implementation are frozen and slotted.

The implementation stores only the exact immutable parameters reference. It
owns no candidate tuple, result, capability, cache, history, runtime state,
dispatcher, device, or external service.

## Existing Contract Stability

TASK-050 does not modify:

- `IntentResolutionBoundary`;
- `DecisionIntent`;
- `EMSCapabilityBoundary`;
- `CapabilityCompositionBoundary`;
- TOU or Self Consumption capabilities;
- Policy contracts;
- Constraint contracts or implementations;
- Evaluation Integration or Cycle;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Dependency Direction

Allowed:

~~~text
DeterministicIntentResolutionImplementation -> IntentResolutionBoundary
DeterministicIntentResolutionImplementation -> DecisionIntent
~~~

Forbidden:

~~~text
Kernel -> deterministic resolver
deterministic resolver -> concrete Capability
deterministic resolver -> Constraint / Evaluation
deterministic resolver -> Runtime / Execution / Dispatch
deterministic resolver -> Device / Persistence / Telemetry
~~~

## Non-goals

- Capability-name or capability-type resolution.
- Hidden or hard-coded priority.
- Weighting, scoring, ranking, or value-based arbitration.
- Intent summation, averaging, clipping, or normalization.
- Optimization, MPC, forecasting, scheduling, or AI selection.
- TOU or Self Consumption special cases.
- SOC, battery power, Grid, export, or zero-export logic.
- Constraint or Evaluation execution.
- Runtime, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, cache, or history.

## Tests

Focused tests cover:

- implementation of the unchanged abstract boundary;
- explicit index selection across multiple positions;
- exact selected intent identity;
- caller tuple order preservation;
- repeated candidate positions;
- parameter type and non-negative validation;
- empty and out-of-range candidate tuples;
- candidate tuple and element validation;
- frozen/slotted parameters and implementation;
- exact parameter identity;
- no runtime state or forbidden dependencies;
- no TOU/Self Consumption special cases; and
- public imports.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
