# ADR-088 — Residential Edge Runtime Safety Contracts

## Status

Accepted for P0.1 interface and safety-contract work only.

## Context

Residential EMS 1.0 has frozen A-F simulation evidence. Future P0 work needs a
common boundary between cloud planning, an Edge host, eventual STM32/DSP code,
PCS/BMS telemetry and HIL without allowing a device protocol to leak into the
frozen control or Simulator contracts.

## Decision

Introduce an independent `edge_runtime` package with only standard-library,
immutable transport-neutral contracts and pure evaluation functions.

- Internal signed battery kW is charge-positive, discharge-negative and idle
  zero, matching `BatterySimulationResult.actual_power_kw`.
- Telemetry actual power is the authority for realised execution. Commands and
  ACKs remain separate evidence layers.
- BMS and PCS capabilities are supplied separately then intersected using
  non-negative directional magnitudes. The effective artifact is derived
  internally and cannot be supplied as a permissive evaluator input.
- A stateless safety evaluator applies hardware, BMS, PCS, Edge, user, EMS and
  economic precedence in that order and fails closed to a software zero-power
  request when safety cannot be demonstrated.
- Only `READY` runtime health admits active power. P0.1 blocks on `CRITICAL`
  active faults; this is an explicit software rule, not a safety certification.
- The command book is immutable, sequence-protected and idempotent. Completion
  requires an executing command's retained `execution_started_at`, matching
  actual telemetry inside the command validity window, and no later-than-expiry
  completion. Parsed records are evidence, never authoritative book hydration.
  Supersession atomically registers a valid successor whose sequence is higher
  than the book's global maximum; failed supersession leaves no partial write.
  The runtime-enforced transition table contains only states with P0.1 public
  producers; it has no generic transition API. P0.1 owns no persistent storage,
  clock or execution loop.
- Immutable data contracts use strict schema-bearing UTC serialization. Service
  objects are intentionally not persistence contracts.

## Consequences

- Later protocol adapters are explicit owners of registers, sign translation,
  retries, CRC and links.
- A future Runtime cannot claim actual execution from a successful ACK.
- A `SAFE_IDLE` software request cannot claim that hardware is safe or clear an
  emergency stop, PCS protection or BMS protection.
- This ADR creates no CAN, RS485, Modbus, MQTT, HTTP, PCS/BMS/DSP, HIL or
  production Runtime behaviour.

## Alternatives rejected

- Extending frozen Strategy, Simulator or Actuation contracts with device data.
- Treating accepted power in an ACK as actual power.
- Hiding stale/unknown facts as zero.
- Adding a concrete protocol adapter before protocol facts are supplied.
- Giving P0.1 a background loop, retry engine or durable command store.
- Restoring a command book from serialized record evidence without a separate
  durable-recovery ADR and replay contract.
