# Residential Edge P0.6 Validation — Controlled Composition

P0.6 focused tests prove one normal P0.5 → P0.3 → P0.4 audit composition with
exact source/metadata preservation, P0.3 caller/admitted identity and P0.4
one-shot transmission evidence.  They deliberately retain P0.3 actual power
and P0.4 actual telemetry as distinct facts, proving that the adapter does not
self-certify execution.

The focused matrix also covers metadata identity/time preservation, equal but
distinct P0.5 source or metadata substitution, a non-admitting P0.3 start
state, duplicate metadata no-replay, forged adapter ACK correlation, explicit
unavailable P0.4 audit facts, malformed adapter facts, immutable result
evidence/continuation separation, and direct-plus-from transport-import
exclusion. No-admission paths observe facts but create no P0.4 transmission
request.

For either equal-but-distinct P0.5 source or metadata substitution, the identity
gate runs immediately after handoff and before any P0.3 logical tick or P0.4
adapter call. Focused counting evidence requires the resulting `ValueError`
with zero runtime ticks and zero observation, transmission, ACK, actual-telemetry,
and transmission-attempt calls.

The test is a producer-corruption harness: it directly overrides public P0.5
`handoff()` to return a type-correct result with an equal-but-distinct source or
metadata object. A compliant P0.5 public boundary already rejects that result
through its own outer identity contract; the direct override deliberately
bypasses that earlier protection so the counted failure is specifically P0.6's
pre-tick defence-in-depth gate rather than a P0.5 rejection.

Evidence has no live input, runtime, adapter, handoff boundary, or request.
Continuation contains only exact P0.3 next runtime for the current caller and
cannot copy, serialize, hydrate, recover a command, or replay a cycle. P0.4
unavailable/missing facts are audit facts, not success, zero power, or physical
completion. Malformed and correlation violations fail closed with no successful
P0.6 result; they cannot retrospectively rewrite P0.3 reconciliation.

P0.3 independently rejects direct runtime copy, deepcopy, pickle/reduce, and
hydration. Therefore `continuation.next_runtime` cannot bypass the P0.6 wrapper
by serialization into a restored execution authority.

P0.6 tests do not claim real-device execution.  P0.1-P0.5 focused suites,
frozen Residential EMS regression, Campaign A-F regression, full pytest and
publication checks remain later gates. The P0.4 adapter production paths must
remain zero-diff relative to the P0.5 baseline. Mutation execution is also a
later gate: its planned matrix corrupts P0.5 metadata, P0.3 admission/no-replay,
P0.4 request/ACK correlation, and adapter actual versus P0.3 reconciliation
through public composition or producer corruption, never a hand-built final
failure result or common-mode self-certification.
