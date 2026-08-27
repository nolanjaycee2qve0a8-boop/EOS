"""Explicit-tick composition of P0.1 lifecycle and P0.2 logical plant."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from edge_runtime.contracts import (
    AcknowledgementStatus,
    PowerCommand,
    RuntimeState,
    SafetyOutcome,
)
from edge_runtime.controlled_runtime.contracts import (
    CommandOrigin,
    CommandReconciliation,
    LifecycleEvidence,
    ReconciliationStatus,
    RuntimeLoopStep,
    RuntimeLoopTrace,
    canonical_reconciliation_reason_codes,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceSimulator,
    FaultTarget,
    FaultType,
)
from edge_runtime.lifecycle import (
    CommandLifecycleBook,
    CommandLifecycleRecord,
    CommandLifecycleState,
    RecoveryReadiness,
)
from edge_runtime.safety import (
    RecoveryReadinessInput,
    evaluate_recovery_readiness,
)
from edge_runtime.validation import (
    require_non_negative_number,
    require_positive_timedelta,
)

_ALLOWED_RUNTIME_TRANSITIONS: dict[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.STARTING: frozenset(
        {
            RuntimeState.STARTING,
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.WAITING_FOR_FRESH_TELEMETRY: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.READY: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.DEGRADED: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.SAFE_IDLE: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.FAULTED: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    # P0.3 has no ACTIVE producer.  It remains a non-admitting compatibility
    # state from the wider P0.1 enum and can only return through observation.
    RuntimeState.ACTIVE: frozenset(
        {
            RuntimeState.WAITING_FOR_FRESH_TELEMETRY,
            RuntimeState.READY,
            RuntimeState.DEGRADED,
            RuntimeState.SAFE_IDLE,
            RuntimeState.FAULTED,
            RuntimeState.SHUTTING_DOWN,
        }
    ),
    RuntimeState.SHUTTING_DOWN: frozenset({RuntimeState.SHUTTING_DOWN}),
}


def _transition(
    state_before: RuntimeState,
    state_after: RuntimeState,
) -> RuntimeState:
    """Apply the P0.3 state matrix; no caller chooses an arbitrary target."""
    if state_after not in _ALLOWED_RUNTIME_TRANSITIONS[state_before]:
        raise ValueError(
            "runtime transition is not allowed: "
            f"{state_before.value} -> {state_after.value}"
        )
    return state_after


def _record_for_command(
    book: CommandLifecycleBook,
    command: PowerCommand | None,
) -> CommandLifecycleRecord | None:
    if command is None:
        return None
    return next(
        (
            item
            for item in book.records
            if item.command.command_id == command.command_id
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class ControlledEdgeRuntime:
    """Caller-driven P0.3 prototype.  It owns no retry, thread or wall clock."""

    simulator: DeterministicDeviceSimulator
    lifecycle_book: CommandLifecycleBook
    state: RuntimeState = RuntimeState.STARTING
    trace: RuntimeLoopTrace = field(default_factory=lambda: RuntimeLoopTrace(()))

    @classmethod
    def start(cls, simulator: DeterministicDeviceSimulator) -> "ControlledEdgeRuntime":
        if not isinstance(simulator, DeterministicDeviceSimulator):
            raise TypeError("simulator must be a DeterministicDeviceSimulator")
        return cls(simulator, CommandLifecycleBook())

    def request_shutdown(self) -> "ControlledEdgeRuntime":
        """Latch a caller-requested shutdown; ordinary ticks never revive it."""
        return ControlledEdgeRuntime(
            self.simulator,
            self.lifecycle_book,
            _transition(self.state, RuntimeState.SHUTTING_DOWN),
            self.trace,
        )

    @staticmethod
    def _admit_current_caller_command(
        caller_command: PowerCommand | None,
        *,
        admission_open: bool,
    ) -> PowerCommand | None:
        """Return only this tick's caller object; history never creates commands."""
        return caller_command if admission_open and caller_command is not None else None

    @staticmethod
    def _assert_current_caller_origin(
        caller_command: PowerCommand | None,
        admitted_command: PowerCommand | None,
    ) -> None:
        """Fail before execution if trace-derived state attempts a command replay."""
        if admitted_command is None:
            return
        if caller_command is None or admitted_command is not caller_command:
            raise ValueError(
                "admitted command must be the current caller command object"
            )

    @staticmethod
    def _observation_state(
        state_before: RuntimeState,
        readiness: RecoveryReadiness,
        *,
        emergency_stop_active: bool,
        critical_fault_active: bool,
        telemetry_actual_known: bool,
        bms_connected: bool,
        pcs_connected: bool,
        bms_available: bool,
        pcs_available: bool,
        command_channel_healthy: bool,
        safe_fallback_active: bool,
        warning_fault_active: bool,
    ) -> tuple[RuntimeState, tuple[str, ...]]:
        """Map one prepared start snapshot to one guarded P0.3 state."""
        if state_before is RuntimeState.SHUTTING_DOWN:
            return RuntimeState.SHUTTING_DOWN, ("shutdown_requested",)
        if emergency_stop_active:
            return RuntimeState.FAULTED, ("emergency_stop_active",)
        if critical_fault_active:
            return RuntimeState.FAULTED, ("critical_fault_active",)
        if not telemetry_actual_known:
            return RuntimeState.WAITING_FOR_FRESH_TELEMETRY, ("actual_power_unknown",)
        telemetry_stale = {
            "telemetry_not_fresh",
            "runtime_health_telemetry_not_fresh",
        }
        capability_stale = {
            "capability_not_fresh",
            "runtime_health_capability_not_fresh",
        }
        waiting_reasons: list[str] = []
        if telemetry_stale.intersection(readiness.reason_codes):
            waiting_reasons.append("telemetry_stale")
        if capability_stale.intersection(readiness.reason_codes):
            waiting_reasons.append("capability_stale")
        if "soc_unknown" in readiness.reason_codes:
            waiting_reasons.append("soc_unknown")
        if waiting_reasons:
            return RuntimeState.WAITING_FOR_FRESH_TELEMETRY, tuple(waiting_reasons)
        if safe_fallback_active:
            return RuntimeState.SAFE_IDLE, ("runtime_safe_fallback_active",)
        degradation_reasons: list[str] = []
        if not bms_connected:
            degradation_reasons.append("bms_disconnected")
        if not pcs_connected:
            degradation_reasons.append("pcs_disconnected")
        if not bms_available:
            degradation_reasons.append("bms_unavailable")
        if not pcs_available:
            degradation_reasons.append("pcs_unavailable")
        if not command_channel_healthy:
            degradation_reasons.append("command_channel_unhealthy")
        if "runtime_state_not_ready" in readiness.reason_codes:
            degradation_reasons.append("runtime_link_unhealthy")
        if "lifecycle_not_quiescent" in readiness.reason_codes:
            degradation_reasons.append("lifecycle_not_quiescent")
        if degradation_reasons:
            return RuntimeState.DEGRADED, tuple(degradation_reasons)
        if readiness.ready_for_new_command:
            return (
                RuntimeState.READY,
                ("warning_fault_active",) if warning_fault_active else (),
            )
        return RuntimeState.WAITING_FOR_FRESH_TELEMETRY, readiness.reason_codes

    @staticmethod
    def _state_after_reconciliation(
        state: RuntimeState,
        reconciliation: CommandReconciliation,
    ) -> tuple[RuntimeState, tuple[str, ...]]:
        """Apply only the minimal stage-2A execution safety consequences."""
        if state is RuntimeState.SHUTTING_DOWN:
            return state, ()
        if reconciliation.status is ReconciliationStatus.UNEXPECTED_ACTUAL:
            return RuntimeState.FAULTED, ("unexpected_nonzero_actual",)
        if reconciliation.status in {
            ReconciliationStatus.ACK_MISSING,
            ReconciliationStatus.ACK_DELAYED,
            ReconciliationStatus.ACK_ACCEPTED_ACTUAL_MISMATCH,
        }:
            return RuntimeState.DEGRADED, (reconciliation.status.value,)
        if reconciliation.status in {
            ReconciliationStatus.ACK_REJECTED,
            ReconciliationStatus.COMMAND_EXPIRED,
            ReconciliationStatus.SAFE_REQUEST_BLOCKED,
            ReconciliationStatus.LIFECYCLE_INCOMPLETE,
        }:
            return RuntimeState.SAFE_IDLE, (reconciliation.status.value,)
        return state, ()

    @staticmethod
    def _reconcile(
        caller_command: PowerCommand | None,
        device_command: PowerCommand | None,
        *,
        telemetry_actual_power_kw: float | None,
        final_safe_request_power_kw: float | None,
        acknowledgement_status: AcknowledgementStatus | None,
        acknowledged_power_kw: float | None,
        acknowledgement_received_at: datetime | None,
        application_authorized: bool,
        safety_blocked: bool,
        lifecycle_before: CommandLifecycleRecord | None,
        lifecycle_after: CommandLifecycleRecord | None,
        tolerance_kw: float,
        command_expired: bool,
    ) -> CommandReconciliation:
        """Classify all evidence before selecting one risk-ordered primary status."""
        actual = telemetry_actual_power_kw
        expected = (
            final_safe_request_power_kw
            if application_authorized and final_safe_request_power_kw is not None
            else (0.0 if device_command is not None else None)
        )
        deviation = (
            None if actual is None or expected is None else abs(actual - expected)
        )
        reasons: set[ReconciliationStatus] = set()
        if actual is None:
            reasons.add(ReconciliationStatus.ACTUAL_UNKNOWN)
        if (
            actual is not None
            and actual != 0
            and (not application_authorized or safety_blocked)
        ):
            reasons.add(ReconciliationStatus.UNEXPECTED_ACTUAL)
        if deviation is not None and deviation > tolerance_kw:
            reasons.add(ReconciliationStatus.ACTUAL_MISMATCH)
        if command_expired:
            reasons.add(ReconciliationStatus.COMMAND_EXPIRED)
        if (
            acknowledgement_status is not None
            and acknowledgement_status is not AcknowledgementStatus.ACCEPTED
        ):
            reasons.add(ReconciliationStatus.ACK_REJECTED)
        if device_command is not None and acknowledgement_status is None:
            reasons.add(ReconciliationStatus.ACK_MISSING)
        if (
            device_command is not None
            and acknowledgement_status is AcknowledgementStatus.ACCEPTED
            and not application_authorized
        ):
            reasons.add(ReconciliationStatus.ACK_DELAYED)
        if device_command is not None and not application_authorized:
            reasons.add(ReconciliationStatus.APPLICATION_NOT_AUTHORIZED)
        if lifecycle_after is not None and lifecycle_after.state not in {
            CommandLifecycleState.ACK_REJECTED,
            CommandLifecycleState.COMPLETED,
            CommandLifecycleState.EXPIRED,
            CommandLifecycleState.SUPERSEDED,
        }:
            reasons.add(ReconciliationStatus.LIFECYCLE_INCOMPLETE)
        if safety_blocked:
            reasons.add(ReconciliationStatus.SAFETY_BLOCKED)
        if (
            application_authorized
            and actual is not None
            and expected is not None
            and deviation is not None
            and deviation <= tolerance_kw
        ):
            reasons.add(ReconciliationStatus.ACTUAL_MATCHED)
        if (
            ReconciliationStatus.ACTUAL_MATCHED in reasons
            and lifecycle_after is not None
            and lifecycle_after.state is CommandLifecycleState.COMPLETED
        ):
            reasons.add(ReconciliationStatus.COMPLETED)
        if not reasons:
            reasons.add(ReconciliationStatus.IDLE_NO_COMMAND)
        ordered = canonical_reconciliation_reason_codes(reasons)
        status = ReconciliationStatus(ordered[0])
        acknowledgement_at = acknowledgement_received_at
        return CommandReconciliation(
            status,
            status.value,
            ordered,
            None if caller_command is None else caller_command.command_id,
            None if caller_command is None else caller_command.sequence,
            None
            if caller_command is None
            else caller_command.requested_battery_power_kw,
            final_safe_request_power_kw,
            acknowledgement_status,
            acknowledged_power_kw,
            acknowledgement_at,
            application_authorized,
            actual,
            expected,
            deviation,
            tolerance_kw,
            None if lifecycle_before is None else lifecycle_before.state,
            None if lifecycle_after is None else lifecycle_after.state,
            None if lifecycle_after is None else lifecycle_after.completion_evidence,
            status
            not in {
                ReconciliationStatus.IDLE_NO_COMMAND,
                ReconciliationStatus.ACTUAL_MATCHED,
                ReconciliationStatus.COMPLETED,
            },
        )

    def tick(
        self,
        command: PowerCommand | None,
        *,
        duration: timedelta,
        tolerance_kw: float = 0.01,
    ) -> "ControlledEdgeRuntime":
        interval = require_positive_timedelta(duration, "duration")
        require_non_negative_number(tolerance_kw, "tolerance_kw")
        if command is not None and not isinstance(command, PowerCommand):
            raise TypeError("command must be PowerCommand or None")
        caller_command = command
        state_before = self.state
        book_at_start = self.lifecycle_book.expire(at=self.simulator.clock.now)
        prepared = self.simulator.prepare_step()
        probe = prepared
        estop = any(
            item.fault_type is FaultType.ESTOP
            and item.target in {FaultTarget.PCS, FaultTarget.EDGE}
            for item in probe.active_faults
        )
        readiness = evaluate_recovery_readiness(
            RecoveryReadinessInput(
                probe.raw_telemetry,
                probe.bms_capability,
                probe.pcs_capability,
                probe.runtime_health,
                self.simulator.configuration.timing_policy,
                book_at_start,
                self.simulator.clock.now,
                estop,
            )
        )
        # Admission is based on the state at tick start. A startup/recovery
        # observation may reach READY, but its command waits for the next tick.
        admitting = (
            readiness.ready_for_new_command and state_before is RuntimeState.READY
        )
        observed_state, observed_reasons = self._observation_state(
            state_before,
            readiness,
            emergency_stop_active=estop,
            critical_fault_active=any(
                item.fault_type is FaultType.CRITICAL_FAULT
                for item in probe.active_faults
            ),
            telemetry_actual_known=probe.raw_telemetry.actual_battery_power_kw
            is not None,
            bms_connected=probe.runtime_health.bms_connected,
            pcs_connected=probe.runtime_health.pcs_connected,
            bms_available=probe.bms_capability.available,
            pcs_available=probe.pcs_capability.available,
            command_channel_healthy=probe.runtime_health.command_channel_healthy,
            safe_fallback_active=probe.runtime_health.safe_fallback_active,
            warning_fault_active=any(
                item.fault_type is FaultType.WARNING_FAULT
                for item in probe.active_faults
            ),
        )
        admitted = self._admit_current_caller_command(
            caller_command,
            admission_open=(
                admitting and state_before is not RuntimeState.SHUTTING_DOWN
            ),
        )
        admission_reasons: tuple[str, ...] = ()
        book = book_at_start
        if admitted is not None:
            book, submission = book.submit(
                admitted,
                received_at=self.simulator.clock.now,
                policy=self.simulator.configuration.timing_policy,
            )
            if submission.idempotent_duplicate:
                admitted = None
                admission_reasons = ("duplicate_command_id",)
            elif submission.record.state is CommandLifecycleState.EXPIRED:
                admitted = None
                admission_reasons = ("command_expired_at_admission",)
        self._assert_current_caller_origin(caller_command, admitted)
        lifecycle_before_record = _record_for_command(
            self.lifecycle_book, caller_command
        )
        simulator, device = prepared.execute(admitted, duration=interval)
        if (
            admitted is not None
            and device.acknowledgement is not None
            and device.acknowledgement.received_at <= device.ended_at
        ):
            book = book.acknowledge(
                device.acknowledgement, received_at=device.acknowledgement.received_at
            )
            if device.command_application_authorized:
                book = book.begin_execution(
                    admitted.command_id, at=device.acknowledgement.received_at
                )
                actual = device.actual_telemetry.actual_battery_power_kw
                if (
                    actual is not None
                    and abs(actual - admitted.requested_battery_power_kw)
                    <= tolerance_kw
                    and device.ended_at < admitted.expires_at
                ):
                    book = book.complete(
                        admitted.command_id,
                        telemetry=device.actual_telemetry,
                        tolerance_kw=tolerance_kw,
                        at=device.ended_at,
                    )
        book = book.expire(at=device.ended_at)
        lifecycle_after_record = _record_for_command(book, caller_command)
        safety_blocked = (
            device.safety_decision is not None
            and device.safety_decision.outcome
            in {SafetyOutcome.BLOCKED, SafetyOutcome.FORCED_IDLE}
        )
        acknowledgement = device.acknowledgement
        reconciliation = self._reconcile(
            caller_command,
            device.command,
            telemetry_actual_power_kw=device.actual_telemetry.actual_battery_power_kw,
            final_safe_request_power_kw=(
                None
                if device.safety_decision is None
                else device.safety_decision.final_requested_battery_power_kw
            ),
            acknowledgement_status=(
                None
                if acknowledgement is None
                else acknowledgement.acknowledgement_status
            ),
            acknowledged_power_kw=(
                None if acknowledgement is None else acknowledgement.accepted_power_kw
            ),
            acknowledgement_received_at=(
                None if acknowledgement is None else acknowledgement.received_at
            ),
            application_authorized=device.command_application_authorized,
            safety_blocked=safety_blocked,
            lifecycle_before=lifecycle_before_record,
            lifecycle_after=lifecycle_after_record,
            tolerance_kw=tolerance_kw,
            command_expired=(
                admission_reasons == ("command_expired_at_admission",)
                or (
                    lifecycle_after_record is not None
                    and lifecycle_after_record.state is CommandLifecycleState.EXPIRED
                )
            ),
        )
        state_after_reconciliation, reconciliation_reasons = (
            self._state_after_reconciliation(observed_state, reconciliation)
        )
        state = _transition(state_before, state_after_reconciliation)
        step = RuntimeLoopStep(
            len(self.trace.steps),
            device.started_at,
            device.ended_at,
            state_before,
            state,
            caller_command,
            admitted,
            (
                CommandOrigin.CURRENT_CALLER
                if admitted is not None
                else CommandOrigin.NONE
            ),
            False,
            device,
            LifecycleEvidence(self.lifecycle_book.records),
            LifecycleEvidence(book.records),
            reconciliation,
            (*observed_reasons, *admission_reasons, *reconciliation_reasons),
        )
        return ControlledEdgeRuntime(
            simulator, book, state, RuntimeLoopTrace((*self.trace.steps, step))
        )
