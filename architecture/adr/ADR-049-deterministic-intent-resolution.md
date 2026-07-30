# ADR-049 - Deterministic Intent Resolution Implementation

## Status

Accepted

## Context

TASK-047 established deterministic production of independent capability intent
candidates. TASK-048 introduced `IntentResolutionBoundary` without choosing a
resolution strategy. TASK-049 added a second concrete capability, making
multiple simultaneous candidates a practical architecture concern.

EOS needs a first concrete resolver to prove that the resolution boundary is
replaceable. The first rule must be explicit and deterministic without
inventing capability names, weights, scores, optimization, or device behavior.

Using candidate tuple position as an unspoken priority would be hidden policy.
Hard-coding TOU or Self Consumption would couple the generic resolver to current
capability implementations.

## Decision

Introduce immutable caller parameters:

~~~python
@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionParameters:
    selected_candidate_index: int
~~~

Introduce the concrete resolver:

~~~python
@dataclass(frozen=True, slots=True)
class DeterministicIntentResolutionImplementation(IntentResolutionBoundary):
    parameters: DeterministicIntentResolutionParameters

    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent:
        return candidates[self.parameters.selected_candidate_index]
~~~

Production validation surrounds the conceptual return expression and rejects
invalid parameters, containers, elements, and unavailable positions.

## Architecture

~~~text
Capability candidates
        |
        v
tuple[DecisionIntent, ...]
        +
caller-owned immutable selected index
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

TASK-050 does not execute any surrounding layer.

## Parameter Contract

`selected_candidate_index` is a literal, unitless, zero-based integer.

It:

- rejects `bool` and non-integer values with `TypeError`;
- rejects negative values with `ValueError`;
- has no default;
- is immutable after construction; and
- must be less than the candidate tuple length during resolution.

The caller explicitly owns both candidate order and index selection.

## Deterministic Rule

For the same parameters and same candidate tuple:

~~~text
resolved is candidates[selected_candidate_index]
~~~

The resolver performs no value comparison. It does not infer intent meaning,
business objective, capability identity, or feasibility.

An index is configuration, not a hidden priority: the selected position is
visible in a required immutable public parameter rather than embedded in
control flow.

## Identity and Mutation

The exact candidate object is returned.

There is no:

- copy or reconstruction;
- serialization;
- power arithmetic;
- mutation;
- sorting or deduplication; or
- candidate regeneration.

The resolver validates every tuple element as `DecisionIntent` but does not
alter tuple order.

## Capability Independence

The resolver imports no concrete capability and contains no TOU or Self
Consumption name, branch, or special case.

Future capability additions therefore require no resolver change unless the
caller intentionally changes candidate order or selected index configuration.

## Constraint and Runtime Separation

The resolver does not read:

- SOC or reserve SOC;
- battery limits;
- Grid or export limits;
- time, price, forecast, or schedule; or
- runtime/device state.

The selected semantic intent still proceeds to Constraint for physical
feasibility. Resolution does not execute Constraint, Evaluation, Runtime,
Dispatch, PCS, BMS, or devices.

## Immutability and Statelessness

Parameters and implementation are frozen and slotted. The implementation
stores only the exact immutable parameters reference.

It owns no mutable collections, candidates, result, cache, history, runtime
state, capability, constraint, dispatcher, or device.

## Dependency Direction

Allowed:

~~~text
capability.deterministic_resolution -> capability.resolution
capability.deterministic_resolution -> kernel.decision
~~~

Forbidden:

~~~text
kernel -> capability.deterministic_resolution
capability.deterministic_resolution -> concrete capability
capability.deterministic_resolution -> constraint / evaluation
capability.deterministic_resolution -> runtime / execution / dispatch
capability.deterministic_resolution -> device / persistence / telemetry
~~~

## Existing Contract Stability

The following remain unchanged:

- `IntentResolutionBoundary`;
- `DecisionIntent` and its sign convention;
- Capability boundary and existing implementations;
- Capability Composition;
- Policy contracts;
- Constraint contracts and implementations;
- Evaluation Integration and Cycle;
- legacy EMS contracts; and
- runtime and execution paths.

## Consequences

- EOS gains its first replaceable concrete intent resolver.
- Resolution behavior is reviewable through immutable public parameters.
- Exact candidate identity is preserved.
- Current and future capabilities remain anonymous to the resolver.
- Constraint and execution ownership remain separate.

## Rejected Alternatives

- Always select the first candidate: rejected as hidden positional priority.
- Select by capability name: rejected because the resolver must remain
  capability-independent.
- Add weights or scores: rejected because no weighting contract exists.
- Sum or average intent power: rejected because it invents an EMS arbitration
  strategy.
- Choose maximum magnitude: rejected because intent values do not encode
  business priority.
- Read SOC or Grid facts: rejected because physical feasibility belongs to
  Constraint.
- Use optimization or forecast: rejected as outside TASK-050.

## Non-goals

- Priority, weighting, scoring, ranking, or value-based arbitration.
- TOU or Self Consumption special cases.
- Optimization, forecasting, scheduling, or AI selection.
- SOC, Battery/Grid constraints, export, or zero-export logic.
- Constraint/Evaluation execution, Runtime, Dispatch, or Device control.
- Persistence, telemetry, cache, or history.
