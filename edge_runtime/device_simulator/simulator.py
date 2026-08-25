"""Explicit-step deterministic virtual PCS/BMS plant and P0.1 integration."""

from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn, SupportsIndex

from edge_runtime import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    CommandLifecycleBook,
    DeterministicEdgeSafetyEvaluator,
    DeviceCapability,
    DeviceCapabilitySource,
    EdgeSafetyEvaluationInput,
    FaultEvent,
    FaultSeverity,
    FaultSource,
    PowerCommand,
    RuntimeHealth,
    RuntimeState,
    SafetyDecision,
    TelemetryQualityStatus,
    TelemetrySnapshot,
)
from edge_runtime.device_simulator.contracts import (
    DeviceSimulatorConfiguration,
    DeviceSimulatorStep,
    FaultSpecification,
    FaultTarget,
    FaultType,
    VirtualClock,
)
from edge_runtime.validation import (
    require_non_negative_number,
    require_positive_timedelta,
)


def _has(
    faults: tuple[FaultSpecification, ...], fault_type: FaultType, *targets: FaultTarget
) -> bool:
    return any(
        item.fault_type is fault_type and item.target in targets for item in faults
    )


def _fault_factor(
    faults: tuple[FaultSpecification, ...], fault_type: FaultType, target: FaultTarget
) -> float:
    values = [
        item.parameter("factor", 0.5)
        for item in faults
        if item.fault_type is fault_type and item.target is target
    ]
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError("fault derating factor must be in [0, 1]")
    return min(values, default=1.0)


def _fault_source(target: FaultTarget) -> FaultSource:
    return {
        FaultTarget.PCS: FaultSource.PCS,
        FaultTarget.BMS: FaultSource.BMS,
        FaultTarget.EDGE: FaultSource.EDGE_RUNTIME,
        FaultTarget.TELEMETRY: FaultSource.DATA_QUALITY,
        FaultTarget.CAPABILITY: FaultSource.DATA_QUALITY,
        FaultTarget.COMMAND_CHANNEL: FaultSource.COMMUNICATION,
    }[target]


