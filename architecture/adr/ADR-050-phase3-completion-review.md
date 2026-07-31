# ADR-050 - Phase 3 EMS Capability Layer Completion Review

## Status

Accepted

## Context

TASK-045 through TASK-051 introduced and validated the EOS EMS Capability
Layer:

- an abstract capability boundary;
- deterministic TOU and Self Consumption capabilities;
- an abstract composition boundary;
- an abstract intent resolution boundary;
- a deterministic caller-index resolver; and
- end-to-end integration evidence through constraints, explanation, and the
  decision evaluation cycle.

Before future phases extend EOS, the repository needs an explicit checkpoint
that confirms the Phase 3 contracts remain separated from physical
feasibility, Runtime, Device control, and the legacy execution path.

## Decision

Accept and freeze the Phase 3 architecture at TASK-052.

The accepted flow is:

```text
DecisionContext
        |
        v
EMS Capability
        |
        v
ordered candidate intents
        |
        v
explicit Intent Resolution
        |
        v
source DecisionIntent
        |
        v
Constraint Pipeline
        |
        v
FeasibleDecisionIntent
        |
        v
Explanation Chain
        |
        v
DecisionEvaluationCycle
```

The freeze means:

- Capability generates semantic intent only.
- Composition preserves caller order and independent candidates.
- Resolution uses an explicit replaceable rule.
- Constraint owns physical feasibility.
- Evidence objects preserve completed identity relationships.
- Runtime and Device execution remain outside this flow.
- Legacy EMS execution remains isolated.

## Identity decision

The lifecycle is identity-based:

```text
resolved intent is selected candidate
cycle.source_intent is result.intent
next constraint input is previous feasible intent
chain.feasible_intent is final constraint result
cycle.feasible_intent is final constraint result
```

Value equality is not a substitute for these object relationships.

## Dependency decision

The accepted direction is:

```text
capability -> kernel decision contracts
```

The following reverse dependency is prohibited:

```text
kernel -> capability implementation
```

Capability implementations must not depend on Runtime, Dispatch, Device,
Persistence, or legacy execution.

## Evidence

TASK-051 supplies end-to-end validation for both charge and discharge flows.
Its test-only probes confirm exactly-once Capability and Constraint execution.
Explanation and Cycle construction occur after those counts are complete and
do not trigger re-execution.

The full repository validation at the checkpoint is:

```text
pytest: 918 passed
ruff check .: passed
ruff format --check .: passed
mypy .: passed
```

## Documentation correction

The architecture guide introductory scope was stale at TASK-037 while the
document body already covered Phase 2 and Phase 3. TASK-052 updates that
statement to TASK-052. This is a documentation-only consistency correction.

## Consequences

- Phase 3 has an explicit accepted completion point.
- Future capability implementations can evolve behind stable contracts.
- Changes to the frozen contracts require a separate TASK and architecture
  review.
- Physical feasibility remains independently testable.
- Runtime, Device, and legacy execution remain isolated.
- Identity lineage remains an architectural invariant.

## Rejected alternatives

### Merge Capability and Constraint

Rejected because business intent and physical feasibility require independent
ownership and review.

### Add arbitration during the completion review

Rejected because completion review observes accepted contracts; it does not
introduce a strategy.

### Connect Capability directly to Runtime or Device control

Rejected because semantic intent is not an executable device command.

### Migrate legacy EMS contracts

Rejected because Phase 3 does not authorize migration of `EMSPolicy`,
`DecisionResult`, Runtime, or Execution.

## Non-goals

- New EMS algorithms.
- New capability composition or resolution strategies.
- Optimization, forecasting, or scheduling.
- Runtime, Dispatch, PCS/BMS, or Device integration.
- Persistence, telemetry, cache, or history.
