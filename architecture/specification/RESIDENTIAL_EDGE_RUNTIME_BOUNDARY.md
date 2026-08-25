# Residential Edge Runtime Boundary — P0.1

## Status and scope

P0.1 defines transport-neutral, immutable and serializable safety contracts for
the future Residential Edge Runtime. It is an interface boundary after the
Residential EMS 1.0 A-F simulation evidence and does not change the frozen
Strategy, MPC, optimizer, physical revision, Feasibility, Actuation or
Simulator chains.

P0.1 is not a PCS/BMS integration, HIL implementation, real-time service,
functional-safety certification or deployment claim.

## System boundary and authorities

```text
Cloud planner / EMS plan
        |  requested semantic power only
        v
P0.1 Edge safety contracts
        |  transport-neutral safe command request / evidence
        v
future protocol adapter  <-->  PCS / BMS actual telemetry
        |                       |
        |                       v
        +----------------> Edge evidence / next planning facts

future STM32/DSP is below the adapter boundary; it is not implemented here.
```

The authority order is fixed. A lower layer never overrides a higher layer:

1. hardware emergency stop, PCS internal protection and BMS protection;
2. BMS charge/discharge permission and limits;
3. PCS availability, derating, operating state and limits;
4. Edge local safety, data freshness and communication health;
5. explicit user safety or reserve-SOC constraints;
6. EMS control plan; then
7. economic, VPP or ancillary-service opportunity.

`actual_battery_power_kw` in `TelemetrySnapshot` is the execution fact.
An EMS plan, `PowerCommand.requested_battery_power_kw` and an accepted ACK are
not execution facts. Settlement, tracing and later planning must use actual
PCS/BMS telemetry once a future adapter supplies it.

## Sign, unit and time contracts

- Internal battery power is signed raw **kW**: positive is charge, negative is
  discharge and zero is idle. This matches the existing Simulator authority.
- `DeviceCapability` limits are non-negative **kW magnitudes**, one field per
  direction; they are never signed limits.
- `soc_fraction` and `soh_fraction` are either explicit unknown (`None`) or
  a finite fraction in `[0, 1]`. Unknown is never converted to zero.
- Existing EOS grid power remains positive import and negative export.
- Every timestamp is timezone-aware. Serialization uses UTC ISO-8601.
- `observed_at`, `received_at`, `issued_at`, `not_before`, `expires_at`, ACK
  time and `execution_started_at` are distinct concepts. Freshness uses
  `observed_at`, not receipt time alone.

Future adapters own register maps, byte order, scale factors, retries, CRC and
any protocol-specific sign reversal. Protocol facts are intentionally TBD in
P0.1; CAN, RS485, Modbus, MQTT and HTTP are not dependencies.

## Contract inventory

| Contract | Purpose | Does not mean |
| --- | --- | --- |
| `PowerCommand` | versioned requested signed power with stable id/sequence | actual execution |
| `CommandAcknowledgement` | receipt status for a known command | actual power reached |
| `TelemetrySnapshot` | observed device facts with explicit unknowns | forecast or plan |
| `DeviceCapability` / `EffectiveDeviceCapability` | exact BMS + PCS authority facts and their intersection | EMS feasibility result |
| `SafetyConstraint` / `SafetyDecision` | candidate command → evidence → allowed/clamped/idle request | PCS/BMS protection action |
| `FaultEvent` | auditable source/severity/code evidence | safety-standard certification |
| `RuntimeHealth` | caller-observed software readiness and fallback state | hardware state |
| `TimingPolicy` / `FreshnessEvaluation` | caller-supplied time policy and freshness evidence | hardware-certified threshold |

`DeterministicEdgeSafetyEvaluator` is pure and stateless. It sends nothing,
does not own a clock and does not treat the safe-idle request as confirmed idle.
Its `SAFE_IDLE` outcome is a software request only; local PCS/BMS protection
remains independent and cannot be cleared by EMS.

