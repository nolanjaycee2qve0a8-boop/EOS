# ADR-033 ? Decision Evaluation Cycle Boundary

## Status

Accepted

## Context

EOS now has immutable contracts for decision context, policy result, semantic
intent, feasible intent, and constraint explanation. Consumers need one stable
lifecycle boundary that preserves their relationships without introducing
execution responsibility.

## Decision

Introduce `DecisionEvaluationCycle` as a frozen, slotted model holding the
exact existing:

- `DecisionContext`;
- `DecisionContextResult`;
- source `DecisionIntent`;
- `FeasibleDecisionIntent`; and
- `ConstraintExplanation`.

Validate the represented chain with identity comparisons. The classmethod
factory stores `result.intent` as `source_intent` but performs no policy call, constraint
evaluation, copying, normalization, or state transition.

## Architecture

~~~text
DecisionContext
        |
        v
DecisionContextResult
        |
        v
source DecisionIntent
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

- One completed evaluation can be observed as a coherent immutable lifecycle.
- The exact policy source and feasible output identities remain available.
- An unchanged feasible intent may retain source identity; an adjusted
  feasible intent may have a different immutable identity.
- Invalid represented identity chains are rejected deterministically.
- Runtime, execution, policy, and constraint implementations remain
  independent.

## Rejected Alternatives

- Store the policy or constraint boundary: rejected because the cycle observes
  artifacts rather than owning behavior.
- Re-run evaluation during construction: rejected because construction must
  not execute lifecycle stages.
- Copy or serialize artifacts: rejected because copies lose identity evidence.
- Add commands or dispatch: rejected because executable behavior belongs to
  later layers.
- Infer context-result provenance: rejected because current result contracts
  do not retain that relationship and re-evaluation is forbidden.

## Non-goals

- EMS strategy, optimization, or forecasting.
- Commands, dispatch, device protocols, or execution.
- Runtime state, persistence, telemetry, cache, or history.
- Mutable lifecycle progression.
