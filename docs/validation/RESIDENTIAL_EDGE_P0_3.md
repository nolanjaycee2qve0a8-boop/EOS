# Residential Edge P0.3 validation

P0.3 validates deterministic runtime composition only.  Focused tests cover
startup/readiness, matching actual completion, delayed ACK fail-closed behavior
and fault-clear no-replay.  It does not validate a real device protocol or
claim that a lost ACK means a real PCS did not execute.

## Stage 2A admission and state coverage

Focused public-tick tests exercise the guarded `STARTING`/waiting/ready/degraded/
safe-idle/faulted/shutdown matrix; stale telemetry and capabilities; known SOC
and actual-power requirements; BMS/PCS connection and availability; command
channel/runtime health; fallback; warning/critical/E-stop evidence; command
identity and sequence validation; ACK drop/rejection/delay; lifecycle expiry;
and ordinary direction safety blocking. The tests prove a fresh startup or
recovery observation does not execute its caller command even when it ends
READY. They also prove a prepared P0.2 session is sampled once and consumed once.

No-replay coverage additionally makes the command-origin contract explicit:
every `tick(None)` evidence record has no caller command, no admitted command,
`CommandOrigin.NONE`, no automatic generation, no device command/ACK/authorized
application, zero clean-plant actual power and no new lifecycle identity. The
matrix covers ACK reject/drop/delay expiry, critical BMS/PCS/Edge faults,
E-stop, stale telemetry/capability, disconnected/unavailable facts, actual
mismatch and ordinary safety blocking. A later caller-provided new ID and
sequence is the only path that can resume active virtual power.

The admission-corruption regression runs a real READY-start
`ControlledEdgeRuntime.tick(command_a)`, monkeypatching only the admission
selection boundary to return a valid but different command B. The
current-caller guard rejects B before P0.2 `execute`; the test spies execute and
then proves the immutable input runtime retains its clock, SOC, previous actual,
lifecycle book and trace. The separately validated `RuntimeLoopStep` provenance
contract remains post-execution audit evidence, not the source of this
pre-execution containment proof.

Stage 2B focused tests additionally cover the five retained power layers,
compound reconciliation precedence, unknown/non-zero/mismatched actual facts,
strict evidence round-trips, forged-schema rejection, immutable trace linkage
and absence of runtime-authority hydration. ACK is never asserted as actual
execution; Simulator actual telemetry remains the execution fact. The matrix is
prototype evidence, not a hardware safety certification: evidence serialization
is audit-only and supplies no persistent recovery. `ControlledEdgeRuntime`
itself rejects copy, deepcopy, pickle/reduce, and hydration, while its trace
remains serializable audit evidence. Final publication gates still require
broader suites.

## Phase 3 final mutation ledger

All mutations below were made only in a system-temporary copy of the current
working tree. Each ran the named minimal Edge test node and was killed by one
related assertion or contract failure (no collection, import, syntax or format
failure). No mutation wrote a repository file. `A10` has separate copy and
pickle probes; together they are one authority invariant.

