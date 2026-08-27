# Residential Edge P0.2 Validation — Deterministic Device Fault Injection

## Scope and evidence status

P0.2 validates the P0.1 Edge safety/lifecycle contracts against deterministic
virtual PCS/BMS adverse conditions. It is not real-device, HIL, protocol,
hardware-safety or deployment evidence.

## Focused matrix

| Area | Deterministic evidence |
| --- | --- |
| Nominal | requested → safe request → ACK → actual telemetry → completed lifecycle |
| Capability | PCS/BMS availability, limits, derating and direction prohibition feed P0.1 directly |
| Freshness | frozen telemetry has an old `observed_at` despite current receipt time |
| Safety | critical fault, E-stop, disconnect, unavailable and non-ready facts fail closed |
| ACK | only immediate accepted ACK applies; reject/drop/late ACK keep actual/SOC at zero and cannot revive expiry |
| Actual response | stuck-at-zero and deviation retain actual mismatch and block completion |
| SOC | actual signed kW with efficiencies changes SOC; min/max limits retain evidence |
| Recovery | clear changes future facts only; no old command auto-replay |
| Overlap | same-time faults have canonical order and stable P0.1 constraint evidence |

The ACK rule is a conservative simulator command-application policy, not a
real-device assertion: a PCS may execute while an ACK is delayed or lost. P0.2
therefore never elevates ACK to execution truth; future Runtime must reconcile
that uncertainty from actual telemetry, which is intentionally outside P0.2.

Fault compatibility is fail-closed before schedule entry: every fault type
whitelists target and exact parameters, so no accepted fault may become a
silent no-op. `WARNING_FAULT` remains retained and non-blocking; critical fault
remains blocking. An overlapping-clear regression proves clearing A leaves B's
raw-fact, safety and actual-response constraints intact.

## Acceptance observations

- P0.2 obtains `EffectiveDeviceCapability` only through the P0.1 evaluator.
- Fail-closed conditions produce a zero final software request, but actual PCS
  zero remains a later virtual telemetry fact rather than a claim from safety.
- Lifecycle completion receives only actual telemetry after execution start and
  before expiry. Actual mismatch, drop, reject and lateness do not fabricate
  completion.
- Every scenario uses its own immutable simulator/trace and explicit UTC time.
- A step samples faults only at `started_at`, with active interval
  `[activation_at, clear_at)`; intra-step changes apply at the next step.
- `prepare_step()` is side-effect-free and produces a one-shot, non-copyable,
  non-serializable authority session bound to its source simulator snapshot.
  Explicit immutable simulator branches remain isolated test scenarios.
- The serializable completed `DeviceSimulatorStep` is immutable evidence only.
  P0.3 reconciliation reads its retained actual telemetry once; evidence
  deserialization cannot recover a simulator or prepared authority.

## Deferred scope

P0.3 loop ownership, polling, transport adapters, retry, durable recovery,
real PCS/BMS/DSP communication, HIL and hardware certification remain deferred.