`EffectiveDeviceCapability` is not a caller-owned write model. The evaluator
receives separately typed BMS and PCS capability facts and derives their
restrictive intersection internally; a caller cannot submit a more permissive
effective capability as an input. The derived artifact retains both source
facts for audit. All immutable data contracts above use strict versioned,
UTC-safe primitive serialization. `CommandLifecycleBook` and the evaluator are
services, not serialized service state or a persistence design. A parsed
`CommandLifecycleRecord` is audit evidence only: it cannot hydrate or inject an
authoritative command book.

## Command lifecycle

| From | Allowed next states |
| --- | --- |
| `ISSUED` | `ACK_ACCEPTED`, `ACK_REJECTED`, `EXPIRED`, `SUPERSEDED` |
| `ACK_ACCEPTED` | `EXECUTING`, `EXPIRED`, `SUPERSEDED` |
| `EXECUTING` | `COMPLETED`, `EXPIRED`, `SUPERSEDED` |
| terminal: `ACK_REJECTED`, `COMPLETED`, `EXPIRED`, `SUPERSEDED` | no transition |

`ACK_ACCEPTED` is deliberately not `COMPLETED`. `COMPLETED` is reachable only
after `EXECUTING`, whose record retains an aware `execution_started_at`. The
authoritative telemetry must be observed at or after that start, received no
earlier than observed, and both observed/received before the completion time
and command expiry. The completion itself is valid only while
`completion_at < expires_at`; equality is expired. Its `actual_battery_power_kw`
must match the issued final `PowerCommand` within caller-supplied tolerance.
ACK time proves receipt only and cannot stand in for execution start. Exact duplicate command and ACK
facts are idempotent. Same sequence with another command, rollback, unknown
ACK and conflicting duplicate ACK are rejected. A late ACK leaves an expired
record expired. `supersede_with()` atomically registers a complete, active,
strictly higher-sequence successor than the book's current global maximum and
then records its id on the predecessor; an arbitrary successor id is never
authoritative. Any failed supersede leaves both command indexes and the
predecessor unchanged.

The table is an executed P0.1 runtime guard, not documentation-only metadata:
the specialized lifecycle methods perform their evidence/time/identity checks,
then use the same private transition guard before writing a new record. P0.1
has no generic public transition API. `CREATED`, `VALIDATED` and `FAILED` were
removed because this boundary has no public producer for them.

After restart, P0.1 restores no command. New-command recovery is permitted
only when telemetry and capability are fresh, SOC is known, BMS/PCS and the
command channel are healthy, the effective capability is available, emergency
stop is clear, no P0.1-blocking active fault exists, the runtime state is
`READY`, and no lifecycle record is non-terminal. P0.1 explicitly treats only
`CRITICAL` active faults as blocking; the rule is a software policy, not a
functional-safety classification.

## Fail-closed and recovery boundary

Only runtime state `READY` admits a new active-power request. Active economic
power is forced to a zero active-power request when telemetry
or capability is stale, a future observed timestamp exceeds clock skew, the
command channel or BMS/PCS connection is unhealthy, Edge is not `READY`, a
blocking active fault exists, effective capability is unavailable, or emergency
stop is asserted.
Capability and telemetry time values are caller-supplied development policy,
not hardware-certified values.

Runtime states are `STARTING`, `WAITING_FOR_FRESH_TELEMETRY`, `READY`,
`ACTIVE`, `DEGRADED`, `SAFE_IDLE`, `FAULTED` and `SHUTTING_DOWN`. P0.1 defines
their facts only. It intentionally has no durable lifecycle hydration or
recovery: a restart starts an empty book. P0.3 must define polling, retry, ACK
wait, durable recovery and transition ownership.

## Explicit exclusions and next inputs

P0.2 may supply a device simulator, fault-injection executor and deterministic
latency/loss simulation. P0.3 may supply a bounded Edge loop, telemetry polling,
EMS invocation, command transmission, ACK wait and durable recovery. Neither is
implemented by this boundary.

No P0.1 artifact accesses a device, opens a network connection, creates a
thread, stores a credential, generates a device address or mutates caller-owned
facts.
