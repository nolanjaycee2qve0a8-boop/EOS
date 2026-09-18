# P0.11 Candidate — Residential Device-Fact Command-Correlation Audit

> **PLANNING-ONLY / PROSPECTIVE.** This candidate is not implementation,
> release, public-API, device-access, or hardware authorization. No P0.11 code
> or validation result is asserted by this document.

## 1. Candidate purpose

Define a possible future, deterministic, audit-only assessment for one finite
caller-owned set of inert transmission identity, ACK-correlation fact,
actual-observation fact, and explicit assessment identity/time facts. Its only
prospective result is immutable PASS/GAP audit evidence.

The candidate asks whether supplied facts have the declared correlation
semantics. It does not request or prove command admission, transmission,
logical execution, reconciliation, hardware execution, or physical completion.

## 2. Candidate input boundary

A future input would require all of the following caller-owned immutable facts:

1. an inert transmission/request identity, including explicit identity,
   sequence, origin, source identity, identity epoch, time, and correlation
   fields but no executable command authority;
2. one explicit ACK observation/correlation fact with its own source identity
   and identity epoch;
3. one independent explicit actual-observation fact with its own source
   identity and identity epoch; and
4. a distinct `assessment_identity` and `assessment_as_of` that define this
   one audit's identity and time scope.

All identity, origin, availability, time, and correlation claims must be
explicit. The caller must also declare the permitted source/epoch relationship
among transmission, ACK, and actual; it is not inferred from equal values. A
missing, unknown, conflicting, or relationship-undeclared source/epoch claim is
GAP. Equal values are not assumed to be the same authority or provenance. The
assessment identity must not be reused as a transmission, ACK, or actual
identity within the same audit.

The input must reject commands, `PowerCommand`, raw strategy/EMS requests,
runtime, adapter, session, continuation, handoff, prepared request, command
factory, trace, receipt, endpoint, address, credential, socket, transport, or
historical audit result as authority.

## 3. Candidate result boundary

A future result would contain immutable PASS/GAP status, non-executable finding
records, the declared audit identity/time scope, and inert identity references
needed to explain each finding. It must not retain a live input or provide any
hydration, restore, factory, copy-to-authority, replay, command, request,
adapter, runtime, session, continuation, or transmission path.

PASS means only that the supplied finite facts satisfy the declared audit rule.
It is not ACK success, device availability, logical execution, P0.3
reconciliation, transmission success, physical completion, hardware readiness,
or field-deployment readiness.

## 4. Candidate correlation rules

| Subject | Prospective fail-closed rule | Not established by a PASS |
| --- | --- | --- |
| Transmission identity | It is caller-owned, inert, explicit, and internally consistent, including source identity and identity epoch; missing, unknown, or conflicting fields are GAP. | Command authority, transmission, or replay permission. |
| ACK correlation | Every required declared identity/sequence/origin/time/source/epoch correlation must exactly match the inert transmission identity or satisfy the caller-declared relationship; missing, unavailable, malformed, stale, unknown, conflicting, mismatched, or relationship-undeclared facts are GAP. | Physical completion or actual execution. |
| Actual observation | It is explicitly present or explicitly unavailable, has explicit source identity and identity epoch, and remains distinct from ACK and transmission identity; missing, unknown, conflicting, or relationship-undeclared source/epoch facts are GAP. | P0.3 retained actual/reconciliation or command authority. |
| Assessment identity / `as_of` | They are explicit, caller-owned, distinct audit facts; unknown or inconsistent scope/time is GAP. | A runtime clock, continuation, history, or freshness inference. |

An unavailable or malformed fact is an explicit GAP, not a default zero-power
observation, successful acknowledgement, completed transmission, recovery, or
device completion. Actual may be assessed beside ACK correlation, but it never
replaces P0.3 retained actual/reconciliation.

## 5. Lifecycle, replay, and state boundary

The prospective evaluator would be synchronous and stateless for authority
purposes. It would own no clock, runtime, adapter, session, continuation,
command book, retry loop, scheduler, persistence, background work, transport,
or device connection. Every audit would require a fresh caller action and
finite caller input. Previous evidence cannot become next-call authority by
serialization, hydration, cloning, re-numbering, retiming, ACK power, actual
power, or any other conversion.

## 6. Frozen scope and non-goals

P0.1–P0.10, Residential EMS 1.0, and Campaign A–F remain zero-diff frozen
dependencies. This candidate cannot change control, feasibility, actuation,
simulation, P0.3 reconciliation, P0.4 observation semantics, or P0.10
lifecycle assessment meaning.

It includes no protocol, network, HTTP, Modbus, CAN, serial, thread,
scheduler, persistence, retry, HIL, PCS/BMS/DSP/STM32 capability, hardware
authority, field control, safety certification, or deployment feature.

## 7. Future validation and review plan

If a separate future implementation is authorized, its tests must independently
cover positive matching and declared-relationship source/epoch facts; ACK
correlation mismatch/missing/unavailable/unknown/conflicting/undeclared
source-epoch facts; actual-vs-P0.3-reconciliation separation;
`assessment_as_of` scope; non-authority serialization/copy/hydration negatives;
no replay from historical evidence; and frozen/import boundaries.

Future mutations must corrupt producers or public composition boundaries rather
than fabricate final PASS/GAP objects or share the producer's validator. The
future release sequence would require focused and upstream/frozen regressions,
Campaign A–F regression, full pytest with terminal summary/exit code, static
and import scans, pre-commit, isolated mutation evidence, independent review,
and an explicit user publication decision. None has been run or approved for
this candidate.
