# TASK-075 — Simulation Model Binding Contract

Status: IN REVIEW

## Objective

Establish the first Phase 7 contract for explicitly relating an existing
simulation component model boundary to an exact caller-supplied model instance.

Binding expresses an ownership/reference relationship only. It does not
execute, select, create, or manage models.

## Architecture

```text
existing component model boundary
        +
caller-supplied model instance
        |
        v
SimulationModelBinding
        |
        v
caller-ordered tuple
        |
        v
SimulationModelBindingCollection
```

The contract is implemented in the existing `simulator` package to preserve a
single Simulation architecture:

```text
simulator/binding.py
```

No parallel `simulation` package is created.

## SimulationModelBinding

`SimulationModelBinding` is an identity-based frozen and slotted dataclass
containing exactly:

- `component_contract` — one exact existing PV, Load, Tariff, Battery, or Grid
  abstract model boundary class;
- `model` — one caller-supplied instance implementing that exact boundary.

The caller model is preserved directly:

```text
binding.model is original_model
```

The binding does not copy, reconstruct, serialize, instantiate, register,
select, invoke, or manage the model.

`eq=False` prevents an equal-field reconstructed binding from substituting for
the original identity in membership checks.

## SimulationModelBindingCollection

`SimulationModelBindingCollection` is an identity-based frozen and slotted
dataclass containing exactly:

- `bindings: tuple[SimulationModelBinding, ...]`.

It preserves the exact tuple, exact binding objects, and caller order:

```text
collection.bindings is original_tuple
collection.bindings[index] is original_binding
```

Empty collections and repeated exact binding references are valid. The
collection does not sort, deduplicate, normalize, infer completeness, create a
registry, perform lookup, or execute a model.

## Identity validation

Membership semantics are identity based. A separately reconstructed binding,
even with the same component contract and exact same model reference, is not
the original binding and is not treated as a member of the caller tuple.

## Dependency direction

```text
simulator.binding
        -> simulator.pv
        -> simulator.load
        -> simulator.tariff
        -> simulator.battery
        -> simulator.grid
```

Component contracts do not depend on `simulator.binding`. Binding does not
depend on Runtime, Scheduler, Device, Command, Dispatcher, Optimization,
Capability, Policy, or Execution.

## Non-goals

- No Simulation Executor or component execution.
- No scenario runner, execution loop, or step progression.
- No registry, factory, reflection, string lookup, auto creation, auto
  selection, sorting, deduplication, or normalization.
- No production component model.
- No Runtime, Scheduler, Device, Command, Dispatcher, or protocol integration.
- No optimization, forecasting, EMS strategy, constraint evaluation, cache,
  or history.

## Tests

Focused tests cover:

- exact model identity;
- exact binding, tuple, element, and caller-order identity;
- reconstructed binding rejection;
- invalid contract, model, collection, and element types;
- frozen/slotted/tuple-only contracts and absence of `__dict__`;
- absence of registry, factory, model execution, and forbidden dependencies;
- public imports and full regression.

## Validation

```text
focused tests: 22 passed
pytest: 1305 passed
ruff check .: passed
ruff format --check .: passed (382 files)
mypy .: passed (235 source files)
pre-commit run --all-files: passed
```
