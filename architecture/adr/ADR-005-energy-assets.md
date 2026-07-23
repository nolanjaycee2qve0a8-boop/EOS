# ADR-005 — Immutable Energy Asset Definitions

## Status

Accepted

## Context

EOS needs explicit energy domain objects before implementing EMS policies,
controllers, scheduling, or hardware integration. Combining physical
definitions with mutable operating state or control behavior would couple the
stable kernel domain to evolving capabilities and infrastructure.

## Decision

Represent physical energy components as immutable domain assets.

EnergyAsset provides a shared explicit AssetId and non-empty name.
BatteryAsset adds rated energy capacity and charge/discharge power limits.
PVAsset and LoadAsset add rated power. These models contain definitions only;
they do not calculate, communicate, schedule, or control.

## Consequences

- Asset construction and comparison are deterministic.
- The domain model remains independent of EMS algorithms.
- Future policies and controllers can consume stable asset definitions.
- Operational observations remain separate Snapshot data.
- New asset behavior requires separate capability or runtime boundaries.

## Alternatives Considered

- Control logic inside assets: rejected because assets define physical
  components rather than runtime decisions.
- BMS behavior mixed with battery definition: rejected because BMS state,
  telemetry, and control evolve independently from rated asset properties.
- Communication concerns inside assets: rejected because Modbus, CAN, MQTT,
  and device adapters belong outside the kernel domain.
- SOC, SOH, voltage, current, and temperature fields: deferred because they
  are operational observations or calculated state, not TASK-006 definitions.
