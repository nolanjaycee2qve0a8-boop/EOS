# ADR-008 — Immutable Energy System Context

## Status

Accepted

## Context

Future EMS decisions require a unified deterministic system input. Passing
asset definitions, operational observations, and power flow as unrelated
arguments would weaken the input boundary and make it easier for policies to
receive inconsistent collection types or incomplete asset observations.

The existing kernel already defines immutable EnergyAsset models, three
immutable operational state models, and immutable PowerFlow. It does not define
a common EnergyState base class.

## Decision

Introduce EnergySystemContext as a frozen slotted aggregate containing:

- an ordered tuple of EnergyAsset instances;
- an ordered tuple of BatteryState, PVState, or LoadState instances; and
- one validated PowerFlow instance.

Require every asset_id to occur in the state tuple. Preserve caller tuple
identity, ordering, duplicate entries, and additional states. Do not sort,
deduplicate, infer asset-state type relationships, or calculate missing data.

Represent the existing state models with an internal type union instead of
introducing a new inheritance hierarchy.

## Consequences

- Future decision processing has one clear immutable input boundary.
- Collection types and minimum asset-state coverage are deterministic.
- Policies remain independent from runtime mutation and data acquisition.
- Callers retain responsibility for ordering and observation consistency.
- Additional state reconciliation rules require a separate architecture decision.

## Alternatives Considered

- Passing many arguments: rejected because it disperses validation and weakens
  the decision input boundary.
- Mutable runtime context: rejected because mutation would undermine replay and
  deterministic decision inputs.
- Hidden power or state calculations: rejected because context only aggregates
  existing observations.
- Adding an EnergyState base class: rejected for this task because the existing
  concrete state models are already stable and no hierarchy was specified.
- Automatic sorting or deduplication: rejected because caller ordering must be
  preserved and no canonical ordering rule exists.