@dataclass(frozen=True, slots=True)
class DeterministicDeviceSimulator:
    """Immutable caller-stepped logical plant; it owns no loop, I/O or sleep."""

    configuration: DeviceSimulatorConfiguration
    clock: VirtualClock
    soc_fraction: float
    previous_actual_power_kw: float = 0.0
    telemetry_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, DeviceSimulatorConfiguration):
            raise TypeError("configuration must be a DeviceSimulatorConfiguration")
        if not isinstance(self.clock, VirtualClock):
            raise TypeError("clock must be a VirtualClock")
        if (
            not self.configuration.min_soc_fraction
            <= self.soc_fraction
            <= self.configuration.max_soc_fraction
        ):
            raise ValueError("soc_fraction must remain within configured bounds")
        object.__setattr__(
            self,
            "previous_actual_power_kw",
            require_non_negative_number(
                abs(self.previous_actual_power_kw), "previous_actual_power_kw"
            )
            * (1 if self.previous_actual_power_kw >= 0 else -1),
        )
        if (
            isinstance(self.telemetry_sequence, bool)
            or not isinstance(self.telemetry_sequence, int)
            or self.telemetry_sequence < 0
        ):
            raise TypeError("telemetry_sequence must be a non-negative int")

    @classmethod
    def start(
        cls, configuration: DeviceSimulatorConfiguration, *, at: VirtualClock
    ) -> "DeterministicDeviceSimulator":
        return cls(configuration, at, configuration.initial_soc_fraction)

    def _active_faults(self) -> tuple[FaultSpecification, ...]:
        return self.configuration.fault_schedule.active_at(self.clock.now)

    def _capability(
        self, source: DeviceCapabilitySource, faults: tuple[FaultSpecification, ...]
    ) -> DeviceCapability:
        target = (
            FaultTarget.BMS if source is DeviceCapabilitySource.BMS else FaultTarget.PCS
        )
        unavailable = _has(faults, FaultType.UNAVAILABLE, target) or _has(
            faults, FaultType.DISCONNECTED, target
        )
        stale = _has(faults, FaultType.CAPABILITY_STALE, target, FaultTarget.CAPABILITY)
        base_valid_from = (
            self.clock.now - self.configuration.timing_policy.max_capability_age
        )
        valid_from = (
            base_valid_from - timedelta(seconds=1) if stale else base_valid_from
        )
        expires_at = (
            self.clock.now
            if stale
            else self.clock.now + self.configuration.timing_policy.max_capability_age
        )
        charge = self.configuration.max_charge_power_kw * _fault_factor(
            faults, FaultType.CHARGE_DERATE, target
        )
        discharge = self.configuration.max_discharge_power_kw * _fault_factor(
            faults, FaultType.DISCHARGE_DERATE, target
        )
        return DeviceCapability(
            source,
            f"virtual-{source.value}",
            self.telemetry_sequence,
            valid_from,
            expires_at,
            charge,
            discharge,
            not _has(faults, FaultType.CHARGE_PROHIBITED, target),
            not _has(faults, FaultType.DISCHARGE_PROHIBITED, target),
            not unavailable,
            "p0_2_derating"
            if charge < self.configuration.max_charge_power_kw
            or discharge < self.configuration.max_discharge_power_kw
            else None,
        )

    def _fault_events(
        self, faults: tuple[FaultSpecification, ...]
    ) -> tuple[FaultEvent, ...]:
        return tuple(
            FaultEvent(
                item.fault_id,
                _fault_source(item.target),
                FaultSeverity.CRITICAL
                if item.fault_type is FaultType.CRITICAL_FAULT
                else FaultSeverity.WARNING,
                item.fault_type.value,
                item.activation_at,
                self.clock.now,
                False,
                item.clear_at is not None,
                item.clear_at,
                None,
                ("p0_2_virtual_fault", item.description),
            )
            for item in faults
            if item.fault_type in {FaultType.CRITICAL_FAULT, FaultType.WARNING_FAULT}
        )

    def _health(
        self, faults: tuple[FaultSpecification, ...], events: tuple[FaultEvent, ...]
    ) -> RuntimeHealth:
        pcs_connected = not _has(faults, FaultType.DISCONNECTED, FaultTarget.PCS)
        bms_connected = not _has(faults, FaultType.DISCONNECTED, FaultTarget.BMS)
        channel = not _has(
            faults, FaultType.DISCONNECTED, FaultTarget.COMMAND_CHANNEL
        ) and not _has(faults, FaultType.UNAVAILABLE, FaultTarget.COMMAND_CHANNEL)
        state = (
            RuntimeState.FAULTED
            if _has(faults, FaultType.CRITICAL_FAULT, FaultTarget.EDGE)
            else RuntimeState.READY
        )
        return RuntimeHealth(
            state,
            self.clock.now,
            not _has(faults, FaultType.TELEMETRY_FROZEN, FaultTarget.TELEMETRY),
            not _has(
                faults,
                FaultType.CAPABILITY_STALE,
                FaultTarget.CAPABILITY,
                FaultTarget.BMS,
                FaultTarget.PCS,
            ),
            pcs_connected,
            bms_connected,
            channel,
            0,
            0,
            False,
            events,
        )

    def _telemetry(
        self,
        faults: tuple[FaultSpecification, ...],
        *,
        at_end: bool,
        actual_power_kw: float,
    ) -> TelemetrySnapshot:
        frozen = _has(faults, FaultType.TELEMETRY_FROZEN, FaultTarget.TELEMETRY)
        observed = (
            self.clock.now
            - self.configuration.timing_policy.max_telemetry_age
            - timedelta(seconds=1)
            if frozen
            else self.clock.now
        )
        soc_unknown = _has(
            faults, FaultType.SOC_UNKNOWN, FaultTarget.BMS, FaultTarget.TELEMETRY
        )
        return TelemetrySnapshot(
            "edge-telemetry/v1",
            "virtual-pcs-bms",
            self.telemetry_sequence + (1 if at_end else 0),
            observed,
            self.clock.now,
            actual_power_kw,
            None if soc_unknown else self.soc_fraction,
            None,
            None,
            None,
            None,
            "unavailable"
            if _has(faults, FaultType.UNAVAILABLE, FaultTarget.PCS)
            else "virtual",
            "unavailable"
            if _has(faults, FaultType.UNAVAILABLE, FaultTarget.BMS)
            else "virtual",
            tuple(item.fault_id for item in faults),
            TelemetryQualityStatus.DEGRADED
            if frozen or soc_unknown
            else TelemetryQualityStatus.VALID,
        )

    def _acknowledgement(
        self,
        command: PowerCommand,
        power_kw: float,
        faults: tuple[FaultSpecification, ...],
    ) -> CommandAcknowledgement | None:
        if _has(
            faults, FaultType.ACK_DROPPED, FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL
        ):
            return None
        delayed = [
            item
            for item in faults
            if item.fault_type is FaultType.ACK_DELAYED
            and item.target in {FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL}
        ]
        delay = max((item.parameter("seconds", 1.0) for item in delayed), default=0.0)
        if delay < 0:
            raise ValueError("ack delay must be non-negative")
        rejected = _has(
            faults, FaultType.ACK_REJECTED, FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL
        )
        return CommandAcknowledgement(
            command.command_id,
            command.sequence,
            AcknowledgementStatus.REJECTED
            if rejected
            else AcknowledgementStatus.ACCEPTED,
            self.clock.now + timedelta(seconds=delay),
            self.clock.now,
            None if rejected else power_kw,
            "p0_2_fault_rejected" if rejected else None,
            "virtual",
            command.correlation_id,
        )

    def _actual_power(
        self,
        requested: float,
        faults: tuple[FaultSpecification, ...],
        duration: timedelta,
        *,
        command_application_authorized: bool,
    ) -> tuple[float, tuple[str, ...]]:
        if not command_application_authorized:
            return 0.0, ()
        evidence: list[str] = []
        power = requested
        if (
            _has(faults, FaultType.ESTOP, FaultTarget.PCS, FaultTarget.EDGE)
            or _has(faults, FaultType.DISCONNECTED, FaultTarget.PCS)
            or _has(faults, FaultType.UNAVAILABLE, FaultTarget.PCS)
        ):
            power = 0.0
            evidence.append("pcs_safe_zero")
        elif _has(faults, FaultType.STUCK_AT_ZERO, FaultTarget.PCS):
            power = 0.0
            evidence.append("pcs_stuck_at_zero")
        elif _has(faults, FaultType.STUCK_AT_PREVIOUS_POWER, FaultTarget.PCS):
            power = self.previous_actual_power_kw
            evidence.append("pcs_stuck_at_previous_power")
        elif _has(faults, FaultType.ACTUAL_POWER_DEVIATION, FaultTarget.PCS):
            power *= _fault_factor(
                faults, FaultType.ACTUAL_POWER_DEVIATION, FaultTarget.PCS
            )
            evidence.append("pcs_actual_power_deviation")
        hours = duration.total_seconds() / 3600
        if power > 0:
            boundary = (
                (self.configuration.max_soc_fraction - self.soc_fraction)
                * self.configuration.capacity_kwh
                / (self.configuration.charge_efficiency * hours)
            )
            if power > boundary:
                power = max(boundary, 0.0)
                evidence.append("max_soc_power_limited")
        elif power < 0:
            boundary = (
                (self.soc_fraction - self.configuration.min_soc_fraction)
                * self.configuration.capacity_kwh
                * self.configuration.discharge_efficiency
                / hours
            )
            if -power > boundary:
                power = -max(boundary, 0.0)
                evidence.append("min_soc_power_limited")
        return (0.0 if power == 0 else power), tuple(evidence)

    def _command_applies_in_current_step(
        self,
        command: PowerCommand | None,
        acknowledgement: CommandAcknowledgement | None,
    ) -> tuple[bool, str | None]:
        """P0.2 fail-closed policy, not a claim about every real PCS protocol."""
        if command is None:
            return False, None
        if acknowledgement is None:
            return False, "ack_missing"
        if (
            acknowledgement.command_id != command.command_id
            or acknowledgement.sequence != command.sequence
            or acknowledgement.correlation_id != command.correlation_id
        ):
            return False, "ack_mismatch"
        if acknowledgement.acknowledgement_status is not AcknowledgementStatus.ACCEPTED:
            return False, "ack_not_accepted"
        if acknowledgement.received_at != self.clock.now:
            return False, "ack_not_immediate"
        if acknowledgement.received_at >= command.expires_at:
            return False, "ack_expired"
        return True, None

    def _next_soc(self, actual_power_kw: float, duration: timedelta) -> float:
        hours = duration.total_seconds() / 3600
        energy = (
            actual_power_kw * hours * self.configuration.charge_efficiency
            if actual_power_kw >= 0
            else actual_power_kw * hours / self.configuration.discharge_efficiency
        )
        return min(
            self.configuration.max_soc_fraction,
            max(
                self.configuration.min_soc_fraction,
                self.soc_fraction + energy / self.configuration.capacity_kwh,
            ),
        )

    def prepare_step(self) -> "PreparedDeviceSimulatorStep":
        """Sample one authoritative start snapshot without advancing plant state."""
        faults = self._active_faults()
        bms = self._capability(DeviceCapabilitySource.BMS, faults)
        pcs = self._capability(DeviceCapabilitySource.PCS, faults)
        events = self._fault_events(faults)
        health = self._health(faults, events)
        raw = self._telemetry(
            faults, at_end=False, actual_power_kw=self.previous_actual_power_kw
        )
        return PreparedDeviceSimulatorStep._create(
            self, faults, bms, pcs, events, health, raw
        )

    def step(
        self, command: PowerCommand | None, *, duration: timedelta
    ) -> tuple["DeterministicDeviceSimulator", DeviceSimulatorStep]:
        """Backward-compatible prepare-once/execute-once wrapper."""
        return self.prepare_step().execute(command, duration=duration)

    def _execute_prepared(
        self,
        command: PowerCommand | None,
        duration: timedelta,
        faults: tuple[FaultSpecification, ...],
        bms: DeviceCapability,
        pcs: DeviceCapability,
        events: tuple[FaultEvent, ...],
        health: RuntimeHealth,
        raw: TelemetrySnapshot,
    ) -> tuple["DeterministicDeviceSimulator", DeviceSimulatorStep]:
        interval = require_positive_timedelta(duration, "duration")
        if command is not None and not isinstance(command, PowerCommand):
            raise TypeError("command must be a PowerCommand or None")
        decision: SafetyDecision | None = None
        acknowledgement: CommandAcknowledgement | None = None
        requested = 0.0
        if command is not None:
            decision = DeterministicEdgeSafetyEvaluator().evaluate(
                EdgeSafetyEvaluationInput(
                    command,
                    raw,
                    bms,
                    pcs,
                    health,
                    self.configuration.timing_policy,
                    self.clock.now,
                    _has(faults, FaultType.ESTOP, FaultTarget.PCS, FaultTarget.EDGE),
                    self.configuration.min_soc_fraction,
                )
            )
            requested = decision.final_requested_battery_power_kw
            acknowledgement = self._acknowledgement(command, requested, faults)
        applies, application_reason = self._command_applies_in_current_step(
            command, acknowledgement
        )
        actual, plant_evidence = self._actual_power(
            requested,
            faults,
            interval,
            command_application_authorized=applies,
        )
        evidence = (
            plant_evidence
            if application_reason is None
            else (f"command_not_applied:{application_reason}", *plant_evidence)
        )
        next_soc = self._next_soc(actual, interval)
        next_clock = self.clock.advance(interval)
        next_simulator = DeterministicDeviceSimulator(
            self.configuration,
            next_clock,
            next_soc,
            actual,
            self.telemetry_sequence + 1,
        )
        actual_telemetry = next_simulator._telemetry(
            faults, at_end=True, actual_power_kw=actual
        )
        return next_simulator, DeviceSimulatorStep(
            self.clock.now,
            next_clock.now,
            command,
            faults,
            bms,
            pcs,
            health,
            raw,
            decision,
            acknowledgement,
            applies,
            actual_telemetry,
            actual,
            self.soc_fraction,
            next_soc,
            evidence,
            events,
        )


