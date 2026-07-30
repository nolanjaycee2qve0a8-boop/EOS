# ADR-041 - Constraint Composition Boundary

## Status

Accepted

## Context

EOS now has independent battery and grid physical constraints. Applying only
one constraint at a time does not define how a decision passes through
multiple physical feasibility checks.

Embedding composition into Policy would expose physical ordering to strategy.
Embedding it into runtime would make execution reinterpret decisions. Storing
a mutable constraint chain would introduce ownership and lifecycle state.

EOS needs one explicit, deterministic, stateless composition boundary.

## Decision

Introduce:

~~~python
class ConstraintEvaluationPipeline:
    __slots__ = ()

    @staticmethod
    def evaluate(
        source_intent: DecisionIntent,
        constraints: tuple[DecisionConstraintBoundary, ...],
    ) -> FeasibleDecisionIntent: ...
~~~

The caller supplies an immutable tuple for each evaluation. Tuple position is
the authoritative order.

For every constraint:

1. call `evaluate()` exactly once;
2. validate the returned `FeasibleDecisionIntent`;
3. pass its exact inner intent to the next constraint; and
4. retain no reference after the call completes.

Return the exact final wrapper. For an empty tuple, construct one wrapper around
the exact source intent.

## Architecture

~~~text
DecisionContextResult.intent
        |
        v
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        +--> DecisionConstraintBoundary[0]
        |
        +--> DecisionConstraintBoundary[1]
        |
        +--> ...
        |
        v
final FeasibleDecisionIntent
~~~

## Identity Contract

- The source intent is never copied, reconstructed, serialized, or mutated.
- Each stage receives the exact previous stage's inner intent.
- The exact final `FeasibleDecisionIntent` is returned.
- When no constraint changes the intent, final inner identity remains the
  source identity.
- Existing source/feasible lifecycle boundaries remain responsible for
  observing both ends of the chain.

## Consequences

- Battery and grid constraints can be composed deterministically.
- Order remains explicit and caller-owned.
- Policy remains independent from constraint selection and ordering.
- Constraint implementations remain independently replaceable.
- Duplicate constraints execute in their supplied positions.
- Exceptions stop evaluation and propagate unchanged.
- No runtime state or execution behavior is introduced.

## Rejected Alternatives

- Store constraints on a mutable pipeline: rejected because it introduces
  retained lifecycle state and mutable ordering.
- Accept a list or arbitrary iterable: rejected because an immutable tuple
  makes the complete order explicit.
- Sort by constraint type or priority: rejected because it introduces hidden
  ordering policy.
- Deduplicate constraints: rejected because it changes caller intent.
- Evaluate constraints in parallel: rejected because each stage consumes the
  previous stage's exact output.
- Put composition in Policy: rejected because Policy must not know physical
  constraint order.
- Put composition in runtime: rejected because runtime must not reinterpret
  decision feasibility.

## Non-goals

- Optimization, MPC, forecasting, TOU, pricing, or scheduling.
- Constraint conflict resolution or priority algorithms.
- New battery or grid physical rules.
- Commands, dispatch, runtime, PCS/BMS, or device control.
- Persistence, telemetry, retry, rollback, cache, or history.
- Changes to intent, constraint, lineage, policy, legacy, or execution
  contracts.
