# TASK-044 - Decision Evaluation Integration Boundary

## Status

IN REVIEW

## Objective

Integrate the existing decision boundaries into one complete deterministic
evaluation without changing their accepted contracts.

TASK-044 coordinates assembly, policy evaluation, one constraint pipeline run,
ordered explanation evidence, and cycle creation. It adds no EMS strategy,
physical constraint rule, runtime behavior, or device command.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult / DecisionIntent
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

## Public Entry Point

~~~python
DecisionEvaluationIntegration.evaluate(
    state,
    policy,
    constraints,
    *,
    constraint_adjustment_reasons,
    timestamp,
    battery_power_limit_kw,
    battery_energy_capacity_kwh,
    load_power_kw,
    electricity_price_cny_per_kwh,
    reserve_soc,
    export_limit_kw,
) -> DecisionEvaluationIntegrationResult
~~~

The integration is stateless and uses empty slots. Policy, constraints, and all
decision facts are caller supplied for each invocation.

## Evaluation Order

One successful call performs:

1. validate boundary inputs and reason configuration;
2. call `DecisionContextAssembler.assemble()` once;
3. call the supplied `DecisionContextPolicy.evaluate()` once;
4. call `ConstraintEvaluationPipeline.evaluate()` once;
5. evaluate each supplied constraint exactly once in caller tuple order;
6. create one `ConstraintExplanationChain`;
7. create the existing final `ConstraintExplanation`;
8. create one `DecisionEvaluationCycle`; and
9. return one immutable integration result.

Failures propagate immediately. Later stages do not execute.

## Constraint Reasons

`constraint_adjustment_reasons` is a caller-supplied tuple aligned by index
with the constraint tuple.

- Both tuples must have equal length.
- Every supplied reason is a non-empty string.
- The reason is used only if that stage changes intent identity.
- An unchanged stage records `None`, as required by TASK-043.
- Integration does not generate, normalize, rank, or analyze reasons.

## Single-execution Observation

The pipeline still owns deterministic constraint order. Integration supplies
private immutable observing decorators to that one pipeline call.

Each decorator:

1. delegates to its exact underlying constraint once;
2. receives the exact returned `FeasibleDecisionIntent`;
3. creates one immutable explanation entry; and
4. returns the exact feasible wrapper unchanged.

The completed entries are accumulated in a local immutable tuple. They are not
stored on the integration boundary and do not form cache, history, or runtime
state.

## Integration Result

~~~python
@dataclass(frozen=True, slots=True)
class DecisionEvaluationIntegrationResult:
    cycle: DecisionEvaluationCycle
    explanation_chain: ConstraintExplanationChain
~~~

The result validates:

~~~python
result.explanation_chain.source_intent is result.cycle.source_intent
result.explanation_chain.feasible_intent is result.cycle.feasible_intent
~~~

It preserves the exact cycle and chain. It copies or reconstructs neither.

## Existing Orchestrator

`DecisionEvaluationOrchestrator` remains unchanged. It continues to coordinate
the earlier single-constraint path and existing `ConstraintExplanation`.

TASK-044 adds an independent multi-constraint integration boundary. It does not
migrate, alias, adapt, or overload the existing orchestrator.

## Boundary Preservation

TASK-044 does not modify:

- `DecisionIntent`;
- `DecisionConstraintBoundary`;
- `FeasibleDecisionIntent`;
- `ConstraintEvaluationPipeline`;
- `ConstraintExplanation`;
- `ConstraintExplanationChain`;
- `DecisionEvaluationCycle`;
- `DecisionContextPolicy`;
- `DecisionEvaluationOrchestrator`;
- legacy `EMSPolicy` or `DecisionResult`; or
- runtime and execution paths.

## Non-goals

- New EMS strategy or policy implementation.
- Constraint algorithms, selection, priority, or conflict resolution.
- Optimization, MPC, forecasting, TOU, pricing, or scheduling.
- Runtime, command generation, dispatch, PCS/BMS, or device control.
- Persistence, telemetry, retry, rollback, cache, or history.

## Tests

Focused tests cover:

- complete context-to-cycle identity;
- multi-constraint stage order and exact lineage;
- exactly-once component execution;
- empty constraint composition;
- caller-supplied reason ownership;
- immediate policy and constraint failure propagation;
- invalid policy and constraint results;
- invalid constraint/reason configuration before assembly;
- immutable integration result identity;
- stateless integration and explicit facts;
- dependency isolation;
- existing contract stability; and
- public imports.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