| ID | Production invariant and actual temporary replacement | Minimal test node | Result |
| --- | --- | --- | --- |
| A01 | `step(command)` → `step(None)` | `test_charge_discharge_efficiency_and_soc_boundaries_use_actual_signed_power` | killed, 1 |
| A02 | one `prepare_step()` → two calls | `test_p03_tick_samples_fault_schedule_once_and_hides_authority` | killed, 1 |
| A03 | `execute()` re-calls `active_at()` | same A02 node | killed, 1 |
| A04 | tick end re-calls `active_at()` | same A02 node | killed, 1 |
| A05 | prepared `_used` guard → `False` | `test_prepared_step_is_single_snapshot_and_one_shot` | killed, 1 |
| A06 | prepared source simulator → unrelated object | `test_prepared_session_is_bound_to_its_creating_snapshot_and_branch` | killed, 1 |
| A07 | add `ControlledEdgeRuntime.from_dict` | `test_trace_linkage_and_evidence_do_not_hydrate_runtime_authority` | killed, 1 |
| A08 | `prepare_step()` mutates previous actual | `test_prepare_is_side_effect_free_and_validation_failure_does_not_consume` | killed, 1 |
| A09 | no-command `execute()` raises/skips execution | `test_each_tick_path_prepares_and_executes_one_fault_snapshot` | killed, 1 |
| A10 | copy returns self; reduce returns pickle tuple | `test_prepared_authority_cannot_be_constructed_copied_or_serialized` | killed, 1 each |
| B11 | READY-start gate → unconditional ready fact | `test_starting_observation_tick_never_admits_active_command` | killed, 1 |
| B12 | `admitted = command if admitting else None` → `admitted = command` | same B11 node | killed, 1 |
| B13 | critical-fault branch → `False` | `test_critical_fault_blocks_admission_and_no_command_replay_after_clear` | killed, 1 |
| B14 | E-stop input → `False` | `test_public_tick_maps_prepared_fault_and_fact_inputs_to_runtime_state` | killed, 1 |
| B15 | stale telemetry freshness and health → fresh | same B14 node | killed, 1 |
| B16 | capability-stale fault → non-stale warning | same B14 node | killed, 1 |
| B17 | FAULTED recovery tick also admits command | `test_recovery_observation_with_new_command_never_replays_or_admits` | killed, 1 |
| B18 | shutdown reconciliation → READY | `test_shutdown_is_terminal_for_ordinary_ticks_and_never_admits` | killed, 1 |
| B19 | sequence rollback guard → `False` | `test_submit_replay_sequence_and_invalid_command_timing` | killed, 1 |
| B20 | nonterminal lifecycle permits replacement | `test_unresolved_inflight_lifecycle_never_admits_a_replacement_command` | killed, 1 |
| C21 | accepted ACK lifecycle state → completed | `test_acknowledgement_identity_duplicate_conflict_and_late_expiry` | killed, 1 |
| C22 | telemetry actual → ACK accepted power | `test_actual_mismatch_is_degraded_and_is_not_lifecycle_completion` | killed, 1 |
| C23 | telemetry actual → caller requested power | same C22 node | killed, 1 |
| C24 | telemetry actual → safety-final request | same C22 node | killed, 1 |
| C25 | actual-match completion check → unconditional | same C22 node | killed, 1 |
| C26 | `actual is None` → `actual == 0` | `test_reconciliation_unknown_actual_is_not_zero_and_fails_closed` | killed, 1 |
| C27 | add lifecycle-book `from_dict` | `test_book_has_no_record_hydration_or_caller_collection_injection` | killed, 1 |
| C28 | successor sequence check → `False` | `test_supersede_with_requires_valid_new_successor_and_is_atomic` | killed, 1 |
| C29 | next simulator previous actual → requested power | `test_failed_or_zero_actual_never_contaminates_stuck_previous_power` | killed, 1 |
| D30 | unexpected-actual precedence 0 → 5 | `test_reconciliation_precedence_retains_all_compound_evidence` | killed, 1 |
| D31 | expired precedence 3 → 6 | same D30 node | killed, 1 |
| D32 | safety-block reason branch → `False` | `test_ordinary_direction_safety_block_is_safe_idle_not_device_fault` | killed, 1 |
| D33 | reason ordering key → lexical string | same D30 node | killed, 1 |
| D34 | strict unknown-field check → `False` | `test_trace_and_reconciliation_serialization_are_strict_and_deterministic` | killed, 1 |
| D35 | add Runtime `from_dict` | `test_trace_linkage_and_evidence_do_not_hydrate_runtime_authority` | killed, 1 |
| D36 | trace SOC-link guard → `False` | same D35 node | killed, 1 |
| E37 | recovery `tick(None)` derives a new-ID/new-sequence/new-window command from prior trace | `test_ack_rejection_is_terminal_and_recovery_does_not_replay` | killed by caller-none/admitted-none evidence, 1 |
| E38 | previous command, cloned identity, READY transition, second READY tick, safety-final, ACK power or actual power creates an admitted command | no-replay target or recovery matrix | killed by caller-none/admitted-none no-replay evidence, 8/8 |
| E39 | delete `_assert_current_caller_origin(...)` after a selector returns forged B for real `tick(command_a)` | `test_admission_corruption_is_rejected_before_p02_execute` | killed: forged B reaches the P0.2 boundary (`execute_calls=1`) instead of being rejected before execution, 1 |

This ledger is regression evidence for the frozen P0.3 prototype. It neither
claims mutation completeness for future Runtime code nor expands P0.3 into a
protocol, persistent-recovery or hardware test program.