@dataclass(frozen=True, slots=True, init=False)
class PreparedDeviceSimulatorStep:
    """One-shot authority; observation facts cannot be used to forge a session."""

    simulator: DeterministicDeviceSimulator
    active_faults: tuple[FaultSpecification, ...]
    bms_capability: DeviceCapability
    pcs_capability: DeviceCapability
    fault_events: tuple[FaultEvent, ...]
    runtime_health: RuntimeHealth
    raw_telemetry: TelemetrySnapshot
    _used: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("PreparedDeviceSimulatorStep is created only by simulator")

    def __copy__(self) -> "PreparedDeviceSimulatorStep":
        raise TypeError("PreparedDeviceSimulatorStep cannot be copied")

    def __deepcopy__(self, memo: object) -> "PreparedDeviceSimulatorStep":
        raise TypeError("PreparedDeviceSimulatorStep cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("PreparedDeviceSimulatorStep cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("PreparedDeviceSimulatorStep cannot be serialized")

    @classmethod
    def _create(
        cls,
        simulator: DeterministicDeviceSimulator,
        faults: tuple[FaultSpecification, ...],
        bms: DeviceCapability,
        pcs: DeviceCapability,
        events: tuple[FaultEvent, ...],
        health: RuntimeHealth,
        raw: TelemetrySnapshot,
    ) -> "PreparedDeviceSimulatorStep":
        item = object.__new__(cls)
        for name, value in {
            "simulator": simulator,
            "active_faults": faults,
            "bms_capability": bms,
            "pcs_capability": pcs,
            "fault_events": events,
            "runtime_health": health,
            "raw_telemetry": raw,
            "_used": False,
        }.items():
            object.__setattr__(item, name, value)
        return item

    def execute(
        self, command: PowerCommand | None, *, duration: timedelta
    ) -> tuple[DeterministicDeviceSimulator, DeviceSimulatorStep]:
        if self._used:
            raise ValueError("prepared step has already executed")
        result = self.simulator._execute_prepared(
            command,
            duration,
            self.active_faults,
            self.bms_capability,
            self.pcs_capability,
            self.fault_events,
            self.runtime_health,
            self.raw_telemetry,
        )
        object.__setattr__(self, "_used", True)
        return result


@dataclass(frozen=True, slots=True)
class DeviceScenarioTrace:
    """Retained deterministic P0.2 evidence; no mutable shared trajectory."""

    simulator: DeterministicDeviceSimulator
    lifecycle_book: CommandLifecycleBook
    steps: tuple[DeviceSimulatorStep, ...]


@dataclass(frozen=True, slots=True)
class DeterministicDeviceScenarioHarness:
    """Small explicit scenario adapter through P0.1 lifecycle, never a runtime."""

    trace: DeviceScenarioTrace

    @classmethod
    def start(
        cls, simulator: DeterministicDeviceSimulator
    ) -> "DeterministicDeviceScenarioHarness":
        return cls(DeviceScenarioTrace(simulator, CommandLifecycleBook(), ()))

    def advance(
        self,
        command: PowerCommand | None,
        *,
        duration: timedelta,
        tolerance_kw: float = 0.01,
    ) -> "DeterministicDeviceScenarioHarness":
        require_non_negative_number(tolerance_kw, "tolerance_kw")
        simulator, step = self.trace.simulator.step(command, duration=duration)
        book = self.trace.lifecycle_book
        if command is not None:
            book, _ = book.submit(
                command,
                received_at=step.started_at,
                policy=simulator.configuration.timing_policy,
            )
            acknowledgement = step.acknowledgement
            if (
                acknowledgement is not None
                and acknowledgement.received_at <= step.ended_at
            ):
                book = book.acknowledge(
                    acknowledgement, received_at=acknowledgement.received_at
                )
                if step.command_application_authorized:
                    book = book.begin_execution(
                        command.command_id, at=acknowledgement.received_at
                    )
                    if (
                        step.actual_telemetry.actual_battery_power_kw is not None
                        and step.actual_telemetry.observed_at
                        >= acknowledgement.received_at
                        and step.actual_telemetry.received_at <= step.ended_at
                        and abs(
                            step.actual_telemetry.actual_battery_power_kw
                            - command.requested_battery_power_kw
                        )
                        <= tolerance_kw
                        and step.ended_at < command.expires_at
                    ):
                        book = book.complete(
                            command.command_id,
                            telemetry=step.actual_telemetry,
                            tolerance_kw=tolerance_kw,
                            at=step.ended_at,
                        )
        book = book.expire(at=step.ended_at)
        return DeterministicDeviceScenarioHarness(
            DeviceScenarioTrace(simulator, book, (*self.trace.steps, step))
        )
