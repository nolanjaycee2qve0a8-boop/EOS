# ADR-072 — Use Explicit Identity-Based Simulation Model Bindings

Status: Accepted

## Context

Phase 6 froze independent PV, Load, Tariff, Battery, and Grid model boundaries.
Future deterministic simulation execution needs a way for callers to state
which concrete model instances participate in one execution without giving an
executor responsibility for discovering, creating, selecting, or managing
those models.

A registry, factory, string name, or reflection mechanism would hide ownership
and selection. A value-based binding would also allow reconstructed artifacts
to masquerade as the exact caller-provided evidence.

## Decision

Introduce two contracts in `simulator.binding`:

- `SimulationModelBinding` relates one exact existing component boundary class
  to one exact caller-supplied model instance;
- `SimulationModelBindingCollection` preserves one exact caller tuple of exact
  bindings in caller order.

Both artifacts are frozen, slotted, and identity based (`eq=False`).

```text
binding.model is original_model
collection.bindings is original_tuple
collection.bindings[index] is original_binding
```

The component contract must be the exact PV, Load, Tariff, Battery, or Grid
boundary class, and the model must implement that contract. No name lookup or
reflection is used.

The collection accepts the caller tuple as supplied. It does not sort,
deduplicate, normalize, infer completeness, or select a model. Empty tuples and
repeated exact references are representation facts, not execution decisions.

Binding expresses an ownership/reference relationship only. It does not
execute, select, create, or manage models.

## Consequences

- Model ownership remains explicit at the caller boundary.
- Future execution can receive exact model references without a global
  registry or hidden factory.
- Caller order and duplicate references are preserved without interpretation.
- Reconstructed equal-field bindings cannot satisfy identity membership.
- TASK-075 provides no executor, loop, runner, or model lifecycle management.

## Rejected alternatives

### Registry or string lookup

Rejected because it introduces hidden global ownership and runtime resolution.

### Factory or automatic model creation

Rejected because callers, not the binding artifact, own model construction and
lifecycle.

### Value-based dataclass equality

Rejected because reconstructed bindings would compare equal and weaken exact
provenance.

### One fixed field per component

Rejected for this boundary because it would impose completeness and selection
semantics before the execution contract is designed.

### Execute models during binding construction

Rejected because binding is immutable relationship evidence, not execution.

## Non-goals

- Simulation execution, scenario running, or step progression.
- Model discovery, selection, registry, factory, reflection, or lifecycle.
- Runtime, Scheduler, Device, Command, Dispatch, or communication.
- Optimization, forecasting, EMS strategy, physical constraint, cache, or
  history.

