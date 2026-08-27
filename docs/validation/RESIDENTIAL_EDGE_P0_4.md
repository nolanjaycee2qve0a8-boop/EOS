# Residential Edge P0.4 Validation — Device Adapter Boundary

P0.4 focused tests cover complete, stale, missing and disconnected observation
facts; explicit safe-zero transmission; successful/failed exact-once attempts;
no retry after failure or adapter recreation; accepted/rejected/missing/late
ACK; actual before ACK; expected/zero/mismatched/unknown actual facts; strict
ACK correlation; and evidence-only serialization.

The correlation negative proof first confirms that a forged ACK is rejected.
It then replaces only the test-time correlation guard and proves the forged ACK
would cross the return boundary. This demonstrates that exact ID/sequence/
correlation matching is meaningful rather than a happy-path assertion.

The scripted adapter has no wall clock, sleep, protocol library, network,
thread, scheduler or retry. It does not replace P0.2 plant dynamics or make
P0.3 asynchronous. P0.1/P0.2/P0.3 focused regressions and frozen Residential
control regression remain mandatory publication gates.
