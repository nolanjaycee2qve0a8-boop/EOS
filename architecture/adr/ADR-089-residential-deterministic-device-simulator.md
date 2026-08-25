# ADR-089 — Residential Deterministic Device Simulator and Fault Injection

## Status

Accepted for P0.2 virtual-device validation only.

## Context

P0.1 defines fail-closed Edge contracts, but it does not prove how those
contracts behave when PCS/BMS facts, acknowledgement timing or actual response
become adverse. P0.2 needs repeatable fault evidence without attaching a real
protocol, clock, device or background Runtime to the frozen Residential EMS
1.0 control chain.

## Decision

Create `edge_runtime.device_simulator`, a deterministic caller-stepped logical
plant. It reuses P0.1 `PowerCommand`, capability, telemetry, health, fault,
safety and lifecycle contracts rather than creating parallel types.

- `VirtualClock` advances only through an explicit positive duration.
- Immutable `FaultSpecification` and canonical `FaultSchedule` use stable IDs
  and order same-time events by activation time, target, type and ID.
- Virtual BMS/PCS facts feed P0.1 safety before the virtual PCS emits an ACK
  and a later actual-telemetry fact.
- P0.2 applies a command only after an immediate, accepted, unexpired ACK;
  reject/drop/delay/expiry fail closed to zero actual power. This is simulator
  policy, not an assertion about every real PCS protocol. A real PCS can still
  execute when its ACK is delayed or lost, so future Runtime must retain actual
  telemetry as execution authority and reconcile ACK uncertainty separately.
- A centralized fault whitelist rejects unsupported target/parameter pairs;
  warning events are retained without blocking, while critical events block.
- SOC is integrated from actual signed kW, not command or ACK power. The model
  uses caller-supplied capacity and efficiencies and clamps at configured SOC
  limits with retained boundary evidence.
- Clearing a fault changes only future raw facts. No prior command is replayed,
  resent or treated as continuing intent.
- Steps sample faults at their explicit start time using `[activation, clear)`;
  no step is retroactively split by an intra-step fault transition.

## Consequences

- P0.2 is deterministic software validation, not a digital twin or HIL result.
- It owns no loop, retry, persistence, network, serial/CAN/Modbus/MQTT/HTTP
  adapter, thread, sleep or wall clock.
- P0.3 remains the separately approved owner of polling, bounded orchestration,
  transmission, ACK waiting and recovery ownership.
