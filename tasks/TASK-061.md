# TASK-061 — DecisionIntent Contract

Status: IN REVIEW

## Objective

Establish the immutable semantic intent artifact for EOS Phase 5 Decision
Formation without generating a decision or changing existing decision paths.

## Architecture

```text
Future Decision Formation
        |
        v
decision_formation.DecisionIntent
        |
        v
Future Resolution and Constraint Boundaries
```

TASK-061 creates only the artifact. Formation, resolution, constraint
evaluation, command formation, runtime, and execution remain outside scope.

## Public contract

```python
from decision_formation import DecisionIntent

DecisionIntent(action="charge")
DecisionIntent(action="discharge")
DecisionIntent(action="idle")
```

`DecisionIntent` is a frozen, slotted dataclass containing exactly one field:

```text
action: Literal["charge", "discharge", "idle"]
```

The contract performs no case folding, whitespace trimming, aliasing, or
normalization. A non-string action raises `TypeError`; any other string raises
`ValueError`.

## Semantic meaning

- `charge`: the decision semantics request charging;
- `discharge`: the decision semantics request discharging;
- `idle`: the decision semantics request neither charging nor discharging.

These values do not define power magnitude or positive/negative device power
direction. Device-specific sign conventions belong outside Decision Formation.

## DecisionIntent is not Command

The artifact expresses what action is intended. It does not contain or create:

- a `Command`;
- PCS or BMS instructions;
- CAN, Modbus, MQTT, or protocol data;
- device identity or address;
- execution or runtime state.

Future command formation must be a separate reviewed boundary.

## Coexistence decision

The existing `kernel.decision.DecisionIntent` numeric power contract remains
unchanged because Phase 3 Capability, Constraint, and Evaluation consumers use
it. TASK-061 introduces an independent Phase 5 public contract at
`decision_formation.DecisionIntent`. There is no inheritance, adapter, alias,
conversion, migration, or shared implementation between them.

## Immutability and identity

- The artifact is frozen and slotted.
- It has no mutable container, cache, history, or runtime state.
- It contains no reference field, so object-reference lineage is not applicable
  in TASK-061.
- Future artifacts that reference an intent must define identity preservation
  in their own direct input/output contracts.

## Dependency direction

`decision_formation.intent` depends only on Python standard-library
`dataclasses` and `typing`. It does not depend on Kernel, Objective, Capability,
Constraint, Optimization, Runtime, Execution, Dispatch, Device, PCS, or BMS.

## Non-goals

- Decision generation or policy evaluation.
- Capability implementation access.
- Objective-to-Intent formation.
- Intent resolution.
- Constraint evaluation.
- Optimization or forecasting.
- Command generation or execution.
- Runtime, Device, PCS, BMS, CAN, Modbus, MQTT, persistence, cache, or history.

## Validation

Required checks:

- valid action creation;
- invalid type and value rejection;
- frozen/slotted structure;
- exact field contract;
- no execution or analysis fields;
- standard-library-only dependency direction;
- public import and legacy isolation;
- full regression suite.
