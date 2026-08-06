# ADR-071 — Freeze the Phase 6 Simulation Contract Architecture

Status: Accepted

## Context

TASK-065 through TASK-073 established explicit simulation step/time facts,
independent PV/Load/Tariff/Battery/Grid contracts, aggregate evidence, and
integration validation. Before future simulation behavior is introduced, EOS
needs a stable statement of what Phase 6 provides and what it intentionally
does not own.

Without a freeze, future model or runner work could silently move clocks,
state progression, device execution, power balance, or physics into immutable
artifacts and weaken the identity lineage already established.

## Decision

Accept and freeze the Phase 6 contracts as an immutable simulation observation
architecture.

The architecture preserves these direct identity relationships:

```text
component input -> exact SimulationStepIdentity
component result -> exact component input
aggregate state -> exact component results
step result -> exact aggregate input and state
scenario -> exact caller tuple and ordered step inputs
```

Battery simulation additionally preserves:

```text
exact FeasibleDecisionIntent
        -> BatterySimulationActuation
        -> BatterySimulationInput
        -> BatterySimulationResult
```

The model boundaries remain abstract and stateless. Production models,
execution coordination, and step progression are not part of the frozen
contract set.

Simulation remains distinct from Runtime and Device Execution:

- Simulation represents deterministic model inputs, responses, and immutable
  state observations.
- Runtime would own invocation lifecycle and failure coordination.
- Device Execution would own external commands and physical side effects.

No layer may infer that a simulation actuation is a Device Command.

## Consequences

- Future component models can be substituted behind stable contracts.
- One-step evidence can be audited through exact identity rather than value
  reconstruction.
- Test-only integration models prove contract composition without becoming
  production implementations.
- A future runner must be introduced separately and cannot hide inside
  aggregate artifacts.
- Physics, balance, progression, persistence, and device behavior remain
  explicit future decisions.

## Rejected alternatives

### Treat SimulationScenario as an executable runner

Rejected because the scenario is immutable caller-ordered input evidence, not
a loop, scheduler, or history owner.

### Reconstruct inputs or states by value

Rejected because value equality cannot prove provenance and would break exact
identity contracts.

### Let aggregate artifacts execute component models

Rejected because aggregation is observation-only and must not cause duplicate
model execution.

### Treat BatterySimulationActuation as a device command

Rejected because feasible decision, simulation actuation, and external command
belong to separate architectural layers.

### Add production physics during completion review

Rejected because TASK-074 freezes and documents existing contracts only.

