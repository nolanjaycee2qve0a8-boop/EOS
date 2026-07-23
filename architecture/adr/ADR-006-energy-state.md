# ADR-006 — Immutable Energy Operational State

## Status

Accepted

## Context

EOS needs current operational observations without adding mutable state to
the physical asset definitions established by ADR-005. Asset capability and
observed condition change at different rates and have different ownership.
Mixing them would weaken deterministic snapshots and couple domain definitions
to telemetry or controller behavior.

## Decision

Represent battery, photovoltaic, and load observations as separate immutable
state values keyed by AssetId. Group consistent system observations in an
immutable EnergySnapshot containing ordered tuples for each state category.

State values validate caller-supplied observations but perform no calculation.
EnergySnapshot preserves caller order rather than inventing a canonical sort.

## Consequences

- Physical asset definitions remain stable and algorithm independent.
- Operational observations can change by constructing new state values.
- Snapshot ordering is explicit, deterministic, and testable.
- Policies can eventually consume a consistent system observation.
- Telemetry collection and asset-definition matching remain external concerns.
- The existing DecisionPipeline contract is unchanged.

## Alternatives Considered

- Mutable state on EnergyAsset: rejected because it combines stable capability
  with changing observations.
- SOC calculation inside BatteryState: rejected because state values record
  observations and do not implement battery models.
- Lists inside EnergySnapshot: rejected because callers could mutate snapshot
  membership and ordering.
- Automatic sorting: rejected because no canonical cross-system ordering rule
  has been specified.
- Telemetry or persistence integration: deferred because acquisition and
  storage are outside this domain boundary.
