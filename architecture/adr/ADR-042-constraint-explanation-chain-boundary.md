# ADR-042 - Constraint Explanation Chain Boundary

## Status

Accepted

## Context

TASK-042 introduced deterministic composition of multiple constraint
boundaries. The pipeline preserves final feasibility identity but does not
provide an ordered artifact describing what happened at each completed stage.

ADR-032 deliberately kept `ConstraintExplanation` free of reason text and
derived analysis. Mutating that stable contract would break existing cycle
consumers. Executing constraints again to create explanations would also turn
observation into re-evaluation.

EOS needs a separate immutable boundary that can preserve ordered completed
stage evidence and explicit reasons without changing existing lineage.

## Decision

Introduce two independent immutable artifacts:

~~~python
@dataclass(frozen=True, slots=True)
class ConstraintExplanationEntry:
    source_intent: DecisionIntent
    feasible_intent: FeasibleDecisionIntent
    adjusted: bool
    adjustment_reason: str | None


@dataclass(frozen=True, slots=True)
class ConstraintExplanationChain:
    source_intent: DecisionIntent
    entries: tuple[ConstraintExplanationEntry, ...]
    feasible_intent: FeasibleDecisionIntent
~~~

An entry observes one already completed constraint stage. Its adjusted flag is
validated against exact object identity:

~~~python
adjusted = feasible_intent.intent is not source_intent
~~~

The caller supplies the adjustment reason. The entry never derives, normalizes,
or interprets it. Adjusted entries require a non-empty reason; unchanged
entries require `None`.

The chain receives an immutable tuple in authoritative caller order and
validates stage-to-stage identity continuity. It stores the exact source, tuple,
entries, and final feasible wrapper.

## Architecture

~~~text
source DecisionIntent
        |
        v
completed constraint stage results
        |
        v
ConstraintExplanationEntry tuple
        |
        v
ConstraintExplanationChain
        |
        v
immutable ordered explanation evidence
~~~

The chain is observation after evaluation. It is not part of constraint
execution and does not call `ConstraintEvaluationPipeline`.

## Identity Contract

- The first entry source is the exact chain source.
- Each next entry source is the exact previous feasible inner intent.
- The chain feasible wrapper is the exact final entry wrapper.
- An empty chain preserves source identity through its feasible wrapper.
- No intent, feasible wrapper, entry, or tuple is copied or reconstructed.

## Relationship to ConstraintExplanation

The existing `ConstraintExplanation` remains unchanged and continues to serve
`DecisionEvaluationCycle` as a two-reference observation boundary.

The new chain is an independent ordered artifact. It does not replace, extend,
alias, or adapt the existing class, and TASK-043 does not change the cycle
contract.

## Consequences

- Multiple completed constraint stages can be explained in deterministic order.
- Adjustment status has exact identity semantics rather than value semantics.
- Reasons remain explicit caller evidence rather than hidden inference.
- Existing source/feasible lineage remains stable.
- Future presentation or persistence boundaries may consume the immutable
  chain without changing its domain contract.

## Rejected Alternatives

- Add fields to `ConstraintExplanation`: rejected because it would change an
  accepted public contract and the cycle boundary.
- Ask constraints to return reasons: rejected because it would change
  `DecisionConstraintBoundary`.
- Re-run the pipeline while explaining: rejected because explanation is
  observation, not evaluation.
- Infer reasons from SOC, grid power, or limits: rejected because that adds
  constraint and diagnostic logic.
- Store entries in a list: rejected because explanation order must be
  immutable.
- Store constraint objects: rejected because the chain records artifacts, not
  implementation ownership.

## Non-goals

- Constraint selection, ordering, priority, or conflict resolution.
- Derived reasoning, diagnosis, recommendation, or analysis.
- TOU, pricing, optimization, MPC, forecasting, or scheduling.
- Runtime, command generation, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, logging, cache, or history.
- Changes to Policy, Constraint, Intent, Cycle, legacy, runtime, or execution
  contracts.
