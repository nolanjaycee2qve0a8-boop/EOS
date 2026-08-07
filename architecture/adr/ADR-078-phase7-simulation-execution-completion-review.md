# ADR-078 — Freeze Phase 7 Deterministic Simulation Execution

Status: Accepted

## Context

TASK-075 through TASK-079 introduced explicit model binding, deterministic
single-step execution, immutable execution evidence, caller-ordered scenario
execution, and caller-owned step progression. TASK-080 validated these
contracts together with test-only models.

Before later phases add new boundaries, EOS needs an explicit completion record
that states what Phase 7 guarantees and what remains outside its ownership.

## Decision

Freeze Phase 7 as a deterministic, caller-controlled simulation execution
architecture.

The frozen guarantees are:

- callers supply all steps, model bindings, ordering, time facts, and next-step
  inputs;
- complete bindings are validated before component execution;
- every component executes exactly once per successful explicit step;
- scenario execution preserves caller step order;
- completed steps are observed through immutable structural traces;
- progression only relates completed evidence to an exact caller-supplied next
  input;
- direct provenance is identity based and rejects reconstructed substitutes;
- component failures stop execution and propagate unchanged.

Identity preservation is scoped to each contract's direct fields. Phase 7 does
not claim that a trace independently proves model invocation because component
results do not carry model identity.

No production code or API change is required for this decision. TASK-081 only
records the reviewed architecture in Markdown.

## Consequences

- Phase 7 has a stable baseline for future architecture work.
- Simulation remains deterministic without owning Runtime lifecycle.
- Scenario ordering cannot be interpreted as automatic step generation.
- Progression cannot be interpreted as clock advancement or scheduling.
- Runtime, Device execution, persistence, strategy, optimization, and forecast
  require separate future boundaries.
- Existing Phase 5, Phase 6, and simulator public contracts remain unchanged.

## Rejected alternatives

### Add a production completion service

Rejected because completion review requires evidence and documentation, not a
new orchestration layer.

### Treat scenario execution as Runtime

Rejected because a caller-provided finite tuple is not lifecycle, clock,
scheduler, thread, queue, or automatic loop ownership.

### Let simulation generate the next step

Rejected because TASK-079 freezes progression as a relationship to an exact
caller-supplied input.

### Describe identity as value equality

Rejected because reconstructed equal-field artifacts do not preserve direct
provenance.
