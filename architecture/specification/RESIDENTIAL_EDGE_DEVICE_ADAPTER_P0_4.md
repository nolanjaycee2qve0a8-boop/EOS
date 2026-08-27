# Residential Edge Device Adapter — P0.4

P0.4 is a transport-neutral I/O contract, not a real device integration.

## Facts and ownership

`DeviceObservation` carries existing P0.1 `TelemetrySnapshot`, BMS/PCS
`DeviceCapability`, and `RuntimeHealth` facts, or explicit `missing`/
`unavailable` evidence. Capture times are preserved. `to_recovery_readiness_input`
only maps complete facts to P0.1; P0.1 continues to decide stale, unknown and
fresh using its timing policy.

Transmission consumes a one-shot `DeviceTransmissionRequest` built only from
the exact current caller/admitted `PowerCommand` and its P0.3 safety-final
decision. It preserves ID, sequence, provenance, correlation, issued,
not-before, expiry, mode and final requested power. Zero remains an explicit
safe-idle request. The adapter cannot accept a raw `PowerCommand`, generate an
identity, increment sequence, alter safety, or reuse a consumed request.

ACK and actual are separate facts. `DeviceAckObservation` can be available,
missing or unavailable. Correlation requires exact ID, sequence and correlation
ID; mismatch is rejected before any lifecycle consumer sees it. Actual telemetry
is deliberately uncorrelated physical evidence and remains P0.3's execution
fact input. ACK-before-actual, actual-before-ACK, missing and late evidence are
all representable.

## Failure and audit boundary

Only transport-neutral failure codes cross the boundary: channel unavailable,
transmission failed, ACK unavailable and observation unavailable. Failure does
not create readiness, completion, actual power or a replacement command.
`DeviceAdapterStepEvidence` and transmission evidence serialize deterministically
for audit, but no evidence type can construct a request, adapter, Runtime,
lifecycle book or P0.2 prepared authority.

## Non-goals

P0.4 does not add protocol bytes, TCP/UDP, MQTT, Modbus, CAN, RS485, HIL,
firmware, persistence, restart recovery, background execution or production
Runtime behavior. It does not change Residential EMS 1.0 or Campaign A–F.
