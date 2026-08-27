# Residential Edge P0.5 Validation — Command Handoff

P0.5 focused tests cover the immutable, transport-neutral
`FeasibleDecision`-to-`PowerCommand` handoff only. They verify signed
charge/discharge/idle mapping, Feasibility limiting and idle downgrade, exact
source/metadata identity, PowerCommand serialization, metadata validation, no
hidden state and public API contracts. Static tests reject runtime, simulator,
lifecycle and clock dependencies.

The result contract independently rereads approved action/power and verifies
the command sign and mode; it deliberately does not reuse the generator's
mapping helper. A permanent public-handoff corruption test changes the
generator helper from approved charge `+2.0` to `-2.0` and requires the result
contract to reject the otherwise-valid `PowerCommand`.

Idle mapping is tested with separate, test-only corruption of a valid idle
command's power while preserving `safe_idle`, and of its mode while preserving
zero power. The respective result-contract checks reject each corruption.
Mutation coverage runs only in temporary copies: sign reversal, raw requested
power substitution, idle power/mode restoration, rewritten identity/time,
direct non-feasible input and a hidden runtime-tick dependency are all required
to fail focused semantic tests. This is not device execution validation.

P0.5 does not change frozen Residential EMS algorithms, Campaign A–F evidence,
P0.1/P0.2/P0.3 behavior, P0.4 Device Adapter behavior, communication or
hardware safety scope.
