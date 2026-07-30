# ADR-043 - Decision Evaluation Integration Boundary

## Status

Accepted

## Context

EOS has stable independent boundaries for physical state, decision context
assembly, policy, deterministic constraint composition, ordered constraint
explanation, and lifecycle observation.

The earlier `DecisionEvaluationOrchestrator` coordinates one constraint and the
original two-reference `ConstraintExplanation`. Modifying it to own the new
multi-constraint explanation chain would migrate an accepted contract.

Calling each boundary ad hoc would also risk repeated constraint execution,
lost intermediate identities, inconsistent reason ownership, and different
failure behavior.

EOS needs one independent stateless integration boundary for the complete new
evaluation path.

## Decision

Introduce:

~~~python
class DecisionEvaluationIntegration:
    __slots__ = ()

    @staticmethod
    def evaluate(
        state: EnergySystemState,
        policy: DecisionContextPolicy,
        constraints: tuple[DecisionConstraintBoundary, ...],
        *,
        constraint_adjustment_reasons: tuple[str, ...],
        # Existing explicit DecisionContext facts
    ) -> DecisionEvaluationIntegrationResult: ...
~~~

The caller owns Policy, constraint instances, constraint order, adjustment
reasons, and all external decision facts.

The integration calls the existing assembler and Policy, then invokes
`ConstraintEvaluationPipeline.evaluate()` exactly once.

## Stage Observation

`ConstraintEvaluationPipeline` intentionally returns only the final feasible
wrapper. `ConstraintExplanationChain` requires every completed stage artifact.

To preserve both contracts, Integration supplies one private immutable
observing decorator per caller constraint. The pipeline evaluates those
decorators in caller order. Each decorator:

- delegates exactly once to the exact caller constraint;
- preserves the exact input and returned feasible wrapper;
- records one `ConstraintExplanationEntry` with the caller reason when
  identity changed; and
- returns the exact feasible wrapper to the pipeline.

The observation tuple exists only inside the synchronous call. No observer,
constraint, reason, or partial result is retained by the public boundary.

## Result

Introduce:

~~~python
@dataclass(frozen=True, slots=True)
class DecisionEvaluationIntegrationResult:
    cycle: DecisionEvaluationCycle
    explanation_chain: ConstraintExplanationChain
~~~

The result stores exact existing references and validates that the cycle and
chain share exact source and feasible identities.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContextPolicy
        |
        v
DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        v
ConstraintExplanationChain
        |
        v
DecisionEvaluationCycle
        |
        v
DecisionEvaluationIntegrationResult
~~~

## Identity Contract

- Policy receives the exact assembled context.
- Pipeline receives the exact policy result intent.
- Every constraint receives the exact previous feasible inner intent.
- Every explanation entry stores exact stage input/output references.
- Chain stores the exact source, entry tuple, and final feasible wrapper.
- Cycle stores the exact context, policy result, source, and final feasible
  wrapper.
- Integration result stores the exact cycle and chain.
- No lifecycle artifact is copied, serialized, or reconstructed.

## Failure Contract

- Configuration validation occurs before assembly.
- Policy failure prevents pipeline execution.
- Constraint failure stops the pipeline immediately.
- Failure prevents chain, cycle, and integration result creation.
- Exceptions propagate unchanged.
- No retry, rollback, or partial result is introduced.

## Existing Contract Stability

The following remain unchanged:

- `DecisionIntent`;
- `DecisionConstraintBoundary`;
- `ConstraintEvaluationPipeline`;
- `ConstraintExplanation`;
- `ConstraintExplanationChain`;
- `DecisionEvaluationCycle`;
- Policy contracts;
- `DecisionEvaluationOrchestrator`;
- legacy EMS and runtime/execution paths.

## Consequences

- EOS has one deterministic new-path evaluation entry point.
- Constraints execute exactly once through the existing pipeline.
- Ordered stage explanations correspond to that same execution.
- Cycle and explanation chain remain independently usable exact artifacts.
- Existing single-constraint orchestration and legacy execution remain stable.

## Rejected Alternatives

- Modify `DecisionEvaluationCycle` to store the chain: rejected because the
  cycle contract is stable.
- Modify Pipeline to return intermediate results: rejected because its final
  result contract is stable.
- Re-run constraints to explain them: rejected because explanation must
  correspond to the original execution.
- Let Integration call constraints directly: rejected because it would bypass
  the composition boundary.
- Generate reasons from state: rejected because reasons are caller supplied.
- Store Policy or constraints on Integration: rejected because the boundary is
  stateless.

## Non-goals

- EMS strategy, optimization, MPC, forecast, TOU, pricing, or scheduling.
- New constraint behavior or conflict resolution.
- Runtime, dispatch, commands, PCS/BMS, or device control.
- Persistence, telemetry, cache, history, retry, or rollback.
