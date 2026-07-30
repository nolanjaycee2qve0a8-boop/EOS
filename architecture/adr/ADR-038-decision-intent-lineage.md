# ADR-038 - Decision Intent Lineage

## Status

Accepted

## Context

The original `DecisionEvaluationCycle` contract treated the policy intent and
the feasible intent as the same object. That assumption held while constraint
implementations only returned the supplied intent.

TASK-038 introduced `BatteryConstraintImplementation`. When a request is
blocked or clipped, it correctly preserves the original immutable policy
intent and creates a different immutable intent for the allowed power. The
cycle's former identity requirement therefore rejected a valid completed
constraint lifecycle.

## Decision

Replace the cycle field named `intent` with `source_intent`.

`source_intent` is the exact intent produced by policy:

~~~python
cycle.source_intent is cycle.result.intent
~~~

`feasible_intent` remains the exact wrapper returned by the constraint. Its
inner intent may preserve source identity when unchanged or differ when the
constraint blocks or clips the request:

~~~python
unchanged = cycle.feasible_intent.intent is cycle.source_intent
adjusted = cycle.feasible_intent.intent is not cycle.source_intent
~~~

Refine `ConstraintExplanation.create()` to accept both
`feasible_intent` and `source_intent`. The explanation and cycle preserve:

~~~python
cycle.explanation.feasible_intent is cycle.feasible_intent
cycle.explanation.source_intent is cycle.source_intent
~~~

No compatibility alias named `intent` is added to the cycle.

## Architecture

~~~text
DecisionContextResult
        |
        v
source DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
ConstraintExplanation
        |
        v
DecisionEvaluationCycle
~~~

## Consequences

- Original policy evidence remains available by exact object identity.
- Adjusted feasible intent remains available by exact object identity.
- Unchanged and adjusted constraint outcomes are both valid lifecycle states.
- `DecisionEvaluationOrchestrator` can complete a cycle after a real battery
  constraint adjustment.
- The cycle remains frozen, slotted, immutable, and observation-only.
- Existing policy, constraint, legacy, runtime, and execution ownership stays
  unchanged.

## Rejected Alternatives

- Mutate the policy intent: rejected because `DecisionIntent` is immutable and
  policy evidence must remain observable.
- Force the constraint to preserve identity after clipping: rejected because
  the adjusted power is a different semantic intent.
- Add a compatibility `intent` alias: rejected because it would preserve the
  ambiguity TASK-039 removes.
- Move SOC or power limiting into policy: rejected because policy expresses
  intention while constraints enforce physical feasibility.
- Modify `DecisionConstraintBoundary.evaluate`: rejected because the existing
  substitutable contract is sufficient.

## Non-goals

- EMS algorithm changes.
- New physical constraint rules.
- Runtime, execution, dispatch, command generation, or device control.
- Legacy `EMSPolicy` or `DecisionResult` migration.
- Persistence, telemetry, optimization, forecasting, cache, or history.
