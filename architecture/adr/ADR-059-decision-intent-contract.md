# ADR-059 — Phase 5 DecisionIntent Contract

## Status

Accepted

## Context

Phase 4 froze Objective and Capability descriptor evidence without generating
intent. Phase 5 needs a foundational semantic artifact before formation,
resolution, and constraint boundaries can be designed.

EOS already has `kernel.decision.DecisionIntent`, a Phase 3 numeric battery
power contract used by Capability, Constraint, and Evaluation code. Changing
that established type from power to semantic action would break reviewed
contracts and violate legacy isolation.

Decision Formation also must not encode charge or discharge through a device
power sign. Device sign conventions are not stable decision semantics, and an
intent must remain distinct from an executable command.

## Decision

Create an independent top-level `decision_formation` package exposing one
artifact:

```text
DecisionIntent
└── action: "charge" | "discharge" | "idle"
```

The model is a frozen, slotted dataclass. It accepts only the three exact action
strings and performs no normalization or alias conversion.

TASK-061 introduces no formation boundary or implementation.

## Semantic decision

- `charge` communicates charge intention;
- `discharge` communicates discharge intention;
- `idle` communicates neither charge nor discharge intention.

The action defines no power magnitude, power sign, device address, protocol
operation, physical feasibility, optimization result, or execution status.

## Intent and command separation

`DecisionIntent` is not a `Command`. Intent is a semantic decision artifact;
Command belongs to a future command-formation and execution boundary. No code
in TASK-061 converts, dispatches, executes, serializes, or journals the intent.

## Coexistence decision

The accepted public contracts are independent:

```text
Existing Phase 3:
kernel.decision.DecisionIntent(battery_power_intent_kw)

New Phase 5:
decision_formation.DecisionIntent(action)
```

The existing type and all consumers remain unchanged. No inheritance, adapter,
compatibility alias, automatic conversion, migration, or overload is added.
Later migration, if ever required, needs a separate TASK and ADR.

## Immutability and identity decision

- The model is frozen and slotted.
- It contains exactly one immutable string-literal field.
- It owns no mutable collection, cache, history, or runtime state.
- It has no reference field, so reference-identity lineage is not part of this
  artifact. Future wrappers must preserve the exact intent they receive.

## Dependency decision

The new artifact depends only on Python standard-library `dataclasses` and
`typing`. It has no dependency on Kernel, Objective, Capability, Constraint,
Optimization, Runtime, Execution, Dispatch, Device, PCS, BMS, or protocols.

## Consequences

- Phase 5 gains an explicit action vocabulary independent of device signs.
- Intent and Command remain separate architectural concepts.
- Future formation and resolution artifacts can reference one stable type.
- Phase 3 Capability and Constraint behavior remains unchanged.
- Two intentionally independent `DecisionIntent` contracts coexist and must be
  imported from their explicit package paths.

## Rejected alternatives

### Modify kernel.decision.DecisionIntent

Rejected because existing consumers rely on its numeric power contract.

### Use positive and negative power to encode action

Rejected because device power-direction conventions do not belong in semantic
Decision Formation.

### Add Command fields

Rejected because execution representation is a separate future boundary.

### Use an enum or normalize aliases

Rejected for TASK-061 because the minimal contract needs only one immutable
literal action field and exact invalid-input rejection.

## Non-goals

- Actual decision generation.
- Objective or Capability implementation access.
- Formation, resolution, or constraint evaluation.
- Optimization, forecasting, Runtime, Dispatch, Device, PCS, BMS, protocols,
  persistence, cache, or history.
