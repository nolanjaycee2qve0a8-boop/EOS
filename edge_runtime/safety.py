"""Pure safety, freshness and recovery evaluation for P0.1 Edge contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from edge_runtime.contracts import (
    DeviceCapability,
    DeviceCapabilitySource,
    EffectiveDeviceCapability,
    FaultSeverity,
    OperatingMode,
    PowerCommand,
    RuntimeHealth,
    RuntimeState,
    SafetyConstraint,
    SafetyDecision,
    SafetyOutcome,
    SafetyPrecedence,
    TelemetryQualityStatus,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.lifecycle import CommandLifecycleBook, RecoveryReadiness
from edge_runtime.validation import (
    SerializableContract,
    require_aware_datetime,
    require_fraction,
)


def merge_device_capabilities(
    bms_capability: DeviceCapability,
    pcs_capability: DeviceCapability,
) -> EffectiveDeviceCapability:
    """Derive the only permitted BMS/PCS capability intersection."""
    if not isinstance(bms_capability, DeviceCapability):
        raise TypeError("bms_capability must be a DeviceCapability")
    if not isinstance(pcs_capability, DeviceCapability):
        raise TypeError("pcs_capability must be a DeviceCapability")
    if bms_capability.source is not DeviceCapabilitySource.BMS:
        raise ValueError("bms_capability source must be BMS")
    if pcs_capability.source is not DeviceCapabilitySource.PCS:
        raise ValueError("pcs_capability source must be PCS")
    return EffectiveDeviceCapability._derive(bms_capability, pcs_capability)


@dataclass(frozen=True, slots=True)
class FreshnessEvaluation(SerializableContract):
    """Freshness evidence based on actual observation and capability windows."""

    evaluated_at: datetime
    telemetry_fresh: bool
    capability_fresh: bool
    telemetry_reason: str | None
    capability_reason: str | None

    SCHEMA_VERSION: ClassVar[str] = "edge-freshness-evaluation/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluated_at",
            require_aware_datetime(self.evaluated_at, "evaluated_at"),
        )
        for field_name in ("telemetry_fresh", "capability_fresh"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        for field_name in ("telemetry_reason", "capability_reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty str or None")


def evaluate_freshness(
    telemetry: TelemetrySnapshot,
    capability: EffectiveDeviceCapability,
    policy: TimingPolicy,
    *,
    evaluated_at: datetime,
) -> FreshnessEvaluation:
    """Evaluate freshness without owning a clock or trusting receipt time alone."""
    if not isinstance(telemetry, TelemetrySnapshot):
        raise TypeError("telemetry must be a TelemetrySnapshot")
    if not isinstance(capability, EffectiveDeviceCapability):
        raise TypeError("capability must be an EffectiveDeviceCapability")
    if not isinstance(policy, TimingPolicy):
        raise TypeError("policy must be a TimingPolicy")
    now = require_aware_datetime(evaluated_at, "evaluated_at")
    observed_age = now - telemetry.observed_at
    if observed_age < -policy.max_clock_skew:
        telemetry_fresh, telemetry_reason = False, "telemetry_observed_in_future"
    elif observed_age > policy.max_telemetry_age:
        telemetry_fresh, telemetry_reason = False, "telemetry_stale"
    else:
        telemetry_fresh, telemetry_reason = True, None
    capability_age = now - capability.valid_from
    if capability_age < -policy.max_clock_skew:
        capability_fresh, capability_reason = False, "capability_valid_from_in_future"
    elif now >= capability.expires_at or capability_age > policy.max_capability_age:
        capability_fresh, capability_reason = False, "capability_stale"
    else:
        capability_fresh, capability_reason = True, None
    return FreshnessEvaluation(
        now, telemetry_fresh, capability_fresh, telemetry_reason, capability_reason
    )


def _blocking_faults(health: RuntimeHealth) -> tuple[str, ...]:
    """P0.1 treats every CRITICAL active fault as blocking, explicitly."""
    return tuple(
        f"fault:{fault.source.value}:{fault.code}"
        for fault in health.active_faults
        if fault.severity is FaultSeverity.CRITICAL
    )


@dataclass(frozen=True, slots=True)
class EdgeSafetyEvaluationInput(SerializableContract):
    """Raw caller facts; effective capability is never accepted as authority."""

    command: PowerCommand
    telemetry: TelemetrySnapshot
    bms_capability: DeviceCapability
    pcs_capability: DeviceCapability
    runtime_health: RuntimeHealth
    timing_policy: TimingPolicy
    evaluated_at: datetime
    emergency_stop_active: bool
    user_min_soc_fraction: float | None

    SCHEMA_VERSION: ClassVar[str] = "edge-safety-evaluation-input/v1"

    def __post_init__(self) -> None:
        if not isinstance(self.command, PowerCommand):
            raise TypeError("command must be a PowerCommand")
        if not isinstance(self.telemetry, TelemetrySnapshot):
            raise TypeError("telemetry must be a TelemetrySnapshot")
        if (
            not isinstance(self.bms_capability, DeviceCapability)
            or self.bms_capability.source is not DeviceCapabilitySource.BMS
        ):
            raise TypeError("bms_capability must be a BMS DeviceCapability")
        if (
            not isinstance(self.pcs_capability, DeviceCapability)
            or self.pcs_capability.source is not DeviceCapabilitySource.PCS
        ):
            raise TypeError("pcs_capability must be a PCS DeviceCapability")
        if not isinstance(self.runtime_health, RuntimeHealth):
            raise TypeError("runtime_health must be a RuntimeHealth")
        if not isinstance(self.timing_policy, TimingPolicy):
            raise TypeError("timing_policy must be a TimingPolicy")
        object.__setattr__(
            self,
            "evaluated_at",
            require_aware_datetime(self.evaluated_at, "evaluated_at"),
        )
        if not isinstance(self.emergency_stop_active, bool):
            raise TypeError("emergency_stop_active must be a bool")
        if self.user_min_soc_fraction is not None:
            object.__setattr__(
                self,
                "user_min_soc_fraction",
                require_fraction(self.user_min_soc_fraction, "user_min_soc_fraction"),
            )


class DeterministicEdgeSafetyEvaluator:
    """Apply fixed precedence without dispatching or claiming actual execution."""

    __slots__ = ()

    def evaluate(self, evaluation: EdgeSafetyEvaluationInput) -> SafetyDecision:
        if not isinstance(evaluation, EdgeSafetyEvaluationInput):
            raise TypeError("evaluation must be an EdgeSafetyEvaluationInput")
        effective = merge_device_capabilities(
            evaluation.bms_capability, evaluation.pcs_capability
        )
        freshness = evaluate_freshness(
            evaluation.telemetry,
            effective,
            evaluation.timing_policy,
            evaluated_at=evaluation.evaluated_at,
        )
        command_power = evaluation.command.requested_battery_power_kw
        constraints: list[SafetyConstraint] = []

        def add(precedence: SafetyPrecedence, reason: str, *evidence: str) -> None:
            constraints.append(SafetyConstraint(precedence, reason, evidence))

        # Audit every applicable restriction; priority decides the final request.
        if evaluation.emergency_stop_active:
            add(
                SafetyPrecedence.HARDWARE_PROTECTION,
                "emergency_stop_active",
                "caller:emergency_stop_active",
            )
        if not freshness.telemetry_fresh:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                freshness.telemetry_reason or "telemetry_not_fresh",
                f"telemetry:{evaluation.telemetry.source_id}",
            )
        if evaluation.telemetry.quality_status is not TelemetryQualityStatus.VALID:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "telemetry_quality_not_valid",
                f"telemetry_quality:{evaluation.telemetry.quality_status.value}",
            )
        if evaluation.telemetry.soc_fraction is None:
            add(SafetyPrecedence.EDGE_RUNTIME, "soc_unknown", "telemetry:soc_fraction")
        if not freshness.capability_fresh:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                freshness.capability_reason or "capability_not_fresh",
                "effective_capability",
            )
        health = evaluation.runtime_health
        if health.runtime_state is not RuntimeState.READY:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "runtime_state_not_ready",
                f"runtime_state:{health.runtime_state.value}",
            )
        if not health.telemetry_fresh:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "runtime_health_telemetry_not_fresh",
                "runtime_health:telemetry_fresh",
            )
        if not health.capability_fresh:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "runtime_health_capability_not_fresh",
                "runtime_health:capability_fresh",
            )
        if (
            not health.command_channel_healthy
            or not health.pcs_connected
            or not health.bms_connected
        ):
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "runtime_link_not_healthy",
                "runtime_health",
            )
        if health.safe_fallback_active:
            add(
                SafetyPrecedence.EDGE_RUNTIME,
                "runtime_safe_fallback_active",
                "runtime_health:safe_fallback_active",
            )
        for evidence in _blocking_faults(health):
            add(SafetyPrecedence.EDGE_RUNTIME, "blocking_active_fault", evidence)
        if not effective.available:
            add(SafetyPrecedence.BMS, "effective_capability_unavailable", "bms+pcs")
        if command_power > 0 and not effective.charge_allowed:
            add(SafetyPrecedence.BMS, "charge_not_allowed", "bms+pcs")
        if command_power < 0 and not effective.discharge_allowed:
            add(SafetyPrecedence.BMS, "discharge_not_allowed", "bms+pcs")
        if command_power > effective.max_charge_power_kw:
            add(
                SafetyPrecedence.PCS,
                "charge_power_limited",
                "effective_max_charge_power_kw",
            )
        if -command_power > effective.max_discharge_power_kw:
            add(
                SafetyPrecedence.PCS,
                "discharge_power_limited",
                "effective_max_discharge_power_kw",
            )
        if (
            command_power < 0
            and evaluation.user_min_soc_fraction is not None
            and evaluation.telemetry.soc_fraction is not None
            and evaluation.telemetry.soc_fraction <= evaluation.user_min_soc_fraction
        ):
            add(
                SafetyPrecedence.USER_SAFETY,
                "minimum_soc_reserve",
                "telemetry:soc_fraction",
            )

        force_reasons = {
            "emergency_stop_active",
            "telemetry_observed_in_future",
            "telemetry_stale",
            "telemetry_quality_not_valid",
            "soc_unknown",
            "capability_valid_from_in_future",
            "capability_stale",
            "runtime_state_not_ready",
            "runtime_health_telemetry_not_fresh",
            "runtime_health_capability_not_fresh",
            "runtime_link_not_healthy",
            "runtime_safe_fallback_active",
            "blocking_active_fault",
            "effective_capability_unavailable",
            "charge_not_allowed",
            "discharge_not_allowed",
            "minimum_soc_reserve",
        }
        force_idle = any(item.reason_code in force_reasons for item in constraints)
        if force_idle:
            final_power = 0.0
        elif command_power > 0:
            final_power = min(command_power, effective.max_charge_power_kw)
        elif command_power < 0:
            final_power = -min(-command_power, effective.max_discharge_power_kw)
        else:
            final_power = 0.0
        mode = OperatingMode.SAFE_IDLE if final_power == 0 else OperatingMode.NORMAL
        if force_idle:
            outcome = (
                SafetyOutcome.FORCED_IDLE
                if any(
                    item.precedence
                    in {
                        SafetyPrecedence.HARDWARE_PROTECTION,
                        SafetyPrecedence.EDGE_RUNTIME,
                    }
                    for item in constraints
                )
                else SafetyOutcome.BLOCKED
            )
        elif final_power != command_power:
            outcome = SafetyOutcome.CLAMPED
        else:
            outcome = SafetyOutcome.ALLOWED
        return SafetyDecision(
            evaluation.command,
            evaluation.telemetry,
            effective,
            health,
            evaluation.evaluated_at,
            final_power,
            mode,
            outcome,
            tuple(constraints),
        )


@dataclass(frozen=True, slots=True)
class RecoveryReadinessInput:
    """Complete caller-owned facts required to admit a new command."""

    telemetry: TelemetrySnapshot
    bms_capability: DeviceCapability
    pcs_capability: DeviceCapability
    runtime_health: RuntimeHealth
    timing_policy: TimingPolicy
    lifecycle_book: CommandLifecycleBook
    evaluated_at: datetime
    emergency_stop_active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.telemetry, TelemetrySnapshot):
            raise TypeError("telemetry must be a TelemetrySnapshot")
        if (
            not isinstance(self.bms_capability, DeviceCapability)
            or self.bms_capability.source is not DeviceCapabilitySource.BMS
        ):
            raise TypeError("bms_capability must be a BMS DeviceCapability")
        if (
            not isinstance(self.pcs_capability, DeviceCapability)
            or self.pcs_capability.source is not DeviceCapabilitySource.PCS
        ):
            raise TypeError("pcs_capability must be a PCS DeviceCapability")
        if not isinstance(self.runtime_health, RuntimeHealth):
            raise TypeError("runtime_health must be a RuntimeHealth")
        if not isinstance(self.timing_policy, TimingPolicy):
            raise TypeError("timing_policy must be a TimingPolicy")
        if not isinstance(self.lifecycle_book, CommandLifecycleBook):
            raise TypeError("lifecycle_book must be a CommandLifecycleBook")
        object.__setattr__(
            self,
            "evaluated_at",
            require_aware_datetime(self.evaluated_at, "evaluated_at"),
        )
        if not isinstance(self.emergency_stop_active, bool):
            raise TypeError("emergency_stop_active must be a bool")


def evaluate_recovery_readiness(
    evaluation: RecoveryReadinessInput,
) -> RecoveryReadiness:
    """Return deterministic admission evidence; never replays an old command."""
    if not isinstance(evaluation, RecoveryReadinessInput):
        raise TypeError("evaluation must be a RecoveryReadinessInput")
    effective = merge_device_capabilities(
        evaluation.bms_capability, evaluation.pcs_capability
    )
    freshness = evaluate_freshness(
        evaluation.telemetry,
        effective,
        evaluation.timing_policy,
        evaluated_at=evaluation.evaluated_at,
    )
    health = evaluation.runtime_health
    reasons: list[str] = []
    if not freshness.telemetry_fresh:
        reasons.append(freshness.telemetry_reason or "telemetry_not_fresh")
    if not freshness.capability_fresh:
        reasons.append(freshness.capability_reason or "capability_not_fresh")
    if evaluation.telemetry.soc_fraction is None:
        reasons.append("soc_unknown")
    if health.runtime_state is not RuntimeState.READY:
        reasons.append("runtime_state_not_ready")
    if not health.telemetry_fresh:
        reasons.append("runtime_health_telemetry_not_fresh")
    if not health.capability_fresh:
        reasons.append("runtime_health_capability_not_fresh")
    if (
        not health.command_channel_healthy
        or not health.pcs_connected
        or not health.bms_connected
    ):
        reasons.append("runtime_link_not_healthy")
    if health.safe_fallback_active:
        reasons.append("runtime_safe_fallback_active")
    if not effective.available:
        reasons.append("effective_capability_unavailable")
    if evaluation.emergency_stop_active:
        reasons.append("emergency_stop_active")
    if _blocking_faults(health):
        reasons.append("blocking_active_fault")
    if evaluation.lifecycle_book.has_nonterminal_records:
        reasons.append("lifecycle_not_quiescent")
    return RecoveryReadiness(
        freshness.telemetry_fresh,
        freshness.capability_fresh,
        not reasons,
        tuple(reasons),
    )
