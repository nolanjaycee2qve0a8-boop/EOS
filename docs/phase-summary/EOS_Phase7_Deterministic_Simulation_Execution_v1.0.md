# EOS Phase 7 Deterministic Simulation Execution v1.0

## 1. Phase goal

Phase 7 turns the immutable Phase 6 simulation contracts into a deterministic,
caller-controlled execution path without introducing Runtime, scheduling, or
Device execution.

The phase answers four questions:

1. Which caller-owned model instances participate?
2. How is one explicit step executed?
3. How is completed execution preserved as evidence?
4. How are explicit scenario order and caller-owned next-step provenance
   represented?

## 2. Completed tasks

### TASK-075 — Simulation Model Binding Contract

Relates exact component contract classes to exact caller-owned model instances.
Collections preserve the exact tuple and caller order without registry,
factory, selection, or execution.

### TASK-076 — Single-Step Simulation Executor Boundary

Validates complete bindings before model calls, invokes each model once in
caller binding order, and returns existing immutable aggregate state/result
contracts. Exceptions stop execution and propagate unchanged.

### TASK-077 — Simulation Execution Trace

Preserves exact input, bindings, state, and step-result references as
structurally completed evidence. Trace creation observes and does not execute.

### TASK-078 — Scenario Execution Boundary

Executes each explicit caller-supplied scenario step in caller order through
the single-step executor. It creates one distinct trace per completed tuple
occurrence and returns immutable complete scenario evidence.

### TASK-079 — Explicit Step Progression Contract

Relates exact previous evidence to an exact caller-supplied next input. It
validates Battery next-state/source-state identity without generating input,
advancing time, or executing the next step.

### TASK-080 — Phase 7 Integration Validation

Uses test-only models to validate the complete success, deterministic
observation, identity, progression, and failure chains. No production contract
is added or modified.

### TASK-081 — Phase 7 Completion Review

Freezes the reviewed Phase 7 guarantees and exclusions. This completion task
changes documentation only; Phase 5 contracts, Phase 6 contracts, simulator
production code, public APIs, and tests remain unchanged.

## 3. Frozen architecture

```text
caller-owned model instances
        |
        v
SimulationModelBindingCollection
        +
caller-owned SimulationScenario
        |
        v
ScenarioExecutionBoundary
        |
        v
SingleStepSimulationExecutor
        |
        v
SimulationStepResult
        |
        v
SimulationExecutionTrace
        |
        +---- caller-supplied next SimulationStepInput
        v
SimulationStepProgression
```

## 4. Ordering and execution semantics

- Scenario step order is caller-owned.
- Component binding order is caller-owned.
- No sorting, deduplication, selection, or inferred dependency exists.
- Each component runs exactly once per successful explicit step.
- Each explicit scenario occurrence runs exactly once on the successful path.
- Failure stops immediately and propagates the exact exception.
- No retry, skip, fallback, or implicit continuation exists.

## 5. Identity and provenance

Phase 7 preserves direct identities:

```text
scenario result -> exact caller scenario
scenario result -> exact caller bindings
trace -> exact scenario step
trace -> exact binding collection
trace -> exact step result/state/input
progression -> exact previous trace/result
progression -> exact caller next input
next Battery input source state -> exact previous Battery result next state
```

Identity is not value equality. Reconstructed equal-field previous results or
Battery states cannot replace the original provenance objects.

The trace remains structurally completed evidence. Current component results
do not embed model identities, so Phase 7 does not claim cryptographic or
independent proof that a particular model instance ran.

## 6. Determinism

Given the same explicit immutable facts and equivalent deterministic models,
independent executions produce the same observed values. Their result and
trace artifacts remain independent objects. Determinism does not require
global caching or reused evidence identity.

## 7. Failure semantics

A component exception:

- stops the current step;
- prevents later bindings and later scenario steps from running;
- propagates unchanged;
- returns no successful scenario result;
- does not trigger retry, rollback, recovery, or persistence.

Calls already made to caller-owned models are not hidden or undone.

## 8. Boundary separation

```text
Simulation != Runtime
Simulation != Device Execution
Scenario ordering != Step generation
Step progression != Time scheduling
Actuation != Command
```

Phase 7 owns no clock, scheduler, current pointer, thread, queue, real-time
loop, Device adapter, command dispatch, or lifecycle history.

## 9. Phase 7 non-goals

- Production PV, Load, Tariff, Battery, or Grid physics.
- Power-balance or SOC algorithms.
- Runtime or real-time scheduling.
- Automatic step generation or progression.
- Device/PCS/BMS control or protocols.
- EMS strategy, optimization, forecast, or decision making.
- Persistence, telemetry, replay, history, retry, or recovery.

## 10. Completion status

Phase 7 deterministic simulation execution architecture is integration-tested,
completion-reviewed, and frozen at TASK-081. Future work must preserve these
contracts and introduce any Runtime, scheduling, persistence, or Device
concerns through separate explicit boundaries.

The freeze is deliberately narrow: every artifact preserves the exact direct
references required by its own contract. Phase 7 does not assert an automatic
cross-boundary lineage beyond those validated relationships, and execution
traces remain structural evidence rather than independent proof of model
invocation.

## 11. Validation

- Focused Phase 7 integration tests: 3 passed.
- Full pytest: 1363 passed.
- Ruff check and format check: passed.
- mypy: passed.
- pre-commit: passed.
