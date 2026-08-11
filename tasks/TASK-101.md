# TASK-101 — EMS End-to-End Integration Runner

## Objective

Compose existing Phase 9 EMS boundaries with the established deterministic
24-hour simulator without changing any strategy, feasibility, handoff, or
simulation contract.

## Flow

```text
caller-supplied daily facts
    |
    v
EMSContext
    |
    v
StrategyCoordinator
    |
    v
EMSDecision + DecisionProvenance
    |
    v
caller-supplied FeasibilityBoundary
    |
    v
caller-supplied ActuationHandoffBoundary
    |
    v
existing deterministic step execution
```

## Contracts

`EMSIntegrationScenarioInput` preserves exact daily facts, active objective/
capability evidence, and caller-provided DecisionContext facts. The runner has
empty slots and accepts a caller-owned coordinator, feasibility implementation,
and handoff implementation; it adds no concrete feasibility rule.

Each `EMSIntegrationStepTrace` preserves exact references for the Context,
Decision, DecisionProvenance, FeasibleDecision, ActuationHandoffResult, and
SimulationExecutionTrace. `EMSIntegrationResult` preserves the exact daily
simulation result and all 24 exact integration traces.

## Non-goals

- no new strategy, optimizer, forecast, MPC, or feasibility algorithm;
- no SOC limit or power-clipping logic beyond the existing battery model;
- no cloud, device, command, dispatcher, or runtime integration;
- no modification to Phase 5–8 public contracts or established simulator
  behavior.

## Validation

- 24 caller-ordered steps with one Strategy, Feasibility, and Handoff call per
  step;
- exact decision, provenance, feasible decision, handoff, actuation, and trace
  identity lineage;
- valid SOC range and frozen grid power-balance convention;
- deterministic repeatability, immutable results, and stateless runner;
- full pytest, Ruff, mypy, and diff validation.
