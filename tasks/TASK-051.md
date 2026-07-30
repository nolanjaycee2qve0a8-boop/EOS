# TASK-051 — Phase 3 Decision Flow Integration Validation

Status: IN REVIEW

## Objective

Validate the complete EOS Phase 3 decision flow with existing production
boundaries and implementations:

```text
Capability
        |
        v
Capability Composition
        |
        v
Intent Resolution
        |
        v
DecisionIntent
        |
        v
Constraint Pipeline
        |
        v
Constraint Explanation Chain
        |
        v
Decision Evaluation Cycle
```

This task adds integration validation only. It does not add a production
algorithm, boundary, capability, resolver, constraint, or orchestration
service.

## Scenarios

### PV surplus and selected charge intent

The test composes the existing `TOUEnergyCapability` and
`SelfConsumptionCapability`, explicitly selects the Self Consumption
candidate through `DeterministicIntentResolutionImplementation`, and evaluates
the selected positive charge intent through:

- `BatteryConstraintImplementation`;
- `GridPowerLimitConstraintImplementation`;
- `ConstraintEvaluationPipeline`;
- `ConstraintExplanationChain`; and
- `DecisionEvaluationCycle`.

The battery constraint reduces the requested charge magnitude. The Grid
constraint observes the exact battery-feasible intent and leaves it unchanged.

### PV deficit and discharge adjustment

The test composes the same existing capabilities in caller order, explicitly
selects the negative Self Consumption candidate, and evaluates it through the
same existing constraint and evidence layers.

The battery constraint reduces the discharge magnitude. The Grid constraint
receives that exact adjusted intent and leaves it unchanged.

## Identity contracts validated

The integration tests verify:

- each capability receives the exact `DecisionContext`;
- composition preserves each returned candidate identity;
- resolver output is the exact selected candidate;
- `DecisionContextResult.intent` is the exact resolved intent;
- `DecisionEvaluationCycle.source_intent` is the exact result intent;
- each constraint receives the previous exact feasible inner intent;
- each explanation entry stores the exact stage input and output;
- the explanation chain stores the exact final feasible wrapper;
- the cycle stores the exact source and feasible artifacts; and
- adjusted intents are new immutable objects while source intents remain
  unchanged.

## Execution contracts validated

- Caller order controls capability and constraint order.
- Each capability executes exactly once.
- Each constraint executes exactly once.
- Explanation construction does not re-execute constraints.
- Cycle construction does not re-execute capabilities, resolution, or
  constraints.

Test-only probes record calls and exact references. They do not introduce
production capabilities or constraints. The test-only sequential composition
implements the existing abstract composition contract without adding a
production composition strategy.

## Files

- `tests/integration/test_phase3_decision_flow.py`
- `tasks/TASK-051.md`
- `docs/EOS_学习手册.md`
- `docs/EOS_架构说明.md`
- `docs/TASK演进记录.md`

## Non-goals

- No new Capability.
- No new Resolver.
- No new Constraint.
- No new EMS algorithm.
- No modification to `DecisionIntent`.
- No modification to Policy contracts.
- No modification to Evaluation contracts.
- No Runtime or Legacy changes.
- No optimization, forecasting, dispatch, PCS/BMS, or device control.

## Validation

Run:

```text
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
```
